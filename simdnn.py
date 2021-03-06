import tensorflow as tf
import numpy as np
import pandas as pd
import shutil
import os
import tools
from preprocessing import dataset
from sklearn.preprocessing import StandardScaler
from sklearn.datasets import load_svmlight_file

#########################################################################

batch_size = 128

X_train, y_train = load_svmlight_file("../data/dedup/train_letor.txt")
X_vali, y_vali = load_svmlight_file("../data/dedup/vali_letor.txt")
X_test, y_test = load_svmlight_file("../data/dedup/test_letor.txt")

model_dir = "./model/simdnn"

#########################################################################


def _input_fn(train=True, num_epochs=1, shuffle=False, seed=0):
    if train:
        ds = tf.data.Dataset.from_tensor_slices(
            ({'x': X_train}, y_train))
    else:
        ds = tf.data.Dataset.from_tensor_slices(
            ({'x': X_test}, y_test))

    if shuffle:
        ds = ds.shuffle(10000, seed=seed)

    ds = ds.batch(batch_size).repeat(num_epochs)

    # Return the next batch of data.
    features, labels = ds.make_one_shot_iterator().get_next()
    return features, labels


#########################################################################

feature_columns = [tf.feature_column.numeric_column(
    "x", shape=X_train.shape[1])]

my_optimizer = tf.train.AdagradOptimizer(
    learning_rate=0.1,
    # l1_regularization_strength=0.001,
)

my_optimizer = tf.contrib.estimator.clip_gradients_by_norm(my_optimizer, 5.0)


classifier = tf.estimator.DNNClassifier(
    feature_columns=feature_columns,
    hidden_units=[100, 100],
    # dropout=0.2,
    optimizer=my_optimizer,
    model_dir=model_dir
)

#########################################################################


if os.path.exists(model_dir):
    shutil.rmtree(model_dir)

tf.logging.set_verbosity(tf.logging.INFO)
classifier.train(lambda: _input_fn(
    True, num_epochs=20, shuffle=True))


def do_eval(name):
    evaluation_metrics = classifier.evaluate(
        input_fn=lambda: _input_fn(
            name == 'train', num_epochs=1, shuffle=False),
        name=name
    )
    print("\n%s set metrics:" % name.upper())
    for m in evaluation_metrics:
        print(m, evaluation_metrics[m])
    print("---")


tf.logging.set_verbosity(tf.logging.ERROR)
do_eval('train')
do_eval('test')
