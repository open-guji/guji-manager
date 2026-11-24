"""AI 文意裁定命中核对（11-20 痛点 K1）。"""
import json
from types import SimpleNamespace as NS

from guji_manager import ruling_hits as RH
from guji_manager._cv import RulingStore
from open_guji_cv.feedback.llm_queue import PENDING


def _page(root, cells):
    d = root / "001" / "seed_admit"
    d.mkdir(parents=True, exist_ok=True)
    (d / "p0001.json").write_text(json.dumps({"seed_admit": {"columns": [{"chars": cells}]}}, ensure_ascii=False), encoding="utf-8")


def test_miss_detected_and_rekeyed(tmp_path):
    store = RulingStore(tmp_path / "fb")
    store._batch = "llm-session-x"
    store.put("ry", "v1", "甲乙丙", "丁戊", char="曰", conf="high", why="文意", model="session", cell="001:1:1:3")
    store.put("ry", "v1", "子丑", "寅卯", char="日", conf="high", why="", model="session", cell="001:1:1:4")
    ask = lambda l, r: {"evidence": {"group": {"id": "ry", "solvers": [{"why": PENDING, "ask": {"ver": "v1", "l": l, "r": r}}]}}}
    _page(tmp_path / "p", [{"id": "001:1:1:3", "char": "日", **ask("甲乙□", "丁戊")},    # 窗口变了 → 未命中
                           {"id": "001:1:1:4", "char": "日", **ask("子丑", "寅卯")},      # 命中（没人会再问，但即使挂着也不算）
                           {"id": "001:1:1:5", "char": "日", **ask("辰", "巳")}])          # 没裁定 → 不列
    rows = RH.check(tmp_path / "p", "001", store)
    assert [r["cell"] for r in rows] == ["001:1:1:3"] and rows[0]["原因"] == "窗口变了" and rows[0]["裁定字"] == "曰"
    store2 = RulingStore(tmp_path / "fb")
    store2._batch = "llm-rekey"
    assert RH.rekey(rows, store2) == 1
    assert RH.check(tmp_path / "p", "001", RulingStore(tmp_path / "fb")) == []


def test_prompt_version_change_not_rekeyed(tmp_path):
    store = RulingStore(tmp_path / "fb")
    store.put("ry", "v1", "甲", "乙", char="曰", conf="high", why="", model="m", cell="001:1:1:1")
    _page(tmp_path / "p", [{"id": "001:1:1:1", "char": "日",
                            "evidence": {"group": {"id": "ry", "solvers": [{"why": PENDING, "ask": {"ver": "v2", "l": "甲", "r": "乙"}}]}}}])
    rows = RH.check(tmp_path / "p", "001", store)
    assert len(rows) == 1 and "提示词版本" in rows[0]["原因"]
    assert RH.rekey(rows, store) == 0


def test_command_registered():
    from guji_manager.commands import COMMANDS
    assert "rulings-hits" in COMMANDS


def test_vis_ruling_still_pending(tmp_path):
    from guji_manager._cv import RulingLog
    from open_guji_cv.feedback.events import EventTarget, make_event
    log = RulingLog(tmp_path / "fb")
    pay = {"source": "llm", "group": "O", "prompt_ver": "ctx-m1", "char": "曰", "conf": "high", "admit_ok": True,
           "cell": "001:1:1:3", "ref": "日", "ctx": {"left": "", "right": "", "hash": "x"}}
    log.append([make_event("vis-b", 1, "ctx_ruling", EventTarget(step="seed_admit", unit="cell", key="001:1:1:3", book="001"),
                           pay, actor="model")])
    _page(tmp_path / "p", [{"id": "001:1:1:3", "char": "日", "admit": False}, {"id": "001:1:1:4", "char": "日", "admit": True}])
    d = tmp_path / "p" / "001" / "align_ref"
    d.mkdir(parents=True)
    (d / "p0001.json").write_text(json.dumps({"align_ref": {"chars": [{"id": "001:1:1:3", "align_char": "曰"}]}}), encoding="utf-8")
    rows = RH.check_vis(tmp_path / "p", "001", RulingStore(tmp_path / "fb"))
    assert len(rows) == 1 and "整理本对位字变了" in rows[0]["原因"]
    assert RH.rekey(rows, RulingStore(tmp_path / "fb")) == 0


def _vis_event(log, i, cell, char, ref, sub, left, right):
    from open_guji_cv.feedback.events import EventTarget, make_event
    from guji_manager._cv import ruling_ctx_hash
    pay = {"source": "llm", "group": "O", "prompt_ver": "ctx-m1", "char": char, "conf": "high", "admit_ok": True,
           "cell": cell, "ref": ref, "subclass": sub, "ctx": {"left": left, "right": right, "hash": ruling_ctx_hash(left, right)}}
    log.append([make_event("vis-b", i, "ctx_ruling", EventTarget(step="seed_admit", unit="cell", key=cell, book="001"),
                           pay, actor="model")])


