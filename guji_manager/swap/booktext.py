"""换包落 book-text：格号变了（增删格、改号）也一条命令走完，不再报 need-A33。

总纲：guji-manager `doc/00-总览/待审单-人裁事件-book-text格子.md`；格号变动的整体整理见
`doc/02-精校/换包落book-text-增删格.md`。要点：

* **格的身份认图块，不认格号**：新旧两版 cord 在同一张图上，按框 IoU≥0.5 一对一配（配不上的同页按中心距再配一次），
  出「旧格→新格」对照表（与 A31 回放脚本 `bt_celltable.py`、book-text `remap_anchors.py` 同格式）。
  下游（字的取舍、标点专名挪锚）都只认这张表，不按格号比，也不按文字猜对齐。
* **字的取舍按块图逐格判**（`resolve.resolve`）：同一块图上 现行有字而新包是 □ → 保持现行；待审且首选字≠现行 → 保持现行；
  机器改出相邻重复字 → 回退现行；其余机器改字、□ 补字照采纳。新增的格照新包；新增格与邻格同字的只报不改（疑似重复切）。
* **标点专名**：`remap_anchors.remap_data` 按表挪锚（同格改字刷新校验字，改字落进专名的列复核）；挪不了的不改不删，
  留给 closeout 现算成 A01–A03 待审格。
* **守卫**：专名条目 id 集合、类型、挂法（entity_id／status／group）不变；标点按（mark、kind、source、pos）计数不变。
  不过就不写。

库函数：``cell_table``、``table_tsv``、``merge_chars``、``remap_in_repo``。
命令：``guji swap book-text --books vol15 -w <工作区> --book-text <book-text 仓> [--push]``（见 ``cmd_book_text``）。
"""
from __future__ import annotations

import collections
import copy
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .resolve import BLANK, detect_flaws, resolve

IOU_MIN = 0.5


# ───────────────────────── 对照表 ─────────────────────────

def _chars(char: dict) -> list[tuple[str, dict]]:
    return [(x["a"], x) for pg in char["pages"] for col in pg["columns"] for x in col["cells"]]


def _boxes(cord: dict) -> dict[int, list[tuple[str, tuple]]]:
    out = collections.defaultdict(list)
    for pg in cord["pages"]:
        for x in pg.get("cells") or []:
            b = x["box"]
            out[int(pg["page"])].append((x["a"], (b[0], b[1], b[0] + b[2], b[1] + b[3])))
    return out


def _iou(a, b) -> float:
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    i = max(0, x2 - x1) * max(0, y2 - y1)
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0.0


def cell_table(old_char: dict, old_cord: dict, new_char: dict, new_cord: dict, thr: float = IOU_MIN) -> list[dict]:
    """旧格→新格。每行 {old, new, oc, nc, kind, iou, note}；kind ∈ 同格／改号／删／新增；格号不带册前缀。"""
    och = {a: x.get("c") for a, x in _chars(old_char)}
    nch = {a: x.get("c") for a, x in _chars(new_char)}
    OB, NB = _boxes(old_cord), _boxes(new_cord)
    rows: list[dict] = []
    for pg in sorted(set(OB) | set(NB)):
        A, B = OB.get(pg, []), NB.get(pg, [])
        pairs = sorted(((_iou(a, b), ka, kb) for ka, a in A for kb, b in B
                        if not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])), reverse=True)
        ua, ub = set(), set()
        for s, ka, kb in pairs:
            if s < thr:
                break
            if ka in ua or kb in ub:
                continue
            ua.add(ka), ub.add(kb)
            rows.append(dict(old=ka, new=kb, oc=och.get(ka, ""), nc=nch.get(kb, ""),
                             kind="同格" if ka == kb else "改号", iou=s, note=""))
        # 第二遍：细字（如「一」）框小、框挪了，IoU 不够：同页按中心距配，要同字或同号、中心距 < 0.6×较大边
        ra = [(ka, a) for ka, a in A if ka not in ua]
        rb = [(kb, b) for kb, b in B if kb not in ub]
        cand = []
        for ka, a in ra:
            for kb, b in rb:
                if och.get(ka) != nch.get(kb) and ka != kb:
                    continue
                d = (((a[0] + a[2]) - (b[0] + b[2])) ** 2 + ((a[1] + a[3]) - (b[1] + b[3])) ** 2) ** .5 / 2
                lim = 0.6 * max(a[2] - a[0], a[3] - a[1], b[2] - b[0], b[3] - b[1])
                if d < lim:
                    cand.append((d, ka, kb, _iou(a, b)))
        for d, ka, kb, s in sorted(cand):
            if ka in ua or kb in ub:
                continue
            ua.add(ka), ub.add(kb)
            rows.append(dict(old=ka, new=kb, oc=och.get(ka, ""), nc=nch.get(kb, ""),
                             kind="同格" if ka == kb else "改号", iou=s, note="低IoU按中心距配"))
        rows += [dict(old=ka, new="", oc=och.get(ka, ""), nc="", kind="删", iou=0.0, note="") for ka, _ in A if ka not in ua]
        rows += [dict(old="", new=kb, oc="", nc=nch.get(kb, ""), kind="新增", iou=0.0, note="") for kb, _ in B if kb not in ub]
    for r in rows:
        if r["kind"] in ("同格", "改号") and r["oc"] != r["nc"]:
            r["note"] = (r["note"] + "；" if r["note"] else "") + "改字"
    return rows


def table_tsv(rows: list[dict], vol: int, punct: dict | None = None, entity: dict | None = None) -> str:
    """写成 remap_anchors／bt_celltable 的 tsv（格号带册前缀 volNN:）。"""
    pu, en = collections.Counter(), collections.Counter()
    for x in (punct or {}).get("punctuations", []):
        pu[x.get("anchor")] += 1
    for x in (entity or {}).get("entities", []):
        a = x.get("anchor") or {}
        for k in {a.get("start"), a.get("end")}:
            en[k] += 1
    pre = f"vol{vol:02d}:"
    out = ["旧格\t新格\t旧字\t新字\t类别\tIoU\t标点锚\t专名锚\t说明"]
    for r in rows:
        o = r["old"]
        out.append("\t".join([pre + o if o else "", pre + r["new"] if r["new"] else "", r["oc"] or "", r["nc"] or "",
                              r["kind"], f"{r['iou']:.2f}" if r["kind"] in ("同格", "改号") else "",
                              str(pu[o] if o else 0), str(en[o] if o else 0), r["note"]]))
    return "\n".join(out) + "\n"


