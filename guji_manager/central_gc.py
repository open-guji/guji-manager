"""中心库定期清理（2026-11-02，A31；方案见 ai-team 通用/中心库维护方案.md）。

现在只清一类：**R2 正式桶里不再有用的产物包**（``pack/products/<工作区>/<册>/<标签>/``）。
产物包只增不改，每重跑一次存一份，殿本 99 册 1800 多份、14 GB，九成以上没人再取。

每册保留（任一条成立就留）：

1. 现行 main（main 指针最新一条）和它之前的 ``--keep-mains`` 份 main（回退用，缺省 1）；
2. 冻结记录（``feedback/lists/freeze/<册>.jsonl`` 的 ``pack``）点名的包；
3. 线上单（``feedback/lists/proofing/<书>/<章>.pending.json``）的 ``cv_commit`` 对得上的最新一份包；
4. ``--keep-days`` 天内存的包（缺省 14，留给对比和返工）；
5. 任务库里排队／在跑的任务点名的包（``base``／``compare_to``），以及这些任务依赖的任务存的包；
6. 标签以 ``freeze-`` 开头的包。

其余列为可删。缺省只列清单（``--out`` 写 TSV），``--apply`` 才删，要正式令牌（``GUJI_DATA_TOKEN_PROD``）。
main 指针（``main-ptr/``）、非 products 前缀（原图、字体库、模板索引）、实验桶一律不动。

    python -m guji_manager.central_gc [--ws siku-zongmu] [--keep-days 14] [--keep-mains 1] [--out 清单.tsv]
    python -m guji_manager.central_gc --apply --from-list 清单.tsv      # 照已审过的清单删
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import csv
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

MAIN_DIR = "main-ptr"


@dataclass
class Pack:
    ws: str
    book: str
    label: str
    bytes: int = 0
    keys: list[str] = field(default_factory=list)
    created: str | None = None
    cv_commit: str | None = None
    keep: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return f"products/{self.ws}/{self.book}/{self.label}"


def _src(write: bool = False):
    from open_guji_cv.datastore.client import WorkerSource
    tok = os.environ.get("GUJI_DATA_TOKEN_PROD" if write else "GUJI_DATA_TOKEN_READ") or os.environ.get("GUJI_DATA_TOKEN")
    if not tok:
        raise SystemExit("缺令牌：只列清单要 GUJI_DATA_TOKEN_READ，--apply 要 GUJI_DATA_TOKEN_PROD")
    return WorkerSource(token=tok, branch="main")


def list_packs(src, ws: str | None = None) -> tuple[dict[tuple, Pack], dict[tuple, list[str]]]:
    """R2 正式桶 products/ 下的包 → {(ws, 册, 标签): Pack}；main 指针 → {(ws, 册): [按时刻排的标签]}。"""
    pre = f"products/{ws}/" if ws else "products/"
    rows = src._call("GET", "/v1/packs", query={"bucket": "main", "prefix": pre})["packs"]
    packs: dict[tuple, Pack] = {}
    ptrs: dict[tuple, list[tuple[str, str]]] = {}
    for r in rows:
        p = r["key"].split("/")
        if len(p) < 5 or p[0] != "products":
            continue
        w, bk = p[1], p[2]
        if p[3] == MAIN_DIR:
            stem = p[4][:-len(".json")] if p[4].endswith(".json") else p[4]
            at, _, label = stem.partition("-")
            ptrs.setdefault((w, bk), []).append((at, label))
            continue
        k = (w, bk, p[3])
        pk = packs.setdefault(k, Pack(w, bk, p[3]))
        pk.bytes += int(r["bytes"])
        pk.keys.append(r["key"])
    mains = {k: [lb for _, lb in sorted(v)] for k, v in ptrs.items()}
    return packs, mains


def read_manifests(src, packs: dict[tuple, Pack], workers: int = 16) -> None:
    def one(pk: Pack):
        if f"{pk.name}/manifest.json" not in pk.keys:
            return
        try:
            m = json.loads(src._call("GET", "/v1/packs/" + f"{pk.name}/manifest.json", query={"bucket": "main"}, raw=True))
        except Exception:                               # noqa: BLE001 —— 读不到就当没有时刻，按「不知道几时存的」处理（不删）
            pk.created = None
            pk.keep.append("manifest 读不到")
            return
        pk.created = m.get("created")
        pk.cv_commit = m.get("cv_commit")
    with cf.ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, packs.values()))


def db_refs(conn) -> dict:
    """中心库里点名产物包的地方：冻结记录、线上单的 cv_commit、排队／在跑的任务。"""
    freeze: set[str] = set()
    for (raw,) in conn.execute("SELECT raw FROM files WHERE src_path LIKE 'feedback/lists/freeze/%%'"):
        for line in (raw or "").splitlines():
            try:
                p = json.loads(line).get("pack")
            except ValueError:
                continue
            if p:
                freeze.add(p.strip("/"))
    online: dict[tuple, str] = {}      # (ws, 册号三位) → cv_commit
    for ws, path, commit in conn.execute(
            "SELECT ws, src_path, doc->>'cv_commit' FROM files WHERE src_path LIKE 'feedback/lists/proofing/%%.pending.json'"):
        m = re.search(r"/(\w+)\.pending\.json$", path)
        if m and commit:
            online[(ws, m.group(1))] = commit
    jobs: set[tuple[str, str]] = set()   # (册, 标签)
    try:
        q = ("SELECT j.book, j.spec FROM jobs.job j WHERE j.status IN ('queued', 'running')")
        live = [(b, s) for b, s in conn.execute(q)]
        dep_ids = set()
        for b, s in live:
            s = s if isinstance(s, dict) else json.loads(s or "{}")
            for k in ("base", "compare_to"):
                v = s.get(k)
                if isinstance(v, str) and v != "main":
                    jobs.add((b, v))
                elif isinstance(v, dict) and v.get("job"):
                    dep_ids.add(int(v["job"]))
        if dep_ids:
            for (name,) in conn.execute("SELECT name FROM jobs.result WHERE kind='pack' AND job_id = ANY(%s)",
                                        (sorted(dep_ids),)):
                jobs.add(("*", name))
    except Exception as e:                               # noqa: BLE001 —— 没有 jobs schema 的库
        print(f"⚠️ 读不了任务库（{type(e).__name__}）：不按任务保留", file=sys.stderr)
    return {"freeze": freeze, "online": online, "jobs": jobs}


def _vol_key(book: str) -> str:
    m = re.search(r"(\d+)$", book)
    return m.group(1).zfill(3) if m else book


def plan(packs: dict[tuple, Pack], mains: dict[tuple, list[str]], refs: dict, *, keep_days: int = 14,
         keep_mains: int = 1, now: datetime | None = None) -> list[Pack]:
    """给每份包标上保留理由（``keep``）；返回可删的（没有任何理由的）。"""
    now = now or datetime.now(timezone.utc)
    cut = (now - timedelta(days=keep_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    by_book: dict[tuple, list[Pack]] = {}
    for pk in packs.values():
        by_book.setdefault((pk.ws, pk.book), []).append(pk)
    for (ws, bk), items in by_book.items():
        hist = mains.get((ws, bk), [])
        cur = hist[-1] if hist else None
        prev = set(hist[-1 - keep_mains:-1]) if keep_mains > 0 and len(hist) > 1 else set()
        commit = refs["online"].get((ws, _vol_key(bk)))
        online_pick = None
        if commit:
            cand = sorted((p for p in items if p.cv_commit == commit), key=lambda p: p.created or "")
            online_pick = cand[-1].label if cand else None
        for pk in items:
            if pk.label == cur:
                pk.keep.append("现行 main")
            elif pk.label in prev:
                pk.keep.append("上一份 main")
            if pk.name in refs["freeze"] or pk.label.startswith("freeze-"):
                pk.keep.append("冻结")
            if pk.label == online_pick:
                pk.keep.append("线上单所用版本")
            if pk.created is None or pk.created >= cut:
                pk.keep.append(f"{keep_days} 天内" if pk.created else "不知存于何时")
            if (bk, pk.label) in refs["jobs"] or ("*", pk.label) in refs["jobs"]:
                pk.keep.append("排队任务要用")
    return sorted((p for p in packs.values() if not p.keep), key=lambda p: (p.ws, p.book, p.created or ""))


def write_list(path: str, drop: list[Pack]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["ws", "book", "label", "bytes", "created", "files"])
        for p in drop:
            w.writerow([p.ws, p.book, p.label, p.bytes, p.created or "", len(p.keys)])


def apply(src, drop: list[Pack], workers: int = 8) -> tuple[int, int]:
    """逐个删包里的对象（manifest 最后删，删一半断了下次还认得出是包）。返回 (删掉的对象数, 字节)。"""
    def one(pk: Pack) -> int:
        keys = sorted(pk.keys, key=lambda k: k.endswith("/manifest.json"))
        for k in keys:
            src._call("DELETE", "/v1/packs/" + k, query={"bucket": "main"})
        return len(keys)
    n = 0
    with cf.ThreadPoolExecutor(workers) as ex:
        for got in ex.map(one, drop):
            n += got
    return n, sum(p.bytes for p in drop)


def summary(packs: dict[tuple, Pack], drop: list[Pack]) -> dict:
    tot = sum(p.bytes for p in packs.values())
    gone = sum(p.bytes for p in drop)
    why: dict[str, int] = {}
    for p in packs.values():
        for k in p.keep:
            why[k] = why.get(k, 0) + 1
    return {"packs": len(packs), "bytes": tot, "drop_packs": len(drop), "drop_bytes": gone,
            "keep_packs": len(packs) - len(drop), "keep_reasons": why,
            "books": len({(p.ws, p.book) for p in packs.values()})}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="guji-manager central-gc", description=__doc__.split("\n\n")[0])
    ap.add_argument("--ws", default=None, help="只看这个工作区（缺省全部）")
    ap.add_argument("--keep-days", type=int, default=14)
    ap.add_argument("--keep-mains", type=int, default=1, help="现行 main 之外再留几份旧 main")
    ap.add_argument("--out", default=None, help="可删清单写成 TSV")
    ap.add_argument("--from-list", default=None, help="--apply 时只删这份清单里、且现在仍判为可删的包")
    ap.add_argument("--apply", action="store_true", help="真删（要 GUJI_DATA_TOKEN_PROD）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    src = _src(write=a.apply)
    packs, mains = list_packs(src, a.ws)
    read_manifests(src, packs)
    from open_guji_cv.datastore.connect import connect
    with connect() as conn:
        refs = db_refs(conn)
    drop = plan(packs, mains, refs, keep_days=a.keep_days, keep_mains=a.keep_mains)
    if a.from_list:
        with open(a.from_list, encoding="utf-8") as f:
            listed = {(r["ws"], r["book"], r["label"]) for r in csv.DictReader(f, delimiter="\t")}
        drop = [p for p in drop if (p.ws, p.book, p.label) in listed]
    if a.out:
        write_list(a.out, drop)
    s = summary(packs, drop)
    if a.apply:
        if not a.from_list:
            raise SystemExit("--apply 要配 --from-list（先出清单、给用户看过再删）")
        n, b = apply(src, drop)
        s["deleted_objects"], s["deleted_bytes"] = n, b
    if a.json:
        print(json.dumps(s, ensure_ascii=False, indent=1))
    else:
        print(f"产物包 {s['packs']} 份（{s['books']} 册）{s['bytes'] / 1e9:.2f} GB；"
              f"可删 {s['drop_packs']} 份 {s['drop_bytes'] / 1e9:.2f} GB，留 {s['keep_packs']} 份")
        print("保留理由：" + "、".join(f"{k} {v}" for k, v in sorted(s["keep_reasons"].items(), key=lambda x: -x[1])))
        if a.apply:
            print(f"已删 {s['deleted_objects']} 个对象，{s['deleted_bytes'] / 1e9:.2f} GB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
