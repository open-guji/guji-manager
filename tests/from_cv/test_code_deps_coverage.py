# -*- coding: utf-8 -*-
"""Step 指纹覆盖守卫：Step 模块 import 的本仓模块要么在 `code_deps` 里，要么在下面登记了为什么不进。

`core/engine.py::code_hash` 只哈希 Step 自己的模块与 `spec.code_deps` 里**手列**的模块，不顺着 import 走。
Step 模块 import 了一个算法模块却没列进 `code_deps`，那个模块改了算法，各册产物照报「新鲜」、不重算——
指纹漏判，比多判过期更难发现（10-23 A20 普查时存量 11 个 Step 共 39 处）。

本测试只看 Step 模块自己的 import（含函数里的惰性 import），不看 `code_deps` 模块再往下 import 的东西。
新加的 import 必须二选一：
- 影响产物 → 列进 `code_deps`（本步 `code_hash` 随之变，各册这一步判过期，按 L 级写进 PR）；
- 不影响产物（只读路径、算库指纹、读图）→ 登进 `NOT_IN_FP`，写一句理由。

`EXISTING_GAPS` 是存量：多半影响产物，但现在补进 `code_deps` 会让那一步各册整体过期。
约定**搭车补**：哪一步下次本来就要改算法（`code_hash` 本来就要变）时，顺手把它的存量补进 `code_deps`
并从这里删掉，不额外多一次全量重跑。表只许减不许加。
"""
from __future__ import annotations

import ast
import importlib
import importlib.util
import inspect
from pathlib import Path

import open_guji_cv.steps  # noqa: F401  —— 注册全部 Step
from open_guji_cv.core.step import STEPS
from cv_paths import KEBEN, keben  # noqa: E402,F401  刻本缺省实现（新旧 cv 两种包名）

#: 框架层，进指纹的是 Step 本身对它们的用法，不单列
_FRAMEWORK = ("open_guji_cv.core", "open_guji_cv.products", "guji_manager.formats", "open_guji_cv.errors")