def table_counts(rows: list[dict]) -> dict[str, int]:
    c = collections.Counter(r["kind"] for r in rows)
    c["对上但改字"] = sum(1 for r in rows if "改字" in r["note"])
    return dict(c)


# ───────────────────────── 字的取舍 ─────────────────────────

def merge_chars(old_char: dict, new_char: dict, rows: list[dict], pending: set[str] | frozenset[str] = frozenset(),
                protected: dict[str, str] | None = None, same=None) -> dict:
    """按对照表逐块图判字，**就地改 new_char**。pending：新单上待审的格（新格号）。
    protected：{新格号: 字}，有效人裁与 char-edits 手改经对照表换到新格后的字（人裁最高，`resolve` 的 human）。

    返回报告 {kind: [(新格, 现行字, 新包字, 落字)]}，另有 ``dup_new``：新增格与邻格同字（疑似重复切，只报不改）。"""
    old_by_new = {r["new"]: r["old"] for r in rows if r["new"] and r["old"]}
    och = {a: x.get("c") for a, x in _chars(old_char)}
    seq = _chars(new_char)
    cur_seq = [och.get(old_by_new[a]) if a in old_by_new else None for a, _ in seq]
    new_seq = [x.get("c") for _, x in seq]
    flaws = detect_flaws(cur_seq, new_seq)
    rep: dict[str, list] = collections.defaultdict(list)
    for i, (a, x) in enumerate(seq):
        if a not in old_by_new:                   # 新增格：照新包；与邻格同字的报出来
            if i in flaws:
                rep["dup_new"].append((a, None, x.get("c"), x.get("c")))
            continue
        cur, new = cur_seq[i], new_seq[i]
        d = resolve(cur, new, (protected or {}).get(a), flaw=i in flaws, new_pending=a in pending,
                    new_lacuna=bool(x.get("lacuna")), same=same)
        if d.result != new and d.result is not None:
            x["c"] = d.result
            if d.result != BLANK:
                x.pop("lacuna", None)
                x.pop("guess_c", None)
        if d.kind != "same":
            rep[d.kind].append((a, cur, new, x.get("c")))
    return dict(rep)


# ───────────────────────── 人裁与手改（受保护的格） ─────────────────────────

def load_human(book: str) -> dict[str, str] | None:
    """事件里的定字人裁 {裁时格号: 字}（不过绑定表：云端没有产物算不了绑定）。取不到（没装 cv、没有事件目录）返回 None。"""
    try:
        from .._cv import human_chars
        h = human_chars(book, bind=False)
    except Exception:  # noqa: BLE001
        return None
    return {k.split(":", 1)[1] if k.startswith(f"{book}:") else k: c for k, c in h.items() if c}


def protected_cells(old_char: dict, human: dict[str, str] | None, edits: list[dict] | None, same=None) -> tuple[dict[str, str], list[tuple]]:
    """旧版里受保护的格 {旧格号: 字}：有效人裁（旧 book-text 该格正是人裁字，才算绑得上）与 char-edits 手改（取改后字）。
    返回 (受保护, 原先就对不上的 [(格, 来源, 人裁或手改字, 旧文本字)])；后者多是异体／归一（删/刪），只报不停。"""
    och = {a: x.get("c") for a, x in _chars(old_char)}
    eq = same or (lambda p, q: p == q)
    prot, pre = {}, []
    for a, c in (human or {}).items():
        if eq(och.get(a), c):
            prot[a] = c
        elif a in och:
            pre.append((a, "人裁", c, och.get(a)))
    for e in edits or []:
        a, c = e.get("anchor"), e.get("new")
        if not a or not c:
            continue
        if eq(och.get(a), c):
            prot[a] = c
        elif a in och:
            pre.append((a, "手改", c, och.get(a)))
    return prot, pre


def human_ledger(rows: list[dict], prot_old: dict[str, str], new_char: dict) -> tuple[dict[str, str], list[str]]:
    """受保护的旧格经对照表换新格号；账不平的列成问题：旧格被「删」（新包里这块图没了）、落字≠人裁／手改字。
    返回 ({新格号: 字}, 问题)。落字在 merge 之后再核一遍（``ledger_check``）。"""
    o2n = {r["old"]: r["new"] for r in rows if r["old"] and r["new"]}
    gone = {r["old"] for r in rows if r["kind"] == "删"}
    seen_old = {r["old"] for r in rows if r["old"]}
    claimed = {r["new"] for r in rows if r["old"] and r["new"]}      # 已被某个旧格认走的新格号
    new_keys = {a for a, _ in _chars(new_char)}
    out, probs = {}, []
    for a, c in prot_old.items():
        # 旧 cord 里这格没有框（旧包排除过），对照表旧侧没有它：新包有同键格、且没被别的旧格认走，按同键认
        # （ZM 11-12：殿本 vol02 125:8:7 於、98:4:17 此）。其余仍只走对照表，不按格号比。
        if a not in seen_old and a in new_keys and a not in claimed:
            out[a] = c
        elif a in gone or a not in o2n:
            probs.append(f"{a}「{c}」（人裁／手改）在新包里没有对应格")
        else:
            out[o2n[a]] = c
    return out, probs


def ledger_check(new_char: dict, prot_new: dict[str, str], same=None) -> list[str]:
    eq = same or (lambda p, q: p == q)
    cur = {a: x.get("c") for a, x in _chars(new_char)}
    return [f"{a} 落字「{cur.get(a)}」≠人裁／手改「{c}」" for a, c in prot_new.items() if not eq(cur.get(a), c)]


# ───────────────────────── book-text 里落地 ─────────────────────────

def _git(repo: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(args)}：{r.stderr.strip()[-300:]}")
    return r.stdout


