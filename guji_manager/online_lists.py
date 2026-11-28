"""标 main 之后自动把这册线上待审条目对到新 main 包（入口点组 `guji.post_promote`，cv `cli_products._note_main` 调用）。

2026-11-27 起走 `guji land`（待审清理计划 1.7）：取 ★ main 包 → `guji land <册> --apply`（新待审格对着中心库条目对账，没变不动、
变了就地覆盖，rev 不升、不整张换单，只发有变的册）。不再调 cv 的 `republish.py issue`／`proof_cycle.py status`，也不再有「旧单已有票就不自动换」的闸：
票按条目记，对账不动条目 id，票不丢；只有挪格且章上还有按旧 rev 记的票时 land 自己拒绝（退出码 4，要先 `guji collect` 落票）。
是否已对到当前 main：看 `<工作区>/reports/<册>/_land/landed.json` 里记的包标签＝★ main 标签（取代以前比线上单 `rev-<rev>` 包）。

book-text 默认不动（land 只改条目与线上单）；要连机器改字一起落 book-text：`GUJI_AUTO_LAND_TEXT=1`（land `--book-text --text-apply`）。
重出要 5–10 分钟，所以起一个脱离终端的子进程跑，日志在 `<工作区>/reports/<册>/_publish/auto_issue.log`。

环境变量：`GUJI_DATA_TOKEN_PROD`（推库）、`GUJI_DATA_TOKEN_READ`（读包）、`GUJI_BOOK_TEXT`（book-text 仓，缺省 /home/user/book-text，只在 `GUJI_AUTO_LAND_TEXT=1` 时用）、
`GUJI_CV_REPO`（cv 仓，只用来补 PYTHONPATH）、`GUJI_AUTO_ONLINE_LISTS=0` 可整体关掉。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.request

BOOK_ID = "96mid1ogzk"          # 殿本；册 yaml 没写 book_id、工作区目录名也认不出时的老口径（只对 volNN）
_BOOK_ID_RE = re.compile(r"[0-9a-z]{10}")
DATA = "https://data.openguji.com"


def _guji_cmd() -> list[str]:
    """`guji` 命令：GUJI_BIN → 本解释器同目录的 guji → PATH 上的 guji → `python -c` 直接调入口。
    标 main 钩子在别的会话的 venv 里起，PATH 上常没有 guji（QTW 11-07 踩过）。"""
    if os.environ.get("GUJI_BIN"):
        return [os.environ["GUJI_BIN"]]
    here = os.path.join(os.path.dirname(sys.executable), "guji")
    if os.path.exists(here):
        return [here]
    import shutil
    if shutil.which("guji"):
        return ["guji"]
    return [sys.executable, "-c", "import sys; from open_guji_cv.cli_v2 import main; sys.argv[0] = 'guji'; sys.exit(main())"]


GUJI = _guji_cmd()


def _cv_repo() -> str:
    """cv 仓：GUJI_CV_REPO → 本解释器装的 open_guji_cv 所在仓 → 老默认。
    写死老路径会用到过期 checkout（11-16：旧 cv 的 export_guji_format 要 --meta，007–015 自动重出全败）。"""
    if os.environ.get("GUJI_CV_REPO"):
        return os.environ["GUJI_CV_REPO"]
    try:
        import importlib.util
        spec = importlib.util.find_spec("open_guji_cv")
        if spec and spec.origin:
            root = os.path.dirname(os.path.dirname(spec.origin))
            if os.path.exists(os.path.join(root, "open_guji_cv", "__init__.py")):
                return root
    except Exception:  # noqa: BLE001
        pass
    return "/home/user/open-guji/open-guji-cv"


def _cfg() -> dict:
    return {"book_text": os.environ.get("GUJI_BOOK_TEXT", "/home/user/book-text"), "cv": _cv_repo()}


def ident(book: str, ws: str | None = None) -> tuple[str | None, str | None]:
    """册名 → (书 id, book-text 章号)。按册配置（cv `core/volume_id`，11-02 统一册号）；
    书 id 依次取册 yaml 的 `book_id`、工作区目录名 `<书id>-<书名>`；老 cv 没有 volume_of 时只认殿本 volNN。"""
    if ws:
        os.environ.setdefault("GUJI_WORKSPACE", ws)
    try:
        from ._cv import volume_of
        v = volume_of(book)
        bid = v.book_id
        if not bid and ws:
            bid = os.path.basename(os.path.normpath(ws)).split("-", 1)[0]
        if not (bid and _BOOK_ID_RE.fullmatch(bid)):
            bid = BOOK_ID if re.fullmatch(r"vol\d+", book) else None
        return bid, v.chapter
    except Exception:  # noqa: BLE001 —— 老 cv：只认殿本 volNN
        m = re.fullmatch(r"vol(\d+)", book)
        return (BOOK_ID, m.group(1).zfill(3)) if m else (None, None)


def book_text_dir(book_text: str, book_id: str) -> str:
    """book-text 条目目录：Book/<id 倒数第三>/<倒数第二>/<末字>/<id>。"""
    return f"{book_text}/Book/{book_id[-3]}/{book_id[-2]}/{book_id[-1]}/{book_id}"


def record_main(book: str, label: str, ws: str | None = None) -> None:
    """把「这册现在的 ★ main 标签」记到后台看板（progress.volume.extra 的 a31.main），页面据此标出线上单有没有追上 main。
    只写看板、永远不抛；连不上库（没有 GUJI_DATA_TOKEN／没装 cv）就静默跳过。"""
    try:
        bid, ch = ident(book, ws)
        if not (bid and ch):
            return
        if not (os.environ.get("GUJI_DATA_TOKEN") or os.environ.get("GUJI_DATA_SQLITE")):
            return
        from ._cv import connect
        payload = json.dumps({"extra": {"a31.main": {"label": label, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}}})
        with connect() as con:
            con.execute("SELECT progress.put_volume(%s, %s, %s::jsonb, %s)", (bid, ch, payload, "A31"))
    except Exception as e:  # noqa: BLE001
        print(f"（后台看板没记上 main 标签：{e}）")


def _note_round(bid: str, label: str) -> None:
    try:
        from .iterate.progress_rounds import note_main_round
        note_main_round(bid, label)
    except Exception as e:  # noqa: BLE001
        print(f"（看板没占上这一轮：{e}）")


def _promote_from_packs(bid: str, ch: str, label: str) -> bool:
    """标 main 后：这册 ★main 包存包时已把人审率写进 extra['cv.packs']（`pack_stats.record`）→ 直接转成看板的包口径 `cv.pack`
    并收这一轮（`auto_round`）。库里没有这个包的数（旧包、存包的机器没连库）返回 False，由调用方走老办法（下包重算）。"""
    try:
        import json
        import time
        from ._cv import connect
        from .iterate.progress_rounds import auto_round
        from .pack_stats import pack_of
        with connect() as conn:
            row = conn.execute("SELECT extra FROM progress.volume WHERE book_id = %s AND vol = %s", (bid, ch)).fetchone()
            st = pack_of((row[0] if row else None), label)
            if not st:
                return False
            pack = {"label": label, "cells": st["cells"], "review": st["review"], "rate": round(st["review"] / st["cells"], 5),
                    "pick": "main", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            conn.execute("SELECT progress.put_volume(%s, %s, %s::jsonb, %s)", (bid, ch, json.dumps({"extra": {"cv.pack": pack}}, ensure_ascii=False), "A31"))
        auto_round(bid, label)
        print(f"包口径人审率取自存包时的统计：{label} 待审 {st['review']} / {st['cells']} 格，已写看板并收轮")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"（从存包统计取人审率没成：{e}；改走下包重算）")
        return False


def push_pack_rate(book: str, ws: str | None, label: str | None = None) -> None:
    """标 main 后在后台统计这册 ★main 包的人审率，写进后台看板（progress.volume.extra['cv.pack']）。
    要 ai-team 检出（GUJI_AITEAM_REPO，缺省 ~/ai-team）、工作区、GUJI_DATA_TOKEN；缺了就静默跳过。永远不抛。"""
    try:
        bid, ch = ident(book, ws)
        if not ws or not (bid and ch):
            return
        if not (os.environ.get("GUJI_DATA_TOKEN") or os.environ.get("GUJI_DATA_SQLITE")):
            return
        if label:
            _note_round(bid, label)   # 先占位：后面的统计跑不成，看板也看得到这一轮
            if _promote_from_packs(bid, ch, label):
                return                # 存包时已随包算好待审数：直接用，不用再下包重算（也不再依赖 ai-team 检出）
        from .progress_sync import RUN_PY, ensure_ai_team
        team = ensure_ai_team()     # 没有检出就自己浅克隆一份；以前这里缺检出静默跳过，看板包口径就此停住（11-08）
        run_py = str(team.joinpath(*RUN_PY)) if team else ""
        if not run_py:
            print("（包口径人审率没自动更新：没有 ai-team 检出且克隆失败；设 GUJI_AITEAM_REPO。看板「迭代轮次」已先占位，"
                  "之后 `guji-manager progress-sync --fix` 会补）")
            return
        out = os.path.join(ws, "reports", book, "_pack_rate")
        os.makedirs(out, exist_ok=True)
        # run.py 要调 `guji` 命令：venv 的 bin 可能不在 PATH 里，把 sys.executable 所在目录补到最前面
        env = dict(os.environ)
        env["PATH"] = os.path.dirname(sys.executable) + os.pathsep + env.get("PATH", "")
        with open(os.path.join(out, "run.log"), "ab") as f:
            # 包口径写完后接着汇总这一轮，写后台「迭代轮次」（每标一册更新一次，册数随之增长）
            cmd = [sys.executable, "-u", run_py, "--ws", ws, "--vol-names", book, "--pick", "main", "--out", out, "--push-progress", bid]
            nxt = [sys.executable, "-u", "-m", "guji_manager.iterate", "auto-round", "--book", bid, "--label", label] if label else None
            sh = " ".join(shlex.quote(x) for x in cmd) + (" && " + " ".join(shlex.quote(x) for x in nxt) if nxt else "")
            subprocess.Popen(["/bin/sh", "-c", sh], stdout=f, stderr=subprocess.STDOUT, start_new_session=True, env=env)
        print(f"包口径人审率已在后台统计并写看板{'，随后汇总本轮写「迭代轮次」' if label else ''}，日志 {out}/run.log")
    except Exception as e:  # noqa: BLE001
        print(f"（包口径人审率没起来：{e}）")


def on_promote(book: str, label: str, ws: str | None = None) -> None:
    """cv 标 main 后调用。永远不抛：自动对账失败不能挡标 main。"""
    record_main(book, label, ws)
    push_pack_rate(book, ws, label)
    try:
        if os.environ.get("GUJI_AUTO_ONLINE_LISTS", "1") == "0":
            return
        bid, ch = ident(book, ws)
        if not (bid and ch):      # 认不出的册（试验册等）静默跳过，同 record_main
            return
        # 首发册（从没 land 过：无 landed.json）不自动上站：首发要等站点侧就绪（D1、页面登记），由 `guji launch` 或人显式 land；
        # 要恢复旧行为设 GUJI_AUTO_LAND_FIRST=1（MJ 脉经 11-28：标 main 自动起 land 被杀）
        if ws and landed_pack(book, ws) is None and os.environ.get("GUJI_AUTO_LAND_FIRST") != "1":
            print(f"（{book} 还没上过站，标 main 不自动 land；首发走 `guji launch {book}`，或设 GUJI_AUTO_LAND_FIRST=1 开自动）")
            return
        c = _cfg()
        missing = [n for n, ok in (("GUJI_DATA_TOKEN_PROD", bool(os.environ.get("GUJI_DATA_TOKEN_PROD"))),
                                   ("GUJI_DATA_TOKEN_READ", bool(os.environ.get("GUJI_DATA_TOKEN_READ"))),
                                   ("工作区", bool(ws)),
                                   ("book-text", os.environ.get("GUJI_AUTO_LAND_TEXT") != "1" or os.path.isdir(c["book_text"]))) if not ok]
        if missing:
            print(f"（线上单没自动对账：缺 {'、'.join(missing)}；换到有这些的机器上跑 `python -m guji_manager.online_lists --vol {book} -w <工作区>`）")
            return
        log_dir = os.path.join(ws, "reports", book, "_publish")
        os.makedirs(log_dir, exist_ok=True)
        log = os.path.join(log_dir, "auto_issue.log")
        with open(log, "ab") as f:
            subprocess.Popen([sys.executable, "-u", "-m", "guji_manager.online_lists", "--vol", book, "-w", ws, "--label", label],
                             stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        print(f"线上单自动对账（guji land）已在后台起（5–10 分钟），日志 {log}")
    except Exception as e:  # noqa: BLE001
        print(f"（线上单自动对账没起来：{e}）")


def _pypath(cv: str) -> str:
    """子进程 PYTHONPATH：cv ＋ 本 manager ＋ 原来的。不能只写 cv：整个盖掉原值会把 guji-manager 挤出路径，
    cv 里已搬走的命令（products pack list 等）就只打一句「已搬到 guji-manager」（11-16 --audit 12 册全报没有 ★ main 包）。"""
    mgr = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.pathsep.join(x for x in (cv, mgr, os.environ.get("PYTHONPATH", "")) if x)


def _packs(vol: str, ws: str, env: dict) -> list[dict]:
    r = subprocess.run([*GUJI, "products", "pack", "list", vol, "-w", ws], capture_output=True, text=True, env=env)
    out = r.stdout
    if "已搬到" in out or (r.returncode and not out.strip()):
        raise RuntimeError(f"`guji products pack list {vol}` 没出包清单（{(out or r.stderr).strip()[:120]}）：多半 guji-manager 不在子进程的 PYTHONPATH 上")
    rows = []
    for ln in out.splitlines():
        parts = ln.lstrip("★ ").split("\t")
        if len(parts) >= 2 and parts[0].strip().startswith("products/"):
            m = re.search(r"cv (\S+) 语料 (\d+)", ln)
            rows.append({"star": ln.startswith("★"), "label": parts[0].strip().rsplit("/", 1)[1], "size": int(parts[1]),
                         "cv": m.group(1) if m else None, "corpus": m.group(2) if m else None})
    return rows


def landed_pack(vol: str, ws: str) -> str | None:
    """这册上次 `guji land --apply` 对到的包标签（`_land/landed.json` 的 pack）；没落过返回 None。"""
    from pathlib import Path
    from .land import landed_path, read_json
    return (read_json(landed_path(Path(ws), vol), {}) or {}).get("pack")


def follow_main(vol: str, ws: str) -> int:
    """前台跑完整流程；返回 0＝已对账或无需对账，非 0＝该人工处理（原因已打印）。
    ★ main 包已对过 → 跳过；否则补原图、取 main 包、`guji land --apply`（对账＋推库＋发站，没变的册不发）。"""
    c = _cfg()
    base = {**os.environ, "PYTHONPATH": _pypath(c["cv"]), "GUJI_WORKSPACE": ws}
    read_env = {**base, "GUJI_DATA_TOKEN": os.environ["GUJI_DATA_TOKEN_READ"]}
    write_env = {**base, "GUJI_DATA_TOKEN": os.environ["GUJI_DATA_TOKEN_PROD"]}
    bid, ch = ident(vol, ws)
    if not (bid and ch):
        print(f"{vol}: 认不出书 id 或章号（册 yaml 写上 book_id、volume）"); return 1
    try:
        rows = _packs(vol, ws, read_env)
    except RuntimeError as e:
        print(f"{vol}: {e}"); return 1
    star = next((r for r in rows if r["star"]), None)
    if not star:
        print(f"{vol}: 没有 ★ main 包"); return 1
    done = landed_pack(vol, ws)
    if done == star["label"]:
        print(f"{vol}: 条目已对到 main 包 {star['label']}"); return 0
    print(f"{vol}: 条目上次对到 {done or '（没对过）'}，main 是 {star['label']}，走 guji land 对账")
    subprocess.run([*GUJI, "source", "pull", vol, "-w", ws], env=read_env, capture_output=True)
    rc = subprocess.run([*GUJI, "products", "pack", "fetch", vol, "--label", star["label"], "-w", ws, "--force"], env=read_env).returncode
    if rc:
        print(f"{vol}: 取 main 包 {star['label']} 失败（退出码 {rc}）"); return rc
    cmd = [*GUJI, "land", vol, "-w", ws, "--text-id", bid, "--apply"]
    if os.environ.get("GUJI_AUTO_LAND_TEXT") == "1":
        cmd += ["--book-text", c["book_text"], "--text-apply"]
    for _ in range(3):   # 读库偶发 500／握手失败；3＝发站没成、4＝land 拒绝（挪格＋旧票），重跑也一样，不重试
        rc = subprocess.run(cmd, env=write_env).returncode
        if rc in (0, 3, 4):
            break
        time.sleep(60)
    print(f"{vol}: land 退出码 {rc}" + {3: "（发站没成或线上格数对不上，见上面日志；修好后手动触发 proofing-sync only=…）",
                                      4: "（land 拒绝：挪格且章上还有按旧 rev 记的票，先 guji collect 落票）"}.get(rc, ""))
    return rc


def _vol_list(spec: str) -> list[str]:
    """`005-015,020` → ['005',…,'015','020']（3 位册号）。"""
    out: list[str] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part and part.replace("-", "").isdigit():
            a, b = part.split("-", 1)
            out += [str(i).zfill(len(a)) for i in range(int(a), int(b) + 1)]
        else:
            out.append(part)
    return out


def _live_list(bid: str, ch: str) -> dict:
    with urllib.request.urlopen(f"{DATA}/proof/{bid}/{ch}.pending.json") as r:
        return json.loads(r.read())


def audit(vols: list[str], ws: str, fix: bool = False) -> int:
    """核对网站上各册待审单：①条目上次对到的包 = 当前 ★ main 包（land 的 landed.json）？②每格 alt（相似字备选）非空？
    不一致打印并返回非 0；`fix` 时对「落后于 main」的册调 follow_main（guji land 对账）。
    11-16 起因：x1 标 main 后自动重出大半失败，网站上 005–015 还是 11-08 的旧单，格子没有备选字，没人发现。
    建议标 main 后（on_promote 已调 follow_main）和每日各跑一次。"""
    c = _cfg()
    read_env = {**os.environ, "PYTHONPATH": _pypath(c["cv"]), "GUJI_DATA_TOKEN": os.environ.get("GUJI_DATA_TOKEN_READ", os.environ.get("GUJI_DATA_TOKEN", ""))}
    bad = 0
    for vol in vols:
        bid, ch = ident(vol, ws)
        if not (bid and ch):
            print(f"{vol}: 认不出书 id 或章号"); bad += 1; continue
        try:
            rows = _packs(vol, ws, read_env)
        except RuntimeError as e:
            print(f"{vol}: ✗ {e}"); bad += 1; continue
        star = next((r for r in rows if r["star"]), None)
        if not star:
            print(f"{vol}: 没有 ★ main 包，跳过"); continue
        try:
            doc = _live_list(bid, ch)
        except Exception as e:  # noqa: BLE001
            print(f"{vol}: 线上没有单子（{e}）"); bad += 1; continue
        rev = doc.get("rev")
        cells = doc.get("cells") or []
        no_alt = sum(1 for x in cells if not x.get("alt"))
        # 条目化后线上单 rev 不再随 main 升（land 就地改），不能比 rev 包；看这册上次 land 对到的包＝★ main 包。
        done = landed_pack(vol, ws)
        stale = done != star["label"]
        msgs = []
        if stale:
            msgs.append(f"落后于 main {star['label']}（条目上次对到 {done or '（没对过）'}，线上 {rev}）")
        if no_alt:
            msgs.append(f"{no_alt}/{len(cells)} 格没有备选字 alt")
        if not msgs:
            print(f"{vol}: ok（{rev}，{len(cells)} 格，alt 齐）"); continue
        bad += 1
        print(f"{vol}: ✗ " + "；".join(msgs))
        if fix and stale:
            if follow_main(vol, ws) == 0:
                bad -= 1
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="把一册线上待审条目对到 ★ main 包（guji land；标 main 后自动调，也可手动跑）；--audit 核对各册")
    ap.add_argument("--vol", help="单册：重出")
    ap.add_argument("--audit", help="核对这些册（如 005-015,020）：单子出自的包是否 ★ main、每格 alt 是否非空；有问题退出码 1")
    ap.add_argument("--fix", action="store_true", help="--audit 时顺带重出落后的册")
    ap.add_argument("-w", "--ws", required=True)
    ap.add_argument("--label", default="", help="（只做记录）刚标 main 的标签")
    a = ap.parse_args(argv)
    if a.audit:
        return audit(_vol_list(a.audit), a.ws, fix=a.fix)
    if not a.vol:
        ap.error("要 --vol 或 --audit")
    return follow_main(a.vol, a.ws)


if __name__ == "__main__":
    sys.exit(main())
