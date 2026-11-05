"""大模型只读文意终审（L2/L3）跨书流水线（T2，A31 2026-11-05）。

由殿本 r4 的 build/finalize/write_rulings（ai-team `domain/CV/质检/终审判读-殿本-r4-2026-11-04/`）抽出，换书不改代码：
`select`（从 cells.tsv 选格）→ `build`（取窗口与候选）→ `batches`（按类分批、A/B 两路、出判读会话清单）
→（会话判读，不调 API）→ `status`（核齐）→ `finalize`（门槛＋金标）→ `write`（写 ctx_ruling）。
一键：`guji-manager final-review run` = select＋build＋batches。
"""