def _show(repo: Path, rev: str, rel: str) -> dict | None:
    r = subprocess.run(["git", "-C", str(repo), "show", f"{rev}:{rel}"], capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 else None


def _load(p: Path) -> dict | None:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


#: 平移不该动的专名字段（A33 11-10：remap_data 平移时不改，守卫补上防别的路径误改）
_ENTITY_KEEP = ("type", "group", "decomposition", "targets", "level", "coarse", "note")


def _entity_key(x: dict) -> str:
    t = x.get("target") or {}
    return json.dumps([[k, x.get(k)] for k in _ENTITY_KEEP] + [t.get("entity_id"), t.get("status"), t.get("targets")],
                      ensure_ascii=False, sort_keys=True)


def _shortened(A: dict, B: dict, old_char: dict | None, rows: list[dict] | None) -> list[str]:
    """专名被切短：新 text 比旧短，且短的量超过旧锚区间里被删的格数（被删格以外不该少字）。"""
    pos = {a: i for i, (a, _) in enumerate(_chars(old_char))} if old_char else {}
    gone = sorted(pos[r["old"]] for r in rows or [] if r.get("kind") == "删" and r.get("old") in pos)
    out = []
    for i, a in A.items():
        b = B.get(i)
        if b is None:
            continue
        d = len(a.get("text") or "") - len(b.get("text") or "")
        if d <= 0:
            continue
        an = a.get("anchor") or {}
        s, e = pos.get(an.get("start")), pos.get(an.get("end"))
        n_del = sum(1 for g in gone if s is not None and e is not None and s <= g <= e)
        if d > n_del:
            out.append(f"{i}（{a.get('text')}→{b.get('text')}）")
    return out


def guard(old_punct: dict | None, new_punct: dict | None, old_entity: dict | None, new_entity: dict | None,
          old_char: dict | None = None, rows: list[dict] | None = None) -> list[str]:
    """平移不该改的东西改了就返回问题列表（空＝通过）。给了 old_char 与对照表 rows 才查「专名被切短」时扣掉被删格。"""
    bad = []
    if old_entity is not None and new_entity is not None:
        LA, LB = old_entity.get("entities", []), new_entity.get("entities", [])
        A = {x["id"]: x for x in LA}
        B = {x["id"]: x for x in LB}
        if set(A) != set(B):
            bad.append(f"专名条目 id 变了：少 {len(set(A) - set(B))}、多 {len(set(B) - set(A))}")
        if len(LA) != len(LB):
            bad.append(f"专名条数变了：{len(LA)}→{len(LB)}")
        ch = [i for i in A if i in B and _entity_key(A[i]) != _entity_key(B[i])]
        if ch:
            bad.append(f"专名挂法或字段变了 {len(ch)} 条：{', '.join(ch[:8])}")
        short = _shortened(A, B, old_char, rows)
        if short:
            bad.append(f"专名被切短 {len(short)} 条：{'；'.join(short[:8])}")
    if old_punct is not None and new_punct is not None:
        k = lambda x: (x.get("mark"), x.get("kind"), x.get("source"), x.get("pos"))
        if collections.Counter(map(k, old_punct.get("punctuations", []))) != collections.Counter(map(k, new_punct.get("punctuations", []))):
            bad.append("标点条目（按 mark／kind／source／pos 计）变了")
    return bad


def remap_in_repo(repo: Path, vdir: Path, chapter: str, *, base: str = "HEAD", pending: set[str] | frozenset[str] = frozenset(),
                  out_dir: Path | None = None, merge: bool = True, human: dict[str, str] | None = None,
                  book: str | None = None, require_human: bool = False) -> dict:
    """book-text 工作树里，NNN.char/cord 已换成新包的（未提交）；对照 ``base`` 提交里的旧版：
    出对照表 → 逐块图判字（写回 char）→ 按表挪标点专名 → 守卫。通过才写 punct／entity。不升版、不提交。

    受保护的格（有效人裁、char-edits 手改）先经对照表换到新格、按人裁最高判字；**账不平就停**：
    受保护的旧格在新包里没了（删），或落字≠人裁／手改字（新包与人裁冲突，按总纲保留人裁，但要人看）。
    human 缺省从事件读（``load_human(book)``，book 缺省 ``vol<章>``）；读不到就只核手改并在 notes 里说明，
    ``require_human``（1.x 册）时读不到就停。

    返回 {ok, problems, counts, chars, remap, table, left, review, notes, human_pre}。"""
    repo, vdir = Path(repo), Path(vdir)
    from ..closeout import remap_lib
    from ..formats.guji_char_cord import dumps
    rel = vdir.relative_to(repo).as_posix()
    old = {t: _show(repo, base, f"{rel}/{chapter}.{t}.json") for t in ("char", "cord", "punct", "entity")}
    if not old["char"] or not old["cord"]:
        raise SystemExit(f"{base} 上没有 {rel}/{chapter}.char/cord.json")
    cf = vdir / f"{chapter}.char.json"
    new_char, new_cord = _load(cf), _load(vdir / f"{chapter}.cord.json")
    rows = cell_table(old["char"], old["cord"], new_char, new_cord)
    notes, human_missing = [], False
    if human is None:
        human = load_human(book or f"vol{int(chapter):02d}")
        if human is None:
            human_missing = True
            notes.append("人裁账没核：取不到事件（没装 cv 或没有事件目录），只核 char-edits 手改")
    edits = (_show(repo, base, f"{rel}/{chapter}.char-edits.json") or {}).get("edits") or []
    from ..charnorm import load_norm
    same = load_norm(book or f"vol{int(chapter):02d}").same     # 同字判定（别／別 不算冲突）
    prot_old, human_pre = protected_cells(old["char"], human, edits, same)
    prot_new, ledger_probs = human_ledger(rows, prot_old, new_char)
    chars = merge_chars(old["char"], new_char, rows, pending, prot_new, same) if merge else {}
    ledger_probs += ledger_check(new_char, prot_new, same)
    conflicts = (chars.get("protected_conflict") or []) if merge else []
    ledger_probs += [f"{a} 新包「{n}」≠人裁／手改「{c}」（保留人裁，要人看）" for a, _, n, c in conflicts]
    cf.write_text(dumps(new_char), encoding="utf-8", newline="\n")
    out_dir = Path(out_dir or tempfile.mkdtemp(prefix="swap-bt-"))
    out_dir.mkdir(parents=True, exist_ok=True)
    vol = int(chapter)
    tsv = out_dir / f"old_new_cells_vol{vol:02d}.tsv"
    tsv.write_text(table_tsv(rows, vol, old["punct"], old["entity"]), encoding="utf-8")
    ra = remap_lib.load_ra(repo)
    pf, ef = vdir / f"{chapter}.punct.json", vdir / f"{chapter}.entity.json"
    punct, entity = _load(pf), _load(ef)
    res = remap_lib.run(ra, chapter, new_char, punct, entity, ra.load_cells(str(tsv)))
    problems = guard(punct, res["punct"], entity, res["entity"], old["char"], rows)
    if human_missing and require_human:
        problems.append("1.x 册要核人裁账，但取不到人裁事件（没装 cv 或没有事件目录）")
    if ledger_probs:
        problems.append(f"人裁账不平 {len(ledger_probs)} 格：" + "；".join(ledger_probs[:8]))
    review = [r for r in res["report"] if r[0] == "entity-复核"]
    grown = _grow_spans(res["entity"], new_char, rows, res["report"])
    moved_breaks = _breaks_follow_headings(res["punct"], new_char, rows)
    review += grown
    done = {(g[1], g[2]) for g in grown}
    left = [r for r in res["report"] if r[0] in ("punct", "entity") and (r[1], r[2]) not in done]
    if not problems:
        sys.path.insert(0, str(repo / "scripts"))
        import original_version as OV  # noqa: E402  book-text 自己的读写，保持排版
        if res["punct"] is not None:
            OV.dump_json(str(pf), res["punct"])
        if res["entity"] is not None:
            OV.dump_json(str(ef), res["entity"])
    (out_dir / f"left_vol{vol:02d}.tsv").write_text(
        "层\t条目\t旧锚\t新锚\t内容\t原因码｜说明\n" + "".join("\t".join(map(str, r)) + "\n" for r in left), encoding="utf-8")
    return {"ok": not problems, "problems": problems, "counts": table_counts(rows), "breaks_moved": moved_breaks,
            "notes": notes, "human_pre": human_pre, "protected": len(prot_new),
            "chars": {k: len(v) for k, v in chars.items()}, "char_detail": chars,
            "remap": {"moved": res["moved"], "left": res["left"]}, "table": str(tsv),
            "left": left, "review": review}


def _grow_spans(entity: dict | None, new_char: dict, rows: list[dict], report: list) -> list[tuple]:
    """remap 挪不了的专名里，两端都在表里对上、只是中间多了／少了格（新增格落在专名里，如 語子→語孟子）：
    两端按表换新格，text 取新格上的字，进复核单。返回放进复核单的条目。就地改 entity。"""
    if not entity:
        return []
    o2n = {r["old"]: r["new"] for r in rows if r["old"] and r["new"]}
    seq = [(a, x.get("c") or "") for a, x in _chars(new_char)]
    pos = {a: i for i, (a, _) in enumerate(seq)}
    byid = {x["id"]: x for x in entity.get("entities", [])}
    out = []
    for r in report:
        if r[0] != "entity" or "长度变了" not in str(r[-1]) and "不连续" not in str(r[-1]):
            continue
        x = byid.get(str(r[1]).lstrip("#")) or byid.get(str(r[1]))
        if not x:
            continue
        a = x.get("anchor") or {}
        ns, nt = o2n.get(a.get("start")), o2n.get(a.get("end"))
        if not ns or not nt or ns not in pos or nt not in pos:
            continue
        i, j = pos[ns], pos[nt]
        if j < i or (j - i + 1) - len(x.get("text") or "") > 3:
            continue
        txt = "".join(c for _, c in seq[i:j + 1])
        old_txt = x.get("text")
        x["anchor"] = {"start": ns, "end": nt}
        x["text"] = txt
        if "span" in x:
            x["span"] = {"start_offset": i, "end_offset": j + 1}
        out.append(("entity-复核", r[1], r[2], f"{ns}～{nt}", old_txt,
                    f"SPAN_GROW｜两端按表对上，中间格数变了，文字 {old_txt}→{txt}，请复核专名是否仍成立"))
    return out


def _breaks_follow_headings(punct: dict | None, new_char: dict, rows: list[dict]) -> list[tuple[str, str]]:
    """标题前的分段符跟着标题走：新增格整段插在「分段符」和「标题」之间（如整页漏切补回），把分段符挪到标题前一格
    （F-OV-12）。只挪中间全是新增格的；就地改 punct，返回 [(旧锚, 新锚)]。"""
    if not punct:
        return []
    seq = [(a, x.get("c") or "") for a, x in _chars(new_char)]
    pos = {a: i for i, (a, _) in enumerate(seq)}
    added = {r["new"] for r in rows if r["kind"] == "新增"}
    pm = punct.get("punctuations", [])
    brk = {m["anchor"]: m for m in pm if m.get("kind") == "break" and m.get("pos") == "after" and m.get("anchor") in pos}
    out = []
    for h in [m for m in pm if m.get("kind") == "heading" and m.get("pos") == "before" and m.get("anchor") in pos]:
        i = pos[h["anchor"]]
        if i == 0 or seq[i - 1][0] in brk:
            continue
        j = i - 1
        while j >= 0 and seq[j][0] in added and seq[j][0] not in brk:
            j -= 1
        if j < 0 or j == i - 1 or seq[j][0] not in brk:
            continue
        m = brk.pop(seq[j][0])
        a_new, c_new = seq[i - 1]
        out.append((m["anchor"], a_new))
        m["anchor"], m["pre_char"] = a_new, c_new
        if "char_offset" in m:
            m["char_offset"] = i - 1
        brk[a_new] = m
    if out:
        pm.sort(key=lambda m: (m.get("char_offset", 0) + (0.4 if m.get("pos") == "after" else -0.4)))
    return out


def structure_changed(old_char: dict, new_char: dict) -> bool:
    """格号集合或次序变了（增删格、改号）。只换字不算。"""
    return [a for a, _ in _chars(old_char)] != [a for a, _ in _chars(new_char)]


# ───────────────────────── R1 前置闸：字形库已 rekey ─────────────────────────

def rekey_gate(glyph_db: Path | str, rows: list[dict], vol: int) -> dict:
    """字形库刻例的键（`册:页:列:格`）是格号坐标，格号变了必须先 rekey（`ops/cell_rekey`），否则人裁刻例会投到别的块图（殿本 99:2:8 出两个「雯」）。
    只读核对：本册字形库实例的格键，不在**新包格集合**里的就是没跟上的（停）；在新包里、但对照表说它改了号的（旧号被别的块图占用）
    无法只靠键判断，只计数报出（``ambiguous``），要用 g 快照对比图字对（字形快速入库.md）。
    返回 {ok, orphan: [键…], ambiguous: n, n_inst}。"""
    import sqlite3
    from ..ops.cell_rekey import _split_instance
    pre = f"vol{vol:02d}:"
    new_cells = {pre + r["new"] for r in rows if r["new"]}
    renamed_old = {pre + r["old"] for r in rows if r["kind"] == "改号" and r["old"]}
    c = sqlite3.connect(f"file:{glyph_db}?mode=ro", uri=True)
    try:
        ids = [r[0] for r in c.execute("SELECT instance_id FROM instances")]
    finally:
        c.close()
    orphan, amb, n = [], 0, 0
    for iid in ids:
        sp = _split_instance(iid, f"vol{vol:02d}")
        if sp is None:
            continue
        n += 1
        key = sp[1]
        if key not in new_cells:
            orphan.append(iid)
        elif key in renamed_old:
            amb += 1
    return {"ok": not orphan, "orphan": orphan, "ambiguous": amb, "n_inst": n}


def open_pr(wt: Path, branch: str, title: str, body: str, base: str = "dev") -> str:
    """R7：1.x 推了 ``swap/<册>-1x`` 分支后开 PR（草稿；需 ``gh`` 且已登录）。已有同分支的开 PR 就返回它。失败不抛，返回 ``failed：…``。"""
    gh = shutil.which("gh")
    if not gh:
        return "failed：没有 gh 命令，手动开 PR"
    ex = subprocess.run([gh, "pr", "list", "--head", branch, "--base", base, "--state", "open", "--json", "url", "-q", ".[0].url"],
                        cwd=wt, capture_output=True, text=True)
    if ex.returncode == 0 and ex.stdout.strip():
        return ex.stdout.strip()
    p = subprocess.run([gh, "pr", "create", "--draft", "--base", base, "--head", branch, "--title", title, "--body", body],
                       cwd=wt, capture_output=True, text=True)
    return p.stdout.strip().splitlines()[-1] if p.returncode == 0 and p.stdout.strip() else f"failed：{(p.stderr or p.stdout).strip()[-200:]}"


# ───────────────────────── 命令 ─────────────────────────

def _latest_export(ws: Path, book: str) -> Path | None:
    c = sorted((ws / "reports" / book / "_cycle").glob("*/export"), key=lambda p: p.stat().st_mtime)
    return c[-1] if c else None


def _bt_dir(repo: Path, text_id: str) -> Path:
    from ..online_lists import book_text_dir
    return Path(book_text_dir(str(repo), text_id))


def _run(cmd: list, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True)


def _worktree(src: Path, wt: Path, branch: str = "swap-booktext", sparse: tuple[str, ...] = ()) -> Path:
    """独立 worktree（swap run 会在共享 book-text 目录里 checkout -- .，手工活不能放那里）。每次重置到最新 origin/dev。"""
    _git(src, "fetch", "-q", "origin", "dev")
    if not (wt / ".git").exists():
        # 稀疏检出：全仓几个 G，只要 scripts 和本书目录（text_id 未知时退回整仓）
        _git(src, "worktree", "add", "-f", "--no-checkout", "-B", branch, str(wt), "FETCH_HEAD")
        if sparse:
            _git(wt, "sparse-checkout", "set", "--cone", "scripts", *sparse)
        _git(wt, "checkout", "-q", branch)
    else:
        _git(wt, "fetch", "-q", "origin", "dev")
        _git(wt, "checkout", "-q", "-f", "-B", branch, "FETCH_HEAD")
        _git(wt, "reset", "-q", "--hard", "FETCH_HEAD")          # 上一册失败留下的改动不能带进来
        _git(wt, "clean", "-fdq", "--", "Book")
    return wt


def _copy_cord(src: Path, dst: Path, cv: Path | None) -> str | None:
    """导出的 cord 写进 book-text。给了 cv 就用 cv ``republish.copy_cord_for_site`` 换到网站页图坐标（换过图源的书，
    与 swap run 的自动路径同一口径）；没给 cv 原样拷（殿本页表未换，坐标相同）。返回 None＝成功，否则是停下的原因。"""
    if not src.exists():
        return None
    if cv is None:
        shutil.copyfile(src, dst)
        return None
    import importlib.util
    f = Path(cv) / "scripts" / "zhengli" / "republish.py"
    try:
        for d in (str(Path(cv)), str(f.parent)):
            if d not in sys.path:
                sys.path.insert(0, d)
        spec = importlib.util.spec_from_file_location("_cv_republish", f)
        rp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rp)
        rp.copy_cord_for_site(src, dst)
    except SystemExit as e:
        return f"cord 换不到网站页图坐标：{e}"
    except Exception as e:  # noqa: BLE001 —— cv 不在或读不了页表：不拿错坐标落库
        return f"cord 换坐标失败（cv {cv}）：{e}"
    return None


