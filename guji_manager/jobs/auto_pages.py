"""重跑只跑受影响的页（用户 2026-11-20 定作缺省，流程慢痛点 D1）。

改几页（落人裁、AI 裁定）也整册重跑：脉經一卷整册 20 分、卷三到六一轮 3 h，殿本 vol32 只改 3 页。
任务库本来支持 ``pages``，产物包缺的页由铺底包补（出单版包只含重跑过的页），只是没人默认用。

``guji job submit --pages auto``：读中心库里 rev 大于铺底包所记 rev 的反馈事件（人裁、AI 裁定），挑这些事件所在的页（按入库 rev 判，不按事件 ts）。
**缺省**（不写 --pages）在这些条件都成立时自动按 auto 算：

- 从 ``context_decide``／``seed_admit`` 起跑（只是重放，不动切分、识别）；
- 没改语料、字形库、册配置、参数（``--corpus``／``--glyph-pin``／``--glyph-diff``／``--override``／``--params``）；
- cv 版本与铺底包相同（换代码要整册）。

算不出来（连不上中心库、取不到铺底包、老包没记 db_rev）就照旧整册，并说明；``--pages all`` 显式要整册。
文意裁定按窗口取键，同一窗口在别的页也会命中，那些页等下一次整册轮自然跟上。
"""
from __future__ import annotations

import sys

REPLAY_FROM = ("context_decide", "seed_admit")


def compress(pages) -> str:
    """[1,2,3,7,9,10] → ``1-3,7,9-10``。"""
    ps = sorted(set(int(p) for p in pages))
    out, i = [], 0
    while i < len(ps):
        j = i
        while j + 1 < len(ps) and ps[j + 1] == ps[j] + 1:
            j += 1
        out.append(str(ps[i]) if i == j else f"{ps[i]}-{ps[j]}")
        i = j + 1
    return ",".join(out)


def _norm_cv(v) -> str:
    return str(v or "").strip().lstrip("v")


def why_not_default(raw: dict, base_cv: str | None = None) -> str | None:
    """不该缺省按页跑的理由；None＝可以。``base_cv`` 给了才比 cv 版本。"""
    if (raw.get("kind") or "rerun") != "rerun":
        return "不是重跑单"
    if raw.get("pages") is not None:
        return "写了 --pages"
    st = raw.get("steps") or {}
    if st.get("from") not in REPLAY_FROM:
        return f"从 {st.get('from') or '头'} 起跑（只有从 {'／'.join(REPLAY_FROM)} 起的重放才按页）"
    if raw.get("glyph_diff") is not None or raw.get("book_overrides") or raw.get("params"):
        return "改了语料／字形库／册配置／参数"
    if base_cv is not None and _norm_cv(base_cv) != _norm_cv(raw.get("cv")):
        return f"cv {raw.get('cv')} 与铺底包 {base_cv} 不同（换代码要整册）"
    return None


def base_manifest(book: str, base: str | None) -> dict | None:
    import json
    from ..datastore import packs as PK
    src = PK._client()
    label = PK.main_label(book, src) if not base or base == "main" else base
    if not label:
        return None
    return json.loads(PK._call(src, "GET", f"{PK._prefix(PK._ws_name(), book)}/{label}/manifest.json", raw=True))


def _page_of(key: str, book: str) -> int | None:
    parts = str(key or "").split(":")
    if len(parts) == 4:
        if parts[0] != book:
            return None
        parts = parts[1:]
    try:
        return int(parts[0])
    except (ValueError, IndexError):
        return None


def base_rev(man: dict) -> int | None:
    """铺底包对应的中心库 rev，记在 manifest 的 ``versions``：各页 seed_admit 跑时的 ``db_revs`` 取最小（保守，只会多算页不会漏；
    有「未记」页就不信它），其次存包时的 ``db_rev``。老包两样都没有返回 None（算不出来）。"""
    v = man.get("versions") or {}
    revs = []
    for k in (v.get("db_revs") or {}):
        try:
            revs.append(int(k))
        except (TypeError, ValueError):
            return None
    if revs:
        return min(revs)
    try:
        return int(v["db_rev"]) if v.get("db_rev") is not None else None
    except (TypeError, ValueError):
        return None


