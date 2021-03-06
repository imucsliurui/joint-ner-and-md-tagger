# coding=utf-8
import itertools
import os
import re
import codecs

from utils import create_dico, create_mapping, zero_digits
from utils import iob2, iob_iobes

from toolkit.joint_ner_and_md_model import MainTaggerModel

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import numpy as np


def load_sentences(path, lower, zeros):
    """
    Load sentences. A line must contain at least a word and its tag.
    Sentences are separated by empty lines.
    """

    sentences = []
    sentence = []
    max_sentence_length = 0
    max_word_length = 0

    for line in codecs.open(path, 'r', 'utf8'):
        line = zero_digits(line.rstrip()) if zeros else line.rstrip()
        if not line:
            if len(sentence) > 0:
                if 'DOCSTART' not in sentence[0][0]:
                    # print sentence
                    # sys.exit()
                    sentences.append(sentence)
                    if len(sentence) > max_sentence_length:
                        max_sentence_length = len(sentence)
                sentence = []
        else:
            tokens = line.split()
            assert len(tokens) >= 2
            sentence.append(tokens)
            if len(tokens[0]) > max_word_length:
                max_word_length = len(tokens[0])
    if len(sentence) > 0:
        if 'DOCSTART' not in sentence[0][0]:
            sentences.append(sentence)
            if len(sentence) > max_sentence_length:
                max_sentence_length = len(sentence)
    return sentences, max_sentence_length, max_word_length


def update_tag_scheme(sentences, tag_scheme):
    """
    Check and update sentences tagging scheme to IOB2.
    Only IOB1 and IOB2 schemes are accepted.
    """
    for i, s in enumerate(sentences):
        tags = [w[-1] for w in s]
        # Check that tags are given in the IOB format
        if not iob2(tags):
            s_str = '\n'.join(' '.join(w) for w in s)
            print s_str.encode("utf8")
            raise Exception('Sentences should be given in IOB format! ' +
                            'Please check sentence %i:\n%s' % (i, s_str))
        if tag_scheme == 'iob':
            # If format was IOB1, we convert to IOB2
            for word, new_tag in zip(s, tags):
                word[-1] = new_tag
        elif tag_scheme == 'iobes':
            new_tags = iob_iobes(tags)
            for word, new_tag in zip(s, new_tags):
                word[-1] = new_tag
        else:
            raise Exception('Unknown tagging scheme!')


def word_mapping(sentences, lower):
    """
    Create a dictionary and a mapping of words, sorted by frequency.
    """
    # words = [[(" ".join(x[0:2])).lower() if lower else " ".join(x[0:2]) for x in s] for s in sentences]
    words = [[x[0].lower() if lower else x[0] for x in s] for s in sentences]
    # TODO: only roots version, but this effectively damages char embeddings.
    # words = [[x[1].split("+")[0].lower() if lower else x[1].split("+")[0] for x in s] for s in sentences]
    dico = create_dico(words)
    dico['<UNK>'] = 10000000
    word_to_id, id_to_word = create_mapping(dico)
    print "Found %i unique words (%i in total)" % (
        len(dico), sum(len(x) for x in words)
    )
    return dico, word_to_id, id_to_word


def char_mapping(sentences):
    """
    Create a dictionary and mapping of characters, sorted by frequency.
    """
    chars = ["".join([w[0] + "".join(w[2:-1]) for w in s]) for s in sentences]
    chars.append("+")
    chars.append("*")
    dico = create_dico(chars)
    char_to_id, id_to_char = create_mapping(dico)
    print "Found %i unique characters" % len(dico)
    return dico, char_to_id, id_to_char


def tag_mapping(sentences):
    """
    Create a dictionary and a mapping of tags, sorted by frequency.
    """
    tags = [[word[-1] for word in s] for s in sentences]
    dico = create_dico(tags)
    tag_to_id, id_to_tag = create_mapping(dico)
    print "Found %i unique named entity tags" % len(dico)
    return dico, tag_to_id, id_to_tag