def do_book(wt: Path, ws: Path, book: str, text_id: str, export: Path, *, note: str, push: bool,
            pending: set[str], out_dir: Path, glyph_db: Path | None = None, open_pr_: bool = True,
            cv: Path | None = None) -> dict:
    vdir = _bt_dir(wt, text_id) / "default"
    ch = f"{int(book[3:]):03d}"
    from ..formats.guji_char_cord import dumps
    base = _git(wt, "rev-parse", "HEAD").strip()
    idx = _load(vdir / "index.json") or {}
    tv = next((c.get("text_version") for c in idx.get("chapters", []) if f"{c.get('n', 0):03d}" == ch or c.get("file", "").startswith(ch)), None) \
        or idx.get("text_version") or "0"
    old_char = _load(vdir / f"{ch}.char.json")
    new_char = _load(export / f"{ch}.char.json")
    if not new_char:
        return {"status": "blocked", "why": f"导出里没有 {ch}.char.json：{export}"}
    old_cord = _load(vdir / f"{ch}.cord.json")
    why = _copy_cord(export / f"{ch}.cord.json", vdir / f"{ch}.cord.json", cv)     # 换过图源的书换到网站页图坐标
    if why:
        _git(wt, "checkout", "-q", "--", ".")
        return {"status": "blocked", "why": why}
    gate_note = "R1 未核（没给 --glyph-db）"
    if glyph_db:
        new_cord = _load(vdir / f"{ch}.cord.json")
        if old_cord and new_cord:
            g = rekey_gate(glyph_db, cell_table(old_char, old_cord, new_char, new_cord), int(book[3:]))
            if not g["ok"]:
                return {"status": "r1-stop", "why": f"字形库有 {len(g['orphan'])} 个刻例的格键不在新包里（没 rekey）：{g['orphan'][:5]}；先 rekey 再落"}
            gate_note = f"R1 已核（实例 {g['n_inst']}，改号待核 {g['ambiguous']}）"
    new_char["version"] = old_char.get("version", new_char.get("version"))
    (vdir / f"{ch}.char.json").write_text(dumps(new_char), encoding="utf-8", newline="\n")
    for t in ("norm", "fig"):
        p = export / f"{ch}.{t}.json"
        if p.exists():
            shutil.copyfile(p, vdir / f"{ch}.{t}.json")
    fd = export / "fig" / ch
    if fd.is_dir():
        (vdir / "fig" / ch).mkdir(parents=True, exist_ok=True)
        for f in fd.iterdir():
            t = vdir / "fig" / ch / f.name
            if not t.exists() or t.read_bytes() != f.read_bytes():
                shutil.copyfile(f, t)
    one_x = str(tv).split(".")[0] not in ("0", "")
    r = remap_in_repo(wt, vdir, ch, base=base, pending=pending, out_dir=out_dir, require_human=one_x)
    if not r["ok"]:
        _git(wt, "checkout", "-q", "--", ".")
        _git(wt, "clean", "-fdq", "--", "Book")
        return {"status": "guard-stop", "why": "；".join(r["problems"]), **r}
    records = []
    lines = [("text", note)] + [(ln, f"{book} 换包格号变动：按格级对照表挪锚（挪 {r['remap']['moved']}，留待重标 {len(r['left'])}，复核 {len(r['review'])}）")
                                for ln in ("punct", "entity") if (vdir / f"{ch}.{ln}.json").exists()]
    for ln, nt in lines:
        p = _run([sys.executable, "scripts/book-text/bump_original.py", vdir, "--line", ln, "--level", "patch",
                  "--chapter", ch, "--note", nt], wt)
        if p.returncode:
            _git(wt, "checkout", "-q", "--", ".")
            _git(wt, "clean", "-fdq", "--", "Book")
            return {"status": "blocked", "why": f"bump {ln} 失败：{(p.stdout + p.stderr).strip()[-300:]}", **r}
        records += [x.strip() for x in p.stdout.splitlines() if x.startswith("版本记录:")]
    sync_headings_keep_unreadable(wt, vdir)
    ar = Path(wt) / "scripts" / "book-text"
    if str(ar) not in sys.path:
        sys.path.insert(0, str(ar))
    try:
        import auto_remap  # noqa: E402  标题符／分段符位置修正（F-OV-12）
        auto_remap.fix_heading_breaks(str(vdir), ch)
    except Exception as e:  # noqa: BLE001
        print(f"  标题符修正跳过：{e}", file=sys.stderr)
    stored = None
    try:
        from .finish import store_table
        stored = store_table(vdir, r["table"], book, _git(wt, "rev-parse", "--short", "HEAD").strip())
    except OSError as e:  # noqa: BLE001
        print(f"  对照表入库跳过：{e}", file=sys.stderr)
    lc = _run([sys.executable, "scripts/local_check.py", "--dev"], wt)
    if lc.returncode and stored is not None:
        # book-text 校验器还不认 lineage/ 目录时（需 book-text 把 lineage 加进 ORIGINAL_SIDECAR_FILES）：不带对照表再核一遍，别因此整册落不了
        drop_stored_table(stored)
        lc2 = _run([sys.executable, "scripts/local_check.py", "--dev"], wt)
        if lc2.returncode == 0:
            print("  对照表入库跳过：book-text 校验器不认 lineage/ 目录，已不带对照表落文本（对照表仍在 reports/_swap/book-text/）", file=sys.stderr)
        lc = lc2
    if lc.returncode:
        keep = out_dir / f"local_check_{book}.txt"
        keep.write_text(lc.stdout + lc.stderr, encoding="utf-8")
        _git(wt, "checkout", "-q", "--", ".")
        _git(wt, "clean", "-fdq", "--", "Book")
        return {"status": "local-check-fail", "why": f"local_check --dev 不过，见 {keep}", **r}
    ch_ = r["chars"]
    body = [f"{book}：换包，格号变动按格级对照表落 book-text（{', '.join(f'{k} {v}' for k, v in r['counts'].items())}）",
            f"字：{', '.join(f'{k} {v}' for k, v in ch_.items()) or '无变化'}"]
    dup = r["char_detail"].get("dup_new") or []
    if dup:
        body.append("疑似重复切（新增格与邻格同字，未改）：" + "、".join(f"{a}{c}" for a, _, c, _ in dup[:10]))
    body.append(f"人裁／手改受保护 {r.get('protected', 0)} 格，账平" + ("；" + "；".join(r["notes"]) if r.get("notes") else ""))
    if r.get("human_pre"):
        body.append(f"人裁／手改与旧文本原先就不同 {len(r['human_pre'])} 格（多为异体／归一，未动）：" + "、".join(f"{a}{c}≠{o}" for a, _, c, o in r["human_pre"][:8]))
    if r.get("breaks_moved"):
        body.append("标题前分段符随标题挪（中间插进新增格）：" + "、".join(f"{o}→{n}" for o, n in r["breaks_moved"][:6]))
    if r["review"]:
        body.append(f"专名复核 {len(r['review'])} 条（改字落进专名）：" + "；".join(f"{x[1]} {x[4]}" for x in r["review"][:8]))
    if r["left"]:
        body.append(f"留待重标 {len(r['left'])} 条（closeout 现算为 A01–A03）：" + "；".join(f"{x[1]} {x[2]}" for x in r["left"][:6]))
    body.append(gate_note)
    msg = f"殿本 {book}：换包增删格，标点专名按对照表平移（patch）\n\n" + "\n".join(body) + "\n\n" + "\n".join(records) + "\n"
    _git(wt, "add", "-A", "--", str(vdir.relative_to(wt)))
    subprocess.run(["git", "-C", str(wt), "commit", "-q", "-F", "-"], input=msg, text=True, check=True)
    if push:
        dest = f"swap/{book}-1x" if one_x else "dev"
        for i in range(3):
            if dest == "dev":
                _git(wt, "pull", "-q", "--rebase", "origin", "dev", check=False)
            p = _run(["git", "push", "-q", "origin", f"HEAD:{'refs/heads/' + dest}"], wt)
            if p.returncode == 0:
                break
        else:
            return {"status": "push-fail", "why": p.stderr.strip()[-200:], **r}
        out = {"status": "pr-needed" if one_x else "pushed", "branch": dest, "commit": _git(wt, "rev-parse", "HEAD").strip(), **r}
        if one_x and open_pr_:
            out["pr"] = open_pr(wt, dest, f"{book} 换包（1.x）：格号变动按格级对照表落 book-text（patch）", "\n".join(body) + "\n\n" + "\n".join(records))
            if not out["pr"].startswith("failed"):
                out["status"] = "pr-opened"
        return out
    return {"status": "committed", "commit": _git(wt, "rev-parse", "HEAD").strip(), **r}


