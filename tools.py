from glob import glob
import json
import re
import pickle
import pandas as pd
import numpy as np
import zipfile
import os
from textblob.tokenizers import WordTokenizer
import string
from nltk.stem.snowball import SnowballStemmer
import cyrtranslit
import paramiko
import time
from pprint import pprint
from tqdm import tqdm
from pymongo import MongoClient

# from tokenizer import tokenize

c_HOST = '10.70.6.154'
ml_HOST = '10.72.100.255'

chars = string.punctuation
chars = chars.replace('%', '').replace('_', '').replace('@', '')
punct_tt = str.maketrans(dict.fromkeys(chars, ' '))
prog = re.compile("[\\W\\d]", re.UNICODE)

float_prog = re.compile(r"[-+]?\d*\.\d+|\d+", re.UNICODE)
dot_prog = re.compile(r'[xх*]', re.UNICODE)

TransTable = str.maketrans(dict.fromkeys(r'/-\[\]()|{}:^+', ' '))
wt = WordTokenizer()

unit_lookup = {
    'г': 'грамм', 'грам': 'грамм', 'гр': 'грамм', 'грамм': 'грамм', 'gr': 'грамм',
    'ml': 'мл', 'милл': 'мл', 'млитр': 'мл', 'млтр': 'мл', 'мл': 'мл',
    'ш': 'шт', 'шт': 'шт',
    'тон': 'тонна', 'тн': 'тонна', 'тонна': 'тонна', 'тонн': 'тонна',
    'л': 'литр', 'литр': 'литр', 'лит': 'литр',
    'kg': 'кг', 'кг': 'кг',
    'mm': 'мм', 'cm': 'см', 'мм': 'мм', 'см': 'см', 'дм': 'дм',
    '№': 'номер', 'номер': 'номер',
    'ват': 'ватт', 'вт': 'ватт', 'ватт': 'ватт'}

stemmer = SnowballStemmer("russian", ignore_stopwords=True)


def normalize(sent, stem=False, translit=True):
    tokens = normalize_v2(sent, translit)
    if stem:
        tokens = (stemmer.stem(t) for t in tokens)
    sent = " ".join((t for t in tokens))
    return sent


def isnum(t):
    try:
        f = float(t)
        # if f.is_integer():
        #     return str(int(f))
        return str(f)
    except:
        return False


def split_unit(t):
    if len(t) == 0 or not t[0].isdigit():
        return t
    tmp = float_prog.findall(t)
    if len(tmp):
        striped = t.lstrip(tmp[0])
        if len(tmp) > 1:
            ix = striped.find(tmp[1])
            postfix = striped[:ix]
        else:
            postfix = striped

        return str(float(tmp[0])), unit_lookup.get(postfix, postfix)
    return t


def proceed_token(t, translit=False):
    t = t.replace('ё', 'е').replace('й', 'и').replace(',', '.')
    num = isnum(t)
    if num:
        return num

    t = t.rstrip('ъ')

    # # all ascii
    if translit and all(ord(char) < 128 for char in t):
        t = cyrtranslit.to_cyrillic(t, 'ru')

    tmp = dot_prog.split(t)
    if len(tmp) > 1:
        tmp = [isnum(el) for el in tmp]
        if all(tmp):
            return 'x'.join(tmp)  # english x

    tmp = split_unit(t)
    if type(tmp) == tuple:
        return tmp[0] + ' ' + tmp[1]

    t = t.replace('.', ' ')
    tmp = (unit_lookup.get(t, t) for t in t.split(' '))
    t = ' '.join((ti for ti in tmp if len(ti) > 1))
    return t


def normalize_v2(sent, translit=False):
    tmp = sent.translate(TransTable).lower()
    tokens = (proceed_token(t, translit) for t in wt.tokenize(tmp, False))
    return tokens


def normalize_v1(sent):
    """
    this is better than v0
    """
    sent = sent.translate(TransTable).lower()
    tokens = (t for t in wt.tokenize(sent, False) if len(t) > 1)
    sent = " ".join(tokens)
    return sent


def normalize_v0(sent):
    tokens = sent.translate(punct_tt).lower().split()
    tokens = (prog.sub('', w) for w in tokens)
    sent = ' '.join((w for w in tokens if len(w) > 1))
    return sent


def current_dir():
    import inspect

    filename = inspect.getframeinfo(inspect.currentframe()).filename
    path = os.path.dirname(os.path.abspath(filename))
    return path


def load_master():
    dir_name = os.path.join(current_dir(), '../data/master/')

    pkls = glob(dir_name + 'master**.pkl')
    if len(pkls):
        data = do_unpickle(pkls[0])
    else:
        fname = sorted(glob(dir_name + 'master**.zip'))[-1]
        with zipfile.ZipFile(fname, 'r') as z:
            inner_name = z.namelist()[0]
            with z.open(inner_name) as f:
                text = f.read()
            data = json.loads(text.decode("utf-8"))
        do_pickle(data, dir_name + 'master.pkl')
    print('master loaded')
    return Updater(data)


def do_pickle(data, fname):
    with open(fname, 'wb') as f:
        pickle.dump(data, f)


def do_unpickle(fname):
    with open(fname, 'rb') as f:
        data = pickle.load(f)
    return data


