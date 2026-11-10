"""换单 driver：把「出新单 → 同步 → 分批发布 → 核对线上 → 清盘 → 刷看板」串成一条可断点续跑的命令。

``guji swap run --books vol20-vol99 -w <工作区> --book-text <book-text>``

设计要点（A32，2026-11-05，换单经验总结）：

* 全程设 ``GUJI_DB_NO_GLYPH=1``：同步只推待审单与事件，绝不碰字形库账本（11-04 字形账本被清空的事故）。
* 开跑前、每批之间都核字形库账本不空、不比基准少一成以上、磁盘够；不过就停在原地不动。
* 每批 ``--batch-size`` 册：auto_cycle（``--no-publish``）→ ``sync_workspace(no_glyph)`` → 对这批 ``proofing-sync only=`` 发布并等跑完
  → 逐册取线上 ``NNN.pending.json`` 核版本 → 核过的清掉本地产物包。全站一把发会撞 40 分钟超时，所以只发这一批。
* 状态写 ``<工作区>/reports/_swap/state.json``，崩了/容器重启后同样的命令接着做（已核对的册跳过）。
* 格号变动（增删格、改号）由 cv republish 交 ``swap.booktext`` 按格级对照表自动落 book-text；守卫拦下的册（guard-stop）、
  出单失败的册（blocked）只记入状态并在最后列出：切坏的交切分线，锚点挪不了的交 A33，修好后 ``guji swap book-text --sheet``。不在这里自动重试。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

WEB_REPO = "open-guji/kaiyuanguji-web"
LIVE = "https://data.openguji.com/proof/{text_id}/{n:03d}.pending.json"
LEDGER_FILES = ("glyphs.jsonl", "exemplars.jsonl", "admissions.jsonl")
MIN_FREE_GB = 3.0
LEDGER_FLOOR = 0.9          # 账本行数低于开跑时的这个比例就拒绝往下做


def parse_books(spec: str) -> list[str]:
    """``vol20-vol25,vol30`` → ['vol20', ..., 'vol25', 'vol30']。"""
    out: list[str] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"vol(\d+)-vol(\d+)", part)
        if m:
            out += [f"vol{i:02d}" for i in range(int(m[1]), int(m[2]) + 1)]
        elif re.fullmatch(r"vol\d+", part):
            out.append(f"vol{int(part[3:]):02d}")
        else:
            raise SystemExit(f"--books 看不懂 {part!r}（如 vol20-vol99 或 vol23,vol24）")
    return list(dict.fromkeys(out))


def chunks(items: list, n: int):
    for i in range(0, len(items), max(1, n)):
        yield items[i:i + n]


def ledger_counts(data_dir: Path) -> dict[str, int]:
    store = Path(data_dir) / "output" / "glyph_store"
    return {f: (sum(1 for _ in open(store / f, "rb")) if (store / f).exists() else 0) for f in LEDGER_FILES}


def ledger_problem(now: dict[str, int], baseline: dict[str, int] | None) -> str | None:
    if not all(now.values()):
        return f"字形库账本有空文件 {now}（像是被清空或没拉全），先 guji db pull 再说"
    if baseline:
        for k, b in baseline.items():
            if b and now.get(k, 0) < b * LEDGER_FLOOR:
                return f"字形库账本 {k} 从 {b} 行降到 {now.get(k, 0)} 行，停下"
    return None


def data_problem(dd: Path) -> str | None:
    """出单要读的两样数据在不在（A31 11-06）：待收字登记表和语料。缺了 R03 待收字会被统计成 R01
    （出单报告 ``glyph_pending_registry_missing`` 会是 1），所以开跑前就核，缺了先 ``guji db pull``。"""
    from ..review.reasons import GLYPH_PENDING_REL
    miss = []
    reg = Path(dd).joinpath(*GLYPH_PENDING_REL)
    if not reg.exists() or reg.stat().st_size == 0:
        miss.append("config/pua/glyph_pending_codes.json（待收字登记表）")
    corpus = Path(dd) / "corpus" / "daizhige"
    if not corpus.is_dir() or not any(corpus.glob("*.jsonl")):
        miss.append("corpus/daizhige/（语料）")
    return f"数据目录 {dd} 缺：{'、'.join(miss)}。先 guji db pull" if miss else None


def precheck(ws: Path, state: dict) -> None:
    from ..datastore.workcopy import data_dir
    if not os.environ.get("GUJI_ACTOR"):
        raise SystemExit("先 export GUJI_ACTOR=<你的名字>")
    free = shutil.disk_usage(ws).free / 2 ** 30
    if free < MIN_FREE_GB:
        raise SystemExit(f"磁盘只剩 {free:.1f}GB（要 ≥ {MIN_FREE_GB}GB）：先清 _packs／cache／旧 exports")
    bad = data_problem(data_dir(ws))
    if bad:
        raise SystemExit(bad)
    now = ledger_counts(data_dir(ws))
    bad = ledger_problem(now, state.get("ledger_baseline"))
    if bad:
        raise SystemExit(bad)
    state.setdefault("ledger_baseline", now)


def load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"books": {}}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def parse_cycle_log(text: str) -> dict[str, dict]:
    """auto_cycle 的输出里取每册结论：``volN\\t→ done\\t说明``。"""
    out: dict[str, dict] = {}
    for line in text.splitlines():
        p = line.split("\t")
        if len(p) >= 2 and re.fullmatch(r"vol\d+", p[0]) and p[1].startswith("→"):
            out[p[0]] = {"verdict": p[1].lstrip("→ ").strip(), "why": p[2] if len(p) > 2 else ""}
    return out


def expected_rev(ws: Path, book: str, text_id: str) -> str | None:
    """auto_cycle 换完后线上单的版本号：最新一次循环 rev 的下一个（NNN-rK → NNN-r(K+1)）。"""
    dirs = sorted((ws / "reports" / book / "_cycle").glob("*/"), key=lambda p: [int(x) for x in re.findall(r"\d+", p.name)])
    if not dirs:
        return None
    m = re.fullmatch(r"(\d+)-r(\d+)", dirs[-1].name)
    return f"{m[1]}-r{int(m[2]) + 1}" if m else None


def live_rev(text_id: str, n: int) -> str | None:
    try:
        with urllib.request.urlopen(LIVE.format(text_id=text_id, n=n) + f"?x={int(time.time())}", timeout=30) as r:
            return json.load(r).get("rev")
    except Exception:
        return None


def publish_batch(books: list[str], text_id: str) -> str:
    """对这批册触发 proofing-sync（only=），等跑完，返回 conclusion。"""
    only = ",".join(f"{text_id}/{int(b[3:]):03d}" for b in books)
    since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    r = subprocess.run(["gh", "workflow", "run", "proofing-sync.yml", "-R", WEB_REPO, "--ref", "main",
                        "-f", "target=production", "-f", "parts=publish", "-f", "dry_run=false", "-f", f"only={only}"],
                       capture_output=True, text=True)
    if r.returncode:
        return "trigger-fail: " + r.stderr.strip()[-200:]
    time.sleep(20)
    q = f'[.[]|select(.createdAt>="{since}")][-1].databaseId'
    rid = subprocess.run(["gh", "run", "list", "-R", WEB_REPO, "--workflow", "proofing-sync.yml", "-L", "5",
                          "--json", "databaseId,createdAt", "-q", q], capture_output=True, text=True).stdout.strip()
    if not rid:
        return "no-run"
    while True:
        st = subprocess.run(["gh", "run", "view", rid, "-R", WEB_REPO, "--json", "status,conclusion"],
                            capture_output=True, text=True)
        d = json.loads(st.stdout or "{}")
        if d.get("status") == "completed":
            return d.get("conclusion") or "unknown"
        time.sleep(45)


def refresh_progress(books: list[str], text_id: str, cv: Path | None, state: dict) -> None:
    """换单后刷新后台「文本整理」看板（pending_review 等）。必须在 db sync 之后跑：auto_cycle 里那次是在新单推库前算的，
    读到的还是旧单（11-08 vol44 显示 377、实际 80）。失败要响，并记进 state，不能静默。"""
    cv = cv or (Path(os.environ["GUJI_CV"]) if os.environ.get("GUJI_CV") else None)
    script = cv / "scripts" / "zhengli" / "progress_report.py" if cv else None
    if not script or not script.exists():
        print(f"⚠ 看板没刷新：找不到 progress_report.py（cv={cv}），请手动 python progress_report.py --books {','.join(books)}", file=sys.stderr)
        for b in books:
            state["books"][b]["progress"] = "no-script"
        return
    for b in books:
        r = subprocess.run([sys.executable, str(script), "--books", b, "--text-id", text_id],
                           capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(cv)})
        ok = r.returncode == 0 and "已写 progress" in r.stdout
        state["books"][b]["progress"] = "ok" if ok else "failed"
        if not ok:
            print(f"⚠ {b} 看板没刷新：{(r.stdout + r.stderr).strip()[-300:]}", file=sys.stderr)


def publish_and_verify(ws: Path, done: list[str], text_id: str, state: dict, sp: Path, book_text: Path | None = None,
                       cv: Path | None = None) -> None:
    """已换好单（status=done）的册：同步进中心库（不碰字形库）→ 发布这一批 → 逐册核线上版本 → 核过的清盘。

    全站冒烟必然「失败」（别的册还是旧版本），所以以逐册线上版本为准。"""
    from ..cli_db import sync_workspace
    audit_books(ws, done, book_text, text_id, state, sp)          # 产物包核过就清，所以在发布前出机器改字抽检数据
    sync_workspace(ws, admit=False, no_glyph=True)
    refresh_progress(done, text_id, cv, state)                       # 新单已进中心库，看板才算得对
    save_state(sp, state)
    if os.environ.get("GUJI_SWAP_NO_PUBLISH"):          # 并行分片时不各自发布（网站发布 workflow 串行排队、互相取消），最后统一发
        for b in done:
            state["books"][b].update(status="done", publish="deferred")
        save_state(sp, state)
        return
    concl = publish_batch(done, text_id)
    for b in done:
        want, got = expected_rev(ws, b, text_id), live_rev(text_id, int(b[3:]))
        ok = want is not None and want == got
        state["books"][b].update(status="verified" if ok else "publish-mismatch", want=want, live=got, publish=concl)
        if ok:
            for p in (ws / "_packs").glob(f"*/{b}"):
                shutil.rmtree(p, ignore_errors=True)
    save_state(sp, state)


def audit_books(ws: Path, books: list[str], book_text: Path | None, text_id: str, state: dict, sp: Path) -> None:
    """机器改字抽检（A31 11-06 定，每次换单报告固定附）：数据存进 state，最后一并写 md／tsv。读不全的册记 audit=None，不挡发布。"""
    if not book_text:
        return
    from ..machine_audit import audit_book
    for b in books:
        try:
            r = audit_book(ws, b, Path(book_text), text_id)
        except Exception as e:  # noqa: BLE001 —— 抽检出不来不能挡换单
            print(f"{b} 机器改字抽检失败：{e}", file=sys.stderr)
            r = None
        state["books"][b]["audit"] = r
    save_state(sp, state)


def write_audit_report(ws: Path, state: dict) -> Path | None:
    from ..machine_audit import write_report
    res = {b: v["audit"] for b, v in state["books"].items() if v.get("audit")}
    return write_report(ws, res, "机器改字抽检表-" + time.strftime("%Y%m%d-%H%M")) if res else None


def cmd_run(a) -> int:
    ws = Path(a.workspace).resolve()
    sp = Path(a.state) if a.state else ws / "reports" / "_swap" / "state.json"
    state = load_state(sp)
    precheck(ws, state)
    save_state(sp, state)
    text_id = a.text_id
    cv = Path(a.cv)
    env = {**os.environ, "GUJI_DB_NO_GLYPH": "1", "GUJI_WORKSPACE": str(ws)}
    books = parse_books(a.books)
    # 上次换好单但没发布成/没核过的册：只补「发布＋核对」，不能再跑 auto_cycle（会再出一张新单）
    pub_only = [b for b in books if state["books"].get(b, {}).get("status") in ("done", "publish-mismatch")]
    todo = [b for b in books if state["books"].get(b, {}).get("status") not in ("verified", "done", "publish-mismatch")]
    print(f"待处理 {len(todo)} 册", file=sys.stderr)
    if a.dry_run:
        print(json.dumps({"todo": todo, "publish_only": pub_only, "state_file": str(sp)}, ensure_ascii=False))
        return 0
    for chunk in chunks(pub_only, a.batch_size):
        precheck(ws, state)
        publish_and_verify(ws, chunk, text_id, state, sp, Path(a.book_text), cv)
    for chunk in chunks(todo, a.batch_size):
        precheck(ws, state)                                  # 每批之间再核一次账本与磁盘
        log = ws / "reports" / "_swap" / f"{chunk[0]}-{chunk[-1]}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with open(log, "w", encoding="utf-8") as f:
            subprocess.run([sys.executable, str(cv / "scripts" / "zhengli" / "auto_cycle.py"), "--books", ",".join(chunk),
                            "-w", str(ws), "--book-text", a.book_text, "--no-publish"],
                           cwd=cv, env={**env, "PYTHONPATH": str(cv)}, stdout=f, stderr=subprocess.STDOUT)
        res = parse_cycle_log(log.read_text(encoding="utf-8"))
        for b in chunk:
            r = res.get(b, {"verdict": "no-result", "why": "auto_cycle 没给结论（进程中断？）"})
            state["books"][b] = {"status": r["verdict"], "why": r["why"][:300]}
        save_state(sp, state)
        done = [b for b in chunk if state["books"][b]["status"] == "done"]
        if not done:
            continue
        publish_and_verify(ws, done, text_id, state, sp, Path(a.book_text), cv)
    rep = write_audit_report(ws, state)
    if rep:
        print(f"机器改字抽检表：{rep}", file=sys.stderr)
    left = {k: v for k, v in state["books"].items() if v["status"] != "verified"}
    print(json.dumps({"verified": sorted(k for k, v in state["books"].items() if v["status"] == "verified"),
                      "left": {k: v["status"] for k, v in left.items()}}, ensure_ascii=False))
    return 0 if not left else 2


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("swap", help="换单 driver：出新单→同步→分批发布→核线上→清盘（断点续跑）")
    p.add_argument("action", choices=["run", "audit", "book-text"],
                   help="run 换单；audit 机器改字抽检；book-text 把已导出的新包落 book-text（格号变了按格级对照表走，见 swap/booktext.py）")
    p.add_argument("--books", required=True, help="如 vol20-vol99 或 vol23,vol24")
    p.add_argument("-w", "--workspace", required=True)
    p.add_argument("--book-text", required=True)
    p.add_argument("--text-id", default="96mid1ogzk")
    p.add_argument("--cv", default=os.environ.get("GUJI_CV", str(Path.home() / "cv")), help="open-guji-cv 检出目录")
    p.add_argument("--batch-size", type=int, default=6, help="每批几册（全站一把发会超时）")
    p.add_argument("--state", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--export", help="book-text：导出目录（缺省取 reports/<册>/_cycle/ 下最新的 export）")
    p.add_argument("--worktree", help="book-text：独立 worktree 路径（缺省 <book-text>-swap，每册重置到 origin/dev）")
    p.add_argument("--note", help="book-text：文本线版本记录的说明")
    p.add_argument("--push", action="store_true", help="book-text：过了守卫和 local_check 就推（0.x 推 dev；1.x 推 swap/<册>-1x 分支待开 PR）")
    p.add_argument("--sheet", action="store_true", help="book-text：推好文本后，把 reports/<册>/_publish/ 里已出的新单补推上线并 db sync")


def cmd_audit(a) -> int:
    """只出机器改字抽检表：对已换完的册（产物包还在才读得到整理本字）。``guji swap audit --books vol20-vol30 …``"""
    from ..machine_audit import audit_book, write_report
    ws = Path(a.workspace).resolve()
    res = {}
    for b in parse_books(a.books):
        r = audit_book(ws, b, Path(a.book_text), a.text_id)
        if r:
            res[b] = r
        else:
            print(f"{b} 读不全（没有导出／产物包已清／book-text 无历史），跳过", file=sys.stderr)
    if res:
        print(write_report(ws, res, "机器改字抽检表-" + time.strftime("%Y%m%d-%H%M")))
    return 0 if res else 1


def cmd_swap(args) -> int:
    if args.action == "book-text":
        from .booktext import cmd_book_text
        return cmd_book_text(args, parse_books(args.books))
    return cmd_audit(args) if args.action == "audit" else cmd_run(args)


COMMANDS = {"swap": (add_parser, cmd_swap)}
