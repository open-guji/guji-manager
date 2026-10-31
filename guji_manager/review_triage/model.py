"""「人会不会拦」的打分模型：GBDT，特征＝裁图几何（＋OCR）。按页分组交叉验证，按目标拦截率定阈值。"""
from __future__ import annotations

import pickle
from dataclasses import dataclass, field

import numpy as np

from .geometry import FEATURE_NAMES
from .ocr import OCR_FEATURE_NAMES


def gbdt():
    from sklearn.ensemble import GradientBoostingClassifier
    return GradientBoostingClassifier(n_estimators=150, max_depth=3, learning_rate=0.08,
                                      subsample=0.8, random_state=0)


def matrix(rows: list[dict], use_ocr: bool = True) -> np.ndarray:
    names = FEATURE_NAMES + (OCR_FEATURE_NAMES if use_ocr else [])
    return np.array([[float(r["f"].get(k, 0.0)) for k in names] for r in rows])


def cv_scores(rows: list[dict], groups: list[str], use_ocr: bool = True, folds: int = 5) -> np.ndarray:
    """按页分组的交叉验证打分（同一页的格不同时出现在训练和验证里）。"""
    from sklearn.model_selection import GroupKFold
    X = matrix(rows, use_ocr); y = np.array([r["label"] == "bad" for r in rows])
    p = np.zeros(len(rows))
    for tr, te in GroupKFold(folds).split(X, y, groups):
        p[te] = gbdt().fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
    return p


def threshold_for_recall(p: np.ndarray, y: np.ndarray, recall: float) -> float:
    """最大阈值 t，使 bad 里 p ≥ t（被拦下）的比例 ≥ recall。分数 < t 的放行。"""
    s = np.sort(p[y])
    k = int(np.floor((1 - recall) * len(s)))
    return float(s[min(k, len(s) - 1)]) if len(s) else 1.0


def table(p: np.ndarray, y: np.ndarray, recalls=(0.9, 0.95, 0.98)) -> list[dict]:
    out = []
    for r in recalls:
        t = threshold_for_recall(p, y, r)
        pas = p < t
        out.append({"target_recall": r, "threshold": round(t, 4), "pass": int(pas.sum()), "total": len(p),
                    "pass_bad": int((pas & y).sum()), "bad": int(y.sum()), "review": int((~pas).sum())})
    return out


@dataclass
class Model:
    clf: object
    use_ocr: bool
    threshold: float
    meta: dict = field(default_factory=dict)

    def score(self, rows: list[dict]) -> np.ndarray:
        return self.clf.predict_proba(matrix(rows, self.use_ocr))[:, 1]

    def save(self, path) -> None:
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path) -> "Model":
        with open(path, "rb") as f:
            return pickle.load(f)


def train(rows: list[dict], use_ocr: bool = True, threshold: float = 0.02, meta: dict | None = None) -> Model:
    y = np.array([r["label"] == "bad" for r in rows])
    return Model(gbdt().fit(matrix(rows, use_ocr), y), use_ocr, threshold, meta or {})
