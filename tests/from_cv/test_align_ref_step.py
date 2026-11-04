# -*- coding: utf-8 -*-
"""Step5-d 整理本对齐（阶段归位，2026-09-09）。

`align_ref` 从 `gold/v2_align.py` 里独立出来，成为与 `glyph_match`/
`ocr_candidates`/`context_decision` 平级的正式 Step；`gold.v2_align.align_page`
改成优先读它的产物再派生 `GoldChar`。这里守两条：

1. Step 本身：注册、`consumes`/`needs`、语料指纹进参数哈希；
2. 两个身份没有互相污染：`align_page` 读 `align_ref` 缓存 与 **不经缓存现算
   一遍**（脚本传非默认语料时的兜底路径）必须给出完全相同的结果——这是
   本次重组"纯重组不改变任何裁决"的核心保证，别的测试测不到这条。
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import open_guji_cv.steps  # noqa: F401
from helpers import make_book, make_ctx, page_match, write_product
from open_guji_cv.core.engine import params_hash
from open_guji_cv.core.step import KINDS, STEPS
from open_guji_cv.steps.align_ref import AlignRefParams

BOOK, PAGE, COL = "tbook", 1, 1

#: 测试自备的「整理本」。内容随便，只要够长到 8-gram 锚得住、且与下面那串
#: 刻本字位对得上——真语料（270 万字）既在仓外也不该被测试依赖。
REF_TEXT = "文華殿大學士臣紀昀等奉敕撰欽定四庫全書總目卷一經部易類一"
COLUMN_CHARS = "文華殿大學士臣紀昀等奉敕撰"


def _ctx_with_corpus(tmp_path, monkeypatch, *, chars: str = COLUMN_CHARS,
                     corpus_text: str = REF_TEXT * 30, corpus_name: str = "ref.txt"):
    """摆好「一列库 same 档字位 + 一份小整理本」，返回 (ctx, 语料路径)。"""
    corpus = tmp_path / corpus_name
    corpus.write_text(corpus_text, encoding="utf-8")
    ctx = make_ctx(tmp_path, make_book(BOOK), monkeypatch=monkeypatch)
    ctx.params["align_ref"] = AlignRefParams(corpus=str(corpus))
    recs = [dict(slot=i + 1, verdict="same", char=ch, cov=0.999, matched_id=f"g{i}")
            for i, ch in enumerate(chars)]
    write_product(ctx, "glyph_match", PAGE,
                  glyph_match=page_match(PAGE, BOOK, recs=recs, col=COL))
    return ctx, corpus


def test_gold_derivation_matches_between_cached_and_live_recompute(tmp_path,
                                                                   monkeypatch, ws):
    """核心保证：读 `align_ref` 缓存 与 不经缓存现算一遍，`GoldChar` 必须逐条相同。

    `gold.v2_align.align_page` 两条路都会走到（默认语料走缓存，脚本传
    自定义语料走现算兜底，见该模块 `_aligned_chars` 的模块头），这条钉住
    两条路径算法完全一致，不是"看着都能跑"那种巧合。

    2026-09-20 改：原先要工作区的 vol01/24 产物 ＋ 8.2 MB 真语料，两样缺一
    就 skip，**而且本机跑的时候还踩过一次 fixture 抄错文件名**（复制的是另
    一部参考本，于是"现算"那一侧实际换了语料，op_run 从 63 变 139 —— 那不是
    算法分叉，是测试自己给错了输入）。现在两侧用的是**同一份内容、只是落盘到
    两个路径**的自备小语料，这才是这条真正要测的东西：语料给的信息完全一致时
    必须逐条相同（包括 op_run）。
    """
    from helpers import page_decision
    from guji_manager.gold.v2_align import align_book

    ctx, corpus = _ctx_with_corpus(tmp_path, monkeypatch)
    ar = STEPS["align_ref"].run_page(ctx, PAGE)["align_ref"]
    assert ar.anchored, f"锚不上：{ar.note}"
    ctx.store.write(BOOK, "align_ref", f"p{PAGE:04d}", {"align_ref": ar})
    # `align_page` 的载体是**定字产物**（金标要挂在已定的字位上），对齐结果
    # 只是给它配字，所以这里也得把 Step6 的产物摆上。
    write_product(ctx, "context_decide", PAGE, context_decision=page_decision(
        PAGE, BOOK, col=COL, recs=[
            dict(slot=i + 1, char=ch, margin=1.0, source="db_same")
            for i, ch in enumerate(COLUMN_CHARS)]))

    cached = align_book(BOOK, [PAGE], ctx.store, corpus_path=corpus)
    # 内容相同、路径不同的副本：指纹（按路径 mtime/size 算）必然对不上缓存的
    # corpus_fingerprint，于是强制走现算兜底路径。
    copy = tmp_path / "corpus_copy.txt"
    copy.write_text(corpus.read_text(encoding="utf-8"), encoding="utf-8")
    live = align_book(BOOK, [PAGE], ctx.store, corpus_path=copy)

    assert cached[0].anchored and live[0].anchored
    assert [asdict(c) for c in cached[0].chars] == [asdict(c) for c in live[0].chars]


# ── 多证人合并（2026-09-27，任务书 D-多证人对齐策略） ─────────────────────


def _write_corpus(ws_root, name: str, text: str) -> None:
    (Path(ws_root) / "corpus" / name).write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# uncontested_relax（任务卡 D-align_ref锚定召回-全唐文，2026-09-27）：
# v006 全书实测发现「最高票簇 1-4 票」失败页里绝大多数没有竞争簇（
# `avg_hits_per_hit_gram`≈1、`n_clusters`==1），是刻本侧连续 8 字全对太难，
# 不是套语碰撞——见 `AlignRefParams.uncontested_relax` 模块头。这里用可控的
# 合成语料复现三种情形：唯一无竞争低票页（该收）、有竞争簇的低票页（不该
# 收）、命中率不够的低票页（不该收）。
# ---------------------------------------------------------------------------

# 目标串本身不含重复子串，嵌进「甲乙丙丁…」这类互不相干的填充文字里，
# 保证除嵌入处外语料里不会有第二处巧合命中。
_UR_TARGET = "文華殿大學士臣紀昀等奉敕撰經進四庫全書總目提要恭呈御覽伏候聖裁謹奏"
_UR_FILLER_A = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥零壹貳參肆伍陸柒捌玖拾"
_UR_FILLER_B = "東西南北中上下前後左右春夏秋冬金木水火土日月星辰風雲雷電山川湖海"


def _ur_corpus_text(*, duplicate: bool = False) -> str:
    if duplicate:
        # 语料里把目标串重复一遍——真「套语碰撞」的最小复现：两处命中票数
        # 相当，谁都不占绝对优势。
        return _UR_FILLER_A * 3 + _UR_TARGET + _UR_FILLER_B * 3 + _UR_TARGET + _UR_FILLER_A * 3
    return _UR_FILLER_A * 3 + _UR_TARGET + _UR_FILLER_B * 3


def _ur_hyp(error_positions: tuple[int, ...] = (5, 15, 25)) -> str:
    """把 `_UR_TARGET` 在给定位置换成形近字混淆的近似——用来控制「留下几个
    干净的 8-gram」。默认三个位置量出来正好留 4 个干净窗口（< 绝对下限 5），
    且只在真实位置命中、没有竞争簇（见模块头「uncontested_relax」一节的
    prototype 实测）。"""
    chars = list(_UR_TARGET)
    for pos in error_positions:
        chars[pos] = "錯"
    return "".join(chars)


