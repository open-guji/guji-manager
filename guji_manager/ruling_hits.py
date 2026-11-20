"""AI 文意裁定命中核对：`guji rulings-hits`（A31 2026-11-20，流程慢痛点 K1）。

裁定（`feedback/rulings/`）按**窗口内容**取键（组＋前后各 20 字的哈希＋提示词版本），不按格号。
重放时 seed_admit 看到的窗口和写裁定时的不一样（邻格放行状态不同、整理本改了字），裁定就静默不命中：
全唐文 d1 有 15 格推了裁定仍待审，要等一整轮出包才知道。

本命令读一份产物（`--products <根>`，含 seed_admit），对每个**仍在问**（ask 还挂着）的格：
这格有裁定（按 `payload.cell`）却查不到 → 列为「未命中」，写出两边窗口。
`--rekey --batch <名>`：用产物里这格当时实际的窗口另写一条裁定（字、把握、模型照抄原裁定，why 前缀 rekey），
下一次重放即可命中。提示词版本不同的不改键（换版本本来就是要作废）。只读产物；--rekey 只追加裁定事件，推库照常 `guji db sync`。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _rulings_by_cell(store) -> dict[str, dict]:
    """格号 → 这格最新一条文意裁定 payload（不含 src-2 私用码记录）。"""
    from ._cv import RULING_KIND
    from ._cv import replay_key
    out: dict[str, dict] = {}
    if not store.log.events_dir.exists():
        return out
    evs = [e for e in store.log.iter_all(raw=True) if e.kind == RULING_KIND]
    for e in sorted(evs, key=replay_key):
        p = e.payload or {}
        if p.get("cell") and p.get("ctx") and p.get("prompt_ver") != "src-2":
            out[p["cell"]] = p
    return out


def check(products: Path, book: str, store) -> list[dict]:
    from ._cv import llm_questions_of_page, ruling_ctx_hash
    by_cell = _rulings_by_cell(store)
    rows = []
    for f in sorted((Path(products) / book / "seed_admit").glob("p*.json")):
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for q in llm_questions_of_page(doc):
            r = by_cell.get(q["cell"])
            if not r or store.get(q["group"], q["ver"], q["l"], q["r"]) is not None:
                continue
            same_ver = r.get("prompt_ver") == q["ver"]
            rows.append({"cell": q["cell"], "组": q["group"], "裁定字": r.get("char") or ("其他" if r.get("other") else ""),
                         "把握": r.get("conf"), "原因": "窗口变了" if same_ver else f"提示词版本 {r.get('prompt_ver')}→{q['ver']}",
                         "裁定窗口": f"{(r.get('ctx') or {}).get('left', '')}｜{(r.get('ctx') or {}).get('right', '')}",
                         "产物窗口": f"{q['l'][-20:]}｜{q['r'][:20]}", "_q": q, "_r": r,
                         "_hash": ruling_ctx_hash(q["l"], q["r"])})
    return rows


def rekey(rows: list[dict], store) -> int:
    n = 0
    for x in rows:
        r, q = x["_r"], x["_q"]
        if r.get("prompt_ver") != q["ver"]:
            continue
        char = "其他" if r.get("other") else r.get("char")
        if not char:
            continue
        store.put(q["group"], q["ver"], q["l"], q["r"], char=char, conf=r.get("conf"),
                  why=("rekey:" + (r.get("why") or ""))[:60], model=r.get("model") or "session", cell=q["cell"],
                  pending_reason=r.get("pending_reason"))
        n += 1
    return n


def cmd(a) -> None:
    from ._cv import RulingStore
    store = RulingStore()
    if a.batch:
        store._batch = a.batch
    books = [b.strip() for b in a.books.split(",") if b.strip()]
    allrows = []
    for b in books:
        rows = check(Path(a.products), b, store)
        allrows += rows
        print(f"{b}：仍在问且有裁定却没命中 {len(rows)} 格", file=sys.stderr)
    cols = ["cell", "组", "裁定字", "把握", "原因", "裁定窗口", "产物窗口"]
    out = Path(a.out) if a.out else None
    text = "\t".join(cols) + "\n" + "".join("\t".join(str(r.get(c) or "") for c in cols) + "\n" for r in allrows)
    if out:
        out.write_text(text, encoding="utf-8")
        print(f"清单：{out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    if a.rekey and allrows:
        if not a.batch:
            sys.exit("--rekey 要给 --batch <批次名>（如 llm-rekey-QTW-20261120）")
        n = rekey(allrows, store)
        print(f"按产物窗口补写裁定 {n} 条（批次 {a.batch}）；guji db sync 推库后重放 seed_admit 即命中", file=sys.stderr)


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("rulings-hits", help="AI 文意裁定命中核对：产物里仍在问、却有裁定没命中的格（窗口变了）；--rekey 按产物窗口补写")
    p.add_argument("--books", required=True, help="册，逗号分隔（如 001,002 或 vol20）")
    p.add_argument("--products", required=True, help="产物根（下有 <册>/seed_admit/）")
    p.add_argument("-w", "--workspace", default=None, help="工作区（定裁定库位置；缺省 GUJI_WORKSPACE）")
    p.add_argument("--out", default=None, help="清单 tsv（缺省打到标准输出）")
    p.add_argument("--rekey", action="store_true", help="按产物里的窗口另写一条裁定（同提示词版本的才写）")
    p.add_argument("--batch", default=None, help="--rekey 写进的裁定批次名")


def _cmd(a) -> None:
    import os
    if a.workspace:
        os.environ["GUJI_WORKSPACE"] = str(Path(a.workspace).resolve())
    cmd(a)


COMMANDS = {"rulings-hits": (add_parser, _cmd)}
