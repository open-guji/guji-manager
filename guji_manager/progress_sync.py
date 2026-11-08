"""后台「文本整理」看板自动对账（A31，2026-11-08，sheldon：看板的意义是监控最新数据，所有数据都要自动更新到最新，不能每次手动改）。

看板（open-guji.com/admin/text）读 progress.volume／progress.metric。这些数靠流程各步顺手写：
标 main 钩子写 `a31.main`、包口径 `cv.pack`、迭代轮次；换单后写 `pending_review`／`pending_rev`。任何一步在某台机器上失败
（缺 ai-team 检出、换单后那次刷新读到旧单……），看板就停在旧数，而且没人知道。11-08 就是这样：21 册 pending_review 没刷、
第 6／7 轮人审率一直是「待统计」、顶栏停在第 5 轮。

本命令不信任何一步：每次对一遍中心库里的事实，落后的就补：

  1. 线上单 rev（files 表 feedback/lists/proofing/<书>/<册>.pending.json 的 rev）≠ progress.volume.pending_rev
     → 跑 cv `progress_report.py` 重算该册。
  2. `a31.main` 的标签 ≠ `cv.pack` 的标签（标 main 后包口径没跟上）
     → 取 ★main 包重算并写看板（ai-team `按包统计人审率/run.py --pick main --push-progress`；没有 ai-team 检出就浅克隆一份）。
  3. 某一轮的所有标 main 的册包口径都到了，但「迭代轮次」里这一轮还是占位（没有人审率）
     → `auto_round` 汇总写回。

幂等：没有落后的册什么都不做。可以每小时跑，也可以标 main 之后跑。

  guji-manager progress-sync                    # 只报告哪里落后（退出码 1＝有落后）
  guji-manager progress-sync --fix              # 报告并补
  guji-manager progress-sync --fix --book 96mid1ogzk --no-packs

连库：GUJI_DATA_PG_DSN，或 NEON_DATABASE_URL（自动起 443 桥）。--fix 的写库需要有写看板的权限。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from .iterate.progress_rounds import SECTION, round_key, round_of

DIANBEN = "96mid1ogzk"          # 殿本；cv 册名是 volNN，progress_report 只认这一种
AITEAM_URL = "https://github.com/open-guji-core/ai-team"
RUN_PY = ("domain", "CV", "质检", "按包统计人审率", "run.py")


# ---------------------------------------------------------------- 找落后的（纯函数，可测）

def find_stale(vols: list[dict], lists: dict, rounds: dict) -> dict:
    """vols：progress.volume 行 {book, vol, ws, pending_rev, extra}；lists：{(book, vol): 线上单 rev}；
    rounds：{(book, key): {"rate": 人审率或 None, "verdict": 结论或 None}}。
    返回 {"lists": [...], "packs": [...], "rounds": [...]}，每项是能直接交给补的函数的一条记录。"""
    out: dict = {"lists": [], "packs": [], "rounds": []}
    by_round: dict = {}
    for v in vols:
        book, vol, ex = v["book"], v["vol"], v.get("extra") or {}
        rev = lists.get((book, vol))
        if rev and rev != v.get("pending_rev"):
            out["lists"].append({"book": book, "vol": vol, "online": rev, "board": v.get("pending_rev")})
        main = (ex.get("a31.main") or {}).get("label")
        if not main:
            continue
        pack = ((ex.get("cv.pack") or {}).get("label"))
        pack_ok = pack == main or not pack      # 没有包口径的册（文本层、1.x 修订册）走线上单口径，不替它们开包口径
        if not pack_ok:
            out["packs"].append({"book": book, "vol": vol, "ws": v.get("ws") or book, "main": main, "pack": pack})
        rk = round_key(main) if round_of(main) else None
        if rk:
            d = by_round.setdefault((book, rk), {"n": 0, "ok": 0})
            d["n"] += 1
            d["ok"] += 1 if pack_ok else 0
    for (book, rk), d in sorted(by_round.items()):
        have = rounds.get((book, rk)) or {}
        done = isinstance(have.get("rate"), (int, float)) and have.get("verdict") != "pending"
        if not done:
            out["rounds"].append({"book": book, "key": rk, "vols": d["n"], "packs_ready": d["ok"] == d["n"]})
    return out


def load(conn, books: list[str] | None = None) -> tuple[list[dict], dict, dict]:
    """从中心库取三份事实。"""
    vols = [dict(zip(("book", "vol", "ws", "pending_rev", "extra"), r)) for r in conn.execute(
        "SELECT book_id, vol, ws, pending_rev, extra FROM progress.volume").fetchall()]
    lists = {}
    for path, rev in conn.execute(
            "SELECT src_path, doc->>'rev' FROM files WHERE src_path LIKE 'feedback/lists/proofing/%%.pending.json'").fetchall():
        parts = path.split("/")
        lists[(parts[3], parts[4][:-len(".pending.json")])] = rev
    rounds = {}
    for book, key, rate, verdict in conn.execute(
            "SELECT book_id, key, value, detail->>'verdict' FROM progress.metric "
            "WHERE vol = '' AND section = %s AND key <> 'target'", (SECTION,)).fetchall():
        rounds[(book, key)] = {"rate": rate, "verdict": verdict}
    if books:
        vols = [v for v in vols if v["book"] in books]
    return vols, lists, rounds


# ---------------------------------------------------------------- 补

def ensure_ai_team() -> Path | None:
    """ai-team 检出：GUJI_AITEAM_REPO → ~/ai-team → 缓存目录；都没有就浅克隆一份到缓存目录。
    以前标 main 机器缺这个检出时静默跳过，看板包口径就此停住（11-08）；现在自己取。"""
    cands = [os.environ.get("GUJI_AITEAM_REPO"), os.path.expanduser("~/ai-team"), "/home/user/ai-team"]
    cache = Path(os.environ.get("GUJI_CACHE", os.path.expanduser("~/.cache/guji"))) / "ai-team"
    for c in [*cands, str(cache)]:
        if c and Path(c, *RUN_PY).is_file():
            if c == str(cache):
                subprocess.run(["git", "-C", c, "pull", "-q", "--ff-only"], capture_output=True)
            return Path(c)
    cache.parent.mkdir(parents=True, exist_ok=True)
    for cmd in (["git", "clone", "-q", "--depth", "1", AITEAM_URL, str(cache)],
                ["gh", "repo", "clone", "open-guji-core/ai-team", str(cache), "--", "--depth", "1", "-q"]):
        if subprocess.run(cmd, capture_output=True).returncode == 0 and Path(cache, *RUN_PY).is_file():
            return cache
    return None


def _cv_dir() -> Path | None:
    for c in (os.environ.get("GUJI_CV"), os.environ.get("GUJI_CV_REPO"), "/home/user/open-guji/open-guji-cv", "/home/user/open-guji-cv"):
        if c and Path(c, "scripts", "zhengli", "progress_report.py").is_file():
            return Path(c)
    return None


def fix_lists(stale: list[dict]) -> dict[str, str]:
    """重算线上单换了但看板没刷的册。返回 {book/vol: 结果}。"""
    res: dict[str, str] = {}
    cv = _cv_dir()
    by_book: dict[str, list[tuple[str, str]]] = {}
    for s in stale:
        if not cv:
            res[f"{s['book']}/{s['vol']}"] = "fail: 找不到 cv 仓（设 GUJI_CV）"
        else:
            by_book.setdefault(s["book"], []).append((s["vol"], _cv_name(s["book"], s["vol"])))
    for book, pairs in by_book.items():
        r = subprocess.run([sys.executable, str(cv / "scripts" / "zhengli" / "progress_report.py"), "--books", ",".join(n for _, n in pairs), "--text-id", book],
                           capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(cv)})
        ok = r.returncode == 0 and "已写 progress" in r.stdout
        for vol, _ in pairs:
            res[f"{book}/{vol}"] = "ok" if ok else f"fail: {(r.stdout + r.stderr).strip()[-200:]}"
    return res


def _cv_name(book: str, vol: str) -> str:
    """看板册号 → cv 册 id：殿本是 volNN，别的书（全唐文 005、史記 01、北行 001）就是册号本身。"""
    return f"vol{int(vol)}" if book == DIANBEN and vol.isdigit() else vol


def _skeleton(ws_id: str, root: Path) -> Path:
    """没有本地工作区时的骨架目录，足够 `guji products pack list/fetch`。"""
    d = root / ws_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "workspace.yaml").write_text(f"id: {ws_id}\n", encoding="utf-8")
    (d / ".central.json").write_text(json.dumps({"ws": ws_id, "branch": "main"}), encoding="utf-8")
    return d


def fix_packs(stale: list[dict]) -> dict[str, str]:
    """标 main 后包口径没跟上的册：取 ★main 包重算并写看板。"""
    res: dict[str, str] = {}
    team = ensure_ai_team()
    if not team:
        return {f"{s['book']}/{s['vol']}": "fail: 没有 ai-team 检出且克隆失败（设 GUJI_AITEAM_REPO，或让环境能访问 open-guji-core/ai-team）" for s in stale}
    groups: dict[tuple[str, str], list[str]] = {}
    for s in stale:
        groups.setdefault((s["book"], s["ws"]), []).append(s["vol"])
    from .online_lists import _guji_cmd
    env = {**os.environ, "PATH": os.path.dirname(_guji_cmd()[0]) + os.pathsep + os.environ.get("PATH", "")}
    if os.environ.get("GUJI_DATA_TOKEN_READ"):
        env["GUJI_DATA_TOKEN"] = os.environ["GUJI_DATA_TOKEN_READ"]
    with tempfile.TemporaryDirectory(prefix="progress_sync_") as tmp:
        for (book, ws_id), vols in groups.items():
            names = [_cv_name(book, v) for v in vols]
            ws = _skeleton(ws_id, Path(tmp))
            out = Path(tmp) / f"out_{book}"
            r = subprocess.run([sys.executable, "-u", str(team.joinpath(*RUN_PY)), "--ws", str(ws), "--vol-names", ",".join(names),
                                "--pick", "main", "--out", str(out), "--push-progress", book],
                               capture_output=True, text=True, env=env)
            ok = r.returncode == 0 and "已写" in r.stdout
            for v in vols:
                res[f"{book}/{v}"] = "ok" if ok else f"fail: {(r.stdout + r.stderr).strip()[-200:]}"
    return res


def fix_rounds(stale: list[dict]) -> dict[str, str]:
    """包口径都到齐的轮次，汇总写「迭代轮次」。包口径没到齐的等下一轮对账（先补包口径）。"""
    from .iterate.progress_rounds import auto_round
    res: dict[str, str] = {}
    for s in stale:
        k = f"{s['book']}/{s['key']}"
        if not s["packs_ready"]:
            res[k] = "wait: 本轮还有册包口径没跟上"
            continue
        rec = auto_round(s["book"], s["key"])
        res[k] = "ok" if rec else "fail: 没有可汇总的册"
    return res


def run(books: list[str] | None, fix: bool, packs: bool = True) -> int:
    from ._cv import connect
    with connect() as conn:
        stale = find_stale(*load(conn, books))
    n = sum(len(v) for v in stale.values())
    print(f"落后：线上单 {len(stale['lists'])} 册、包口径 {len(stale['packs'])} 册、迭代轮次 {len(stale['rounds'])} 轮")
    for kind in ("lists", "packs", "rounds"):
        for s in stale[kind][:30]:
            print(f"  [{kind}] {json.dumps(s, ensure_ascii=False)}")
    if not fix or not n:
        return 1 if n else 0
    results: dict[str, dict] = {}
    if stale["lists"]:
        results["lists"] = fix_lists(stale["lists"])
    if stale["packs"] and packs:
        results["packs"] = fix_packs(stale["packs"])
    if stale["rounds"]:
        # 包口径刚补完就重新对一次，这样同一次运行里轮次也能收
        with connect() as conn:
            again = find_stale(*load(conn, books))
        results["rounds"] = fix_rounds(again["rounds"])
    bad = 0
    for kind, rs in results.items():
        for k, v in rs.items():
            print(f"  {kind} {k}: {v}")
            bad += 0 if v.startswith(("ok", "skip", "wait")) else 1
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--book", action="append", help="只对这本书（书 id，可重复）；缺省全部")
    ap.add_argument("--fix", action="store_true", help="补落后的；不给只报告")
    ap.add_argument("--no-packs", action="store_true", help="不重算包口径（慢，要下包）")
    a = ap.parse_args(argv)
    return run(a.book, a.fix, not a.no_packs)


if __name__ == "__main__":
    sys.exit(main())
