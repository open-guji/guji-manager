"""意见采纳写裁定事件（GM4 11-26，待审与裁定整理方案第 6 步；形状经 CV0 审）。

revise 真写 book-text（非 dry-run、带 PR）后，对每个改了字／新增的格写一条 ``confirm`` 事件，
这样「读者意见被采纳」和别的人裁一样进事件流、进 ``events.u/level``，以后能当钉读。

- 事件：kind=confirm，target{step:seed_admit, unit:cell, key:册:页:列:格, anchor}，
  payload{v:confirm, shape:新字, source:opinion, opinion:<意见 id>, text_version, level, no_glyph_lib}。
- level 明写：用户采纳（status=accepted）→ actor=user、level=human；规则自动采纳（auto_accepted）→ actor=model、level=ai。
- 锚直接带全：{u, bbox 现行格框, cells_sha 现行切分戳, 有则 content_sha}；补锚档只兜底。
- B′ 新增格：现行切分的身份账里要有这个 u（对得上 char 的新 u），没有就只留 book-text、不写事件（返回 skipped）。
- no_glyph_lib=True（沿用审查卡「这张图不建库」的老标记，glyphdb_admit 与重建后重放都认）：用户只看文字没看字图，定字照用、不进字形库；写完另把字形库消费者记账兜底。
- batch 名 ``opinion-<册>-<章>-<日期>``，不带「~」（带「~」的批次按口径算人裁）。
"""
from __future__ import annotations
from ..products_io import RULING_STEP

import datetime as dt
from dataclasses import dataclass, field

GLYPH_CONSUMERS = ("glyphdb_admit", "glyphdb_replay")


def batch_name(book: str, vol: str, today: dt.date | None = None) -> str:
    return f"opinion-{book}-{vol}-{(today or dt.date.today()):%Y%m%d}"


def level_of(status: str) -> tuple[str, str] | None:
    """意见状态 → (actor, level)。只认 accepted／auto_accepted（以及已 applied 前一状态由调用方传入）。"""
    if status == "accepted":
        return "user", "human"
    if status == "auto_accepted":
        return "model", "ai"
    return None


def _cell(char: dict, a: str) -> dict | None:
    for pg in char.get("pages") or []:
        for col in pg.get("columns") or []:
            for c in col.get("cells") or []:
                if c.get("a") == a:
                    return c
    return None


def _box(cord: dict, a: str):
    page = int(a.split(":")[0])
    for pg in cord.get("pages") or []:
        if pg.get("page") == page:
            for c in pg.get("cells") or []:
                if c.get("a") == a:
                    return c.get("box"), c
    return None, None


@dataclass
class Built:
    events: list = field(default_factory=list)     # 事件的字典形（batch/kind/actor/target/payload）
    skipped: list = field(default_factory=list)    # [(格号, 原因)]


def build(book: str, vol: str, applied: list, statuses: dict, char: dict, cord: dict, *, text_version: str | None,
          ledger=None, cells_sha_of=None, batch: str | None = None, adopter: str | None = None) -> Built:
    """``applied``＝revise 的 Applied 列表；``statuses``＝意见 id → 状态（派生状态，采纳时的）；
    ``char``／``cord``＝写完之后的现行文件；``ledger``＝uid Ledger（B′ 核账用）；``cells_sha_of(page)``＝现行切分戳；
    ``adopter``＝采纳人账号（写 `payload.by`；不给：accepted 记 `opinion:<意见 id>`，auto_accepted 记规则名 `auto_accept`）。"""
    out = Built()
    batch = batch or batch_name(book, vol)
    sha_cache: dict = {}
    for ap in applied:
        lv = level_of(statuses.get(ap.opinion, ""))
        if lv is None:
            out.skipped.append((ap.opinion, f"意见状态 {statuses.get(ap.opinion)!r} 不是采纳，不写事件"))
            continue
        actor, level = lv
        for c in ap.cells:
            a = c["a"]
            cell = _cell(char, a)
            if cell is None or not isinstance(cell.get("u"), int):
                out.skipped.append((a, "char 里这格没有 u（旧格式），不写事件"))
                continue
            u = int(cell["u"])
            page = int(a.split(":")[0])
            if ap.cls == "B′" and (ledger is None or not ledger.exists or ledger.u_map(page).get(a) != u):
                out.skipped.append((a, "新增格 u 不在现行切分的身份账里，只留 book-text，等账入后再补"))
                continue
            box, ccell = _box(cord, a)
            anchor: dict = {"u": u}
            if box is not None:
                anchor["bbox"] = box
            if cells_sha_of is not None:
                if page not in sha_cache:
                    sha_cache[page] = cells_sha_of(page)
                if sha_cache[page]:
                    anchor["cells_sha"] = sha_cache[page]
            if ccell and ccell.get("content_sha"):
                anchor["content_sha"] = ccell["content_sha"]
            col, slot = a.split(":")[1], a.split(":")[2]
            payload = {"v": "confirm", "shape": cell["c"], "source": "opinion", "opinion": ap.opinion,
                       "text_version": text_version, "level": level, "no_glyph_lib": True,
                       "by": adopter or (f"opinion:{ap.opinion}" if level == "human" else "auto_accept"),
                       "channel": "opinion"}
            out.events.append({
                "batch": batch, "kind": "confirm", "actor": actor,
                "target": {"step": RULING_STEP, "unit": "cell", "key": f"{book}:{a}", "book": book,
                           "page": page, "col": int(col), "slot": int(slot.rstrip("ab")), "anchor": anchor},
                "payload": payload})
    return out


def write(built: Built, log=None) -> int:
    """把 ``Built.events`` 经 cv 的 EventLog 落事件日志；写完把字形库消费者记账兜底。→ 写了几条。"""
    if not built.events:
        return 0
    from .._cv import EventLog, EventTarget, make_event
    from ..u_stamp import stamp_strict
    log = log or EventLog()
    base = log.latest_seq(built.events[0]["batch"])
    evs = []
    for i, d in enumerate(built.events, 1):
        t = dict(d["target"])
        evs.append(make_event(d["batch"], base + i, d["kind"], EventTarget(**t), d["payload"], actor=d["actor"]))
    stamp_strict(evs)      # 锚已带 u；这里只核（册有账写不出 u 整批报错）
    n = log.append(evs)
    for cons in GLYPH_CONSUMERS:
        try:
            log.mark_consumed(cons, evs, note="意见采纳：只看文字未看字图，不入字形库")
        except Exception:  # noqa: BLE001 —— 消费者名在旧 cv 里可能没有；no_glyph_lib 标记是主闸
            pass
    return n
