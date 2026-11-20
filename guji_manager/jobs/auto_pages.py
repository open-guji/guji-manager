"""重跑只跑受影响的页（用户 2026-11-20 定作缺省，流程慢痛点 D1）。

改几页（落人裁、AI 裁定）也整册重跑：脉經一卷整册 20 分、卷三到六一轮 3 h，殿本 vol32 只改 3 页。
任务库本来支持 ``pages``，产物包缺的页由铺底包补（出单版包只含重跑过的页），只是没人默认用。

``guji job submit --pages auto``：读本机工作区的反馈事件（人裁、AI 裁定），挑铺底包生成之后有新事件的页。
**缺省**（不写 --pages）在这些条件都成立时自动按 auto 算：

- 从 ``context_decide``／``seed_admit`` 起跑（只是重放，不动切分、识别）；
- 没改语料、字形库、册配置、参数（``--corpus``／``--glyph-pin``／``--glyph-diff``／``--override``／``--params``）；
- cv 版本与铺底包相同（换代码要整册）。

算不出来（本机没工作区、取不到铺底包）就照旧整册，并说明；``--pages all`` 显式要整册。
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


def changed_pages(book: str, since: str, events=None, rulings=None) -> set[int]:
    """``since``（ISO，铺底包 created）之后有人裁／AI 裁定事件的页。"""
    if events is None:
        from .._cv import EventLog, feedback_root
        events = EventLog(feedback_root()).iter_all()
    if rulings is None:
        from .._cv import RULING_KIND, RulingStore
        st = RulingStore()
        rulings = [e for e in st.log.iter_all(raw=True) if e.kind == RULING_KIND] if st.log.events_dir.exists() else []
    out: set[int] = set()
    for e in events:
        if (e.ts or "") <= since or e.target.unit != "cell":
            continue
        p = _page_of(e.target.key, book)
        if p is not None:
            out.add(p)
    for e in rulings:
        cell = (e.payload or {}).get("cell")
        if (e.ts or "") <= since or not cell:
            continue
        p = _page_of(cell, book)
        if p is not None:
            out.add(p)
    return out


def resolve(raw: dict) -> None:
    """就地改 ``raw["pages"]``：auto 或缺省可按页时填页集，否则留原样。打印说明。"""
    explicit = raw.get("pages") == "auto"
    if not explicit:
        # 2026-11-20 先关掉缺省：事件 ts 是判定时间不是入库时间，比铺底包 created 会漏页（全唐文 閒 14 条裁定
        # ts 早于 d4 包、推库在后，auto 算成 0 页）。改按入库 rev 之前不自动按页；显式 --pages auto 仍可用但同样有此限制
        return
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
    try:
        pages = changed_pages(book, man.get("created") or "")
    except BaseException as e:  # noqa: BLE001
        if explicit:
            sys.exit(f"✗ --pages auto 读不了本机反馈事件（{type(e).__name__}: {str(e)[:120]}）；先 guji db pull，或写 --pages all")
        print(f"ⓘ 没按页跑（读不了本机反馈事件：{type(e).__name__}），整册", file=sys.stderr)
        return
    if not pages:
        sys.exit(f"✗ 铺底包 {man.get('label')}（{man.get('created')}）之后 {book} 没有新的人裁／AI 裁定，不用重放；"
                 "确要整册写 --pages all（先 guji db pull 拉到最新）")
    print("⚠ --pages auto 按事件判定时间（ts）比铺底包生成时间：判定早于铺底包、推库晚于它的裁定会漏页，核对页集再交", file=sys.stderr)
    raw["pages"] = compress(pages)
    print(f"按受影响的页跑：{book} {len(pages)} 页（{raw['pages']}），铺底包 {man.get('label')} 之后有新人裁／AI 裁定；"
          "要整册写 --pages all", file=sys.stderr)
