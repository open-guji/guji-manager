"""migrate_v03.py：punct／entity 迁到 v0.3 落盘写法（A 每条一行 + B default_source；C 删下标另议，本脚本不删）。

用法：python migrate_v03.py <目录或文件>... [--apply]    不带 --apply 只报告（dry-run）
做法：default_source＝本文件出现最多的 source；条目 source 与它相同则不写；$schema 升到 v0.3；
      用 guji_manager.formats.guji_format.dump_json 写。迁移前后做语义比对：除 source 的表示方式外逐条相同，
      且每条 effective_source 不变；比对不过的文件不写、列出。
"""
import argparse, collections, json, sys
from pathlib import Path
from guji_manager.formats.guji_format import dump_json, effective_source

LAYERS = {"punct": "punctuations", "entity": "entities"}


def migrate(doc: dict, key: str) -> dict:
    ents = doc[key]
    cnt = collections.Counter(e.get("source") for e in ents if e.get("source"))
    new = {}
    for k, v in doc.items():
        if k == key:
            continue
        new[k] = v
    new["$schema"] = doc["$schema"].replace("/v0.1.json", "/v0.3.json").replace("/v0.2.json", "/v0.3.json")
    default = cnt.most_common(1)[0][0] if cnt else None
    out_doc = {}
    for k, v in new.items():
        out_doc[k] = v
        if k == "text_version" and default:
            out_doc["default_source"] = default
    if default and "default_source" not in out_doc:
        out_doc["default_source"] = default
    out_doc[key] = [{k: v for k, v in e.items() if not (k == "source" and v == default)} for e in ents]
    return out_doc


def same(old: dict, new: dict, key: str) -> bool:
    if len(old[key]) != len(new[key]):
        return False
    for a, b in zip(old[key], new[key]):
        if effective_source(a, old) != effective_source(b, new):
            return False
        a2 = {k: v for k, v in a.items() if k != "source"}
        b2 = {k: v for k, v in b.items() if k != "source"}
        if a2 != b2 or list(a2) != list(b2):
            return False
    rest_old = {k: v for k, v in old.items() if k not in (key, "$schema", "default_source")}
    rest_new = {k: v for k, v in new.items() if k not in (key, "$schema", "default_source")}
    return rest_old == rest_new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    files = []
    for p in map(Path, a.paths):
        files += sorted(p.rglob("*.punct.json")) + sorted(p.rglob("*.entity.json")) if p.is_dir() else [p]
    before = after = bad = skipped = 0
    for f in files:
        key = LAYERS["punct" if f.name.endswith(".punct.json") else "entity"]
        raw = f.read_text(encoding="utf-8")
        old = json.loads(raw)
        if old.get("$schema", "").endswith("/v0.3.json"):
            skipped += 1
            continue
        new = migrate(old, key)
        out = dump_json(new)
        if not same(old, json.loads(out), key):
            bad += 1
            print("语义比对不过:", f)
            continue
        before += len(raw.encode())
        after += len(out.encode())
        if a.apply:
            f.write_text(out, encoding="utf-8")
    print(f"文件 {len(files)}，已是 v0.3 {skipped}，比对失败 {bad}；体积 {before}→{after}（{after / max(before, 1):.0%}）{'，已写' if a.apply else '，dry-run'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
