"""红线（A31 定，方案 8.7 第 2 条）：任一条踩了，整册不写进本轮、标「超红线」进轮报告，A31 看。

- 人裁丢失（换号后仍绑不回）> 本册人裁格数的 1%
- 锚点余项（标点＋专名分流）> 本册参与挪动的锚点数的 15%（分母＝改＋分流；25 册回放实测约 9%）
- 任何一步程序报错，或字形库 verify 不过
红线以内的余项（待审格）照常出卡，不拦标 main。跑满一轮后按实测再收紧（常量在此，改一处）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

HUMAN_LOSS_MAX = 0.01
ANCHOR_LEFT_MAX = 0.15


@dataclass
class Redline:
    book: str
    human_total: int = 0
    human_lost: int = 0
    anchors_moved: int = 0
    anchors_left: int = 0
    errors: list[str] = field(default_factory=list)
    glyph_verify_ok: bool = True
    tripped: list[str] = field(default_factory=list)

    @property
    def human_loss_rate(self) -> float:
        return self.human_lost / self.human_total if self.human_total else 0.0

    @property
    def anchor_left_rate(self) -> float:
        t = self.anchors_moved + self.anchors_left
        return self.anchors_left / t if t else 0.0

    @property
    def ok(self) -> bool:
        return not self.tripped

    def line(self) -> str:
        s = "超红线：" + "；".join(self.tripped) if self.tripped else "红线内"
        return (f"{self.book}\t{s}\t人裁丢失 {self.human_lost}/{self.human_total}（{self.human_loss_rate:.2%}）\t"
                f"锚点余项 {self.anchors_left}/{self.anchors_moved + self.anchors_left}（{self.anchor_left_rate:.2%}）")


def check(book: str, *, human_total: int, human_lost: int, anchors_moved: int, anchors_left: int,
          errors=(), glyph_verify_ok: bool = True) -> Redline:
    r = Redline(book, human_total, human_lost, anchors_moved, anchors_left, list(errors), glyph_verify_ok)
    if human_lost and (not human_total or r.human_loss_rate > HUMAN_LOSS_MAX):
        r.tripped.append(f"人裁丢失 {human_lost}/{human_total} 超 {HUMAN_LOSS_MAX:.0%}")
    if r.anchor_left_rate > ANCHOR_LEFT_MAX:
        r.tripped.append(f"锚点余项 {anchors_left}/{anchors_moved + anchors_left} 超 {ANCHOR_LEFT_MAX:.0%}")
    if r.errors:
        r.tripped.append(f"程序报错 {len(r.errors)} 处：{r.errors[0]}")
    if not glyph_verify_ok:
        r.tripped.append("字形库 verify 不过")
    return r