def morpho_tag_mapping(sentences, morpho_tag_type='wo_root', morpho_tag_column_index=1,
                       joint_learning=False):
    """
    Create a dictionary and a mapping of tags, sorted by frequency.
    """
    if morpho_tag_type == 'char':
        morpho_tags = ["".join([w[morpho_tag_column_index] for w in s]) for s in sentences]
        morpho_tags += [ww for ww in w[2:-1] for w in s for s in sentences]
    else:
        morpho_tags = extract_morpho_tags_ordered(morpho_tag_type,
                                                  sentences, morpho_tag_column_index,
                                                  joint_learning=joint_learning)
        ## TODO: xxx

    # print morpho_tags
    #morpho_tags = [[word[1].split("+") for word in s] for s in sentences]
    # print morpho_tags
    morpho_tags.append(["*UNKNOWN*"])
    dico = create_dico(morpho_tags)
    # print dico
    morpho_tag_to_id, id_to_morpho_tag = create_mapping(dico)
    print morpho_tag_to_id
    print "Found %i unique morpho tags" % len(dico)
    return dico, morpho_tag_to_id, id_to_morpho_tag


def extract_morpho_tags_ordered(morpho_tag_type,
                                sentences, morpho_tag_column_index,
                                joint_learning=False):
    morpho_tags = []
    for s in sentences:
        # print s
        # sys.exit(1)
        morpho_tags += extract_morpho_tags_from_one_sentence_ordered(morpho_tag_type, [],
                                                                     s, morpho_tag_column_index,
                                                                     joint_learning=joint_learning)
    return morpho_tags


def extract_morpho_tags_from_one_sentence_ordered(morpho_tag_type, morpho_tags,
                                                  s, morpho_tag_column_index,
                                                  joint_learning=False):
    assert morpho_tag_column_index in [1, 2], "We expect to 1 or 2"
    for word in s:
        if joint_learning:
            for morpho_analysis in word[1:-1]:
                morpho_tags += [morpho_analysis.split("+")[1:]]
        else:
            if morpho_tag_type.startswith('wo_root'):
                if morpho_tag_type == 'wo_root_after_DB' and morpho_tag_column_index == 1: # this is only applicable to Turkish dataset
                    tmp = []
                    for tag in word[1].split("+")[1:][::-1]:
                        if tag.endswith("^DB"):
                            tmp += [tag]
                            break
                        else:
                            tmp += [tag]
                    morpho_tags += [tmp]
                else:
                    if morpho_tag_column_index == 2: # this means we're reading Czech dataset (it's faulty in a sense)
                        morpho_tags += [word[morpho_tag_column_index].split("")]
                    else:
                        morpho_tags += [word[morpho_tag_column_index].split("+")[1:]]
            elif morpho_tag_type.startswith('with_root'):
                if morpho_tag_column_index == 1:
                    root = [word[morpho_tag_column_index].split("+")[0]]
                else:
                    root = [word[1]] # In Czech dataset, the lemma is given in the first column
                tmp = []
                tmp += root
                if morpho_tag_type == 'with_root_after_DB' and morpho_tag_column_index == 1:
                    for tag in word[morpho_tag_column_index].split("+")[1:][::-1]:
                        if tag.endswith("^DB"):
                            tmp += [tag]
                            break
                        else:
                            tmp += [tag]
                    morpho_tags += [tmp]
                else:
                    if morpho_tag_column_index == 2:
                        morpho_tags += [tmp + word[morpho_tag_column_index].split("")]
                    else: # only 1 is possible
                        morpho_tags += [word[morpho_tag_column_index].split("+")] # I removed the 'tmp +' because it just repeated the first element which is root
    return morpho_tags


def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

def cap_feature(s):
    """
    Capitalization feature:
    0 = low caps
    1 = all caps
    2 = first letter caps
    3 = one capital (not first letter)
    """

    def cap_characterization(input_s):
        if input_s.lower() == input_s:
            return 0
        elif input_s.upper() == input_s:
            return 1
        elif input_s[0].upper() == input_s[0]:
            return 2
        elif sum([x == y for (x, y) in zip(input_s.upper(), input_s)]) > 0:
            return 3

    if is_number(s):
        return 0
    elif sum([(str(digit) in s) for digit in range(0, 10)]) > 0:
        if "'" in s:
            return 1 + cap_characterization(s)
        else:
            return 1 + 4 + cap_characterization(s)
    else:
        if "'" in s:
            return 1 + 8 + cap_characterization(s)
        else:
            return 1 + 12 + cap_characterization(s)


