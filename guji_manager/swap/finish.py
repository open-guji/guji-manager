"""R8：C 类重切批（swap book-text 落的格号变动）合并后的收尾。``guji swap finish-merged``。

* 对照表随文本提交入库：``<版本目录>/lineage/revisions/<册>-<run>.tsv``（``store_table``，由 ``booktext.do_book`` 在提交前放进去）。
  它同时就是**旧格号 redirect 登记**：旧格→新格（同格／改号／删），``redirect_map`` 沿历次对照表把任一旧格号走到现行格号
  （删了的得 None）。网站链接、意见池里的旧格号按它迁。
* 无锚人裁（ZM 11-10）：人裁事件按旧格号挂，格号变了的格上（改号／删／对照表里没有），cv 出包按锚框 IoU 重绑，
  iou=0 的 backfill 旧人裁会错位还被优先采信。``unanchored_human`` 把这些格列出来，写成 ``republish --recheck`` 清单
  （格号<TAB>说明<TAB>旧人裁 id<TAB>旧人裁的字），进下一张单让用户重投覆盖。删掉的格没有新格号，只在报告里列。
* 度量：``reports/_swap/metrics.jsonl`` 追加一行。
* 网站已投未落的票要在换包**之前**落库（``guji cellvotes``）；本命令不替做，只在报告里提醒。
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

REV_DIR = "lineage/revisions"


def store_table(vdir: Path, tsv: Path, book: str, run: str) -> Path:
    """对照表放进 ``<版本目录>/lineage/revisions/``（随文本提交走）。返回目标路径。"""
    dst = Path(vdir) / REV_DIR / f"{book}-{run}.tsv"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(Path(tsv).read_text(encoding="utf-8"), encoding="utf-8")
    return dst


def read_table(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def redirect_map(tables: list[list[dict]]) -> dict[str, str | None]:
    """按时间顺序的几张对照表（旧版→新版）串成 {最早的旧格: 现行格号／None（已删）}。格号带册前缀。"""
    cur: dict[str, str | None] = {}
    for rows in tables:
        step = {r["旧格"]: (r["新格"] or None) for r in rows if r.get("旧格") and r.get("类别") in ("同格", "改号", "删")}
        for k, v in list(cur.items()):
            if v is not None and v in step:
                cur[k] = step[v]
        for o, n in step.items():
            if o not in cur and not any(v == o for v in cur.values()):
                cur[o] = n
    return {k: v for k, v in cur.items() if v != k}


def unanchored_human(rows: list[dict], human: dict[str, str], vol: int) -> tuple[list[str], list[tuple]]:
    """human：{旧格号（不带册前缀）: 人裁字}。返回 (recheck 清单行, 被删格上的人裁 [(旧格, 字)])。
    改号格上的人裁→按新格号进 recheck；对照表里没有的人裁格（切分已大改）也进报告（无新格号，不能上单）。"""
    pre = f"vol{vol:02d}:"
    by_old = {r["old"]: r for r in rows if r["old"]}
    lines, gone = [], []
    for old, ch in sorted(human.items()):
        r = by_old.get(old)
        if r is None or r["kind"] == "删":
            gone.append((old, ch))
        elif r["kind"] == "改号" and r["new"]:
            lines.append(f"{pre}{r['new']}\t格号变动：人裁挂在旧格 {old}（{ch}），换包后改号，请照书影重核\t\t{ch}")
    return lines, gone


def finish(ws: Path, book: str, rows: list[dict], human: dict[str, str] | None, *, run: str, commit: str = "") -> dict:
    """写 recheck 清单、metrics，返回报告。rows 是 ``cell_table`` 的行。"""
    vol = int(book[3:])
    out = Path(ws) / "reports" / "_swap" / "finish" / book
    out.mkdir(parents=True, exist_ok=True)
    rep: dict = {"book": book, "run": run}
    if human is None:
        rep["human"] = "取不到人裁事件（没装 cv 或没有事件目录），未列无锚人裁"
        lines, gone = [], []
    else:
        lines, gone = unanchored_human(rows, human, vol)
        (out / "recheck_unanchored.tsv").write_text("".join(x + "\n" for x in lines), encoding="utf-8")
        rep["recheck"] = {"file": str(out / "recheck_unanchored.tsv"), "n": len(lines)}
        rep["human_on_deleted"] = gone
    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    m = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "book": book, "run": run, "commit": commit,
         "table": kinds, "recheck_human": len(lines), "human_on_deleted": len(gone)}
    mp = Path(ws) / "reports" / "_swap" / "metrics.jsonl"
    mp.parent.mkdir(parents=True, exist_ok=True)
    with open(mp, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(m, ensure_ascii=False) + "\n")
    rep["metrics"] = m
    rep["reminder"] = "下一张单：republish prep|issue --recheck <recheck_unanchored.tsv>；网站已投未落的票须在换包前 guji cellvotes 落库"
    return rep