def test_vis_reasons_and_rekey(tmp_path):
    """终审裁定没放行的原因逐格分开（11-20 ZM 殿本 29 格）；只是窗口变了的能补键。"""
    from guji_manager._cv import RulingLog
    log = RulingLog(tmp_path / "fb")
    _vis_event(log, 1, "001:1:1:2", "曰", "曰", "N", "甲", "丙丁")       # 窗口变了（邻格 1 现放行成 乙）
    _vis_event(log, 2, "001:1:1:3", "丙", "丙", "P", "甲乙曰", "丁")     # 子类 P 不收（缺省）
    _vis_event(log, 3, "001:1:1:4", "大", "丁", "Z", "乙曰丙", "")     # 越过整理本
    ch = lambda i, c, adm: {"id": f"001:1:1:{i}", "slot": i, "char": c, "admit": adm}  # noqa: E731
    d = tmp_path / "p" / "001"
    (d / "seed_admit").mkdir(parents=True)
    (d / "seed_admit" / "p0001.json").write_text(json.dumps({"seed_admit": {"page": 1, "columns": [
        {"col": 1, "chars": [ch(1, "乙", True), ch(2, "日", False), ch(3, "两", False), ch(4, "犬", False)]}]}},
        ensure_ascii=False), encoding="utf-8")
    (d / "align_ref").mkdir()
    (d / "align_ref" / "p0001.json").write_text(json.dumps({"align_ref": {"chars": [
        {"id": "001:1:1:1", "align_char": "甲"}, {"id": "001:1:1:2", "align_char": "曰"},
        {"id": "001:1:1:3", "align_char": "丙"}, {"id": "001:1:1:4", "align_char": "丁"}]}}, ensure_ascii=False), encoding="utf-8")
    rows = {r["cell"]: r for r in RH.check_vis(tmp_path / "p", "001", RulingStore(tmp_path / "fb"))}
    assert rows["001:1:1:2"]["原因"].startswith("窗口变了") and rows["001:1:1:2"]["_vis"]
    assert "子类 P 不收" in rows["001:1:1:3"]["原因"]
    rows2 = {r["cell"]: r for r in RH.check_vis(tmp_path / "p", "001", RulingStore(tmp_path / "fb"), RH.VIS_SUBS | {"P"})}
    assert "子类" not in rows2["001:1:1:3"]["原因"]
    assert "越过整理本" in rows["001:1:1:4"]["原因"] and "没给 --override-groups" in rows["001:1:1:4"]["原因"]
    o = {r["cell"]: r for r in RH.check_vis(tmp_path / "p", "001", RulingStore(tmp_path / "fb"), override=("mb",))}
    assert "不同属白名单" in o["001:1:1:4"]["原因"]          # 大／丁 不在 mb
    from guji_manager._cv import FLOW_GROUPS
    assert {"本", "木"} <= set(FLOW_GROUPS["mb"].members)     # 殿本 vol31:65:9:8 木→本：mb 有两字，白名单不挡
    assert RH.rekey_vis(list(rows.values()), "vis-rekey", tmp_path / "fb") == 1
    again = {r["cell"]: r for r in RH.check_vis(tmp_path / "p", "001", RulingStore(tmp_path / "fb"))}
    assert not again["001:1:1:2"]["原因"].startswith("窗口变了")


def _one_page(tmp_path, anchored=None):
    ch = lambda i, c, adm: {"id": f"001:1:1:{i}", "slot": i, "char": c, "admit": adm}  # noqa: E731
    d = tmp_path / "p" / "001"
    (d / "seed_admit").mkdir(parents=True)
    (d / "seed_admit" / "p0001.json").write_text(json.dumps({"seed_admit": {"page": 1, "columns": [
        {"col": 1, "chars": [ch(1, "甲", True), ch(2, "日", False), ch(3, "丙", True)]}]}}, ensure_ascii=False), encoding="utf-8")
    (d / "align_ref").mkdir()
    ar = {"chars": [{"id": "001:1:1:2", "align_char": "曰"}]}
    if anchored is not None:
        ar["anchored"] = anchored
    (d / "align_ref" / "p0001.json").write_text(json.dumps({"align_ref": ar}, ensure_ascii=False), encoding="utf-8")


def test_vis_fallback_reasons(tmp_path):
    """QTW 11-20：窗口同、条件都满足的兜底不再断言「产物早于裁定」；裁定库按键取到的不是这条、页没锚定都单列。"""
    from guji_manager._cv import RulingLog
    log = RulingLog(tmp_path / "fb")
    _vis_event(log, 1, "001:1:1:2", "曰", "曰", "N", "甲", "丙")
    _one_page(tmp_path)
    row = RH.check_vis(tmp_path / "p", "001", RulingStore(tmp_path / "fb"))[0]
    assert "多半是产物早于" not in row["原因"] and "codepoint_semantic" in row["原因"] and "裁定写于" in row["原因"]
    _vis_event(log, 2, "001:9:9:9", "日", "曰", "N", "甲", "丙")    # 同窗口、别的格、更晚 → 盖过
    row = RH.check_vis(tmp_path / "p", "001", RulingStore(tmp_path / "fb"))[0]
    assert "更晚的一条裁定盖过" in row["原因"]


