"""guji-manager：pipeline（open-guji-cv）的 manager。设计见 open-guji-cv 仓 `doc/design/拆分-pipeline与manager.md`。"""

__version__ = "0.0.1"

#: 本版 manager 支持的 pipeline 契约版本范围（闭区间）。契约见 open-guji-cv `doc/契约.md`；兼容矩阵见 COMPAT.md。
SUPPORTED_CONTRACT = (1, 1)
