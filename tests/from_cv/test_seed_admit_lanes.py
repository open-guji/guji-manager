# -*- coding: utf-8 -*-
"""Step7 待审补放三通道（overview#433，R2 道）：R1 `witness3`、R4 `coord_fallback`、R5 `seal`。

直接测页末那一遍 `_review_lanes_pass`（只吃已写好的 AdmitRec ＋ 库/对齐/坐标/证人），证人逐格读法
测 `clustering.witness_cells`。数据全是自造的。"""
from __future__ import annotations

from types import SimpleNamespace as NS

import pytest

from open_guji_cv.clustering.align_eval import build_ngram_index
from open_guji_cv.clustering.variants import VariantMap
from open_guji_cv.clustering.witness_cells import witness_readings
from open_guji_cv.products.kinds.recog import AdmitRec, ColumnAdmit
from guji_manager.review.cards import card_class
from open_guji_cv.steps.seed_admit import SeedAdmitParams, _lane_class, _review_lanes_pass

pytestmark = pytest.mark.usefixtures("no_cnn")   # CNN 通道开不开随环境变，钉成关（overview#407）

B = "tbook:1"
BODY = "天地玄黃宇宙洪荒日月盈昃辰宿列張寒來暑往秋收冬藏閏餘成歲律呂調陽雲騰致雨露結爲霜"


def _vm():
    return VariantMap.load(None)


def _wit(name, text):
    return NS(name=name, text=text, index=build_ngram_index(text))


def _page(chars, pending: dict):
    """一列，`chars` 是整列的字；`pending={slot: dict(doubts=…, char=…, evidence=…)}` 的格待审，其余已放行。"""
    recs = []
    for i, ch in enumerate(chars, 1):
        if i in pending:
            pd = pending[i]
            recs.append(AdmitRec(id=f"{B}:1:{i}", slot=i, admit=False, char=pd.get("char", ch),
                                 doubts=list(pd.get("doubts", [])), evidence=dict(pd.get("evidence", {}))))
        else:
            recs.append(AdmitRec(id=f"{B}:1:{i}", slot=i, admit=True, channel="match_ref", char=ch))
    return [ColumnAdmit(col=1, chars=recs)]


def _mm(lib: dict, guard: dict | None = None):
    return {f"{B}:1:{s}": NS(char=None, candidates=list(c) if isinstance(c, list) else [(c, 0.95)],
                             guard=(guard or {}).get(s)) for s, c in lib.items()}


def _run(out, *, lib=None, amap=None, coord=None, wits=(), guard=None, canon=None, lib_n=None, **params):
    p = SeedAdmitParams(db_path="x", **params)
    n = _review_lanes_pass(p, out, _mm(lib or {}, guard), amap or {}, coord or {}, _vm(),
                           (lambda: list(wits)) if wits else None, canon=canon, lib_n=lib_n)
    return n, {r.slot: r for r in out[0].chars}


def _ids(d):
    return {f"{B}:1:{s}": v for s, v in d.items()}


# ── 证人逐格读法 ──────────────────────────────────────────────────────


# ── 类别镜像 ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("doubts,ev,char,ref,lib", [
    (["replace_align"], {}, "天", "天", "大"),
    (["context_vs_ref", "replace_align"], {}, "天", "天", "大"),
    (["near_form", "库里没有这个字"], {}, "天", "天", "夭"),
    (["库里没有这个字", "replace_align"], {}, "天", "天", None),
    (["variant_indirect"], {}, "天", "天", "天"),
    (["occluded"], {"occluded": {"via": "coord"}}, "天", None, None),
    (["form_open"], {}, None, "天", "天"),
    (["库 unsure(cov=0.9)"], {}, "已", "已", "巳"),
    (["库 unsure(cov=0.9)", "shadow_veto"], {}, "天", None, "天"),
])
def test_lane_class_mirrors_card_class(doubts, ev, char, ref, lib):
    assert _lane_class(doubts, ev, char, ref, lib) == card_class(doubts, ev, char=char, ref_char=ref, lib_top=lib)


# ── R1 三证人一致 ──────────────────────────────────────────────────────

def _r1_setup(lib_char="大", wit_char=None, coord_char="天"):
    chars = BODY[:30]
    out = _page(chars, {5: dict(doubts=["replace_align", "库 unsure(cov=0.93)"], char="天")})
    chars5 = chars[:4] + (wit_char or "天") + chars[5:]
    wits = [_wit("d.txt", "前" + chars5 + "後"), _wit("w.txt", "前" + chars5 + "後"),
            _wit("y.txt", "前" + chars5 + "後")]
    return out, dict(lib={5: lib_char}, amap=_ids({5: ("天", "replace")}), coord=_ids({5: coord_char}), wits=wits)


# ── R4 坐标对位兜底 ────────────────────────────────────────────────────

def _r4(lib_char, coord_char, wit_chars, guard=None, **params):
    chars = BODY[:30]
    out = _page(chars, {5: dict(doubts=["库 unsure(cov=0.95)", "上下文 margin 不足(0.10)"], char=lib_char)})
    wits = [_wit(f"{k}.txt", "前" + chars[:4] + c + chars[5:] + "後") for k, c in zip("dwy", wit_chars)]
    return _run(out, lib={5: lib_char}, coord=_ids({5: coord_char}), wits=wits,
                guard=({5: guard} if guard else None), **params)


