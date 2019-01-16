import xgboost as xgb
import numpy as np
import pandas as pd
import shutil
import os
import tools
from preprocessing.textsim import get_sim_features
from collections import Counter
from sklearn.metrics import classification_report
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.model_selection import GridSearchCV
from sklearn.preprocessing import Normalizer

#########################################################################


def load_data(fname):
    npzfile = np.load(fname)
    vals = pd.DataFrame(npzfile['vals'])
    vals.columns = npzfile['columns']
    return vals


data_train = load_data('../data/dedup/train_sim_ftrs.npz')
data_test = load_data('../data/dedup/test_sim_ftrs.npz')

cols = [c for c in data_train.columns if c not in {
    'qid', 'synid', 'fid', 'target'}]

norm = Normalizer()
X_train = norm.fit_transform(data_train[cols])
X_test = norm.transform(data_test[cols])

y_train = data_train['target']
y_test = data_test['target']

#########################################################################

params = {'n_estimators': 100, 'n_jobs': -1,
          'max_depth': 5, 'min_child_weight': 1,
          'gamma': 3, 'subsample': 0.8,
          'colsample_bytree': 0.8, 'reg_alpha': 5}

model = xgb.XGBClassifier(**params)
model.fit(X_train, y_train)


def predict(model, X, y, threshold=0.5):
    c = Counter(y)
    probs = model.predict_proba(X)
    y_pred = (probs[:, 1] >= threshold).astype(int)
    print(classification_report(y, y_pred, labels=[1]))
    print('base accuracy %f' % (c[0]/sum(c.values())))
    print('accuracy %f' % accuracy_score(y, y_pred))
    return y_pred


_ = predict(model, X_train, y_train)
y_pred = predict(model, X_test, y_test, threshold=0.8)
cm = confusion_matrix(y_test, y_pred)


corpus = tools.load_samples('../data/dedup/corpus.npz')
corpus[corpus['fid'] == 1026586]['text'].iloc[0]

q = tools.normalize(
    'Паяльник импульсный (HS-50T) 220V/30-70 Вт (ZD-60) REXANT', stem=False, translit=True)
d = tools.normalize(
    'арт. 12-0162, паяльник импульсный hs-50 30-130 вт (zd-80), REXANT REXANT', stem=False, translit=True)

get_sim_features(q, d)