def test_vis_unanchored_and_no_hash(tmp_path):
    from guji_manager._cv import RulingLog
    from open_guji_cv.feedback.events import EventTarget, make_event
    log = RulingLog(tmp_path / "fb")
    _vis_event(log, 1, "001:1:1:2", "曰", "曰", "N", "甲", "丙")
    _one_page(tmp_path, anchored=False)
    row = RH.check_vis(tmp_path / "p", "001", RulingStore(tmp_path / "fb"))[0]
    assert "没锚定" in row["原因"]
    log2 = RulingLog(tmp_path / "fb2")
    pay = {"source": "llm", "group": "O", "prompt_ver": "ctx-m1", "char": "曰", "conf": "high", "admit_ok": True,
           "cell": "001:1:1:2", "ref": "曰", "subclass": "N", "ctx": {"left": "甲", "right": "丙"}}
    log2.append([make_event("vis-c", 1, "ctx_ruling", EventTarget(step="seed_admit", unit="cell", key="001:1:1:2", book="001"),
                            pay, actor="model")])
    q = tmp_path / "q"
    q.mkdir()
    import shutil
    shutil.copytree(tmp_path / "p", q / "p")
    (q / "p" / "001" / "align_ref" / "p0001.json").write_text(json.dumps({"align_ref": {"anchored": True, "chars": [
        {"id": "001:1:1:2", "align_char": "曰"}]}}, ensure_ascii=False), encoding="utf-8")
    row = RH.check_vis(q / "p", "001", RulingStore(tmp_path / "fb2"))[0]
    assert "没写 ctx.hash" in row["原因"] and row["_vis"]


def test_accept_old_ver_rekey(tmp_path):
    """旧版本裁定换键两档（11-24 用户定）：只差模型后缀直接换；真换版要 high 单字、窗口同、字在新候选里。"""
    store = RulingStore(tmp_path / "fb")
    store.put("ry", "v1#m:high", "甲", "乙", char="曰", conf="high", why="", model="m", cell="001:1:1:1")   # 只差后缀 → 收（即使不是机器字）
    store.put("ry", "v1", "丙", "丁", char="日", conf="high", why="", model="m", cell="001:1:1:2")          # 换版、字在候选 → 收
    store.put("ry", "v1", "戊", "己", char="巳", conf="low", why="", model="m", cell="001:1:1:3")           # 非 high → 不收
    store.put("ry", "v1", "庚", "辛", char="己", conf="high", why="", model="m", cell="001:1:1:4")          # 窗口也变 → 不收
    store.put("ry", "v1", "壬", "癸", char="午", conf="high", why="", model="m", cell="001:1:1:5")          # 换版、字不在候选 → 不收
    ask = lambda l, r, ver="v2": {"evidence": {"group": {"id": "ry", "solvers": [
        {"why": PENDING, "ask": {"ver": ver, "l": l, "r": r}, "probs": {"日": 0.6, "已": 0.4}}]}}}
    _page(tmp_path / "p", [{"id": "001:1:1:1", "char": "已", **ask("甲", "乙", "v1")},
                           {"id": "001:1:1:2", "char": "已", **ask("丙", "丁")},
                           {"id": "001:1:1:3", "char": "巳", **ask("戊", "己")},
                           {"id": "001:1:1:4", "char": "己", **ask("庚x", "辛")},
                           {"id": "001:1:1:5", "char": "未", **ask("壬", "癸")}])
    rows = RH.check(tmp_path / "p", "001", store)
    assert len(rows) == 5
    assert RH.rekey(rows, store) == 0                                  # 缺省不收旧版本
    assert RH.rekey(rows, store, accept_old_ver=True) == 2             # 只收 1、2 两格
    assert store.get("ry", "v2", "丙", "丁")["char"] == "日"
    assert store.get("ry", "v2", "壬", "癸") is None


def test_check_uses_get_equiv_when_available(tmp_path):
    """cv 带版本等价表（get_equiv）时，等价命中的裁定不算「未命中」（11-24，不另写等价逻辑）。"""
    store = RulingStore(tmp_path / "fb")
    store.put("ry", "v1", "甲", "乙", char="曰", conf="high", why="", model="m", cell="001:1:1:1")
    ask = {"evidence": {"group": {"id": "ry", "solvers": [{"why": PENDING, "ask": {"ver": "v2", "l": "甲", "r": "乙"}}]}}}
    _page(tmp_path / "p", [{"id": "001:1:1:1", "char": "日", **ask}])
    assert len(RH.check(tmp_path / "p", "001", store)) == 1                       # 精确键没中 → 未命中
    store.get_equiv = lambda g, v, l, r: store.get(g, "v1", l, r)                 # 模拟登记了 v1→v2
    assert RH.check(tmp_path / "p", "001", store) == []
