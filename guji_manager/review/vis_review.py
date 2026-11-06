"""看图裁定（对话统一审，不调 API）的导出与写入：给「机器字＝参校字、只差字形证据」的待审格用（A23 2026-11-06，L04 库认不出）。

文意终审（`guji-manager final-review`，ctx-m1）只读文字，判不了这类格：机器字本来就是参校字，读文意永远「通」，
要看的是**图上刻的是不是这个字**。这里把格图、参校字刻例、库首位刻例拼成对照图，配上管线同口径的裁定键窗口，
交对话逐格看图；回来的答案写成裁定事件（`feedback/rulings/<批次>.jsonl`，kind `ctx_ruling`，group `O`，
prompt_ver `vis-o1`，子类按原因码），seed_admit 的 `vis_rulings`（`_vis_ruling_pass`）下次重放时按窗口命中放行。

  # 1 取格：pending-stats 出 cells.tsv（带 detail 列），按原因／细分筛，算窗口、取格图、拼对照图
  guji-manager pending-stats --ws siku-zongmu --text 96mid1ogzk --out /tmp/ps
  python -m guji_manager.review.vis_review export --cells /tmp/ps/cells.tsv --reason lib_unrecognized --detail lib_other \\
      --pkg <出单产物包根> --ws siku-zongmu --text 96mid1ogzk --out /tmp/l04
  # 2 对话看图：读 /tmp/l04/sheets/*.png 与 todo.jsonl，逐格在 answers.jsonl 补 char／conf（high/mid/low）／why（≤60 字）
  # 3 写裁定（只有 conf=high 且 char＝参校字的才 admit_ok；其余也写，记弃权免得重看）
  python -m guji_manager.review.vis_review write /tmp/l04/answers.jsonl --ruling-dir <数据目录>/feedback/rulings \\
      --batch llm-vis-YYYYMMDD-<谁>-l04 --subclass L04
  # 4 推库（push-safety：备份、guji db pull、GUJI_ACTOR、guji db push）；下一轮从 seed_admit 起重放即生效

产物包要是**出这版待审单的那个包**（`guji products pack list <册>` 里的 `rev-<单号>`，或现行 ★main），窗口才和管线一致。
seed_admit 只收 `_VIS_RULING_SUBCLASSES` 里的子类（cv #1184 起含 L04）；别的原因要用这条路，先请 cv 加子类。
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

PROMPT_VER = "vis-o1"
GROUP = "O"
CONF = ("high", "mid", "low")


def _read_tsv(p: Path) -> list[dict]:
    with open(p, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def pick(rows: list[dict], reason: str, detail: str | None = None, vol_fmt: str = "vol{n:02d}") -> list[dict]:
    """cells.tsv 行 → 待看格 [{id, vol, cell, ref, detail}]；`detail` 是 pending_reason_detail 的前缀（如 lib_other）。"""
    out = []
    for r in rows:
        if (r.get("pending_reason") or "") != reason or r.get("kind", "body") != "body":
            continue
        d = r.get("detail") or ""
        if detail and not d.startswith(detail + ":") and d != detail:
            continue
        n = int(re.sub(r"\D", "", str(r["vol"])) or 0)
        out.append({"id": f"{vol_fmt.format(n=n)}:{r['cell']}", "vol": str(r["vol"]), "cell": r["cell"],
                    "ref": r.get("ref") or "", "lib_top": r.get("top") or "", "detail": d})
    return out


def answers_to_events(rows: list[dict], *, batch: str, subclass: str, model: str, ts: str | None = None) -> list:
    """答案行（todo 行＋char/conf/why）→ 裁定事件。只有 conf=high 且 char＝参校字（坐标对位字）才 admit_ok。"""
    from .. import _cv
    make_event, EventTarget = _cv.make_event, _cv.EventTarget
    ctx_hash, KIND, SOURCE, OTHER = _cv.ruling_ctx_hash, _cv.RULING_KIND, _cv.RULING_SOURCE, _cv.RULING_OTHER
    evs = []
    for n, a in enumerate(rows, 1):
        ch, conf = a.get("char"), a.get("conf")
        if conf not in CONF or not ch:
            raise SystemExit(f"第 {n} 行缺 char 或 conf 不在 {CONF}：{a.get('id')}")
        other = ch == OTHER
        left, right = a.get("left") or "", a.get("right") or ""
        payload = {"source": SOURCE, "group": GROUP, "char": None if other else ch, "other": other, "conf": conf,
                   "why": (a.get("why") or "")[:60], "model": model, "prompt_ver": PROMPT_VER, "cell": a["id"], "tok": {},
                   "ctx": {"left": left, "right": right, "hash": ctx_hash(left, right)},
                   "subclass": subclass, "ref": a.get("ref_align") or "", "coord_ref": a.get("ref") or "",
                   "machine": a.get("lib_top") or "", "admit_ok": conf == "high" and not other and ch == a.get("ref"),
                   "pending_reason": a.get("reason") or "unknown", "detail": a.get("detail") or ""}
        evs.append(make_event(batch, n, KIND, EventTarget(step="seed_admit", unit="cell", key=a["id"], book=a["id"].split(":")[0]),
                              payload, actor="model", ts=ts or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
    return evs


def _sheets(todo: list[dict], ws: str, text: str, out: Path, per: int = 10) -> list[Path]:
    """格图＋参校字刻例＋库首位刻例 拼成对照图（取线上待审单的雪碧图）。没装 PIL、单子上没图的格跳过图。"""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("没装 Pillow，不出对照图（todo.jsonl 照出）", file=sys.stderr)
        return []
    from .. import _cv
    from ..pending_stats import load_db
    lists, _, _ = load_db(ws, text, None)
    need: dict[str, dict] = {}
    for t in todo:
        doc = lists.get(f"{int(re.sub(r'[^0-9]', '', t['vol']) or 0):03d}") or lists.get(t["vol"]) or {}
        c = next((x for x in doc.get("cells") or [] if x.get("cell") == t["cell"]), None)
        if not c or not c.get("img"):
            continue
        sp = {s["name"]: s["sha256"] for s in doc.get("sprites") or []}
        alts = [x for x in c.get("alt") or [] if x.get("c") == t["ref"]][:2] + [x for x in c.get("alt") or [] if x.get("c") == t["lib_top"]][:1]
        t["_crops"] = [(c["img"], "")] + [(x["g"], f"{x['c']} {x.get('s', '')}") for x in alts if x.get("g")]
        for g, _ in t["_crops"]:
            need[g["s"]] = sp.get(g["s"])
    cache = _cv.BlobCache()
    cache.ensure(_cv.WorkerSource(), [s for s in need.values() if s], ext="webp")
    out.mkdir(parents=True, exist_ok=True)
    font = _cjk_font(ImageFont)
    files, ims = [], {}
    rows = [t for t in todo if t.get("_crops")]
    for i in range(0, len(rows), per):
        chunk = rows[i:i + per]
        S = Image.new("RGB", (5 * 160 + 260, 170 * len(chunk)), "white")
        dr = ImageDraw.Draw(S)
        for j, t in enumerate(chunk):
            y = j * 170
            for k, (g, lab) in enumerate(t["_crops"]):
                sha = need.get(g["s"])
                if not sha:
                    continue
                im = ims.get(sha) or ims.setdefault(sha, Image.open(cache.path(sha)).convert("RGB"))
                S.paste(im.crop((g["x"], g["y"], g["x"] + g["w"], g["y"] + g["h"])).resize((150, 150)), (k * 160, y))
                if lab:
                    dr.text((k * 160 + 2, y + 152), lab, fill="red", font=font)
            dr.text((5 * 160, y + 10), f"{i + j + 1}. {t['id']}", fill="black", font=font)
            dr.text((5 * 160, y + 40), f"ref={t['ref']} lib={t['lib_top']}", fill="black", font=font)
            dr.text((5 * 160, y + 70), t["detail"], fill="black", font=font)
        f = out / f"sheet_{i // per + 1:02d}.png"
        S.save(f)
        files.append(f)
    for t in todo:
        t.pop("_crops", None)
    return files


def _cjk_font(ImageFont, size: int = 16):
    """标签用的中文字体：`GUJI_CJK_FONT`，否则 fc-list 找一个 zh 字体；都没有用缺省（中文显示成方框）。"""
    import os
    import subprocess
    cand = [os.environ.get("GUJI_CJK_FONT") or ""]
    try:
        cand += subprocess.run(["fc-list", ":lang=zh", "file"], capture_output=True, text=True, timeout=5).stdout.replace(":", "").split()[:3]
    except (OSError, subprocess.SubprocessError):
        pass
    for f in cand:
        try:
            if f:
                return ImageFont.truetype(f, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m guji_manager.review.vis_review", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--cells", type=Path, required=True, help="pending-stats 的 cells.tsv（带 detail 列）")
    e.add_argument("--reason", default="lib_unrecognized")
    e.add_argument("--detail", help="只取这个细分（pending_reason_detail 前缀），如 lib_other")
    e.add_argument("--pkg", type=Path, required=True, help="出单产物包根（<册>/<步>/pNNNN.json）")
    e.add_argument("--vol-fmt", default="vol{n:02d}", help="包里的册目录名：殿本 vol{n:02d}，史記 {n:02d}，全唐文 {n:03d}")
    e.add_argument("--ws", help="中心库工作区（取格图出对照图）；不给就只出 todo.jsonl")
    e.add_argument("--text", help="文本号（线上单路径里的）")
    e.add_argument("--out", type=Path, required=True)
    w = sub.add_parser("write")
    w.add_argument("answers", type=Path)
    w.add_argument("--ruling-dir", type=Path, required=True, help="<数据目录>/feedback/rulings")
    w.add_argument("--batch", required=True, help="如 llm-vis-20261106-a23-l04")
    w.add_argument("--subclass", default="L04", help="写进裁定的子类（seed_admit 只收 _VIS_RULING_SUBCLASSES 里的）")
    w.add_argument("--model", default="claude-session-hand-review")
    a = ap.parse_args(argv)
    if a.cmd == "export":
        from ..final_review import pack
        todo = pick(_read_tsv(a.cells), a.reason, a.detail, a.vol_fmt)
        sort_fn, _, _, width = pack.default_cv()
        win = pack.key_windows(a.pkg, [t["id"] for t in todo], sort_fn, width)
        for t in todo:
            left, right, ref_align = win.get(t["id"], ("", "", ""))
            t.update({"left": left, "right": right, "ref_align": ref_align, "reason": a.reason, "window_ok": t["id"] in win})
        a.out.mkdir(parents=True, exist_ok=True)
        sheets = _sheets(todo, a.ws, a.text, a.out / "sheets") if a.ws and a.text else []
        (a.out / "todo.jsonl").write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in todo), encoding="utf-8")
        bad = sum(1 for t in todo if not t["window_ok"])
        print(f"{len(todo)} 格 → {a.out}/todo.jsonl（取不到窗口 {bad}），对照图 {len(sheets)} 张")
        print("下一步：对话看图，逐行补 char／conf／why 存成 answers.jsonl，再 write。")
    else:
        from .. import _cv
        rows = [json.loads(x) for x in a.answers.read_text(encoding="utf-8").splitlines() if x.strip()]
        evs = answers_to_events(rows, batch=a.batch, subclass=a.subclass, model=a.model)
        log = _cv.RulingLog(str(a.ruling_dir.parent if a.ruling_dir.name == "rulings" else a.ruling_dir))
        log.append(evs)
        ok = sum(1 for e in evs if e.payload["admit_ok"])
        print(f"写 {len(evs)} 条（可放 {ok}）→ {log.batch_path(a.batch)}；推库前 guji db pull，设 GUJI_ACTOR")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