def prepare_sentence(str_words, word_to_id, char_to_id, lower=False):
    """
    Prepare a sentence for evaluation.
    """
    def f(x): return x.lower() if lower else x
    words = [word_to_id[f(w) if f(w) in word_to_id else '<UNK>']
             for w in str_words]
    chars = [[char_to_id[c] for c in w if c in char_to_id]
             for w in str_words]
    caps = [cap_feature(w) for w in str_words]
    return {
        'str_words': str_words,
        'words': words,
        'chars': chars,
        'caps': caps
    }


def turkish_lower(s):
    return s.replace(u"IİŞÜĞÖÇ", u"ıişüğöç")


def prepare_dataset(sentences, word_to_id, char_to_id, tag_to_id,
                    morpho_tag_to_id, lower=False,
                    morpho_tag_dimension=0,
                    morpho_tag_type='wo_root',
                    morpho_tag_column_index=1):
    """
    Prepare the dataset. Return a list of lists of dictionaries containing:
        - word indexes
        - word char indexes
        - tag indexes
    """

    def f(x): return x.lower() if lower else x
    data = []

    for s in sentences:
        str_words = [w[0] for w in s]
        words = [word_to_id[f(w) if f(w) in word_to_id else '<UNK>']
                 for w in str_words]
        # Skip characters that are not in the training set
        chars = [[char_to_id[c] for c in w if c in char_to_id]
                 for w in str_words]
        caps = [cap_feature(w) for w in str_words]
        tags = [tag_to_id[w[-1]] for w in s]

        if morpho_tag_dimension > 0:
            if morpho_tag_type == 'char':
                str_morpho_tags = [w[morpho_tag_column_index] for w in s]
                morpho_tags = [[morpho_tag_to_id[c] for c in str_morpho_tag if c in morpho_tag_to_id]
                     for str_morpho_tag in str_morpho_tags]
            else:
                morpho_tags_in_the_sentence = \
                    extract_morpho_tags_from_one_sentence_ordered(morpho_tag_type, [],
                                                                  s, morpho_tag_column_index,
                                                                  joint_learning=False)

                morpho_tags = [[morpho_tag_to_id[morpho_tag] for morpho_tag in ww if morpho_tag in morpho_tag_to_id]
                               for ww in morpho_tags_in_the_sentence]

        def f_morpho_tag_to_id(m):
            if m in morpho_tag_to_id:
                return morpho_tag_to_id[m]
            else:
                return morpho_tag_to_id['*UNKNOWN*']

        # for now we ignore different schemes we did in previous morph. tag parses.
        morph_analyzes_tags = [[map(f_morpho_tag_to_id, analysis.split("+")[1:]) if analysis.split("+")[1:] else [morpho_tag_to_id["*UNKNOWN*"]]
                                for analysis in w[2:-1]] for w in s]

        def f_char_to_id(c):
            if c in char_to_id:
                return char_to_id[c]
            else:
                return char_to_id['*']

        morph_analyzes_roots = [[map(f_char_to_id, list(analysis.split("+")[0])) if list(analysis.split("+")[0]) else [char_to_id["+"]]
                                for analysis in w[2:-1]] for w in s]

        morph_analysis_from_NER_data = [w[morpho_tag_column_index] for w in s]
        morph_analyzes_from_FST_unprocessed = [w[2:-1] for w in s]

        def remove_Prop_and_lower(s):
            return turkish_lower(s.replace(u"+Prop", ""))

        golden_analysis_indices = []
        for w_idx, w in enumerate(s):
            found = False
            try:
                golden_analysis_idx = \
                    morph_analyzes_from_FST_unprocessed[w_idx]\
                        .index(morph_analysis_from_NER_data[w_idx])
                found = True
            except ValueError as e:
                # step 1
                pass
            if not found:
                try:
                    golden_analysis_idx = \
                        map(remove_Prop_and_lower, morph_analyzes_from_FST_unprocessed[w_idx])\
                            .index(remove_Prop_and_lower(morph_analysis_from_NER_data[w_idx]))
                    found = True
                except ValueError as e:
                    pass
            if not found:
                if len(morph_analyzes_from_FST_unprocessed[w_idx]) == 1:
                    golden_analysis_idx = 0
                else:
                    # WE expect that this never happens in gungor.ner.14.* files as they have been processed for unfound golden analyses
                    import random
                    golden_analysis_idx = random.randint(0, len(morph_analyzes_from_FST_unprocessed[w_idx])-1)
            if golden_analysis_idx >= len(morph_analyzes_from_FST_unprocessed[w_idx]) or \
                golden_analysis_idx < 0 or \
                golden_analysis_idx >= len(morph_analyzes_roots[w_idx]):
                logging.error("BEEP at golden analysis idx")
            golden_analysis_indices.append(golden_analysis_idx)

        data_item = {
            'str_words': str_words,
            'word_ids': words,
            'char_for_ids': chars,
            'char_lengths': [len(char) for char in chars],
            'cap_ids': caps,
            'tag_ids': tags,
            'morpho_analyzes_tags': morph_analyzes_tags,
            'morpho_analyzes_roots': morph_analyzes_roots,
            'golden_morph_analysis_indices': golden_analysis_indices,
            'sentence_lengths': len(s),
            'max_word_length_in_this_sample': max([len(x) for x in chars])
        }
        if morpho_tag_dimension > 0:
            data_item['morpho_tag_ids'] = morpho_tags

        data.append(data_item)

    logging.info("Sorting the dataset by sentence length..")
    data_sorted_by_sentence_length = sorted(data, key=lambda x: x['sentence_lengths'])
    stats = [[x['sentence_lengths'],
              x['max_word_length_in_this_sample'],
              x['char_lengths']] for x in data]
    n_unique_words = set()
    for x in data:
        for word_id in x['word_ids']:
            n_unique_words.add(word_id)
    n_unique_words = len(n_unique_words)

    n_buckets = min([9, len(sentences)])
    print "n_sentences: %d" % len(sentences)
    n_samples_to_be_bucketed = len(sentences)/n_buckets

    print "n_samples_to_be_binned: %d" % n_samples_to_be_bucketed

    buckets = []
    for bin_idx in range(n_buckets+1):
        logging.info("Forming bin %d.." % bin_idx)
        data_to_be_bucketed = data_sorted_by_sentence_length[n_samples_to_be_bucketed*(bin_idx):n_samples_to_be_bucketed*(bin_idx+1)]
        if len(data_to_be_bucketed) == 0:
            continue

        buckets.append(data_to_be_bucketed)

    return buckets, stats, n_unique_words, data

