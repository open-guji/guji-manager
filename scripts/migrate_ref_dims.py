"""册配置参校本补四维（CV0 2026-11-28，Sheldon 定「按四个维度走，旧书尽快替换，不重跑」）。

cv 0.9.17 起只认 `references[]` 的 `form`／`script`／`accuracy`（＋`accuracy_evidence`），`quality`／`line_is_column`
与 seed_admit 的 `reference_trust`／`ref_lib_coord`／`follow_ref_variants`／`ref_topk_follow` 不再读。
本脚本**只加不删**（第一期）：给工作区数据目录里 `books/*.yaml`、`config/book_defaults.yaml` 的每份参校本补上缺的四维键，
旧键原样留着给还钉 0.7.x／0.9.x 老 cv 的册用；第二期（没有册钉读旧键的 cv 后）再删。

- `form` 按 `line_is_column` 换（true→column、false→text），没写不补；
- `accuracy`／`script`／`accuracy_evidence` 按下面 `LABELS`（按参校本文件名），表里没有的不标（＝low）；
- 已经写了的键不动；按行插入，不改注释与原有写法（块式插在这一项最后一行后，流式插在 `}` 前）。

    python scripts/migrate_ref_dims.py <数据目录>/<分支>/<工作区 id> [...] [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

#: 参校本文件名 → 四维（CV0 11-27 实测，门槛 very_high ≥99.9%、high ≥99.5%、mid ≥98%，待审全算错的下限定档；
#: 实测表见 cv doc/design/参校本四维与准确度分档.md 第三节）
LABELS: dict[str, dict] = {
    "shiji_wyg_daizhige.txt": {"script": "faithful", "accuracy": "very_high",
                               "accuracy_evidence": "CV0 11-27 史記 03 定字 49,965 格一致 99.988%，下限 99.958%"},
    "qtw_kanripo_grid.txt": {"script": "trad", "accuracy": "high",
                             "accuracy_evidence": "CV0 11-27 全唐文 030/050/070/090 一致 99.57–99.96%，下限 99.52%；码位异体差 1.36%（已归一）"},
    "qtw_front_wiki.txt": {"accuracy": "low"},
    "siku_daizhige.txt": {"script": "faithful", "accuracy": "high",
                          "accuracy_evidence": "CV0 11-27 殿本 vol05/vol28 一致 99.75%／99.86%，下限 99.73%"},
    "zongmu_wenyuange_wikisource.txt": {"accuracy": "low"},
    "zongmu_wuyingdian_reference.txt": {"accuracy": "low"},
    "maijing_kanripo_sbck.txt": {"script": "faithful", "accuracy": "mid",
                                 "accuracy_evidence": "CV0 11-27 脉经 01 定字 9,599 格一致 99.667%，下限 99.397%"},
    "maijing_kanripo_sbck_2.txt": {"script": "faithful", "accuracy": "mid"},
    "maijing_wikisource.txt": {"accuracy": "low"},
    "zfl_mbj_ocr.txt": {"script": "faithful", "accuracy": "high",
                        "accuracy_evidence": "未量；沿用原 reference_trust: high（CV0 11-28 迁移）"},
}
ORDER = ("form", "script", "accuracy", "accuracy_evidence")
_FLOW = re.compile(r"^(\s*-\s*)\{(.*)\}(\s*(#.*)?)$")
_BLOCK = re.compile(r"^(\s*)-\s+file:\s*(\S+)")


def _q(v: str) -> str:
    return f'"{v}"' if any(c in v for c in ":#{}[],'\"") or " " in v else v


def _want(entry: dict) -> list[tuple[str, str]]:
    f = str(entry.get("file") or "").strip("'\"")
    add = dict(LABELS.get(f, {}))
    lic = str(entry.get("line_is_column", "")).lower()
    if lic in ("true", "false"):
        add["form"] = "column" if lic == "true" else "text"
    return [(k, add[k]) for k in ORDER if k in add and k not in entry]


def _flow_items(body: str) -> dict:
    out = {}
    for part in body.split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def migrate_text(text: str) -> tuple[str, int]:
    lines = text.split("\n")
    out: list[str] = []
    n = 0
    i = 0
    while i < len(lines):
        ln = lines[i]
        m = _FLOW.match(ln)
        if m and "file:" in m.group(2):
            items = _flow_items(m.group(2))
            add = _want(items)
            if add:
                body = m.group(2).rstrip() + "".join(f", {k}: {_q(v)}" for k, v in add)
                ln = f"{m.group(1)}{{{body}}}{m.group(3) or ''}"
                n += 1
            out.append(ln)
            i += 1
            continue
        m = _BLOCK.match(ln)
        if m:
            ind = len(m.group(1)) + 2           # 「- 」后的键列
            entry = {"file": m.group(2)}
            block = [ln]
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                s = nxt.strip()
                lead = len(nxt) - len(nxt.lstrip())
                if s and not s.startswith("#") and lead == ind and ":" in s and not s.startswith("-"):
                    k, v = s.split(":", 1)
                    entry[k.strip()] = v.split("#", 1)[0].strip()
                    block.append(nxt)
                    j += 1
                    continue
                break
            add = _want(entry)
            out.extend(block)
            if add:
                out.extend(f"{' ' * ind}{k}: {_q(v)}" for k, v in add)
                n += 1
            i = j
            continue
        out.append(ln)
        i += 1
    return "\n".join(out), n


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dirs", nargs="+", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    total = 0
    for d in a.dirs:
        files = sorted((d / "books").glob("*.yaml")) + [d / "config" / "book_defaults.yaml"]
        for f in files:
            if not f.exists():
                continue
            src = f.read_text(encoding="utf-8")
            new, n = migrate_text(src)
            if n:
                total += n
                print(f"{f}: 补 {n} 份")
                if not a.dry_run:
                    f.write_text(new, encoding="utf-8")
    print(f"共补 {total} 份参校本{'（dry-run）' if a.dry_run else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
