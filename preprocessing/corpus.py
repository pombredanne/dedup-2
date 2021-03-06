r"""
Sample command lines:

python3 preprocessing/corpus.py \
--data_dir=../data/dedup \
--build_tfidf
"""

from absl import flags
from absl import app
import tools
import pandas as pd
import numpy as np
from tqdm import tqdm
from pymongo import MongoClient
import io
import sys
from nltk.corpus import stopwords
from tokenizer import tokenize

FLAGS = tools.FLAGS


def id2ets(samples, normalizer=None, all_master=False):
    client = MongoClient(FLAGS.mongo_host)
    db = client[FLAGS.feed_db]
    mdb = client[FLAGS.release_db]

    id2brand = {c['_id']: c for c in db.brands.find({}, projection=['name'])}
    mid2brand = {c['_id']: c for c in mdb.brands.find({}, projection=['name'])}

    def get_brand_name(et, id2brand):
        bid = et.get('brandId')
        if bid:
            bname = id2brand[bid]['name'].lower()
            return bname
        else:
            return ''

    proj = ['name', 'brandId', 'synonyms']

    if all_master:
        total = mdb.etalons.count_documents({})
        mets = mdb.etalons.find({}, projection=proj)
    else:
        ids = list(samples['fid'].unique())
        total = len(ids)
        mets = mdb.etalons.find({'_id': {'$in': ids}},
                               projection=proj)

    mid2et = {}
    for met in tqdm(mets, total=total):
        met['brand'] = get_brand_name(met, mid2brand)
        met.pop('brandId', None)
        
        if normalizer:
            text = tools.constitute_text(met, use_syns=True)
            met['text'] = normalizer(text)
        
        mid2et[met['_id']] = met

    subdf = samples[['qid', 'synid']].drop_duplicates()
    qids = subdf['qid'].unique().tolist()
    ets = db.etalons.find({'_id': {'$in': qids}}, projection=proj)
    id2et = {et['_id']: et for et in ets}
    
    id2et_new = {}
    for qid, sid in tqdm(subdf.values):
        et = id2et[qid]
        if pd.isna(sid):
            name = et['name']
            sid = None
        else:
            name = next((s['name'] for s in et.get('synonyms')
                         if s['id'] == sid))
        
        brand = get_brand_name(et, id2brand)
        new_et = {'_id': et['_id'], 'name': name, 'brand': brand}

        if normalizer:
            text = tools.constitute_text(new_et, use_syns=False)
            new_et['text'] = normalizer(text)

        id2et_new[(qid, sid)] = new_et

    return mid2et, id2et_new


def make_corpus(samples):
    corpus = []
    # translit = not FLAGS.notranslit

    mid2et, id2et = id2ets(samples, tools.normalize, all_master=FLAGS.build_tfidf)

    ###############################################################

    for et in mid2et.values():
        corpus.append((None, None, et['_id'], et['text']))

    ###############################################################

    subdf = samples[['qid', 'synid']].drop_duplicates()
    for qid, sid in subdf.values:
        sid = None if pd.isna(sid) else sid
        et = id2et[(qid, sid)]
        corpus.append((qid, sid, None, et['text']))

    corpus = np.array(corpus)
    columns = ['qid', 'synid', 'fid', 'text']
    np.savez(FLAGS.data_dir + '/corpus.npz', samples=corpus, columns=columns)

    return corpus, columns


def get_tfidf(samples, corpus, columns):
    '''
    Build tf-idf model using master data and 1c-Fresh train data
    '''
    from sklearn.feature_extraction.text import TfidfVectorizer

    def get_stop_words():
        words = set(stopwords.words("russian"))
        with io.open('./solr/stopwords_ru.txt', encoding='utf8') as f:
            for l in f:
                splited = l.split('|')
                word = splited[0].strip()
                if word:
                    words.update([word])

        return words

    corpus = pd.DataFrame(corpus)
    corpus.columns = columns

    samples = samples[(samples['train']==0)|(samples['vali']==1)]
    qids = samples['qid'].unique()

    corpus = corpus[~corpus['qid'].isin(qids)]
    if len(corpus) == 0:  # test
        return
    texts = corpus['text'].values

    vectorizer = TfidfVectorizer(
        stop_words=get_stop_words(), token_pattern=r"(?u)\S+")
    model = vectorizer.fit(texts)
    tools.do_pickle(model, '../data/dedup/tfidf_model.pkl')

    # sent = 'молоко пастеризованное домик в деревне'
    # model.transform([normalizer(sent)])


def main(argv):
    del argv  # Unused.
    samples = tools.load_samples(FLAGS.data_dir + '/samples.npz')
    corpus, columns = make_corpus(samples)
    if FLAGS.build_tfidf:
        get_tfidf(samples, corpus, columns)


if __name__ == '__main__':
    import __main__
    flags.mark_flag_as_required("data_dir")

    if hasattr(__main__, '__file__'):
        app.run(main)
    else:
        sys.argv += ['--data_dir=../data/dedup', '--build_tfidf']
        FLAGS(sys.argv)