def read_an_example(_bucket_data_dict, batch_idx, batch_size_scalar, n_sentences):
    given_placeholders = {}
    # print batch_idx
    # print batch_size_scalar
    for key in _bucket_data_dict.keys():
        if key in ["max_sentence_length", "max_word_length"]:
            continue

        lower_index = batch_idx * batch_size_scalar
        upper_index = min((batch_idx + 1) * batch_size_scalar, n_sentences)
        if key == "str_words":
            str_words = _bucket_data_dict[key][lower_index:upper_index]
        else:
            if _bucket_data_dict[key].ndim > 1:
                given_placeholders[key] = _bucket_data_dict[key][np.arange(lower_index, upper_index), :]
            else:
                # print data[key].shape
                given_placeholders[key] = _bucket_data_dict[key][np.arange(lower_index, upper_index)]

            # if the size of this slice is smaller than the batch_size_scalar
            for i in range(batch_size_scalar-(upper_index-lower_index)):
                if given_placeholders[key].ndim > 1:
                    row_to_be_duplicated = given_placeholders[key][0, :]
                    # print "n_sentences: %d" % n_sentences
                    # print key
                    # print ret_dict[key].shape
                    # print row_to_be_duplicated.shape
                    # print np.expand_dims(row_to_be_duplicated, axis=0).shape
                    given_placeholders[key] = np.concatenate(
                        [given_placeholders[key], np.expand_dims(row_to_be_duplicated, axis=0)])
                else:
                    row_to_be_duplicated = given_placeholders[key][0]
                    # print "n_sentences: %d" % n_sentences
                    # print key
                    # print ret_dict[key].shape
                    # print row_to_be_duplicated.shape
                    # print np.expand_dims(row_to_be_duplicated, axis=0).shape
                    given_placeholders[key] = np.concatenate([given_placeholders[key], np.expand_dims(row_to_be_duplicated, axis=0)])

    # for key in ret_dict.keys():
    #     print key
    #     print ret_dict[key].shape

    return given_placeholders, str_words

