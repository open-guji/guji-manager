"""换单 driver：把「取 main 包 → guji land 对账＋推库 → 发站 → 核对线上 → 清盘 → 刷看板」串成一条可断点续跑的命令。

``guji swap run --books vol20-vol99 -w <工作区> --book-text <book-text>``

2026-11-27（待审清理计划 1.7）：出单从 cv 的 ``auto_cycle.py``（整张换单、升 rev）改为 ``guji land``（条目对账、就地覆盖、rev 不升）。
每批 ``--batch-size`` 册：每册 ``guji products pack fetch --label <★main>`` → 一次 ``guji land <这批> --apply``（land 自己推库、只发有变的册、核线上格数；
带 ``--book-text`` 时顺带 ``--text-apply`` 把机器改字落 book-text，``--no-text-apply`` 关掉）。没变的册记 fresh，land 拒绝的（挪格＋旧 rev 票）记 blocked。
auto_cycle 以前做的「票落成人裁」「手加格补回」「引擎 worktree 重跑」不再有：票按条目记，用 ``guji collect`` 落；手加格条目 land 不会关掉。

设计要点（A32，2026-11-05，换单经验总结）：

* 全程设 ``GUJI_DB_NO_GLYPH=1``：同步只推待审单与事件，绝不碰字形库账本（11-04 字形账本被清空的事故）。
* 开跑前、每批之间都核字形库账本不空、不比基准少一成以上、磁盘够；不过就停在原地不动。
* 状态写 ``<工作区>/reports/_swap/state.json``，崩了/容器重启后同样的命令接着做（已核对的册跳过）。
* 格号变动（增删格、改号）交 ``swap.booktext`` 按格级对照表落 book-text；守卫拦下的册（guard-stop）、
  land 拒绝的册（blocked）只记入状态并在最后列出：切坏的交切分线，锚点挪不了的交 GM3，修好后 ``guji swap book-text``。不在这里自动重试。
"""

from __future__ import annotations

import calendar
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
DIANBEN_ID = "96mid1ogzk"
LEDGER_FILES = ("glyphs.jsonl", "exemplars.jsonl", "admissions.jsonl")
MIN_FREE_GB = 3.0
LEDGER_FLOOR = 0.9          # 账本行数低于开跑时的这个比例就拒绝往下做


def parse_books(spec: str) -> list[str]:
    """``vol20-vol25,vol30`` → ['vol20', ..., 'vol25', 'vol30']；全唐文、史記的纯数字册名同样可写区间，位数照写的
    （``001-045`` → '001'…'045'，``01-42`` → '01'…'42'）。别的册名原样（不展开）。"""
    out: list[str] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"vol(\d+)-vol(\d+)", part)
        n = re.fullmatch(r"(\d+)-(\d+)", part)
        if m:
            out += [f"vol{i:02d}" for i in range(int(m[1]), int(m[2]) + 1)]
        elif n:
            w = len(n[1])
            out += [f"{i:0{w}d}" for i in range(int(n[1]), int(n[2]) + 1)]
        elif re.fullmatch(r"vol\d+", part):
            out.append(f"vol{int(part[3:]):02d}")
        elif re.fullmatch(r"[A-Za-z0-9_]+", part):
            out.append(part)
        else:
            raise SystemExit(f"--books 看不懂 {part!r}（如 vol20-vol99、001-045 或 vol23,vol24）")
    return list(dict.fromkeys(out))


def vol_no(book: str) -> int:
    """册序：``vol07`` → 7，``007``／``07`` → 7；别的册名读册 yaml 的 ``volume:``（cv ``core.volume_id``）。"""
    m = re.fullmatch(r"(?:vol)?(\d+)", book)
    if m:
        return int(m[1])
    try:
        from .._cv import volume_of
        v = volume_of(book).volume
    except Exception:  # noqa: BLE001
        v = None
    if v is None:
        raise SystemExit(f"{book} 推不出册序：册 yaml 写上 volume:")
    return int(v)


def chapter_of(book: str) -> str:
    """book-text 章号（三位，殿本、全唐文、史記都是一册一章、三位）。"""
    return f"{vol_no(book):03d}"


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


