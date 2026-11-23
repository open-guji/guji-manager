"""评测护栏：按书、按集写死的「不许变差」门（CV3，2026-11-23；Sheldon 定护栏放 dataset、manager 发版时读）。

护栏表在数据集仓 `guards/*.yaml`（见那里的文件头）：每条＝评测器 id＋指标名＋方向（max 不许超过／min 不许低于）
＋基线＋放宽后的门 limit，要字形库的再写 `lib: <书id>`。

- `guji eval run` 跑完一个评测器，若护栏表里有它，就逐条比；任一条越过 limit → 状态 regressed（回归门失败）。
- `guji eval guard` 把护栏表里的评测器全跑一遍出总表；缺库（没给 `--lib`）的记「未验证」，不算过。
  发版（cv、manager 的 rc）必须全过，见两仓 `doc/版本号规矩.md`。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Guard:
    eval: str
    metric: str
    dir: str            # max | min
    limit: float
    baseline: float | None = None
    book: str = ""
    set: str = ""
    lib: str = ""
    since: str = ""
    src: str = ""       # 来自哪个文件

    def check(self, value) -> str:
        """pass | fail | missing（报告里没有这个指标）。"""
        if value is None or isinstance(value, str):
            return "missing"
        if self.dir == "max":
            return "pass" if value <= self.limit else "fail"
        return "pass" if value >= self.limit else "fail"

    def label(self) -> str:
        op = "≤" if self.dir == "max" else "≥"
        b = f"（基线 {self.baseline}）" if self.baseline is not None else ""
        return f"{self.book} {self.metric} {op} {self.limit}{b}"


@dataclass
class GuardResult:
    guard: Guard
    value: object = None
    verdict: str = "missing"    # pass | fail | missing | unverified

    def to_dict(self) -> dict:
        g = self.guard
        return dict(eval=g.eval, book=g.book, metric=g.metric, dir=g.dir, limit=g.limit,
                    baseline=g.baseline, value=self.value, verdict=self.verdict)


def load_guards(dataset_root: Path) -> list[Guard]:
    """读 `<dataset>/guards/*.yaml`；没有目录就空表。格式错直接抛，别静默当没护栏。"""
    d = Path(dataset_root) / "guards"
    if not d.is_dir():
        return []
    import yaml
    out: list[Guard] = []
    for f in sorted(d.glob("*.yaml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        for i, r in enumerate(doc.get("guards") or []):
            miss = [k for k in ("eval", "metric", "dir", "limit") if k not in r]
            if miss or r["dir"] not in ("max", "min"):
                raise ValueError(f"{f.name} 第 {i + 1} 条护栏缺 {miss} 或 dir 不是 max/min：{r}")
            out.append(Guard(eval=str(r["eval"]), metric=str(r["metric"]), dir=r["dir"], limit=float(r["limit"]),
                             baseline=r.get("baseline"), book=str(r.get("book", "")), set=str(r.get("set", "")),
                             lib=str(r.get("lib", "") or ""), since=str(r.get("since", "") or ""), src=f.name))
    return out


def guards_for(guards: list[Guard], eval_id: str) -> list[Guard]:
    return [g for g in guards if g.eval == eval_id]


def check_report(rep, guards: list[Guard]) -> list[GuardResult]:
    """拿一个 EvalReport 比它的护栏。报告没跑成（failed／skipped）一律记 unverified。"""
    vals = {m.name: m.value for m in (rep.metrics or [])}
    out = []
    for g in guards:
        if rep.status in ("failed", "skipped"):
            out.append(GuardResult(g, None, "unverified"))
            continue
        v = vals.get(g.metric)
        out.append(GuardResult(g, v, g.check(v)))
    return out


@dataclass
class GuardSummary:
    results: list[GuardResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.results) and all(r.verdict == "pass" for r in self.results)

    def counts(self) -> dict[str, int]:
        c: dict[str, int] = {}
        for r in self.results:
            c[r.verdict] = c.get(r.verdict, 0) + 1
        return c

    def table(self) -> str:
        mark = {"pass": "✓", "fail": "✗", "missing": "?", "unverified": "–"}
        lines = [f"{'':2}{'评测器':20s} {'护栏':36s} {'实测':>10s}"]
        for r in self.results:
            v = "" if r.value is None else str(r.value)
            lines.append(f"{mark[r.verdict]} {r.guard.eval:20s} {r.guard.label():36s} {v:>10s}")
        c = self.counts()
        lines.append(f"\n护栏 {len(self.results)} 条：过 {c.get('pass', 0)}／越线 {c.get('fail', 0)}／"
                     f"缺指标 {c.get('missing', 0)}／未验证 {c.get('unverified', 0)}"
                     + ("　→ 全过" if self.ok else "　→ **不能发版**"))
        return "\n".join(lines)