# ── R5 印章区 ─────────────────────────────────────────────────────────

def _seal(cells, coord=None, **params):
    """`cells={slot: (默认字, via)}` 是遮挡格。"""
    chars = BODY[:20]
    pend = {s: dict(doubts=["occluded"], char=c,
                    evidence={"occluded": {"density": 9.0, "via": via, **({"ref_blank": True} if via == "coord_blank" else {})}})
            for s, (c, via) in cells.items()}
    return _run(_page(chars, pend), coord=_ids(coord or {}), **params)


def _title_col(text, cells, lib=None, **params):
    """第 1 列坐标对位整串是 `text`；`cells={slot: 默认字}` 是遮挡格（via=coord）。"""
    chars = text + BODY[len(text):20]
    pend = {s: dict(doubts=["occluded"], char=c, evidence={"occluded": {"density": 9.0, "via": "coord"}})
            for s, c in cells.items()}
    coord = {i: ch for i, ch in enumerate(text, 1)}
    coord.update({i: "" for i in range(len(text) + 1, 21)})
    return _run(_page(chars, pend), coord=_ids(coord), lib=lib, lane_seal=True, **params)


# ── R5 补充：库首位同字当第二证据（seal_lib_agree，overview#471 去章）──────────


# ── 开关与指纹 ────────────────────────────────────────────────────────


# ── 三通道统一异体护栏（#433 vol04：coord_fallback 把刻本「㫖」放成「旨」）──────────────


# ── lane_variant_keep_rare（A24 10-24，vol11–20：整理本照录刻本异体、库首位同形，却被异体护栏拦）──────

def _keep_rare(char, cands, **params):
    chars = BODY[:30]
    out = _page(chars, {5: dict(doubts=["库 unsure(cov=0.95)", "上下文 margin 不足(0.10)"], char=char)})
    wits = [_wit(f"{k}.txt", "前" + chars[:4] + char + chars[5:] + "後") for k in "dwy"]
    p = SeedAdmitParams(db_path="x", lane_coord=True, **params)
    mm = {f"{B}:1:5": NS(char=None, candidates=cands, guard=None)}
    n = _review_lanes_pass(p, out, mm, {}, _ids({5: char}), _vm(), lambda: wits)
    return n, out[0].chars[4]


pytestmark = pytest.mark.usefixtures("seed_admit_switches_off")   # 老测试按「放行开关缺省全关」造的数据，见 conftest


# ── 异体形近规则先于印章（occluded_variant_first，A31 10-28）──────────────────

def _seal_variant(cands, **params):
    """第 5 格遮挡、默认字＝坐标对位字「旨」；库候选 `cands`。"""
    chars = BODY[:20]
    out = _page(chars, {5: dict(doubts=["occluded"], char="旨",
                                evidence={"occluded": {"density": 9.0, "via": "coord"}})})
    p = SeedAdmitParams(db_path="x", lane_seal=True, **params)
    mm = {f"{B}:1:5": NS(char=None, candidates=cands, guard=None)}
    n = _review_lanes_pass(p, out, mm, {}, _ids({5: "旨"}), _vm(), None)
    return n, out[0].chars[4]


def _flow_occluded(monkeypatch, lifted_char, **params):
    """字组流程在遮挡格上放行 `lifted_char` 时，`_group_flow_pass` 的核对（`occluded_variant_first` ③）。"""
    from types import SimpleNamespace as _NS
    import open_guji_cv.groups.flow as flow
    from open_guji_cv.steps.seed_admit import _group_flow_pass
    out = _page(BODY[:10], {3: dict(doubts=["occluded"], char="黃", evidence={"occluded": {"density": 9.0, "via": "coord"}})})

    def fake(seq, amap, cands_of, blocked, cfg, **kw):
        rec = next(r for r in seq if r.slot == 3)
        assert not blocked(rec) if params.get("occluded_variant_first", True) else blocked(rec)
        rec.admit, rec.channel, rec.provenance, rec.char, rec.doubts = True, "group_flow", "context", lifted_char, []
        return _NS(lifted=1, demoted=0)
    monkeypatch.setattr(flow, "group_flow_pass", fake)
    p = SeedAdmitParams(db_path="x", **params)
    net = _group_flow_pass(p, out, {}, {}, None, 1, {})
    return net, out[0].chars[2]


# ── R4 本书 codepoints 已归一的异体对（lane_coord_codepoint_variant）──────────────

def _r4cp(cands, coord_char, **params):
    chars = BODY[:30]
    out = _page(chars, {5: dict(doubts=["库 unsure(cov=0.94)", "上下文 margin 不足(0.08)"], char=cands[0][0])})
    cp = {"清": "淸"}
    canon = lambda c: cp.get(c, c)    # noqa: E731
    return _run(out, lib={5: cands}, coord=_ids({5: coord_char}), canon=canon, lane_coord=True, **params)