def precheck(ws: Path, state: dict, text_id: str = DIANBEN_ID) -> None:
    from ..datastore.workcopy import data_dir
    if not os.environ.get("GUJI_ACTOR"):
        raise SystemExit("先 export GUJI_ACTOR=<你的名字>")
    free = shutil.disk_usage(ws).free / 2 ** 30
    if free < MIN_FREE_GB:
        freed = auto_clean(ws, state)                       # 换包提速：先自己清已核对册的包和字块缓存，清完还不够才停
        free = shutil.disk_usage(ws).free / 2 ** 30
        print(f"磁盘不足，自动清理释放 {freed:.1f}GB，现剩 {free:.1f}GB", file=sys.stderr)
        if free < MIN_FREE_GB:
            raise SystemExit(f"磁盘只剩 {free:.1f}GB（要 ≥ {MIN_FREE_GB}GB），自动清理后仍不够：先清旧 exports／别的大目录")
    # 待收字登记表和 corpus/daizhige 是殿本的数据；全唐文、史記的数据目录本来就没有（11-18 全唐文 swap run 被它误拦），非殿本只提示不拦
    bad = data_problem(data_dir(ws))
    if bad:
        if text_id == DIANBEN_ID:
            raise SystemExit(bad)
        print(f"提示（非殿本，不拦）：{bad}", file=sys.stderr)
    now = ledger_counts(data_dir(ws))
    bad = ledger_problem(now, state.get("ledger_baseline"))
    if bad:
        raise SystemExit(bad)
    state.setdefault("ledger_baseline", now)


def _du(p: Path) -> float:
    n = 0
    for root, _d, files in os.walk(p):
        for f in files:
            try:
                n += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return n / 2 ** 30


def auto_clean(ws: Path, state: dict) -> float:
    """磁盘不够时自动清（QTW 11-24：每轮要停下手清 _packs／cache／sha256）。只清能再生的：
    ①状态里 verified／fresh 的册的 ``_packs/*/<册>``；②没有「进行中」册时的 ``_packs`` 空壳；③``cache/sha256``（按内容寻址的缓存，用到再取）。
    不碰 reports、book-text、数据目录。返回释放的 GB。"""
    freed = 0.0
    finished = {b for b, v in state.get("books", {}).items() if v.get("status") in ("verified", "fresh")}
    for b in finished:
        for p in (ws / "_packs").glob(f"*/{b}"):
            freed += _du(p)
            shutil.rmtree(p, ignore_errors=True)
    c = ws / "cache" / "sha256"
    if shutil.disk_usage(ws).free / 2 ** 30 < MIN_FREE_GB and c.is_dir():
        freed += _du(c)
        shutil.rmtree(c, ignore_errors=True)
    return freed


def pull_workspace(ws: Path, force_ok: bool = False) -> int:
    """开跑先拉一次库（不碰字形库）：旧 glyph.db 挡住时加 --force（丢掉本地没推的改动，换包的 ws 本来就只是出单用）。
    状态里已有「进行中」册（断点续跑）不 --force，免得丢掉已写未推的新单。"""
    env = {**os.environ, "GUJI_DB_NO_GLYPH": "1", "GUJI_WORKSPACE": str(ws)}
    base = [sys.executable, "-m", "open_guji_cv.cli_v2", "db", "pull", "-w", str(ws), "--no-glyph"]
    rc = subprocess.run(base, env=env).returncode
    if rc and force_ok:                                  # 旧 glyph.db 等挡住拉库（11-24 QTW 001）：没有未推的新单才敢 --force
        rc = subprocess.run([*base, "--force"], env=env).returncode
    return rc


def sync_retry(ws: Path, tries: int = 3) -> dict:
    """一趟里唯一的一次 db sync；Stale／StaleBase（库被别人写过）等几秒重试，SyncConflict 先 pull 再试（11-24 QTW 001 册被拦）。"""
    from ..cli_db import sync_workspace
    last: Exception | None = None
    for i in range(tries):
        try:
            return sync_workspace(ws, admit=False, no_glyph=True)
        except Exception as e:  # noqa: BLE001
            name = type(e).__name__
            if name not in ("Stale", "StaleBase", "SyncConflict") or i == tries - 1:
                raise
            last = e
            print(f"sync 遇到 {name}：{str(e)[:120]}，{5 * (i + 1)} 秒后{'拉库' if name == 'SyncConflict' else ''}重试（第 {i + 2} 次）", file=sys.stderr)
            time.sleep(5 * (i + 1))
            if name == "SyncConflict":
                pull_workspace(ws)
    raise last  # pragma: no cover


