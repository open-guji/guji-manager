from __future__ import annotations

import sys

SUB = {"round-report": "round_report", "gold": "gold", "audit": "audit", "leverage": "leverage", "freeze": "freeze", "push-rounds": "progress_rounds", "auto-round": "progress_rounds:auto_main"}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in SUB:
        print("用法：guji-manager iterate {" + "|".join(SUB) + "} …（-h 看各自参数）", file=sys.stderr)
        return 2
    import importlib
    mod, _, fn = SUB[argv[0]].partition(":")
    return getattr(importlib.import_module(f"guji_manager.iterate.{mod}"), fn or "main")(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