def _unreadable_headings(vdir: Path) -> dict[int, list]:
    """index.json 里 char／punct 文件不在盘上的章（稀疏检出、只取了本册）已有的 headings，按章序号 → 原值。"""
    try:
        idx = json.loads((Path(vdir) / "index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    keep = {}
    for i, c in enumerate(idx.get("chapters") or []):
        if not isinstance(c, dict) or "headings" not in c:
            continue
        stem = c.get("file") or (f"{c['n']:03d}" if isinstance(c.get("n"), int) else None)
        if not stem or not (Path(vdir) / f"{stem}.char.json").is_file() or not (Path(vdir) / f"{stem}.punct.json").is_file():
            keep[i] = c["headings"]
    return keep


def sync_headings_keep_unreadable(wt: Path, vdir: Path) -> None:
    """跑 book-text ``OV.sync_headings`` 重算目录缓存 headings，但**别章读不到数据文件时不删它的 headings**。
    ``sync_headings`` 把「char／punct 文件不在」当成「没有标题」而删键；工作树只检出本章时，会把别章（殿本 vol03 的 #437：98 章）
    的 headings 全删光。这里先记下读不到数据的章的 headings，同步后原样放回。"""
    keep = _unreadable_headings(vdir)
    _run([sys.executable, "-c", "import sys; sys.path.insert(0, 'scripts'); import original_version as OV; OV.sync_headings(sys.argv[1])", vdir], wt)
    if not keep:
        return
    ip = Path(vdir) / "index.json"
    idx = json.loads(ip.read_text(encoding="utf-8"))
    changed = False
    for i, h in keep.items():
        chs = idx.get("chapters") or []
        if i < len(chs) and chs[i].get("headings") != h:
            chs[i]["headings"] = h
            changed = True
    if changed:
        ip.write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def drop_stored_table(stored: Path) -> None:
    """只删刚放进去的那张对照表；同版本目录早先已提交的 ``lineage/revisions/*.tsv`` 一张都不能动。
    ``lineage/revisions`` 和 ``lineage`` 只有在删完变空时才顺手删（本次新建的目录）。"""
    stored = Path(stored)
    stored.unlink(missing_ok=True)
    for d in (stored.parent, stored.parent.parent):
        try:
            d.rmdir()            # 非空会抛 OSError，留着
        except OSError:
            break


def pending_cells_of(ws: Path, text_id: str, ch: str) -> set[str]:
    """本册新单（`republish prep` 出在 reports/<册>/_publish/<rev>/ 的新单）格号；读不到就当没有（只影响「待审保持现字」一条）。"""
    for p in sorted((ws / "reports").glob(f"vol{int(ch):02d}/_publish/*/{ch}.pending.json"), key=lambda p: p.stat().st_mtime)[::-1]:
        try:
            return {c["cell"] for c in json.loads(p.read_text(encoding="utf-8")).get("cells", []) if c.get("cell")}
        except (OSError, ValueError, KeyError):
            continue
    return set()


def push_sheet(ws: Path, book: str, cv: Path) -> str:
    """book-text 这步没过（guard-stop，旧称 need-A33）时 auto_cycle 停在推库之前：新单已出（reports/<册>/_publish/<rev>）但没换上线。book-text 落好后补推这张单
    （cv `republish.py push --yes --no-pack`，不带 --book-text：文本已由本命令落好）。只写本机数据目录，最后统一 db sync。"""
    ch = f"{int(book[3:]):03d}"
    pubs = sorted((ws / "reports" / book / "_publish").glob(f"{ch}-r*"), key=lambda p: int(p.name.rsplit("-r", 1)[1]))
    if not pubs or not (pubs[-1] / f"{ch}.pending.json").exists():
        return "no-sheet（没有已出的新单）"
    rev = pubs[-1].name
    env = {**os.environ, "GUJI_WORKSPACE": str(ws), "GUJI_DB_NO_GLYPH": "1"}
    for _ in range(3):
        p = subprocess.run([sys.executable, str(cv / "scripts" / "zhengli" / "republish.py"), "push", "--book", book, "-w", str(ws),
                            "--rev", rev, "--yes", "--no-pack"], cwd=cv, env={**env, "PYTHONPATH": str(cv)}, capture_output=True, text=True)
        if p.returncode == 0:
            return f"pushed {rev}"
        if not re.search(r"Connection reset|timed out|HTTP Error 5", p.stdout + p.stderr):
            break
    return f"sheet-fail {rev}：{(p.stdout + p.stderr).strip()[-200:]}"


def db_sync(ws: Path, cv: Path, tries: int = 4) -> bool:
    env = {**os.environ, "GUJI_WORKSPACE": str(ws), "GUJI_DB_NO_GLYPH": "1"}
    env.setdefault("GUJI_ACTOR", "swap-book-text")        # 推中心库要有操作人
    for _ in range(tries):
        p = subprocess.run([sys.executable, "-m", "open_guji_cv.cli_v2", "db", "sync", "-w", str(ws), "--no-glyph"],
                           cwd=cv, env=env, capture_output=True, text=True)
        if p.returncode == 0:
            return True
    return False


def cmd_book_text(a, books: list[str]) -> int:
    ws = Path(a.workspace).resolve()
    src = Path(a.book_text).resolve()
    sp = (Path(_bt_dir(Path("."), a.text_id)).as_posix().lstrip("./"),)
    wt = _worktree(src, Path(a.worktree or (str(src) + "-swap")).resolve(), sparse=sp)
    out_root = ws / "reports" / "_swap" / "book-text"
    res = {}
    for b in books:
        export = Path(a.export) if a.export else _latest_export(ws, b)
        if not export or not export.exists():
            res[b] = {"status": "blocked", "why": "找不到导出目录（reports/<册>/_cycle/*/export），先 swap run 或给 --export"}
            continue
        _worktree(src, wt)
        ch = f"{int(b[3:]):03d}"
        r = do_book(wt, ws, b, a.text_id, export, note=a.note or f"{b} 换包（{export.parent.name}），增删格按格级对照表落 book-text",
                    push=a.push, pending=pending_cells_of(ws, a.text_id, ch), out_dir=out_root / b,
                    glyph_db=Path(a.glyph_db) if getattr(a, "glyph_db", None) else None, open_pr_=not getattr(a, "no_pr", False),
                    cv=Path(a.cv) if getattr(a, "cv", None) and (Path(a.cv) / "scripts" / "zhengli" / "republish.py").exists() else None)
        res[b] = {k: v for k, v in r.items() if k not in ("char_detail", "left", "review")}
        if getattr(a, "sheet", False) and r["status"] == "pushed":
            res[b]["sheet"] = push_sheet(ws, b, Path(a.cv))
        print(f"{b}\t{r['status']}\t{r.get('why', '')}\t{res[b].get('sheet', '')}", file=sys.stderr)
    if any(str(v.get("sheet", "")).startswith("pushed") for v in res.values()):
        ok = db_sync(ws, Path(a.cv))
        print(f"中心库同步：{'好' if ok else '失败，手动 guji db sync -w ' + str(ws)}；网站随 swap run 的发布或每日 proofing-sync 上线", file=sys.stderr)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0 if all(v["status"] in ("pushed", "committed", "pr-needed", "pr-opened") for v in res.values()) else 2


def cmd_finish_merged(a, books: list[str]) -> int:
    """R8：合并后收尾。对照表取 book-text 版本目录 ``lineage/revisions/<册>-*.tsv`` 里最新的一张（含 ``--table`` 指定）。"""
    from . import finish as F
    ws, src = Path(a.workspace).resolve(), Path(a.book_text).resolve()
    vdir = _bt_dir(src, a.text_id) / "default"
    res = {}
    for b in books:
        tabs = sorted((vdir / F.REV_DIR).glob(f"{b}-*.tsv"), key=lambda p: p.stat().st_mtime)
        tp = Path(a.table) if getattr(a, "table", None) else (tabs[-1] if tabs else None)
        if tp is None:      # book-text 校验器还不认 lineage/ 时表没入库：退到本机 reports 里的那张
            loc = ws / "reports" / "_swap" / "book-text" / b / f"old_new_cells_vol{int(b[3:]):02d}.tsv"
            tp = loc if loc.exists() else None
        if not tp or not tp.exists():
            res[b] = {"status": "blocked", "why": f"book-text 里没有 {F.REV_DIR}/{b}-*.tsv（先 guji swap book-text 落文本并合并）"}
            continue
        raw = F.read_table(tp)
        rows = [dict(old=(r["旧格"].split(":", 1)[1] if r["旧格"] else ""), new=(r["新格"].split(":", 1)[1] if r["新格"] else ""),
                     kind=r["类别"], oc=r["旧字"], nc=r["新字"]) for r in raw]
        res[b] = {"status": "done", **F.finish(ws, b, rows, load_human(b), run=(tp.stem.split("-", 1)[1] if "-" in tp.stem else "local"), commit=getattr(a, "commit", "") or ""),
                  "table": str(tp)}
        allt = [F.read_table(p) for p in sorted((vdir / F.REV_DIR).glob(f"{b}-*.tsv"), key=lambda p: p.stat().st_mtime)]
        red = F.redirect_map(allt)
        rp = ws / "reports" / "_swap" / "finish" / b / "redirects.tsv"
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text("旧格\t现行格\n" + "".join(f"{o}\t{n or ''}\n" for o, n in sorted(red.items())), encoding="utf-8")
        res[b]["redirects"] = {"file": str(rp), "n": len(red)}
        print(f"{b}\tdone\t无锚人裁 {res[b].get('recheck', {}).get('n', '-')}\tredirect {len(red)}", file=sys.stderr)
    print(json.dumps(res, ensure_ascii=False, indent=1, default=str))
    return 0 if all(v["status"] == "done" for v in res.values()) else 2