def current_main(ws: Path, book: str) -> str | None:
    """这册现在的 ★main 标签；读不到（没网、没标过）→ None，不挡换单。"""
    from ..datastore.packs import main_label
    old = os.environ.get("GUJI_WORKSPACE")
    os.environ["GUJI_WORKSPACE"] = str(ws)
    try:
        return main_label(book)
    except Exception:  # noqa: BLE001
        return None
    finally:
        if old is None:
            os.environ.pop("GUJI_WORKSPACE", None)
        else:
            os.environ["GUJI_WORKSPACE"] = old


def load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"books": {}}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def live_rev(text_id: str, n: int) -> str | None:
    try:
        with urllib.request.urlopen(LIVE.format(text_id=text_id, n=n) + f"?x={int(time.time())}", timeout=30) as r:
            return json.load(r).get("rev")
    except Exception:
        return None


def last_publish_age_hours() -> float | None:
    """最近一次 proofing-sync（任何触发方）离现在多少小时；查不到返回 None。
    定时收单每半小时一趟，每趟都发站会耗尽腾讯云每日 CDN purge 配额（11-23 LimitExceeded.DailyQuota），
    所以 collect 用它做节流（``GUJI_PUBLISH_MIN_HOURS``，缺省 3）。"""
    r = subprocess.run(["gh", "run", "list", "-R", WEB_REPO, "--workflow", "proofing-sync.yml", "-L", "1",
                        "--json", "createdAt", "-q", ".[0].createdAt"], capture_output=True, text=True)
    ts = (r.stdout or "").strip()
    if r.returncode or not ts:
        return None
    try:
        t = calendar.timegm(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        return None
    return max(0.0, (time.time() - t) / 3600)


def _proofing_runs(limit: int = 10) -> list[dict]:
    r = subprocess.run(["gh", "run", "list", "-R", WEB_REPO, "--workflow", "proofing-sync.yml", "-L", str(limit),
                        "--json", "databaseId,createdAt,status,conclusion"], capture_output=True, text=True)
    try:
        return json.loads(r.stdout or "[]")
    except ValueError:
        return []


def wait_idle(max_minutes: float = 60.0) -> bool:
    """等网站 proofing-sync 没有排队／在跑的 run 再触发（并发的 run 会互相取消：11-24 全唐文 011 假 verified、008 手加格被冲掉）。
    等到了返回 True，超时返回 False（照触发，由后面的 conclusion 判）。"""
    end = time.time() + max_minutes * 60
    while time.time() < end:
        if not any(r.get("status") in ("in_progress", "queued", "waiting", "pending", "requested") for r in _proofing_runs()):
            return True
        time.sleep(30)
    return False


def publish_batch(books: list[str], text_id: str, retries: int = 2) -> str:
    """对这批册触发**一次** proofing-sync（only=），等跑完，返回 conclusion（只有 ``success`` 才算发成）。

    触发前先等别的 run 跑完（串行，不并发）；被取消（cancelled，多半被别的触发顶掉）就等空闲后重发，最多 ``retries`` 次。"""
    only = ",".join(f"{text_id}/{chapter_of(b)}" for b in books)
    concl = "unknown"
    for attempt in range(retries + 1):
        wait_idle()
        since = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        r = subprocess.run(["gh", "workflow", "run", "proofing-sync.yml", "-R", WEB_REPO, "--ref", "main",
                            "-f", "target=production", "-f", "parts=publish", "-f", "dry_run=false", "-f", f"only={only}"],
                           capture_output=True, text=True)
        if r.returncode:
            return "trigger-fail: " + r.stderr.strip()[-200:]
        rid = ""
        for _ in range(6):                               # 触发后 run 要几秒才出现
            time.sleep(10)
            runs = sorted((x for x in _proofing_runs() if x.get("createdAt", "") >= since), key=lambda x: x["createdAt"])
            if runs:
                rid = str(runs[0]["databaseId"])           # 我们是触发前才确认空闲的，这段时间里最早的一条就是我们的
                break
        if not rid:
            return "no-run"
        deadline = time.time() + 50 * 60
        concl = "timeout"
        while time.time() < deadline:
            st = subprocess.run(["gh", "run", "view", rid, "-R", WEB_REPO, "--json", "status,conclusion"],
                                capture_output=True, text=True)
            d = json.loads(st.stdout or "{}")
            if d.get("status") == "completed":
                concl = d.get("conclusion") or "unknown"
                break
            time.sleep(45)
        if concl != "cancelled":
            return concl
        print(f"⚠ proofing-sync {rid} 被取消（第 {attempt + 1} 次），等空闲后重发", file=sys.stderr)
    return concl


def refresh_progress(books: list[str], text_id: str, cv: Path | None, state: dict) -> None:
    """换单后刷新后台「文本整理」看板（pending_review 等）。必须在 db sync 之后跑：对账前算的是旧单，
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
                       cv: Path | None = None, sync: bool = True) -> None:
    """已对好条目（status=done／publish-mismatch，续跑补发用）的册：同步进中心库（不碰字形库）→ 发布这一批 → 逐册核线上能读到 → 核过的清盘。
    rev 不再升，没有「想要的版本」可核；以发站 run 成功＋线上单读得到为准。"""
    from ..land import verify_live
    audit_books(ws, done, book_text, text_id, state, sp)          # 产物包核过就清，所以在发布前出机器改字抽检数据
    if sync:
        sync_retry(ws)
        refresh_progress(done, text_id, cv, state)                   # 新单已进中心库，看板才算得对
    save_state(sp, state)
    if os.environ.get("GUJI_SWAP_NO_PUBLISH"):          # 并行分片时不各自发布（网站发布 workflow 串行排队、互相取消），最后统一发
        for b in done:
            state["books"][b].update(status="done", publish="deferred")
        save_state(sp, state)
        return
    concl = publish_batch(done, text_id)
    for b in done:
        # 发站没成功（failure／cancelled／no-run／timeout）一律不算 verified，哪怕线上碰巧读得到：
        # 11-24 011 状态 verified、实际 proofing-sync 失败，线上停在 011-r13
        ok = concl == "success" and verify_live(text_id, vol_no(b), None)
        state["books"][b].update(status="verified" if ok else "publish-mismatch", publish=concl)
        if ok:
            for p in (ws / "_packs").glob(f"*/{b}"):
                shutil.rmtree(p, ignore_errors=True)
    save_state(sp, state)


def land_chunk(ws: Path, chunk: list[str], text_id: str, mains: dict, book_text: str, log: Path, text_apply: bool = True) -> dict[str, dict]:
    """这一批：每册取 ★main 包，再一次 ``guji land <这批> --apply``（对账、推库、发站、核线上都在 land 里）。返回 {册: {verdict, why}}。
    verdict：verified（有变、已发站且线上核过）、fresh（条目没变）、publish-mismatch（有变但发站没成）、blocked（land 拒绝或没有 main 包）、land-failed。"""
    env = {**os.environ, "GUJI_DB_NO_GLYPH": "1", "GUJI_WORKSPACE": str(ws)}
    cv_cli = [sys.executable, "-m", "open_guji_cv.cli_v2"]
    res: dict[str, dict] = {}
    ready: list[str] = []
    with open(log, "w", encoding="utf-8") as f:
        for b in chunk:
            if not mains.get(b):
                res[b] = {"verdict": "blocked", "why": "没有 ★main 包可对账"}
                continue
            r = subprocess.run([*cv_cli, "products", "pack", "fetch", b, "--label", mains[b], "-w", str(ws), "--force"],
                               env=env, stdout=f, stderr=subprocess.STDOUT)
            if r.returncode:
                res[b] = {"verdict": "land-failed", "why": f"取 main 包 {mains[b]} 失败（退出码 {r.returncode}）"}
            else:
                ready.append(b)
        if not ready:
            return res
        no_pub = bool(os.environ.get("GUJI_SWAP_NO_PUBLISH"))      # 并行分片：各片只对账推库，最后统一发（续跑时 done 的册补发）
        cmd = [*cv_cli, "land", ",".join(ready), "-w", str(ws), "--text-id", text_id, "--apply", *(["--no-publish"] if no_pub else []),
               *(["--book-text", book_text, "--text-apply"] if text_apply else [])]
        r = subprocess.run(cmd, env=env, capture_output=True, text=True)
        f.write(r.stdout + r.stderr)
    summary = {}
    for line in reversed(r.stdout.splitlines()):         # land 最后印一行 JSON：{changed, unchanged, blocked}
        if line.startswith("{") and '"changed"' in line:
            try:
                summary = json.loads(line)
            except ValueError:
                pass
            break
    if not summary:
        for b in ready:
            res[b] = {"verdict": "land-failed", "why": f"land 没给结论（退出码 {r.returncode}），见 {log}"}
        return res
    for b in ready:
        if b in (summary.get("blocked") or {}):
            res[b] = {"verdict": "blocked", "why": str(summary["blocked"][b].get("why", ""))}
        elif b in (summary.get("unchanged") or []):
            res[b] = {"verdict": "fresh", "why": "条目与 main 包一致，没动"}
        elif b in (summary.get("changed") or []):
            res[b] = {"verdict": ("done" if no_pub else "verified") if r.returncode == 0 else "publish-mismatch",
                      "why": "land 已对账" + ("、发站并核过" if r.returncode == 0 else f"，但发站没成或线上格数对不上（land 退出码 {r.returncode}）")}
        else:
            res[b] = {"verdict": "land-failed", "why": f"land 结论里没有这册（退出码 {r.returncode}）"}
    return res


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
    text_id = a.text_id
    precheck(ws, state, text_id)
    save_state(sp, state)
    if text_id == DIANBEN_ID and any(not b.startswith("vol") for b in parse_books(a.books)):
        raise SystemExit("非殿本的册（纯数字册名）要写 --text-id <书 ID>（全唐文 995ejelvk0、史記 988g3f0wsu）")
    cv = Path(a.cv)
    env = {**os.environ, "GUJI_DB_NO_GLYPH": "1", "GUJI_WORKSPACE": str(ws)}
    books = parse_books(a.books)
    mains = {b: current_main(ws, b) for b in books}
    for b in books:                                      # 状态按「册＋主包」记：标了新 main 的册，旧结论作废（全唐文 11-20 d2 29 册假 verified）
        st = state["books"].get(b)
        if st and st.get("main") and mains[b] and mains[b] != st["main"]:
            print(f"{b}：主包 {st['main']} → {mains[b]}，上次的「{st.get('status')}」作废，重做", file=sys.stderr)
            state["books"][b] = {"status": "stale-main", "why": f"上次结论基于 {st['main']}"}
    # 上次换好单但没发布成/没核过的册：只补「发布＋核对」，不能再跑 land（条目已对到 main，只剩发站）
    pub_only = [b for b in books if state["books"].get(b, {}).get("status") in ("done", "publish-mismatch")]
    todo = [b for b in books if state["books"].get(b, {}).get("status") not in ("verified", "done", "publish-mismatch")]
    print(f"待处理 {len(todo)} 册", file=sys.stderr)
    if a.dry_run:
        print(json.dumps({"todo": todo, "publish_only": pub_only, "state_file": str(sp)}, ensure_ascii=False))
        return 0
    for chunk in chunks(pub_only, a.batch_size):
        precheck(ws, state, text_id)
        publish_and_verify(ws, chunk, text_id, state, sp, Path(a.book_text), cv)
    for flag, why in (("ack_unlanded_votes", "票按条目记，对账不动条目 id"), ("land_votes", "要落票请先 guji collect"),
                      ("hand_cells", "手加格条目 land 不会关掉"), ("no_single_sync", "land 每册只推条目文件")):
        if getattr(a, flag, None):
            print(f"⚠ --{flag.replace('_', '-')} 已不起作用（换单改走 guji land）：{why}", file=sys.stderr)
    if todo and not a.no_pull:
        unpushed = any(v.get("status") in ("done", "publish-mismatch") for v in state["books"].values())
        if pull_workspace(ws, force_ok=not unpushed):
            print("⚠ guji db pull 没成：照现有本地库往下做（land 对账前会再拉这册的条目文件）", file=sys.stderr)
    landed: list[str] = []
    for chunk in chunks(todo, a.batch_size):
        precheck(ws, state, text_id)                         # 每批之间再核一次账本与磁盘（磁盘不够先自动清）
        log = ws / "reports" / "_swap" / f"{chunk[0]}-{chunk[-1]}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        res = land_chunk(ws, chunk, text_id, mains, a.book_text, log, text_apply=not getattr(a, "no_text_apply", False))
        for b in chunk:
            r = res[b]
            state["books"][b] = {"status": r["verdict"], "why": r["why"][:300], "main": mains.get(b)}
            if r["verdict"] == "verified":
                landed.append(b)
        save_state(sp, state)
    if landed:
        refresh_progress(landed, text_id, cv, state)         # land 已推库、发站，看板才算得对
        save_state(sp, state)
    rep = write_audit_report(ws, state)
    if rep:
        print(f"机器改字抽检表：{rep}", file=sys.stderr)
    left = {k: v for k, v in state["books"].items() if v["status"] not in ("verified", "fresh")}
    print(json.dumps({"verified": sorted(k for k, v in state["books"].items() if v["status"] == "verified"),
                      "fresh": sorted(k for k, v in state["books"].items() if v["status"] == "fresh"),
                      "left": {k: v["status"] for k, v in left.items()}}, ensure_ascii=False))
    return 0 if not left else 2


def add_parser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("swap", help="换单 driver：出新单→同步→分批发布→核线上→清盘（断点续跑）")
    p.add_argument("action", choices=["run", "audit", "book-text", "finish-merged", "doctor"],
                   help="run 换单；audit 机器改字抽检；book-text 把已导出的新包落 book-text（格号变了按格级对照表走，见 swap/booktext.py）；"
                        "doctor 开跑前自检（令牌、-w、cv、book-text 稀疏检出、CNN 权重、磁盘；--fix 补模型与稀疏检出，--env 打印 export 行）")
    p.add_argument("--books", default=None, help="如 vol20-vol99 或 vol23,vol24（doctor 可不给：给了才核各册引擎的模型）")
    p.add_argument("-w", "--workspace", required=True)
    p.add_argument("--book-text", required=True)
    p.add_argument("--text-id", default=DIANBEN_ID, help="book-text 书 ID（缺省殿本；全唐文 995ejelvk0、史記 988g3f0wsu）")
    p.add_argument("--cv", default=os.environ.get("GUJI_CV", str(Path.home() / "cv")), help="open-guji-cv 检出目录")
    p.add_argument("--batch-size", type=int, default=6, help="每批几册（一批一次 guji land，也是发站的一批）")
    p.add_argument("--publish-batch", type=int, default=10, help="（已不起作用：发站按 --batch-size 一批）")
    p.add_argument("--no-single-sync", action="store_true", help="（已不起作用）")
    p.add_argument("--no-text-apply", action="store_true", help="run：land 不把机器改字写回 book-text（缺省写：land --book-text --text-apply）")
    p.add_argument("--no-pull", action="store_true", help="run：开跑不先 db pull（刚拉过）")
    p.add_argument("--hand-cells", help="（已不起作用：手加格条目 land 不会关掉）")
    p.add_argument("--state", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--export", help="book-text：导出目录（缺省取 reports/<册>/_cycle/ 下最新的 export）")
    p.add_argument("--worktree", help="book-text：独立 worktree 路径（缺省 <book-text>-swap，每册重置到 origin/dev）")
    p.add_argument("--note", help="book-text：文本线版本记录的说明")
    p.add_argument("--push", action="store_true", help="book-text：过了守卫和 local_check 就推（0.x 推 dev；1.x 推 swap/<册>-1x 分支待开 PR）")
    p.add_argument("--glyph-db", help="book-text：字形库 sqlite（R1 前置闸：库里刻例的格键须都在新包里，否则停 r1-stop；不给则只标「R1 未核」）")
    p.add_argument("--ack-unlanded-votes", metavar="原因", default=None,
                   help="（已不起作用：票按条目记）")
    p.add_argument("--land-votes", action="store_true",
                   help="（已不起作用：要落票请先 guji collect）")
    p.add_argument("--no-pr", action="store_true", help="book-text：1.x 推 swap/<册>-1x 后不自动开草稿 PR（缺省开，需 gh）")
    p.add_argument("--table", help="finish-merged：指定对照表 tsv（缺省取 book-text lineage/revisions/<册>-*.tsv 最新一张）")
    p.add_argument("--commit", help="finish-merged：合并提交号（记进 metrics）")
    p.add_argument("--fix", action="store_true", help="doctor：取缺的模型（cv 与各册引擎 worktree）、book-text 稀疏检出补本书目录")
    p.add_argument("--env", action="store_true", help="doctor：打印可 eval 的 export 行（PATH、PYTHONPATH、GUJI_CV、GUJI_WORKSPACE）")


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
    if args.action == "doctor":
        from .doctor import cmd_doctor
        return cmd_doctor(args, parse_books(args.books) if args.books else [])
    if not args.books:
        raise SystemExit(f"swap {args.action} 要给 --books")
    if args.action == "finish-merged":
        from .booktext import cmd_finish_merged
        return cmd_finish_merged(args, parse_books(args.books))
    if args.action == "book-text":
        from .booktext import cmd_book_text
        return cmd_book_text(args, parse_books(args.books))
    return cmd_audit(args) if args.action == "audit" else cmd_run(args)


COMMANDS = {"swap": (add_parser, cmd_swap)}
