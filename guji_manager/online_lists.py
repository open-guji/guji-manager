"""标 main 之后自动重出这册的线上待审单（入口点组 `guji.post_promote`，cv `cli_products._note_main` 调用）。

以前靠定时任务每 2 小时轮询 ★ main 包（ai-team `sync_online_lists.py`）；现在改成标 main 这个动作自己触发，不再轮询。
做法同那个脚本：线上单发布时存过 `rev-<rev>` 包，字节数与新 main 包相同＝内容相同＝不用重出。

不自动重出（只在输出里提示）：文本挂了标点／实体层的册（机器改字会让实体校验不过，要走 proof_cycle 落票）、
旧单上已有票的册、还没有线上单的册、线上单没存 rev 包的册（没法确认出自哪个包）。缺令牌／工作区／book-text 时也只提示。
重出要 5–10 分钟，所以起一个脱离终端的子进程跑，日志在 `<工作区>/reports/<册>/_publish/auto_issue.log`。

环境变量：`GUJI_DATA_TOKEN_PROD`（推库）、`GUJI_DATA_TOKEN_READ`（读包、读票）、`GUJI_BOOK_TEXT`（book-text 仓，缺省 /home/user/book-text）、
`GUJI_CV_REPO`（cv 仓，缺省 /home/user/open-guji/open-guji-cv）、`GUJI_AUTO_ONLINE_LISTS=0` 可整体关掉。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

BOOK_ID = "96mid1ogzk"
DATA = "https://data.openguji.com"
GUJI = os.environ.get("GUJI_BIN", "guji")


def _cfg() -> dict:
    return {"book_text": os.environ.get("GUJI_BOOK_TEXT", "/home/user/book-text"),
            "cv": os.environ.get("GUJI_CV_REPO", "/home/user/open-guji/open-guji-cv")}


def record_main(book: str, label: str) -> None:
    """把「这册现在的 ★ main 标签」记到后台看板（progress.volume.extra 的 a31.main），页面据此标出线上单有没有追上 main。
    只写看板、永远不抛；连不上库（没有 NEON_DATABASE_URL／没装 cv）就静默跳过。"""
    try:
        if not (book.startswith("vol") and book[3:].isdigit()):
            return
        if not (os.environ.get("NEON_DATABASE_URL") or os.environ.get("GUJI_DATA_PG_DSN")):
            return
        from open_guji_cv.datastore.connect import connect
        payload = json.dumps({"extra": {"a31.main": {"label": label, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}}})
        with connect() as con:
            con.execute("SELECT progress.put_volume(%s, %s, %s::jsonb, %s)", (BOOK_ID, book[3:].zfill(3), payload, "A31"))
    except Exception as e:  # noqa: BLE001
        print(f"（后台看板没记上 main 标签：{e}）")


def on_promote(book: str, label: str, ws: str | None = None) -> None:
    """cv 标 main 后调用。永远不抛：自动重出失败不能挡标 main。"""
    record_main(book, label)
    try:
        if os.environ.get("GUJI_AUTO_ONLINE_LISTS", "1") == "0":
            return
        if not (book.startswith("vol") and book[3:].isdigit()):
            return
        c = _cfg()
        missing = [n for n, ok in (("GUJI_DATA_TOKEN_PROD", bool(os.environ.get("GUJI_DATA_TOKEN_PROD"))),
                                   ("GUJI_DATA_TOKEN_READ", bool(os.environ.get("GUJI_DATA_TOKEN_READ"))),
                                   ("工作区", bool(ws)), ("book-text", os.path.isdir(c["book_text"])),
                                   ("cv 仓", os.path.isdir(c["cv"]))) if not ok]
        if missing:
            print(f"（线上单没自动重出：缺 {'、'.join(missing)}；换到有这些的机器上跑 `python -m guji_manager.online_lists --vol {book} -w <工作区>`）")
            return
        log_dir = os.path.join(ws, "reports", book, "_publish")
        os.makedirs(log_dir, exist_ok=True)
        log = os.path.join(log_dir, "auto_issue.log")
        with open(log, "ab") as f:
            subprocess.Popen([sys.executable, "-u", "-m", "guji_manager.online_lists", "--vol", book, "-w", ws, "--label", label],
                             stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        print(f"线上单自动重出已在后台起（5–10 分钟），日志 {log}")
    except Exception as e:  # noqa: BLE001
        print(f"（线上单自动重出没起来：{e}）")


def _packs(vol: str, ws: str, env: dict) -> list[dict]:
    out = subprocess.run([GUJI, "products", "pack", "list", vol, "-w", ws], capture_output=True, text=True, env=env).stdout
    rows = []
    for ln in out.splitlines():
        parts = ln.lstrip("★ ").split("\t")
        if len(parts) >= 2 and parts[0].strip().startswith("products/"):
            rows.append({"star": ln.startswith("★"), "label": parts[0].strip().rsplit("/", 1)[1], "size": int(parts[1])})
    return rows


def _online_rev(ch: str) -> str | None:
    with urllib.request.urlopen(f"{DATA}/proof/{BOOK_ID}/{ch}.pending.json") as r:
        return json.loads(r.read()).get("rev")


def _votes(vol: str, ws: str, cv: str, env: dict) -> int:
    for _ in range(3):   # 网站读票接口偶发 500
        out = subprocess.run([sys.executable, f"{cv}/scripts/zhengli/proof_cycle.py", "status", "--book", vol, "-w", ws],
                             capture_output=True, text=True, env=env, cwd=cv).stdout.strip().splitlines()
        if out:
            try:
                return json.loads(out[-1]).get("voted", 0)
            except ValueError:
                pass
        time.sleep(15)
    return -1


def follow_main(vol: str, ws: str) -> int:
    """前台跑完整流程；返回 0＝已重出或无需重出，非 0＝该人工处理（原因已打印）。"""
    c = _cfg()
    base = {**os.environ, "PYTHONPATH": c["cv"]}
    read_env = {**base, "GUJI_DATA_TOKEN": os.environ["GUJI_DATA_TOKEN_READ"]}
    write_env = {**base, "GUJI_DATA_TOKEN": os.environ["GUJI_DATA_TOKEN_PROD"], "GUJI_PRODUCTS_DIR": "/home/user/prod_issue"}
    os.makedirs("/home/user/prod_issue", exist_ok=True)
    ch = f"0{vol[3:]}"
    rows = _packs(vol, ws, read_env)
    star = next((r for r in rows if r["star"]), None)
    if not star:
        print(f"{vol}: 没有 ★ main 包"); return 1
    if os.path.exists(f"{c['book_text']}/Book/g/z/k/{BOOK_ID}/default/{ch}.punct.json"):
        print(f"{vol}: 文本挂了标点／实体层，不自动重出；走 proof_cycle plan/apply（A32）"); return 1
    try:
        rev = _online_rev(ch)
    except Exception as e:  # noqa: BLE001
        print(f"{vol}: 还没有线上单（首发另行决定）：{e}"); return 1
    rp = next((r for r in rows if r["label"] == f"rev-{rev}"), None)
    if rp and rp["size"] == star["size"]:
        print(f"{vol}: 线上单 {rev} 已与 main 包 {star['label']} 一致"); return 0
    if not rp:
        print(f"{vol}: 线上单 {rev} 没存 rev 包，没法确认出自哪个包，不盲目重出；请人工 `republish.py issue`"); return 1
    n = _votes(vol, ws, c["cv"], read_env)
    if n != 0:
        print(f"{vol}: 旧单{'读不到票' if n < 0 else f'已有票（{n}）'}，不自动换；先走 proof_cycle plan/apply"); return 1
    print(f"{vol}: 线上单 {rev} 落后于 main {star['label']}，重出单")
    subprocess.run([GUJI, "source", "pull", vol, "-w", ws], env=read_env, capture_output=True)
    rc = 1
    for _ in range(3):   # 读票接口偶发 500／握手失败
        rc = subprocess.run([sys.executable, "-u", f"{c['cv']}/scripts/zhengli/republish.py", "issue", "--book", vol, "-w", ws,
                             "--label", star["label"], "--book-text", c["book_text"], "--no-pull", "--no-wait"],
                            env=write_env, cwd=c["cv"]).returncode
        if rc == 0:
            break
        time.sleep(60)
    print(f"{vol}: issue 退出码 {rc}")
    if rc == 0:
        subprocess.run(["gh", "workflow", "run", "proofing-sync.yml", "-R", "open-guji/kaiyuanguji-web", "--ref", "main",
                        "-f", "target=production", "-f", "parts=publish", "-f", "dry_run=false", "-f", f"only={BOOK_ID}/{ch}"])
        print(f"{vol}: 已触发网站 proofing-sync")
    return rc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="按 ★ main 包重出一册的线上待审单（标 main 后自动调，也可手动跑）")
    ap.add_argument("--vol", required=True)
    ap.add_argument("-w", "--ws", required=True)
    ap.add_argument("--label", default="", help="（只做记录）刚标 main 的标签")
    a = ap.parse_args(argv)
    return follow_main(a.vol, a.ws)


if __name__ == "__main__":
    sys.exit(main())
