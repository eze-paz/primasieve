"""Per-task heads for Regime A. The 'JIT training' happens here.

Each head implements:
    fit(X, y, n_classes) -> state         # the per-task 'training'
    predict(state, X)    -> labels        # inference

All are pure numpy, CPU. The point of the bake-off is: how much accuracy does
each per-task fit buy, and how many milliseconds does it cost? kNN/prototype
are effectively zero-train; ridge is a single linear solve; logistic is a few
iterations. None of them backprop a network.
"""
from __future__ import annotations
import numpy as np


# ---- kNN: no fit at all (store the pool) -----------------------------------
class KNN:
    def __init__(self, k=5):
        self.k = k

    def fit(self, X, y, n_classes):
        return {"X": X, "y": y, "C": n_classes}

    def predict(self, st, X):
        # cosine sim (features are L2-normed already -> dot product)
        sims = X @ st["X"].T                     # (Nq, Ntrain)
        idx = np.argpartition(-sims, min(self.k, sims.shape[1] - 1), axis=1)[:, :self.k]
        yk = st["y"][idx]                        # (Nq, k)
        out = np.zeros(len(X), dtype=np.int64)
        for i in range(len(X)):
            out[i] = np.bincount(yk[i], minlength=st["C"]).argmax()
        return out


# ---- Prototype / nearest-centroid: one pass --------------------------------
class Prototype:
    def fit(self, X, y, n_classes):
        P = np.zeros((n_classes, X.shape[1]), dtype=np.float32)
        for c in range(n_classes):
            m = X[y == c]
            if len(m):
                v = m.mean(0)
                n = np.linalg.norm(v)
                P[c] = v / n if n > 0 else v
        return {"P": P}

    def predict(self, st, X):
        return (X @ st["P"].T).argmax(1)


# ---- Ridge regression on one-hot targets: one linear solve -----------------
class Ridge:
    def __init__(self, lam=1.0):
        self.lam = lam

    def fit(self, X, y, n_classes):
        n, d = X.shape
        Y = np.eye(n_classes, dtype=np.float32)[y]         # (n, C)
        # solve (X^T X + lam I) W = X^T Y  -- fit in feature-dim space
        # use the smaller Gram to keep it cheap when n<d (usual JIT case)
        if d <= n:
            A = X.T @ X + self.lam * np.eye(d, dtype=np.float32)
            B = X.T @ Y
            W = np.linalg.solve(A, B)                       # (d, C)
            return {"W": W, "kernel": False}
        else:
            # kernel ridge in sample space: alpha = (K + lam I)^-1 Y
            K = X @ X.T
            A = K + self.lam * np.eye(n, dtype=np.float32)
            alpha = np.linalg.solve(A, Y)                   # (n, C)
            return {"alpha": alpha.astype(np.float32), "Xtr": X, "kernel": True}

    def predict(self, st, X):
        if st.get("kernel"):
            return (X @ st["Xtr"].T @ st["alpha"]).argmax(1)
        return (X @ st["W"]).argmax(1)


# ---- Multinomial logistic regression: a few gradient steps -----------------
class Logistic:
    def __init__(self, steps=25, lr=1.0, lam=1e-3):
        self.steps = steps
        self.lr = lr
        self.lam = lam

    def fit(self, X, y, n_classes):
        n, d = X.shape
        W = np.zeros((d, n_classes), dtype=np.float32)
        Y = np.eye(n_classes, dtype=np.float32)[y]
        lr = self.lr
        for _ in range(self.steps):
            logits = X @ W
            logits -= logits.max(1, keepdims=True)
            P = np.exp(logits)
            P /= P.sum(1, keepdims=True)
            grad = X.T @ (P - Y) / n + self.lam * W
            W -= lr * grad
        return {"W": W}

    def predict(self, st, X):
        return (X @ st["W"]).argmax(1)


REGISTRY = {
    "knn":       lambda: KNN(k=5),
    "prototype": lambda: Prototype(),
    "ridge":     lambda: Ridge(lam=1.0),
    "logistic":  lambda: Logistic(steps=25, lr=1.0, lam=1e-3),
}