def augment_with_pretrained(dictionary, ext_emb_path, words):
    """
    Augment the dictionary with words that have a pretrained embedding.
    If `words` is None, we add every word that has a pretrained embedding
    to the dictionary, otherwise, we only add the words that are given by
    `words` (typically the words in the development and test sets.)
    """
    print 'Loading pretrained embeddings from %s...' % ext_emb_path
    assert os.path.isfile(ext_emb_path)

    # Load pretrained embeddings from file
    pretrained = set([
        line.split()[0].strip()
        for line in codecs.open(ext_emb_path, 'r', 'utf-8')
        if len(ext_emb_path) > 0
    ])

    # We either add every word in the pretrained file,
    # or only words given in the `words` list to which
    # we can assign a pretrained embedding
    if words is None:
        for word in pretrained:
            if word not in dictionary:
                dictionary[word] = 0
    else:
        for word in words:
            if any(x in pretrained for x in [
                word,
                word.lower(),
                re.sub('\d', '0', word.lower())
            ]) and word not in dictionary:
                dictionary[word] = 0

    word_to_id, id_to_word = create_mapping(dictionary)
    return dictionary, word_to_id, id_to_word


def calculate_global_maxes(max_sentence_lengths, max_word_lengths):
    global_max_sentence_length = 0
    global_max_char_length = 0
    for i, d in enumerate([max_sentence_lengths, max_word_lengths]):
        for label in d.keys():
            if i == 0:
                if d[label] > global_max_sentence_length:
                    global_max_sentence_length = d[label]
            elif i == 1:
                if d[label] > global_max_char_length:
                    global_max_char_length = d[label]
    return global_max_sentence_length, global_max_char_length


def _prepare_datasets(opts, parameters, for_training=True):

    # Data parameters
    lower = parameters['lower']
    zeros = parameters['zeros']
    tag_scheme = parameters['t_s']
    max_sentence_lengths = {}
    max_word_lengths = {}

    # Load sentences
    if for_training:
        train_sentences, max_sentence_lengths['train'], max_word_lengths['train'] = load_sentences(opts.train, lower, zeros)

    dev_sentences, max_sentence_lengths['dev'], max_word_lengths['dev'] = load_sentences(opts.dev, lower, zeros)
    test_sentences, max_sentence_lengths['test'], max_word_lengths['test'] = load_sentences(opts.test, lower, zeros)
    if parameters['test_with_yuret'] or parameters['train_with_yuret']:
        # train.merge and test.merge
        if for_training:
            yuret_train_sentences, max_sentence_lengths['yuret_train'], max_word_lengths['yuret_train'] = \
                load_sentences(opts.yuret_train, lower, zeros)
        yuret_test_sentences, max_sentence_lengths['yuret_test'], max_word_lengths['yuret_test'] = \
            load_sentences(opts.yuret_test, lower, zeros)

        if for_training:
            update_tag_scheme(yuret_train_sentences, tag_scheme)
        update_tag_scheme(yuret_test_sentences, tag_scheme)
    else:
        yuret_train_sentences = []
        yuret_test_sentences = []
    # Use selected tagging scheme (IOB / IOBES)
    if for_training:
        update_tag_scheme(train_sentences, tag_scheme)
    update_tag_scheme(dev_sentences, tag_scheme)
    update_tag_scheme(test_sentences, tag_scheme)

    # if for_training:
    #     create_mappings(dev_sentences, lower, parameters, test_sentences, train_sentences, yuret_test_sentences,
    #                     yuret_train_sentences)

    return train_sentences, dev_sentences, test_sentences, yuret_train_sentences, yuret_test_sentences,\
           max_sentence_lengths, max_word_lengths


