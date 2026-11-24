"""路径限定的 pull／push／sync（``guji db pull|push|sync --only <路径>``，换包按条目对账，GM4 11-24）。

只碰 ``--only`` 给的路径：以 ``/`` 结尾的是目录（其下所有文件），否则是单个文件。范围外的文件库里不动、本机不动、
基准记录原样留着；不扫整个数据目录、不读整张 ``source_files``、不导出也不重建 glyph.db。

新鲜度按路径记：状态文件里 ``only_revs``＝{路径: rev}，表示「这条路径下的文件与库里 rev 时一致」。一个文件的
基准 rev＝全局 ``rev`` 与覆盖它的 ``only_revs`` 中较大的那个。推的时候只要这些路径在各自基准 rev 之后库里没人改过
就能推，不要求整个工作区最新；库里自全局 rev 后只有这次推的改动时，全局 rev 跟着前进。

字形库（``output/glyph_store/``）和已发布的语料库／字形库清单不许用 ``--only``（要全量比、要重建 glyph.db）。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .scope import BLOB_TABLES, GS, classify, scan_files, sha256
from .workcopy import (
    APPEND_ONLY,
    STATE,
    WS_YAML,
    FileDeleteRefused,
    StaleBase,
    SyncConflict,
    _diff,
    _local,
    _merge_append,
    _merge_events,
    _partial_guard,
    data_dir,
    dup_key_problems,
    incremental_ok,
    read_state,
    write_state,
)

#: 不许 ``--only`` 的前缀：字形库（行在文件间挪、要重建 glyph.db）、已发布版本清单（推时要核不可改）
ONLY_DENY = (GS, "config/glyph-pack/", "config/corpus-pack/")
SCOPE = ("books/", "feedback/", "review/", "config/", "corpus/")


def norm_only(only) -> tuple[str, ...]:
    out: set[str] = set()
    for x in only or ():
        x = str(x).strip()
        while x.startswith("./"):
            x = x[2:]
        if not x or x.startswith("/") or ".." in x.split("/") or x == WS_YAML:
            raise SystemExit(f"--only 不能是 {x!r}（要数据目录里的相对路径，目录以 / 结尾）")
        if x.startswith(ONLY_DENY) or any(d.startswith(x) for d in ONLY_DENY):
            raise SystemExit(f"--only {x!r} 覆盖了字形库或已发布的语料库／字形库清单，这些要整体 sync")
        if not x.startswith(SCOPE):
            raise SystemExit(f"--only {x!r} 不在中心库管的目录里（{'、'.join(SCOPE)}）")
        if not x.endswith("/") and classify(x) is None:
            raise SystemExit(f"--only {x!r} 不是中心库管的文件（目录请以 / 结尾）")
        out.add(x)
    if not out:
        raise SystemExit("--only 至少给一个路径")
    return tuple(sorted(out))


def covers(x: str, path: str) -> bool:
    return path == x or (x.endswith("/") and path.startswith(x))


def in_only(path: str, only) -> bool:
    return any(covers(x, path) for x in only)


def base_rev_of(st: dict, path: str) -> int:
    """这条路径的基准 rev：全局 rev 与覆盖它的 only_revs 取大。"""
    return max([int(st.get("rev") or 0)]
               + [int(r) for x, r in (st.get("only_revs") or {}).items() if covers(x, path)])


def _local_under(data: Path, only) -> dict[str, str]:
    out: dict[str, str] = {}
    for x in only:
        p = data / x
        if x.endswith("/"):
            if not p.is_dir():
                continue
            for dirpath, _, names in os.walk(p):
                rel_dir = os.path.relpath(dirpath, data).replace(os.sep, "/")
                for n in names:
                    rel = f"{rel_dir}/{n}"
                    k = classify(rel)
                    if k is not None and k != "patch":
                        out[rel] = sha256((Path(dirpath) / n).read_bytes())
        elif p.is_file():
            out[x] = sha256(p.read_bytes())
    return out


def _rows_under(src, tbl: str, ws: str, cols, x: str) -> list[dict]:
    """``tbl`` 里路径在 ``x`` 下的行。单个文件按 src_path 等值查；目录用 Worker 的 ``prefix``（走主键区间），
    旧 Worker／简易数据源不认就整表读再筛。表不存在当空。"""
    from .._cv import CentralError
    try:
        if not x.endswith("/"):
            return list(src.rows(tbl, ws, cols=cols, src_path=[x]))
        try:
            return list(src.rows(tbl, ws, cols=cols, prefix=x))
        except (TypeError, ValueError, CentralError) as e:
            if isinstance(e, CentralError) and e.code == "no_table":
                raise
            return [r for r in src.rows(tbl, ws, cols=cols) if str(r["src_path"]).startswith(x)]
    except CentralError as e:
        if e.code == "no_table":
            return []
        raise


def _remote_under(src, ws: str, only) -> tuple[dict[str, dict], dict[str, tuple[str, str]]]:
    """库里范围内的文本文件（source_files 行）与 R2 文件（路径 → (表, sha)）。"""
    files: dict[str, dict] = {}
    blobs: dict[str, tuple[str, str]] = {}
    for x in only:
        for r in _rows_under(src, "source_files", ws, None, x):
            files[r["src_path"]] = r
        for tbl in BLOB_TABLES:
            for r in _rows_under(src, tbl, ws, ("src_path", "sha256"), x):
                blobs[r["src_path"]] = (tbl, r["sha256"])
    return files, blobs


def _touched_since(src, ws: str, rev: int, only, st: dict | None = None) -> list[str]:
    """库里 ``rev`` 之后改过的范围内路径（给了 ``st`` 就再按各路径自己的基准 rev 筛）。整批导入记不清路径的算全碰了。"""
    tbls = ["source_files", *BLOB_TABLES]
    if hasattr(src, "conn"):
        cur = src.conn.cursor()
        cur.execute("SELECT tbl, pk, rev FROM changes WHERE ws = %s AND rev > %s", (ws, int(rev)))
        rows = [{"tbl": t, "pk": k, "rev": r} for t, k, r in cur.fetchall()]
    else:
        rows = list(src.rows("changes", ws, cols=("tbl", "pk", "rev"), tbl=tbls, since_rev=int(rev)))
    out: list[str] = []
    for r in rows:
        if r["tbl"] not in tbls:
            continue
        pk = r["pk"]
        if isinstance(pk, str):
            pk = json.loads(pk)
        if not isinstance(pk, list) or not pk:
            return ["<整批导入>"]
        p = str(pk[0])
        if in_only(p, only) and (st is None or int(r["rev"]) > base_rev_of(st, p)):
            out.append(p)
    return sorted(set(out))


def _fetch(src, ws: str, ws_dir: Path, data: Path, files: dict, blobs: dict, want: set[str], cache, bucket):
    """``want`` 里的路径在库里的字节（文本走 _texts，R2 文件走缓存）。"""
    from .materialize import _texts
    texts, reused, fetched, _ = _texts(src, ws, {p: files[p] for p in want if p in files}, _local(ws_dir, data))
    imgs = {p: blobs[p] for p in want if p in blobs}
    if imgs:
        if cache is None:
            from .._cv import BlobCache
            cache = BlobCache()
        by_ext: dict[str, set[str]] = {}
        for tbl, sha in imgs.values():
            by_ext.setdefault(BLOB_TABLES[tbl], set()).add(sha)
        missing: set[str] = set()
        for ext, shas in sorted(by_ext.items()):
            missing.update(cache.ensure(src, shas, bucket=bucket, ext=ext).get("missing", ()))
        for p, (_, sha) in imgs.items():
            if sha in missing:
                raise SystemExit(f"{p} 的文件在 R2 里取不到（sha {sha[:12]}）")
            texts[p] = Path(cache.path(sha)).read_bytes()
    return texts, {"reused": reused, "fetched": fetched, "blobs": len(imgs)}


def _write(data: Path, rel: str, b: bytes | None) -> None:
    p = data / rel
    if b is None:
        p.unlink(missing_ok=True)
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".only.tmp")
    tmp.write_bytes(b)
    os.replace(tmp, p)


def _save(data: Path, st: dict, only, remote_in: dict[str, str], rev: int, *, advance: bool = False) -> None:
    """范围内的基准换成 ``remote_in``、范围内路径记 only_revs=rev；``advance`` 时全局 rev 也到 rev。"""
    base = {k: v for k, v in (st.get("base") or {}).items() if not in_only(k, only)}
    base.update(remote_in)
    revs = dict(st.get("only_revs") or {})
    for x in only:
        revs[x] = int(rev)
    g = int(rev) if advance else int(st.get("rev") or 0)
    revs = {x: r for x, r in revs.items() if int(r) > g}
    kw = {k: v for k, v in st.items() if k not in ("at", "base", "rev", "only_revs")}
    write_state(data, **kw, base=base, rev=g, **({"only_revs": revs} if revs else {}))


def _state(ws_dir: Path) -> tuple[Path, dict]:
    data = data_dir(Path(ws_dir))
    st = read_state(data)
    if st is None:
        raise SystemExit(f"数据目录 {data} 没有 {STATE}：先整体 guji db pull -w {ws_dir}")
    return data, st


def pull_only(src, ws_dir: Path, only, *, cache=None, bucket: str = "main", force: bool = False,
              retries: int = 3) -> dict:
    """库里范围内的文件换到本机。范围内本机有没推的改动就拒绝（``force`` 丢掉）；范围外一概不动。"""
    ws_dir = Path(ws_dir)
    only = norm_only(only)
    data, st = _state(ws_dir)
    ws = str(st["ws"])
    base_in = {k: v for k, v in (st.get("base") or {}).items() if in_only(k, only)}
    local = _local_under(data, only)
    dirty = _diff(base_in, local)
    if dirty and not force:
        raise SystemExit(f"范围内本地有 {len(dirty)} 个文件改了还没推（如 {dirty[:3]}）；"
                         f"先 guji db push --only，或 sync --only，或加 --force 丢掉")
    for _ in range(retries):
        r0 = src.status()
        files, blobs = _remote_under(src, ws, only)
        remote_in = {**{p: r["sha256"] for p, r in files.items()}, **{p: s for p, (_, s) in blobs.items()}}
        want = {p for p, s in remote_in.items() if local.get(p) != s}
        texts, stats = _fetch(src, ws, ws_dir, data, files, blobs, want, cache, bucket)
        if not _touched_since(src, ws, r0, only):
            break
    else:
        raise SystemExit("拉的过程中范围内一直有新写入，稍后再拉")
    for p in sorted(want):
        _write(data, p, texts[p])
    gone = sorted(set(local) - set(remote_in))
    for p in gone:
        _write(data, p, None)
    _save(data, st, only, remote_in, r0)
    return {"ws": ws, "only": list(only), "rev": r0, "files": len(remote_in), "written": len(want),
            "removed": len(gone), **stats}


def push_only(conn, ws_dir: Path, only, *, actor: str | None, dry_run: bool = False, allow_delete: bool = False,
              uploader=None) -> dict:
    """本机范围内改了的文件推进库。要求这些路径在各自基准 rev 之后库里没人改过（否则先 sync --only）。"""
    from .importer import import_scans
    ws_dir = Path(ws_dir)
    only = norm_only(only)
    data, st = _state(ws_dir)
    _partial_guard(st, "push")
    ws = str(st["ws"])
    base_in = {k: v for k, v in (st.get("base") or {}).items() if in_only(k, only)}
    local = _local_under(data, only)
    changed = sorted(_diff(base_in, local))
    if not changed:
        return {"ws": ws, "only": list(only), "action": "nothing"}
    if not incremental_ok(changed):
        raise SystemExit(f"范围内有要全量比的表的文件（如 {changed[:3]}），不能 --only，请整体 push")
    deleted = [c for c in changed if c not in local]
    if deleted and not allow_delete:
        raise FileDeleteRefused(f"范围内本地少了 {len(deleted)} 个库里有的文件（如 {deleted[:3]}）；"
                                f"确认要删再加 --allow-delete")
    items = [(WS_YAML, (lambda: (ws_dir / WS_YAML).read_bytes()))]
    items += [(rel, (lambda p=data / rel: p.read_bytes())) for rel in changed if rel in local]
    sc = scan_files(items, ws_dir.name)
    if sc.ws != ws:
        raise SystemExit(f"数据目录记的工作区是 {ws}，workspace.yaml 写的是 {sc.ws}")
    dup = dup_key_problems(sc.problems, set(changed))
    if dup and os.environ.get("GUJI_DB_ALLOW_DUP_KEYS") != "1":
        raise SystemExit(f"要推的文件里有同主键重复行：{'；'.join(dup[:4])}。先去重再推")
    from .._cv import RevGate
    rgate = RevGate(books_dir=data / "books")
    stale_ev = {r.key[1]: r.src_path for r in sc.rows
                if r.tbl == "events" and not rgate.admits(r.cols.get("kind"), r.cols.get("target") or {})}
    if any(c.startswith(("books/", "corpus/", "config/")) for c in changed):
        from .._cv import push_problems
        problems = push_problems(ws_dir)
        if problems:
            raise SystemExit(problems[0])
    g = int(st.get("rev") or 0)
    floor = min(base_rev_of(st, x) for x in only)
    others = {"any": True}

    def guard(cur):
        cur.execute("SELECT tbl, pk, rev FROM changes WHERE ws = %s AND rev > %s", (ws, floor))
        stale = []
        for tbl, pk, rev in cur.fetchall():
            if tbl != "source_files" and tbl not in BLOB_TABLES:
                continue
            pk = json.loads(pk) if isinstance(pk, str) else pk
            if not isinstance(pk, list) or not pk:
                raise StaleBase(f"工作区 {ws} 在 rev {floor} 之后有整批导入；先整体 guji db sync")
            p = str(pk[0])
            if in_only(p, only) and int(rev) > base_rev_of(st, p):
                stale.append(p)
        if stale:
            raise StaleBase(f"范围内这些文件库里有人改过（如 {sorted(set(stale))[:3]}）；先 guji db sync --only")
        cur.execute("SELECT 1 FROM changes WHERE ws = %s AND rev > %s LIMIT 1", (ws, g))
        others["any"] = cur.fetchone() is not None
        if stale_ev:
            cur.execute("SELECT id FROM events WHERE ws = %s AND id = ANY(%s)", (ws, list(stale_ev)))
            new = sorted(set(stale_ev) - {r[0] for r in cur.fetchall()})
            if new:
                raise SystemExit(f"{len(new)} 条新事件指向已换图源的册、页表 rev 不符，中心库拒收（如 {new[:3]}）")

    images: dict[str, dict[str, Path]] = {}
    for r in sc.rows:
        if r.tbl in BLOB_TABLES:
            images.setdefault(BLOB_TABLES[r.tbl], {})[r.cols["sha256"]] = data / r.src_path
    up = None
    if images and uploader is not None and not dry_run:
        with conn.cursor() as cur:
            for t, ext in BLOB_TABLES.items():
                want = sorted(images.get(ext, {}))
                if want:
                    cur.execute(f"SELECT sha256 FROM {t} WHERE ws = %s AND sha256 = ANY(%s)", (ws, want))
                    known = {r[0] for r in cur.fetchall()}
                    images[ext] = {s: p for s, p in images[ext].items() if s not in known}
        conn.commit()
        images = {e: g_ for e, g_ in images.items() if g_}
        if images:
            up = {ext: (uploader(g_) if ext == "png" else uploader(g_, ext=ext)) for ext, g_ in sorted(images.items())}
    rep = import_scans(conn, [sc], label=f"push-only:{ws}@{floor}", actor=actor, dry_run=dry_run,
                       source="push", guard=guard, allow_delete=allow_delete, only_paths=set(changed))
    out = rep.as_dict()
    out.update(only=list(only), pushed=changed, images=up, base_rev=floor)
    if not dry_run:
        remote_in = {**base_in, **{p: local[p] for p in changed if p in local}}
        for p in deleted:
            remote_in.pop(p, None)
        # 推完时范围内库里＝本机（guard 查过别人没碰）；库里自全局 rev 后只有这次的改动，全局 rev 也前进
        _save(data, read_state(data) or st, only, remote_in, rep.rev_to, advance=not others["any"])
    return out


def sync_only(src, conn, ws_dir: Path, only, *, actor: str | None, cache=None, bucket: str = "main",
              uploader=None, dry_run: bool = False, retries: int = 3) -> dict:
    """范围内的拉 → 合并 → 推。合并规矩同整体 sync：库里改了本地没改取库里；两边都改了的只追加台账按追加合，
    事件撞号要重编时停下（重编会改到范围外的引用，请整体 sync），别的两边都改了的整次停下。"""
    ws_dir = Path(ws_dir)
    only = norm_only(only)
    data, st = _state(ws_dir)
    _partial_guard(st, "sync")
    ws = str(st["ws"])
    base_in = {k: v for k, v in (st.get("base") or {}).items() if in_only(k, only)}
    local = _local_under(data, only)
    mine = set(_diff(base_in, local))
    out: dict = {"ws": ws, "only": list(only), "local_changes": sorted(mine)}
    for _ in range(retries):
        r0 = src.status()
        files, blobs = _remote_under(src, ws, only)
        remote_in = {**{p: r["sha256"] for p, r in files.items()}, **{p: s for p, (_, s) in blobs.items()}}
        theirs = set(_diff(base_in, remote_in))
        texts, stats = _fetch(src, ws, ws_dir, data, files, blobs,
                              {p for p in theirs if p in remote_in and local.get(p) != remote_in[p]}, cache, bucket)
        if not _touched_since(src, ws, r0, only):
            break
    else:
        raise SystemExit("拉的过程中范围内一直有新写入，稍后再 sync")
    out["remote_changes"] = sorted(theirs)
    merged: dict[str, bytes | None] = {}
    conflicts: list[str] = []
    for rel in sorted(mine & theirs):
        if local.get(rel) == remote_in.get(rel):
            continue
        lp = data / rel
        if rel not in texts or not lp.exists():
            conflicts.append(rel)
            continue
        if classify(rel) == "events":
            b, ren = _merge_events(lp.read_bytes(), texts[rel])
            if ren:
                raise SyncConflict(f"{rel} 两边新事件撞号要重编（{list(ren)[:3]}），重编会改到范围外的引用；请整体 guji db sync")
            merged[rel] = b
            continue
        if classify(rel) in APPEND_ONLY or rel.endswith(".items.jsonl"):
            m = _merge_append(lp.read_bytes(), texts[rel])
            if m is not None:
                merged[rel] = m
                continue
        conflicts.append(rel)
    if conflicts:
        raise SyncConflict(f"这些文件本地和库里都改了，合不了（如 {conflicts[:5]}）；"
                           f"要库里的：guji db pull --only … --force；要本地的：手工合进去再推")
    out["merged"] = sorted(merged)
    if dry_run:
        return {**out, "action": "merge (dry-run)" if theirs else ("push (dry-run)" if mine else "nothing")}
    for rel in sorted(theirs - mine):
        if rel not in remote_in:
            _write(data, rel, None)
        elif rel in texts:                                 # 不在 texts 的是本机已与库里相同
            _write(data, rel, texts[rel])
    for rel, b in merged.items():
        _write(data, rel, b)
    _save(data, st, only, remote_in, r0)
    out["pull"] = {"rev": r0, **stats} if theirs else None
    if not _diff(remote_in, _local_under(data, only)):
        return {**out, "action": "pulled" if theirs else "nothing"}
    res = push_only(conn, ws_dir, only, actor=actor, uploader=uploader)
    return {**out, "action": "merged+push" if theirs else "push", "push": res}