#: 不影响产物、不进指纹的 import：(Step 模块, 被 import 模块) → 理由
NOT_IN_FP: dict[tuple[str, str], str] = {
    ("open_guji_cv.gates.row_segment_gate", "open_guji_cv.impl.keben.row_boundaries"):
        "只取 row_split_extra 读 cells 列旗 jiazhu_row_split+N（cv 45d548e5，GUJI-774 书级钩子 jiazhu_step.row_split，缺省 None 不出旗）；"
        "旗由 row_segment 写进 cells，row_boundaries 已在 row_segment 指纹里，逻辑一变 cells 跟变、本闸按输入过期。"
        "补进本闸 code_deps 会让各册 row_segment_gate 整体过期（A31 11-19）",
    ("open_guji_cv.steps.seal_detect", "open_guji_cv.utils.image_io"): "只读图",
    ("open_guji_cv.gates.border_detect_gate", "open_guji_cv.utils.image_io"):
        "只读图：no_frame_skip 开且册配 ink（墨层书 raw 是二值图）时另读原图灰度判纯色页（cv#1821，缺省关，参数缺省不进 dump）；"
        "判纯色的阈值与 _no_frame 在本闸模块里，已进指纹",
    ("open_guji_cv.steps.seed_admit", "open_guji_cv.utils.image_io"): "只读图",
    ("open_guji_cv.steps.seed_admit", "open_guji_cv.clustering.keben_counts"):
        "只在 solo_5b_cov 开时读刻例数（cv#1278，缺省关；参数进指纹，缺省不进 dump，故关时产物逐字节不变，code_equiv 已证）；"
        "册开 solo_5b 之前要把本模块并入该册指纹（随 solo_5b 启用的 PR 补）",
    ("open_guji_cv.steps.glyph_match", "open_guji_cv.clustering.sim_cnn"):
        "只在 sim_model 开时换精验（cv#1394，缺省 None＝关，参数缺省不进 dump，故关时产物逐字节不变，code_equiv 已证）；"
        "开着时权重 sha256＋sim_cnn 代码哈希经 sim_model_sha 进参数指纹，改 sim_cnn 照样判过期",
    ("open_guji_cv.steps.glyph_match", "open_guji_cv.steps.glyph_stages"):
        "只在 stages 开时跑库匹配之后的分段判定（cv#1589，缺省 None＝关，参数缺省不进 dump，故关时产物逐字节不变，code_equiv 已证）；"
        "开着时 glyph_stages、near_route、shape_stage、groups.methods、ids_online、registry 的代码哈希＋形近字组表＋终判组模板库"
        "经 stages_sha 进参数指纹，改这些模块照样判过期",
    ("open_guji_cv.steps.seed_admit", "open_guji_cv.groups.stroke_veto"):
        "只在 stroke_veto 开时跑笔画反向护栏（cv#1487，缺省空串＝关，参数缺省不进 dump，故关时产物逐字节不变，code_equiv 已证）；"
        "册开 stroke_veto 之前要把本模块并入该册指纹（随启用的 PR 补）",
    ("open_guji_cv.steps.seed_admit", "open_guji_cv.groups.wu_shape"):
        "只在 group_flow_wu_shape 开时跑嗚鳴刻形判法（cv#1509，缺省空串＝关，旧指纹不变）；开着时模型文件 sha256 经 \"ws\" 段进参数指纹。"
        "但 wu_shape 模块代码本身不进指纹（同类 rr_shape 在 code_deps 里）——开它的书（全唐文）改了这个模块要手动判过期，"
        "或随下次本来就要变 seed_admit code_hash 的 PR 把它补进 code_deps（A31 11-14 登记，已告知 A20）",
    ("open_guji_cv.steps.seed_admit", "open_guji_cv.groups.part_shape"):
        "只在 group_flow_part_shape 开时跑部件刻形判法（cv#1553，缺省空＝关，旧指纹不变）；开着时模型文件经 \"pt\" 段进参数指纹。"
        "模块代码本身不进指纹（同 wu_shape）——开它的书改了这个模块要手动判过期，或随下次本来就要变 seed_admit code_hash 的 PR 补进 code_deps（A31 11-15 登记）",
    ("open_guji_cv.steps.invert_detect", "open_guji_cv.utils.preclean"): "只解析预处理后的原图路径",
    ("open_guji_cv.steps.border_detect", "open_guji_cv.feedback.lookup"):
        "只读人裁逐列抬头（head-raise-columns）；裁决不进指纹、靠该页显式重跑生效，同 row_segment 读 manual-cells（#706）",
    ("open_guji_cv.gates.cut_gate", "open_guji_cv.gates.column_gate"):
        "只借 COLUMN_GATE_SPEC 的闸层次描述（GateSpec.levels），判据代码在 cut_gate 自己（cv #1872）",
    ("open_guji_cv.gates.cut_gate", "open_guji_cv.steps.column_geometry"):
        "只借拒收原因名常量 TABLE_COLUMN_REJECT；几何量经 column_geometry 产物读入，产物 sha 进上游指纹",
    ("open_guji_cv.steps.row_segment", "open_guji_cv.steps.context_decide"):
        "只借 corpus_fingerprint 算整理本文件指纹（roster_ref_fingerprint 进参数指纹），不影响切分",
}

#: 存量缺口（2026-10-23 普查）：搭车补，只减不加。
EXISTING_GAPS: dict[str, set[str]] = {
    "open_guji_cv.gates.column_gate": {
        f"{KEBEN}.jiazhu_split",
    },
    "open_guji_cv.steps.align_ref": {
        "open_guji_cv.clustering.align_eval",
        "open_guji_cv.steps.context_decide",
        "open_guji_cv.utils.cjk_compat",
        "open_guji_cv.variants",
    },
    "open_guji_cv.steps.cell_shrink": {
        "open_guji_cv.steps._warpmap",
        "open_guji_cv.steps.seed_admit",
    },
    "open_guji_cv.steps.column_crop": {
        "open_guji_cv.steps.column_warp",
    },
    "open_guji_cv.steps.context_decide": {
        "open_guji_cv.clustering.llm_context",
        "open_guji_cv.clustering.seeding",
        "open_guji_cv.clustering.variants",
        "open_guji_cv.steps.align_ref",
    },
    "open_guji_cv.steps.glyph_match": {
        "open_guji_cv.clustering.glyph_db",
        "open_guji_cv.clustering.near_shape",
        "open_guji_cv.clustering.seeding",
    },
    "open_guji_cv.steps.rare_candidates": {
        "open_guji_cv.clustering.glyph_fp",
        "open_guji_cv.steps.align_ref",
    },
    "open_guji_cv.steps.row_segment": {
        "open_guji_cv.feedback.lookup",
        "open_guji_cv.steps._warpmap",
        "open_guji_cv.steps.glyph_match",
    },
    "open_guji_cv.steps.row_segment_runs": {
        "open_guji_cv.steps._warpmap",
    },
    "open_guji_cv.steps.seed_admit": {
        "open_guji_cv.clustering.confusable",
        "open_guji_cv.clustering.exclusions",
        "open_guji_cv.clustering.glyph_db",
        "open_guji_cv.clustering.glyph_fp",
        "open_guji_cv.clustering.normalize",
        "open_guji_cv.feedback.mojibake",
        "open_guji_cv.hanzi.symbols",
        "open_guji_cv.shadow.gate",
        "open_guji_cv.shadow.model",
        "open_guji_cv.shadow.signals",
        "open_guji_cv.steps.align_ref",
        "open_guji_cv.utils.ji_yi_si",
    },
}