def create_mappings(dev_sentences,
                    lower, parameters,
                    test_sentences, train_sentences,
                    yuret_test_sentences,
                    yuret_train_sentences):
    # Create a dictionary / mapping of words
    # If we use pretrained embeddings, we add them to the dictionary.
    if parameters['pre_emb']:
        dico_words_train = word_mapping(train_sentences, lower)[0]
        dico_words, word_to_id, id_to_word = augment_with_pretrained(
            dico_words_train.copy(),
            parameters['pre_emb'],
            list(itertools.chain.from_iterable(
                [[w[0] for w in s] for s in dev_sentences + test_sentences])
            ) if not parameters['all_emb'] else None
        )
    else:
        dico_words, word_to_id, id_to_word = word_mapping(train_sentences, lower)
        dico_words_train = dico_words
    sentences_for_mapping = []
    sentences_for_mapping += train_sentences + yuret_train_sentences + dev_sentences + test_sentences + yuret_test_sentences
    # Create a dictionary and a mapping for words / POS tags / tags
    dico_chars, char_to_id, id_to_char = \
        char_mapping(sentences_for_mapping)
    dico_tags, tag_to_id, id_to_tag = \
        tag_mapping(sentences_for_mapping)
    if parameters['mt_d'] > 0:
        dico_morpho_tags, morpho_tag_to_id, id_to_morpho_tag = \
            morpho_tag_mapping(
                sentences_for_mapping,
                morpho_tag_type=parameters['mt_t'],
                morpho_tag_column_index=parameters['mt_ci'],
                joint_learning=True)
    else:
        id_to_morpho_tag = {}
        morpho_tag_to_id = {}

    return word_to_id, id_to_word,\
           char_to_id, id_to_char, \
           tag_to_id, id_to_tag, \
           morpho_tag_to_id, id_to_morpho_tag