class Updater:
    def __init__(self, master):
        self.ets = []
        self.id2cat, self.cat2id, self.id2man, \
            self.man2id, self.brand2id, \
            self.id2et, self.ftr2id, \
            self.id2brand, self.id2clr, self.fval2id = [dict()] * 10

        self.db = master['Database']
        if type(self.db) == list:
            self.db = self.db[0]
        self.tags = {'etalons': 'ets',
                     'features': 'ftrs',
                     'categories': 'cats',
                     'featureValues': 'fvals',
                     'brands': 'brands',
                     'subBrands': 'subBrands',
                     'goodTypes': 'goodTypes',
                     'manufacturers': 'mans',
                     'suppliers': 'sups',
                     'units': 'units',
                     'classifiers': 'clrs'}

        self.attr_cols = ['barcodes', 'synonyms', 'manufacturerId', 'comment',
                          'brandId', 'description', 'manufacturerCode',
                          'source', 'srcId', 'unitName', 'classifiers',
                          'weight', 'volume', 'length', 'nameShort',
                          'unitOKEI', 'vat', 'area', 'subBrandId',
                          'goodTypeId', 'supplierId']

        for k, v in self.tags.items():
            setattr(self, v, self.db.get(k, {}))

        for k, v in self.tags.items():
            ltag = 'name' if v in {'units', 'clrs'} else 'id'
            name = 'id2' + v.rstrip('s')
            setattr(self, name, self.get_dict(getattr(self, v), ltag))

        for k, v in self.tags.items():
            if v in {'units', 'clrs'}:
                continue
            elif v == 'fvals':
                ltag = 'value'
            elif v == 'ftrs':
                ltag = 'name'
            name = v.rstrip('s') + '2id'
            setattr(self, name, self.get_dict(getattr(self, v), ltag, 'id'))

    @staticmethod
    def get_dict(array, ltag, rtag=None):
        if not array:
            return None
        elif rtag:
            return {el[ltag]: el[rtag] for el in array if ltag in el}
        else:
            return {el[ltag]: el for el in array if ltag in el}


def constitute_text(name, et, id2brand):
    text = name
    bid = et.get('brandId')
    if bid:
        bname = id2brand[bid]['name'].lower()
        if bname not in text.lower():
            text += ' ' + bname
    return text


def load_samples(filename, key='samples'):
    npzfile = np.load(filename)
    samples = pd.DataFrame(npzfile[key])
    samples.columns = npzfile['columns']
    return samples


def scp(host, user, localfile, remotefile):
    transport = paramiko.Transport((host, 22))
    transport.connect(username=user, pkey='~/.ssh/id_rsa')
    sftp = paramiko.SFTPClient.from_transport(transport)
    sftp.put(localfile, remotefile)
    sftp.close()
    transport.close()


def feed2mongo(feed, dbname):
    client = MongoClient()
    client.drop_database(dbname)
    db = client[dbname]

    fdb = feed['Database']
    if isinstance(fdb, list):
        fdb = fdb[0]

    for k, v in fdb.items():
        if not isinstance(v, list):
            continue
        for el in v:
            _id = el.pop('id', None)
            if _id is not None:
                el['_id'] = _id

        if len(v):
            db[k].insert_many(v)


def dcg_at_k(r, k, method=1):
    """Score is discounted cumulative gain (dcg)
    Relevance is positive real values.  Can use binary
    as the previous methods.
    Example from
    http://www.stanford.edu/class/cs276/handouts/EvaluationNew-handout-6-per.pdf
    >>> r = [3, 2, 3, 0, 0, 1, 2, 2, 3, 0]
    >>> dcg_at_k(r, 1)
    3.0
    >>> dcg_at_k(r, 1, method=1)
    3.0
    >>> dcg_at_k(r, 2)
    5.0
    >>> dcg_at_k(r, 2, method=1)
    4.2618595071429155
    >>> dcg_at_k(r, 10)
    9.6051177391888114
    >>> dcg_at_k(r, 11)
    9.6051177391888114
    Args:
        r: Relevance scores (list or numpy) in rank order
            (first element is the first item)
        k: Number of results to consider
        method: If 0 then weights are [1.0, 1.0, 0.6309, 0.5, 0.4307, ...]
                If 1 then weights are [1.0, 0.6309, 0.5, 0.4307, ...]
    Returns:
        Discounted cumulative gain
    """
    r = np.asfarray(r)[:k]
    if r.size:
        if method == 0:
            return r[0] + np.sum(r[1:] / np.log2(np.arange(2, r.size + 1)))
        elif method == 1:
            return np.sum(r / np.log2(np.arange(2, r.size + 2)))
        else:
            raise ValueError('method must be 0 or 1.')
    return 0.


def ndcg_at_k(r, k, method=1):
    """Score is normalized discounted cumulative gain (ndcg)
    Relevance is positive real values.  Can use binary
    as the previous methods.
    Example from
    http://www.stanford.edu/class/cs276/handouts/EvaluationNew-handout-6-per.pdf
    >>> r = [3, 2, 3, 0, 0, 1, 2, 2, 3, 0]
    >>> ndcg_at_k(r, 1)
    1.0
    >>> r = [2, 1, 2, 0]
    >>> ndcg_at_k(r, 4)
    0.9203032077642922
    >>> ndcg_at_k(r, 4, method=1)
    0.96519546960144276
    >>> ndcg_at_k([0], 1)
    0.0
    >>> ndcg_at_k([1], 2)
    1.0
    Args:
        r: Relevance scores (list or numpy) in rank order
            (first element is the first item)
        k: Number of results to consider
        method: If 0 then weights are [1.0, 1.0, 0.6309, 0.5, 0.4307, ...]
                If 1 then weights are [1.0, 0.6309, 0.5, 0.4307, ...]
    Returns:
        Normalized discounted cumulative gain
    """
    dcg_max = dcg_at_k(sorted(r, reverse=True), k, method)
    if not dcg_max:
        return 0.
    return dcg_at_k(r, k, method) / dcg_max
