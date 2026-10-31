"""单字 OCR：PP-OCR 识别模型（rapidocr-onnxruntime 自带的 onnx，免 GPU、免 paddle）。

不只取首选字：把每个时间步的 softmax 取全图最大，得到「参校字在 OCR 眼里的概率」`pref`，
首选不是参校字时也有分数可用。单字块约 3ms。手写体异体（亳/毫）、生僻字（字典外）OCR 认不了，
所以 OCR 只当一票，不单独作放行依据（史記第 1 轮：OCR 单用 AUC 0.70）。
"""
from __future__ import annotations

import cv2
import numpy as np


class OcrScorer:
    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR   # 可选依赖：pip install -e ".[triage]"
        self._rec = RapidOCR().text_recognizer
        self.chars = list(self._rec.postprocess_op.character)   # 0 是 CTC blank
        self.index = {c: i for i, c in enumerate(self.chars)}

    @staticmethod
    def _prep(gray: np.ndarray) -> np.ndarray:
        """缩到长边 40、四周留 4 白边 → 高 48 的识别输入。"""
        h, w = gray.shape
        k = 40 / max(w, h)
        im = cv2.resize(gray, (max(1, int(w * k)), max(1, int(h * k))))
        im = cv2.copyMakeBorder(im, 4, 4, 4, 4, cv2.BORDER_CONSTANT, value=255)
        im = cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)
        W = max(im.shape[1], 48)
        x = cv2.resize(im, (W, 48)).astype("float32").transpose(2, 0, 1) / 255
        return ((x - 0.5) / 0.5)[None]

    def score(self, gray: np.ndarray, ref: str | None) -> dict:
        p = self._rec.session(self._prep(gray))[0][0]          # T × V
        if p.min() < 0 or abs(float(p.sum(1).mean()) - 1) > 0.05:
            e = np.exp(p - p.max(1, keepdims=True)); p = e / e.sum(1, keepdims=True)
        text, confs, prev = [], [], -1
        for a, pr in zip(p.argmax(1), p.max(1)):
            if a != prev and a != 0:
                text.append(self.chars[a]); confs.append(float(pr))
            prev = a
        mx = p.max(0)
        top = [(self.chars[i], round(float(mx[i]), 4)) for i in np.argsort(-mx)[:6] if i != 0][:5]
        return {"ocr": "".join(text), "ocr_conf": min(confs) if confs else 0.0, "ocr_top": top,
                "ocr_pref": float(mx[self.index[ref]]) if ref in self.index else None}


def ocr_features(o: dict, ref: str | None) -> dict[str, float]:
    return {"ocr_eq": float(o["ocr"] == ref), "ocr_conf": float(o["ocr_conf"]),
            "ocr_pref": float(o["ocr_pref"] or 0.0),
            "ocr_in_top5": float(ref in [c for c, _ in o["ocr_top"]]), "ocr_len": float(len(o["ocr"]))}


OCR_FEATURE_NAMES = ["ocr_eq", "ocr_conf", "ocr_pref", "ocr_in_top5", "ocr_len"]