def prepare_datasets(model, opts, parameters, for_training=True):
    """

    :type model: MainTaggerModel
    :param model: description
    :param opts:
    :param parameters:
    :param for_training:
    :return:
    """

    train_sentences, dev_sentences, test_sentences, \
    yuret_train_sentences, yuret_test_sentences, \
    max_sentence_lengths, max_word_lengths = \
        _prepare_datasets(opts, parameters, for_training=for_training)

    if not for_training:
        model.reload_mappings()

        # words
        # dico_words, word_to_id, id_to_word
        id_to_word = dict(model.id_to_word)
        word_to_id = {word: word_id for word_id, word in id_to_word.items()}
        # id_to_word[10000000] = "<UNK>"
        # word_to_id["<UNK>"] = 10000000

        # chars
        id_to_char = dict(model.id_to_char)
        char_to_id = {char: char_id for char_id, char in id_to_char.items()}

        # tags
        id_to_tag = dict(model.id_to_tag)
        print id_to_tag
        tag_to_id = {tag: tag_id for tag_id, tag in id_to_tag.items()}
        print tag_to_id

        # morpho_tags
        id_to_morpho_tag = dict(model.id_to_morpho_tag)
        morpho_tag_to_id = {morpho_tag: morpho_tag_id for morpho_tag_id, morpho_tag in id_to_morpho_tag.items()}
    else:
        word_to_id, id_to_word, \
        char_to_id, id_to_char, \
        tag_to_id, id_to_tag, \
        morpho_tag_to_id, id_to_morpho_tag = create_mappings(dev_sentences, parameters['lower'], parameters, test_sentences,
                                                             train_sentences,
                                                             yuret_test_sentences, yuret_train_sentences)

    if opts.overwrite_mappings and for_training:
        print 'Saving the mappings to disk...'
        model.save_mappings(id_to_word, id_to_char, id_to_tag, id_to_morpho_tag)

    # Index data
    if for_training:
        _, train_stats, train_unique_words, train_data = prepare_dataset(
            train_sentences, word_to_id, char_to_id, tag_to_id, morpho_tag_to_id,
            parameters['lower'], parameters['mt_d'], parameters['mt_t'], parameters['mt_ci'],
        )
    _, dev_stats, dev_unique_words, dev_data = prepare_dataset(
        dev_sentences, word_to_id, char_to_id, tag_to_id, morpho_tag_to_id,
        parameters['lower'], parameters['mt_d'], parameters['mt_t'], parameters['mt_ci'],
    )
    _, test_stats, test_unique_words, test_data = prepare_dataset(
        test_sentences, word_to_id, char_to_id, tag_to_id, morpho_tag_to_id,
        parameters['lower'], parameters['mt_d'], parameters['mt_t'], parameters['mt_ci'],
    )
    if parameters['test_with_yuret'] or parameters['train_with_yuret']:
        # yuret train and test datasets
        if for_training:
            _, yuret_train_stats, yuret_train_unique_words, yuret_train_data = prepare_dataset(
                yuret_train_sentences, word_to_id, char_to_id, tag_to_id, morpho_tag_to_id,
                parameters['lower'], parameters['mt_d'], parameters['mt_t'], parameters['mt_ci'],
            )
        _, yuret_test_stats, yuret_test_unique_words, yuret_test_data = prepare_dataset(
            yuret_test_sentences, word_to_id, char_to_id, tag_to_id, morpho_tag_to_id,
            parameters['lower'], parameters['mt_d'], parameters['mt_t'], parameters['mt_ci'],
        )
    else:
        yuret_train_data = []
        yuret_test_data = []

    if for_training:
        print "%i / %i / %i sentences in train / dev / test." % (
            len(train_stats), len(dev_stats), len(test_stats))

        print "%i / %i / %i words in  dev / test." % (
            sum([x[0] for x in train_stats]), sum([x[0] for x in dev_stats]), sum([x[0] for x in test_stats]))
        print "%i / %i / %i longest sentences in  dev / test." % (
            max([x[0] for x in train_stats]), max([x[0] for x in dev_stats]), max([x[0] for x in test_stats]))
        print "%i / %i / %i shortest sentences in  dev / test." % (
            min([x[0] for x in train_stats]), min([x[0] for x in dev_stats]), min([x[0] for x in test_stats]))

        for i, label in [[2, 'char']]:
            print "%i / %i / %i total %s in train / dev / test." % (
                sum([sum(x[i]) for x in train_stats]), sum([sum(x[i]) for x in dev_stats]),
                sum([sum(x[i]) for x in test_stats]),
                label)

            print "%i / %i / %i max. %s lengths in train / dev / test." % (
                max([max(x[i]) for x in train_stats]), max([max(x[i]) for x in dev_stats]),
                max([max(x[i]) for x in test_stats]),
                label)

            print "%i / %i / %i min. %s lengths in train / dev / test." % (
                min([min(x[i]) for x in train_stats]), min([min(x[i]) for x in dev_stats]),
                min([min(x[i]) for x in test_stats]),
                label)
    else:
        print "%i / %i sentences in dev / test." % (
            len(dev_stats), len(test_stats))

        print "%i / %i words in dev / test." % (
            sum([x[0] for x in dev_stats]), sum([x[0] for x in test_stats]))
        print "%i / %i longest sentences in dev / test." % (
            max([x[0] for x in dev_stats]), max([x[0] for x in test_stats]))
        print "%i / %i shortest sentences in dev / test." % (
            min([x[0] for x in dev_stats]), min([x[0] for x in test_stats]))


        for i, label in [[2, 'char']]:
            print "%i / %i total %s in train / dev / test." % (
                sum([sum(x[i]) for x in dev_stats]),
                sum([sum(x[i]) for x in test_stats]),
                label)

            print "%i / %i max. %s lengths in train / dev / test." % (
                max([max(x[i]) for x in dev_stats]),
                max([max(x[i]) for x in test_stats]),
                label)

            print "%i / %i min. %s lengths in train / dev / test." % (
                min([min(x[i]) for x in dev_stats]),
                min([min(x[i]) for x in test_stats]),
                label)

    print "Max. sentence lengths: %s" % max_sentence_lengths
    print "Max. char lengths: %s" % max_word_lengths

    if for_training:
        triple_list = [['train', train_stats, train_unique_words],
                       ['dev', dev_stats, dev_unique_words],
                       ['test', test_stats, test_unique_words]]

        for label, bucket_stats, n_unique_words in triple_list:
            int32_items = len(train_stats) * (max_sentence_lengths[label] * (5 + max_word_lengths[label]) + 1)
            float32_items = n_unique_words * parameters['word_dim']
            total_size = int32_items + float32_items
            # TODO: fix this with byte sizes
            logging.info("Input ids size of the %s dataset is %d" % (label, int32_items))
            logging.info(
                "Word embeddings (unique: %d) size of the %s dataset is %d" % (n_unique_words, label, float32_items))
            logging.info("Total size of the %s dataset is %d" % (label, total_size))

    # # Save the mappings to disk
    # print 'Saving the mappings to disk...'
    # model.save_mappings(id_to_word, id_to_char, id_to_tag, id_to_morpho_tag)

    if for_training:
        return dev_data, {}, id_to_tag, parameters['t_s'], test_data, \
               train_data, train_stats, word_to_id, yuret_test_data, yuret_train_data
    else:
        return dev_data, {}, id_to_tag, parameters['t_s'], test_data, [], {}, word_to_id, yuret_test_data, []