import tools
import numpy as np
import tensorflow as tf
import os
import io
from preprocessing import textsim
from tqdm import tqdm
import multiprocessing as mp
from itertools import islice


samples = tools.load_samples('../data/dedup/samples.npz')

# exclude samples not found in TOP
synids_exclude = set(samples[samples['ix'] == -1]['synid'].unique())
synids_exclude.remove(-1)
samples = samples[~samples['synid'].isin(synids_exclude)]
qids_exclude = samples[samples['ix'] == -1]['qid'].unique()
samples = samples[~samples['qid'].isin(qids_exclude)]

corpus = tools.load_samples('../data/dedup/corpus.npz')

qids = samples[samples['synid'] == -1]['qid'].unique()
sids = samples[samples['synid'] != -1]['synid'].unique()
fids = samples['fid'].unique()


def get_id2text(tag, ids):
    id2text = {}
    for _id, text in corpus[corpus[tag].isin(ids)][[tag, 'text']].values:
        id2text[_id] = text
    return id2text


qid2text = get_id2text('qid', qids)
sid2text = get_id2text('synid', sids)
fid2text = get_id2text('fid', fids)

vals = corpus[corpus['train'] != 0]['text'].values
informative_terms = set([w for s in vals for w in s.split()])
with io.open('../data/dedup/vocab.txt', 'w', encoding='utf8') as f:
    for term in informative_terms:
        f.write(term + '\n')

#########################################################################


def input_data(train=True):
    cur_samples = samples[samples['train'] == int(train)]

    q_terms, d_terms = [], []
    rows = []
    for row in cur_samples.itertuples():
        f_splited = fid2text[row.fid].split()
        if row.synid != -1:
            qtext = sid2text[row.synid]
        else:
            qtext = qid2text[row.qid]

        q_splited = qtext.split()
        if row.target == 0 and ' '.join(f_splited) == ' '.join(q_splited):
            continue

        if len(q_splited) * len(f_splited) == 0:
            continue

        rows.append(row.Index)
        d_terms.append(f_splited)
        q_terms.append(q_splited)

    # TODO: add DNN features: brands ...

    cur_samples = cur_samples.loc[rows]
    values = cur_samples[['qid', 'synid', 'fid', 'score', 'ix', 'target']]
    assert len(values) == len(q_terms)
    return q_terms,  d_terms, values.values


train_data = input_data(True)
test_data = input_data(False)
tools.do_pickle(train_data, '../data/dedup/train_data.pkl')
tools.do_pickle(test_data, '../data/dedup/test_data.pkl')


def worker(tup):
    q_terms, d_terms, info = tup
    q = ' '.join(q_terms)
    d = ' '.join(d_terms)
    ftrs = textsim.get_sim_features(q, d)
    values = list(info) + list(ftrs.values())
    columns = ['qid', 'synid', 'fid', 'score',
               'ix', 'target'] + list(ftrs.keys())
    return values, columns


def get_similarity_features(data, output_file):
    labels = data[-1][:, -1]
    columns = None

    def feeder(data):
        for tup in zip(*data):
            yield tup

    vals = []
    with mp.Pool(mp.cpu_count(), maxtasksperchild=10000) as p:
        with tqdm(total=len(data[0])) as pbar:
            for values, columns in tqdm(p.imap_unordered(worker, feeder(data))):
                vals.append(values)
                pbar.update()

    vals = np.array(vals, dtype=np.float32)
    np.savez(output_file, vals=vals, labels=labels, columns=columns)
    return vals, labels, columns


# train_data = tools.do_unpickle('../data/dedup/train_data.pkl')
# test_data = tools.do_unpickle('../data/dedup/test_data.pkl')


# sub_test = [v[:1000] for v in test_data]
# vals, labels, columns = test_sim_ftrs
test_sim_ftrs = get_similarity_features(
    test_data, '../data/dedup/test_sim_ftrs.npz')
train_sim_ftrs = get_similarity_features(
    train_data, '../data/dedup/train_sim_ftrs.npz')


def _int64_feature(value):
    return tf.train.Feature(int64_list=tf.train.Int64List(value=[value]))


def _bytes_feature(values):
    return tf.train.Feature(bytes_list=tf.train.BytesList(value=values))


def to_example(data, filename):
    writer = tf.python_io.TFRecordWriter(filename)
    q_terms, d_terms, info = data
    labels = info[:, -1]
    for q, d, l in zip(q_terms, d_terms, labels):
            # Create a feature
        feature = {
            'q_terms': _bytes_feature([tf.compat.as_bytes(qi) for qi in q]),
            'd_terms': _bytes_feature([tf.compat.as_bytes(di) for di in d]),
            'labels': _int64_feature(int(l)),
        }
        # Create an example protocol buffer
        example = tf.train.Example(features=tf.train.Features(feature=feature))

        # Serialize to string and write on the file
        writer.write(example.SerializeToString())

    writer.close()


to_example(train_data, '../data/dedup/train.tfrecord')
to_example(test_data, '../data/dedup/test.tfrecord')
