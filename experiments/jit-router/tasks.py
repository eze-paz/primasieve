"""Synthetic multi-task text-classification suite for the bake-off.

These tasks are TEMPLATED, not scraped — but every method sees identical data,
so the relative accuracy/cost ranking is meaningful even if absolute numbers
are illustrative. Difficulty is varied on purpose:

  sentiment  : 2-class, cleanly lexically separable (easy; everything wins)
  intent     : 4-class, separable but overlapping filler vocab (medium)
  topic      : 4-class, heavier vocab overlap + noise (medium-hard)
  xor_signal : 2-class, label = (kwA present) XOR (kwB present) -> NOT linearly
               separable in bag-of-words; separates linear heads (prototype/
               ridge) from neighborhood/interaction-capturing heads.

Each Task carries labeled train pool + held-out test. The 'JIT' step fits a
head on a SUBSET of the train pool (pool_k) to mimic router-selected data.
"""
from __future__ import annotations
import numpy as np

FILLER = ("the a to my i we you please could can now today just really".split())


def _rng(seed):
    return np.random.default_rng(seed)


def _compose(rng, kws, n_words=(6, 12)):
    k = rng.integers(*n_words)
    words = list(rng.choice(kws, size=max(1, k // 2)))
    words += list(rng.choice(FILLER, size=k - len(words)))
    rng.shuffle(words)
    return " ".join(words)


class Task:
    def __init__(self, name, texts, labels, n_classes):
        self.name = name
        self.texts = np.array(texts, dtype=object)
        self.labels = np.array(labels, dtype=np.int64)
        self.n_classes = n_classes

    def split(self, seed, n_train_per_class, n_test_per_class):
        rng = _rng(seed)
        tr_i, te_i = [], []
        for c in range(self.n_classes):
            idx = np.where(self.labels == c)[0]
            rng.shuffle(idx)
            tr_i += list(idx[:n_train_per_class])
            te_i += list(idx[n_train_per_class:n_train_per_class + n_test_per_class])
        return (self.texts[tr_i], self.labels[tr_i],
                self.texts[te_i], self.labels[te_i])


def _lexical_task(name, class_vocabs, n_per_class, seed):
    rng = _rng(seed)
    texts, labels = [], []
    for c, kws in enumerate(class_vocabs):
        for _ in range(n_per_class):
            texts.append(_compose(rng, kws))
            labels.append(c)
    return Task(name, texts, labels, len(class_vocabs))


def _xor_task(name, n, seed):
    rng = _rng(seed)
    A = "aurora zephyr quasar".split()
    B = "basalt cobalt drift".split()
    noise = "lorem ipsum dolor amet sigma delta gamma".split()
    texts, labels = [], []
    for _ in range(n):
        a = rng.random() < 0.5
        b = rng.random() < 0.5
        words = list(rng.choice(noise, size=rng.integers(4, 8)))
        if a:
            words += list(rng.choice(A, size=rng.integers(1, 3)))
        if b:
            words += list(rng.choice(B, size=rng.integers(1, 3)))
        rng.shuffle(words)
        texts.append(" ".join(words))
        labels.append(int(a ^ b))
    return Task(name, texts, labels, 2)


def build_suite(n_per_class=120, seed=0):
    tasks = [
        _lexical_task("sentiment", [
            "love great amazing excellent wonderful fantastic best perfect happy".split(),
            "hate terrible awful worst horrible bad disappointing broken sad".split(),
        ], n_per_class, seed + 1),
        _lexical_task("intent", [
            "weather forecast rain temperature sunny cloudy umbrella outside".split(),
            "alarm wake timer remind minutes clock snooze morning".split(),
            "music play song album artist volume playlist track".split(),
            "calendar meeting schedule appointment event tomorrow invite".split(),
        ], n_per_class, seed + 2),
        _lexical_task("topic", [
            "match goal team player score league championship coach season".split(),
            "software chip algorithm data cloud model server code network".split(),
            "market stock invest revenue profit shares economy trading fund".split(),
            "patient doctor disease treatment symptom clinic health medicine".split(),
        ], n_per_class, seed + 3),
        _xor_task("xor_signal", n_per_class * 2, seed + 4),
    ]
    return tasks
