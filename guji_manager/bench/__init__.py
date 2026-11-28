"""`guji bench`：benchmark 统一入口（CV0 2026-11-28，Sheldon 定「每个 benchmark 统一接口、命令接进 guji-manager」）。

登记表、结果格式、各 bench 的跑法在 cv `open_guji_cv.eval.bench`；本包只做两件事：
按书备齐资源（`resources.py`）、命令行（`cli.py`）。老评测器（`eval/registry.py`）经 `legacy.py` 照旧能跑，
P1 各线接成原生 bench 后删。设计与分派：ai-team `domain/CV/规范/bench统一接口-2026-11-28.md`。
"""