# cv #1911（11-26，CV4）把 seed_admit 拆出 seed_admit_common／lanes／shapes（纯搬家，指纹不变），stroke_veto／wu_shape
# 等的 import 随各遍搬进这些 helper。本测试只扫 Step 模块自己，不扫 helper，新 cv 上这几条登记就看不到了；理由照旧
# （开这些开关前要把对应模块并入该册指纹）。旧 cv（patch 线）上仍在 seed_admit 里，保留。
_SA_HELPERS = ("open_guji_cv.steps.seed_admit_common", "open_guji_cv.steps.seed_admit_lanes",
               "open_guji_cv.steps.seed_admit_shapes")

def _imports(mod_name: str) -> set[str]:
    mod = importlib.import_module(mod_name)
    path = Path(inspect.getsourcefile(mod))
    pkg = mod_name if path.name == "__init__.py" else mod_name.rpartition(".")[0]
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names if a.name.startswith("open_guji_cv")}
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = pkg.split(".")
                base = ".".join(parts[:len(parts) - node.level + 1] + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            if not base.startswith("open_guji_cv"):
                continue
            for a in node.names:                 # `from ..steps import align_ref` 这种拿的是子模块
                sub = f"{base}.{a.name}"
                out.add(sub if _is_pkg(base) and importlib.util.find_spec(sub) else base)
    return {m for m in out if m != mod_name and not m.startswith(_FRAMEWORK) and m != "open_guji_cv"}


def _is_pkg(name: str) -> bool:
    try:
        spec = importlib.util.find_spec(name)
    except ModuleNotFoundError:
        return False
    return bool(spec and spec.submodule_search_locations)


def _gaps() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for st in STEPS.values():
        m = type(st).__module__
        if not m.startswith("open_guji_cv."):    # 别的测试往 STEPS 里注册的假 Step（全量跑时才在）
            continue
        miss = {i for i in _imports(m) - set(st.spec.code_deps) if (m, i) not in NOT_IN_FP}
        if miss:
            out.setdefault(m, set()).update(miss)
    return out


def test_step_imports_are_fingerprinted_or_explained():
    new = {m: sorted(miss - EXISTING_GAPS.get(m, set())) for m, miss in _gaps().items()}
    new = {m: v for m, v in new.items() if v}
    assert not new, ("这些 Step import 的模块既不在 code_deps 也没登记理由（改了它产物照报新鲜）：\n"
                     + "\n".join(f"  {m}: {v}" for m, v in sorted(new.items())))


def test_existing_gaps_only_shrink():
    """补进 code_deps 或删了 import 之后，把对应条目从 EXISTING_GAPS 删掉，免得表里留死条目。"""
    cur = _gaps()
    stale = {m: sorted(v - cur.get(m, set())) for m, v in EXISTING_GAPS.items()}
    stale = {m: v for m, v in stale.items() if v}
    assert not stale, f"EXISTING_GAPS 里这些已经不缺了，删掉：{stale}"


def _moved_to_helper(m: str, i: str) -> bool:
    """seed_admit 的登记条目：新 cv 上这个 import 搬进了 helper 模块（cv #1911）。"""
    if m != "open_guji_cv.steps.seed_admit":
        return False
    return any(importlib.util.find_spec(h) and i in _imports(h) for h in _SA_HELPERS)


def test_not_in_fp_entries_are_live():
    for (m, i), why in NOT_IN_FP.items():
        assert why.strip()
        if i not in _imports(m) and _moved_to_helper(m, i):
            continue
        assert i in _imports(m), f"{m} 已不 import {i}，删掉这条 NOT_IN_FP"
