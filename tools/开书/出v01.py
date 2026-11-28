#!/usr/bin/env python3
"""薄壳：已搬进 guji 包，等价于 `guji launch prepare`（11-28，GM4）。"""
import sys

from guji_manager.launch.v01 import main

if __name__ == "__main__":
    sys.exit(main())