def _event_rows_since(rev: int):
    """中心库里 rev 之后新写入的反馈事件／裁定（人裁、AI 裁定、看图裁定）：[(target, payload)]。"""
    import json
    from .._cv import connect
    with connect() as con:
        rows = con.execute("SELECT target, payload FROM events WHERE rev > %s", (int(rev),)).fetchall()
    out = []
    for t, pl in rows:
        out.append((json.loads(t) if isinstance(t, str) else (t or {}), json.loads(pl) if isinstance(pl, str) else (pl or {})))
    return out


def changed_pages(book: str, since_rev: int, rows=None) -> set[int]:
    """中心库 rev > ``since_rev`` 之后有人裁／AI 裁定入库的页。

    按入库 rev 而不是事件 ts 判：ts 是判定时间，裁定早判、晚推库的会被 ts 口径漏掉（全唐文 閒 14 条，11-20）；
    rev 是写进库那一刻的版本，铺底包记着自己跑时的 rev，两边同一把尺。"""
    rows = _event_rows_since(since_rev) if rows is None else rows
    out: set[int] = set()
    for target, payload in rows:
        keys = []
        if (target or {}).get("unit") == "cell" and target.get("key"):
            keys.append(target["key"])
        if (payload or {}).get("cell"):
            keys.append(payload["cell"])
        for k in keys:
            p = _page_of(k, book)
            if p is not None:
                out.add(p)
    return out


def resolve(raw: dict) -> None:
    """就地改 ``raw["pages"]``：``auto``（或缺省且条件都满足）时填页集，否则留原样。打印说明。

    ``--pages auto``＝铺底包记的库 rev 之后入库的事件所在页；``auto:<rev>`` 自己给基准 rev。"""
    pg = raw.get("pages")
    explicit = isinstance(pg, str) and (pg == "auto" or pg.startswith("auto:"))
    book = raw.get("book")
    try:
        man = base_manifest(book, raw.get("base"))
    except BaseException as e:  # noqa: BLE001
        man, err = None, f"{type(e).__name__}: {str(e)[:120]}"
    else:
        err = "这册没有铺底包"
    if not man:
        if explicit:
            sys.exit(f"✗ --pages auto 算不出来（{err}）；要整册写 --pages all")
        print(f"ⓘ 没按页跑（取不到铺底包：{err}），整册", file=sys.stderr)
        return
    if not explicit:
        why = why_not_default(raw, (man.get("versions") or {}).get("cv") or man.get("cv_version"))
        if why:
            print(f"ⓘ 整册跑：{why}", file=sys.stderr)
            return
    rev = None
    if explicit and pg.startswith("auto:"):
        try:
            rev = int(pg.split(":", 1)[1])
        except ValueError:
            sys.exit(f"✗ --pages {pg}：auto: 后面要写中心库 rev（整数）")
    if rev is None:
        rev = base_rev(man)
    if rev is None:
        msg = f"铺底包 {man.get('label')} 没记中心库 rev（老包），算不出哪些页之后有新裁定"
        if explicit:
            sys.exit(f"✗ --pages auto {msg}；给基准 --pages auto:<rev>，或整册写 --pages all")
        print(f"ⓘ 整册跑：{msg}", file=sys.stderr)
        return
    try:
        pages = changed_pages(book, rev)
    except BaseException as e:  # noqa: BLE001
        if explicit:
            sys.exit(f"✗ --pages auto 读不了中心库事件（{type(e).__name__}: {str(e)[:120]}）；要整册写 --pages all")
        print(f"ⓘ 没按页跑（读不了中心库事件：{type(e).__name__}），整册", file=sys.stderr)
        return
    if not pages:
        sys.exit(f"✗ 中心库 rev {rev}（铺底包 {man.get('label')}）之后 {book} 没有新入库的人裁／AI 裁定，不用重放；"
                 "确要整册写 --pages all")
    raw["pages"] = compress(pages)
    print(f"按受影响的页跑：{book} {len(pages)} 页（{raw['pages']}），中心库 rev {rev}（铺底包 {man.get('label')}）之后有新入库的人裁／AI 裁定；"
          "要整册写 --pages all", file=sys.stderr)
