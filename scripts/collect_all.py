#!/usr/bin/env python3
"""定时批量收单（GM4）：读网站票 → 对每本有新票的书跑 ``guji collect`` → 有新落格的册触发网站发布。

不需要 AI：全是确定性命令。给 GitHub Action（.github/workflows/collect-all.yml）和手工都能用。

做什么（每本书）：
1. 查 web_inbox，找出有 cellreview 票的书（``--exclude`` 里的不管，如殿本、全唐文由原线程管）。
2. 建工作区目录（``<WS_ROOT>/<ws 目录名>/.central.json``），没拉过库就 ``guji db pull``。
3. ``guji collect --books auto``（写人裁事件、推库、定字落 book-text dev）。
4. 被「现格字块图拿不到」挡住的册：``guji source pull`` + ``guji products pack fetch --label rev-<单版>``，重试一次。
5. 本轮有写人裁／写 book-text 的册：触发 kaiyuanguji-web 的 proofing-sync（只发这些册）。
6. 把每本书的票账、被挡的册、要书线确认的格写进 ``$GITHUB_STEP_SUMMARY``（没有就打印）。

环境变量：GUJI_DATA_TOKEN_PROD／_READ（中心库）、GUJI_BOOK_TEXT（book-text 检出，已在 dev）、
GUJI_ACTOR（缺省 GM4）、GH_TOKEN_WEB（能触发 kaiyuanguji-web workflow 的令牌；缺省用 gh 当前登录）。
用法：python scripts/collect_all.py --ws-root ~/ws [--exclude 96mid1ogzk,995ejelvk0] [--only 988g3f0wsu] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_EXCLUDE = "96mid1ogzk,995ejelvk0"   # 殿本、全唐文：原收单线程在管


def sh(cmd, cwd=None, env=None, check=False, timeout=3300):
    r = subprocess.run(cmd, cwd=cwd, env=env, text=True, capture_output=True, timeout=timeout)
    out = (r.stdout or "") + (r.stderr or "")
    if check and r.returncode:
        raise SystemExit(f"命令失败：{' '.join(cmd)}\n{out[-2000:]}")
    return r.returncode, out


def books_with_votes(exclude: set[str]) -> dict[str, int]:
    from guji_manager.datastore.d1conn import connect
    c = connect("main")
    rows = c.execute("select book, count(*) from web_inbox where kind='cellreview' group by book").fetchall()
    return {r[0]: r[1] for r in rows if r[0] and r[0] not in exclude}


def ws_dir_names() -> dict[str, str]:
    from guji_manager.datastore.d1conn import connect
    c = connect("main")
    return {r[0]: r[1] for r in c.execute("select ws, dir from workspaces").fetchall()}


def book_text_path(book_id: str) -> str:
    return f"Book/{book_id[-3]}/{book_id[-2]}/{book_id[-1]}/{book_id}"


def ensure_workspace(ws_root: Path, ws_id: str, dir_name: str, env) -> Path:
    ws = ws_root / dir_name
    ws.mkdir(parents=True, exist_ok=True)
    marker = ws / ".central.json"
    if not marker.exists():
        marker.write_text(json.dumps({"ws": ws_id, "branch": "main"}), encoding="utf-8")
    data_home = Path(env.get("GUJI_DATA_HOME", str(Path.home() / ".guji-data")))
    if not (data_home / "main" / ws_id / "feedback").exists():
        e = dict(env, GUJI_DATA_TOKEN=env.get("GUJI_DATA_TOKEN_READ") or env.get("GUJI_DATA_TOKEN", ""))
        rc, out = sh(["guji", "db", "pull", "-w", str(ws)], env=e, timeout=3000)
        if rc:
            raise RuntimeError(f"db pull 失败：{out[-500:]}")
    return ws


def newest_ledger(ws: Path):
    runs = ws / "reports" / "_collect" / "runs"
    fs = sorted(runs.glob("*.ledger.tsv"), key=lambda p: p.stat().st_mtime) if runs.exists() else []
    if not fs:
        return []
    lines = [l.split("\t") for l in fs[-1].read_text(encoding="utf-8").splitlines()]
    hdr = lines[0]
    return [dict(zip(hdr, r)) for r in lines[1:] if r and r[0] and r[0] != "合计"]


def run_collect(ws: Path, book_id: str, book_text: str, env, extra):
    cmd = ["guji", "collect", "--books", "auto", "-w", str(ws), "--book-text", book_text,
           "--text-id", book_id, "-j", "4", "--no-publish"] + extra
    return sh(cmd, env=env)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ws-root", default=str(Path.home() / "ws"))
    ap.add_argument("--exclude", default=DEFAULT_EXCLUDE)
    ap.add_argument("--only", default="", help="只做这些书 ID（逗号分隔）")
    ap.add_argument("--extra", default=os.environ.get("COLLECT_EXTRA_ARGS", ""), help="原样附给 guji collect")
    ap.add_argument("--dry-run", action="store_true", help="只列出要处理的书，不动任何东西")
    ap.add_argument("--no-publish", action="store_true")
    a = ap.parse_args()

    env = dict(os.environ)
    env.setdefault("GUJI_ACTOR", "GM4")
    env.setdefault("GUJI_DATA_URL", "https://data.open-guji.com")
    if env.get("GUJI_DATA_TOKEN_PROD"):
        env["GUJI_DATA_TOKEN"] = env["GUJI_DATA_TOKEN_PROD"]
    book_text = env.get("GUJI_BOOK_TEXT", "")
    ws_root = Path(a.ws_root).expanduser()

    voted = books_with_votes({x for x in a.exclude.split(",") if x})
    only = {x for x in a.only.split(",") if x}
    if only:
        voted = {k: v for k, v in voted.items() if k in only}
    dirs = ws_dir_names()
    summary = ["# 定时收单", ""]
    print("有票的书：", voted)
    if a.dry_run:
        return
    publish: dict[str, set[str]] = {}
    for book_id in sorted(voted):
        if book_id not in dirs:
            summary.append(f"- {book_id}：中心库 workspaces 里没有，跳过（票 {voted[book_id]} 条）")
            continue
        try:
            ws = ensure_workspace(ws_root, book_id, dirs[book_id], env)
            rc, out = run_collect(ws, book_id, book_text, env, a.extra.split())
            led = newest_ledger(ws)
            blocked = [r for r in led if r.get("状态") == "blocked"]
            for r in blocked:                       # 字块图缺：拉原图和出单版包再试一次
                vol = r["册"]
                sh(["guji", "source", "pull", vol, "-w", str(ws)], env=env)
                sh(["guji", "products", "pack", "fetch", vol, "-w", str(ws), "--label", f"rev-{r['单版']}", "--force"], env=env)
            if blocked:
                rc, out = run_collect(ws, book_id, book_text, env, a.extra.split())
                led = newest_ledger(ws)
            def num(r, k):
                v = (r.get(k) or "").strip()
                return int(v) if v.isdigit() else 0
            wrote = [r for r in led if num(r, "写人裁") or num(r, "写book-text")]
            still = [r["册"] for r in led if r.get("状态") == "blocked"]
            summary.append(f"## {book_id}（{dirs[book_id]}）：票 {voted[book_id]}，本轮有落格 {len(wrote)} 册，仍被挡 {still or '无'}")
            confirm = re.findall(r"(?m)^\s+(?:落字≠人裁／手改|旧单票挡下)[^\n]*", out)
            summary += [f"- 待书线确认：{c.strip()}" for c in confirm[:30]]
            for r in wrote:
                publish.setdefault(book_id, set()).add(f"{int(r['册']):03d}")
        except Exception as e:                         # 一本书出错不挡别的书
            summary.append(f"## {book_id}：出错 {type(e).__name__}: {str(e)[:300]}")

    if not a.no_publish:
        genv = dict(env)
        if env.get("GH_TOKEN_WEB"):
            genv["GH_TOKEN"] = env["GH_TOKEN_WEB"]
        for book_id, vols in publish.items():
            only_arg = ",".join(f"{book_id}/{v}" for v in sorted(vols))
            rc, out = sh(["gh", "workflow", "run", "proofing-sync.yml", "-R", "open-guji/kaiyuanguji-web",
                          "--ref", "main", "-f", "target=production", "-f", "parts=publish", "-f", f"only={only_arg}"], env=genv)
            summary.append(f"- 发站 {only_arg}：{'已触发' if rc == 0 else '触发失败 ' + out[-200:]}")
    text = "\n".join(summary)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        Path(path).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    sys.exit(main())
