"""`guji pending`：待审条目（一格一条，设计 doc/00-总览/设计-待审条目化.md）。

    guji pending ls vol04 -w <工作区> [--state open|withdrawn|resolved|closed|all] [--json]
    guji pending show vol04 <条目 id 或格号> -w <工作区>          # 当前版本与全部改动记录
    guji pending withdraw vol04 <条目或格号…> --why "…" -w <工作区>   # 撤下（机器下一轮不会自己放回）
    guji pending restore  vol04 <条目或格号…> --why "…" -w <工作区>   # 放回
    guji pending note vol04 <条目或格号> "说明" -w <工作区>           # 改卡片头说明；空串删掉
    guji pending set  vol04 <条目或格号> --field ctx='{"c":"曰"}' -w <工作区>   # 改卡片字段（JSON 值；null 删）
    guji pending add  vol04 <格号> --note "…" [--recheck] [--src script:xx] -w <工作区>   # 加复审格
    guji pending import vol04 -w <工作区>                         # 从现行整张单导入（可重复执行，只动有变化的）
    guji pending reconcile vol04 --sheet <新出的 pending.json> [--fps <格号→指纹.json>] --src rev:<rev> -w <工作区>
                                                                  # 机器一轮：按新单逐格比，只动有变化的条目
    guji pending export vol04 -w <工作区> [--out <文件>]          # 条目 → 整张 pending.json（缺省写回中心库的那份）

改条目、导出之后跑 `guji db sync -w <工作区>`；加 `--sync` 顺带同步并触发网站 proofing-sync（只发这一章）。
人改条目缺省同时导出整张单（网站照旧按整张单读），`--no-export` 不导。
条目文件在数据目录 `feedback/lists/pending/<书>/<章>.items.jsonl`（只追加），随 `guji db sync` 进中心库。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .review import pending_items as P

WEB_REPO = "open-guji/kaiyuanguji-web"


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("pending", help="待审条目（一格一条）：列、撤下、放回、改说明、加复审、导入、reconcile、导出")
    p.add_argument("action", choices=["ls", "show", "withdraw", "restore", "note", "set", "add", "resolve",
                                      "import", "reconcile", "export"])
    p.add_argument("book", help="册号（如 vol04）")
    p.add_argument("refs", nargs="*", help="条目 id 或格号；note 的最后一个是说明")
    p.add_argument("--text-id", default=None, help="book-text 书 id（缺省取工作区目录名 <id>-<书名> 的 id）")
    p.add_argument("--chapter", default=None, help="章号 NNN（缺省按册配置推）")
    p.add_argument("--data", default=None, help="数据目录（缺省按工作区找）")
    p.add_argument("--state", default="open")
    p.add_argument("--json", action="store_true")
    p.add_argument("--why", default="")
    p.add_argument("--by", default=None, help="谁改的（缺省 GUJI_ACTOR）")
    p.add_argument("--note", default=None, help="add：卡片头说明")
    p.add_argument("--recheck", action="store_true", help="add：标复审格")
    p.add_argument("--field", action="append", default=[], help="set：键=JSON 值")
    p.add_argument("--src", default=None, help="add／reconcile：来源（rev:<rev>、pack:<标签>、script:<名>…）")
    p.add_argument("--event", default="", help="resolve：落成的人裁事件 id")
    p.add_argument("--sheet", default=None, help="reconcile：新出的整张 pending.json")
    p.add_argument("--fps", default=None, help="reconcile：{格号: 图块指纹} 的 json")
    p.add_argument("--keep-missing", action="store_true", help="reconcile：新单上没有的开着条目不关")
    p.add_argument("--out", default=None, help="export：写到这里（缺省写回数据目录的整张单）")
    p.add_argument("--no-export", action="store_true", help="人改条目后不重导整张单")
    p.add_argument("--sync", action="store_true", help="改完 guji db sync 并触发网站发布这一章")
    p.add_argument("--dry-run", action="store_true", help="只看结果，不写")


def _loc(a) -> tuple[Path, str, str, Path | None]:
    w = getattr(a, "workspace", None) or os.environ.get("GUJI_WORKSPACE")   # -w 由 cv 给带 book 的子命令统一加
    ws = Path(w).resolve() if w else None
    if a.data:
        data = Path(a.data)
    else:
        if ws is None:
            sys.exit("✗ 要 -w <工作区> 或 --data <数据目录>")
        from ._cv import data_root
        data = Path(data_root(ws) or ws)
    text_id = a.text_id or (ws.name.split("-", 1)[0] if ws else None)
    if not text_id:
        sys.exit("✗ 要 --text-id")
    chapter = a.chapter
    if not chapter:
        from ._cv import chapter_of
        chapter = chapter_of(a.book, None)
    if not chapter:
        sys.exit(f"✗ {a.book} 推不出章号：给 --chapter NNN")
    return data, text_id, chapter, ws


def _brief(r: dict) -> str:
    d = r.get("doc") or {}
    why = ",".join(d.get("why") or []) if isinstance(d.get("why"), list) else str(d.get("why") or "")
    extra = (" 图变" if r.get("fp_changed") else "") + (f" 「{d['note']}」" if d.get("note") else "")
    return f"{r['id']}\t{r['cell']}\t{r['state']}\tv{r['ver']}\t{why}{extra}"


def _publish(a, ws: Path | None, chapter: str) -> None:
    if not a.sync:
        print(f"还要：guji db sync -w {ws or '<工作区>'}（加 --sync 会顺带触发网站发布这一章）")
        return
    if ws is None:
        print("⚠ 没给工作区，没 sync")
        return
    p = subprocess.run([sys.executable, "-m", "open_guji_cv.cli_v2", "db", "sync", "-w", str(ws)],
                       env={**os.environ, "GUJI_WORKSPACE": str(ws)})
    if p.returncode:
        print("✗ guji db sync 失败，没触发网站发布")
        return
    if not shutil.which("gh"):
        print("⚠ 没有 gh：网站等每日定时发布，或手动跑 proofing-sync.yml")
        return
    base = ["gh", "workflow", "run", "proofing-sync.yml", "-R", WEB_REPO, "--ref", "main",
            "-f", "target=production", "-f", "parts=publish", "-f", "dry_run=false"]
    if subprocess.run(base + ["-f", f"only={a.text_id_resolved}/{chapter}"]).returncode:
        subprocess.run(base)


def export(store: P.ItemStore, data: Path, out: Path | None = None) -> Path:
    """条目 → 整张单，写回（单头取现行那份）。"""
    sheet = P.sheet_path(data, store.text_id, store.chapter)
    head = json.loads(sheet.read_text(encoding="utf-8")) if sheet.exists() else {}
    doc = P.export_sheet(store, head)
    dst = Path(out) if out else sheet
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return dst


def cmd_pending(a) -> int:
    data, text_id, chapter, ws = _loc(a)
    a.text_id_resolved = text_id
    store = P.ItemStore.open(data, text_id, chapter)
    by = a.by or os.environ.get("GUJI_ACTOR", "")
    act = a.action
    if act == "ls":
        states = P.STATES if a.state == "all" else tuple(a.state.split(","))
        rows = store.by_state(*states)
        if a.json:
            print(json.dumps(rows, ensure_ascii=False, indent=1))
        else:
            for r in rows:
                print(_brief(r))
            n = store.counts()
            print(f"# {text_id}/{chapter}：" + "、".join(f"{k} {v}" for k, v in n.items()))
        return 0
    if act == "show":
        for ref in a.refs:
            for r in store.find(ref):
                print(json.dumps(r, ensure_ascii=False, indent=1))
                print("## 改动记录")
                for line in store.path.read_text(encoding="utf-8").splitlines():
                    x = json.loads(line)
                    if x["id"] == r["id"]:
                        print(f"v{x['ver']}\t{x['at']}\t{x['op']}\t{x.get('by', '')}\t{x.get('why', '')}")
        return 0
    if act in ("import", "reconcile"):
        fps = json.loads(Path(a.fps).read_text(encoding="utf-8")) if a.fps else None
        if act == "import":
            sheet = P.sheet_path(data, text_id, chapter)
            if not sheet.exists():
                sys.exit(f"✗ 没有现行单：{sheet}")
            res = P.import_sheet(store, json.loads(sheet.read_text(encoding="utf-8")), by=by, fps=fps)
        else:
            if not a.sheet:
                sys.exit("✗ reconcile 要 --sheet <新出的 pending.json>")
            doc = json.loads(Path(a.sheet).read_text(encoding="utf-8"))
            res = P.reconcile(store, doc.get("cells") or [], src=a.src or f"rev:{doc.get('rev') or '?'}", fps=fps,
                              by=by, close_missing=not a.keep_missing)
        print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in res.items()}, ensure_ascii=False))
        if res.get("撤下仍判待审"):
            print(f"ⓘ 人工撤下、机器仍判待审 {len(res['撤下仍判待审'])} 格（保持撤下）：{' '.join(res['撤下仍判待审'][:20])}")
        if res.get("图变"):
            print(f"ⓘ 格号对上、图块指纹变了 {len(res['图变'])} 格（条目照旧，标 fp_changed）：{' '.join(res['图变'][:20])}")
        if a.dry_run:
            print("（--dry-run，没写）")
            return 0
        print(f"条目追加 {store.save()} 行 → {store.path}")
        if act == "reconcile" or not a.no_export:
            head_src = Path(a.sheet) if act == "reconcile" else None
            sheet = P.sheet_path(data, text_id, chapter)
            if head_src is not None:
                head = json.loads(head_src.read_text(encoding="utf-8"))
                doc = P.export_sheet(store, head)
                dst = Path(a.out) if a.out else sheet
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            else:
                dst = export(store, data, a.out)
            print(f"整张单 → {dst}")
        _publish(a, ws, chapter)
        return 0
    if act == "export":
        print(f"整张单 → {export(store, data, a.out)}")
        _publish(a, ws, chapter)
        return 0
    # 人工操作
    try:
        if act == "withdraw":
            done = [store.withdraw(r, by=by, why=a.why) for r in a.refs]
        elif act == "restore":
            done = [store.restore(r, by=by, why=a.why) for r in a.refs]
        elif act == "note":
            if len(a.refs) != 2:
                sys.exit("✗ note 写成：guji pending note <册> <条目或格号> \"说明\"")
            done = [store.note(a.refs[0], a.refs[1], by=by, why=a.why)]
        elif act == "set":
            fields = {}
            for kv in a.field:
                k, _, v = kv.partition("=")
                fields[k.strip()] = json.loads(v) if v.strip() else None
            done = [store.set_fields(r, fields, by=by, why=a.why) for r in a.refs]
        elif act == "add":
            doc = {**({"note": a.note} if a.note else {}), **({"recheck": True} if a.recheck else {})}
            done = [store.add(r, doc, by=by, why=a.why, src=a.src or f"human:{by or '?'}") for r in a.refs]
        elif act == "resolve":
            done = [store.resolve(r, by=by, event=a.event, why=a.why) for r in a.refs]
        else:
            raise AssertionError(act)
    except (KeyError, ValueError) as e:
        sys.exit(f"✗ {e.args[0] if e.args else e}")
    for r in done:
        print(_brief(r))
    if a.dry_run:
        print("（--dry-run，没写）")
        return 0
    store.save()
    if not a.no_export:
        print(f"整张单 → {export(store, data)}")
    _publish(a, ws, chapter)
    return 0


COMMANDS = {"pending": (add_parser, cmd_pending)}
