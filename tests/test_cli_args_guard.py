"""守卫：每条子命令的处理函数读的 `args.X`，都得是它那个 parser 定义过的参数。

11-07 A31 报 `guji corpus pin` 崩在 `args.shift_book_ver`：给 rekey-cells 加 `--shift-book` 时整词替换
把 `args.book` 连带改坏，`recheck` 的 `args.book` 也成了 `args.shift_book`。手拼 SimpleNamespace 的测试抓不到，
这里拿真 parser 的 dest 对处理函数的源码（只看函数本体，不追进它调的辅助函数）。"""

from __future__ import annotations

import argparse
import ast
import inspect
import textwrap

import pytest

from guji_manager import commands


def _subparsers() -> dict[str, argparse.ArgumentParser]:
    ap = argparse.ArgumentParser(prog="guji")
    sub = ap.add_subparsers(dest="command")
    seen = set()
    for add, _ in commands.COMMANDS.values():
        if add not in seen:
            add(sub)
            seen.add(add)
    return sub.choices


def _dests(p: argparse.ArgumentParser) -> set[str]:
    out = set()
    for act in p._actions:
        out.add(act.dest)
        if isinstance(act, argparse._SubParsersAction):     # 二级子命令（如 guji db pull）的参数并进来
            for sp in act.choices.values():
                out |= _dests(sp)
    return out


def _arg_reads(fn) -> set[str]:
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    f = tree.body[0]
    if not f.args.args:
        return set()
    name = f.args.args[0].arg
    return {n.attr for n in ast.walk(f)
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == name
            and isinstance(n.ctx, ast.Load)}


PARSERS = _subparsers()


@pytest.mark.parametrize("command", sorted(commands.COMMANDS))
def test_handler_reads_only_defined_args(command):
    fn = commands.COMMANDS[command][1]
    missing = _arg_reads(fn) - _dests(PARSERS[command]) - {"command"}
    assert not missing, f"guji {command}：{fn.__module__}.{fn.__name__} 读了 parser 没定义的 args.{sorted(missing)}"
