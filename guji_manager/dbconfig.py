"""连库配置：所有数据库「怎么连」集中在 databases.toml，代码只按库名取（2026-11-22 用户定）。

    from guji_manager import dbconfig
    spec = dbconfig.get("central")      # {'driver': 'd1-worker', 'url': ..., 'db': 'main', 'token': [...], ...}
    dbconfig.tokens("central")          # 依次试的令牌值（已去重、去空）

覆盖顺序（后者盖前者，按库逐键合并）：包内 ``config/databases.toml`` → ``~/.config/guji/databases.toml``
→ ``GUJI_DB_CONFIG`` 指的文件 → 各库 ``env_*`` 键点名的单项环境变量（老用法，如 ``GUJI_DATA_URL``）。
令牌只写环境变量名，值不进配置。说明见 ``doc/数据库/README.md``。
"""
from __future__ import annotations

import copy
import os
from importlib import resources
from pathlib import Path

try:                                    # 3.11+
    import tomllib as _toml
except ModuleNotFoundError:             # 3.10：没有 tomllib，用极简解析（只认本仓配置用到的写法）
    _toml = None

USER_FILE = Path("~/.config/guji/databases.toml")
#: 单项环境变量盖哪个键：env_url → url、env_db → db、env_path → path（driver 随之改 sqlite）、env_user → user
_ENV_KEYS = {"env_url": "url", "env_db": "db", "env_path": "path", "env_user": "user"}
DRIVERS = ("d1-worker", "sqlite", "pg-tunnel", "postgres")


def _parse_min(text: str) -> dict:
    """tomllib 不在时的极简 TOML：[表]、key = "串" | 数字 | true/false | ["串", ...]、# 注释。"""
    import ast
    out: dict = {}
    cur = out
    for raw in text.splitlines():
        line, q = raw, False
        for i, ch in enumerate(raw):          # 去掉引号外的注释
            if ch == '"':
                q = not q
            elif ch == "#" and not q:
                line = raw[:i]
                break
        line = line.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            cur = out.setdefault(line[1:-1].strip(), {})
            continue
        k, _, v = line.partition("=")
        v = v.strip()
        if v in ("true", "false"):
            cur[k.strip()] = v == "true"
        else:
            cur[k.strip()] = ast.literal_eval(v)
    return out


def _loads(text: str) -> dict:
    return _toml.loads(text) if _toml else _parse_min(text)


def _files() -> list[tuple[str, str]]:
    """[(来源, 文本)]，按覆盖顺序。"""
    out = [("包内缺省", resources.files(__package__).joinpath("config/databases.toml").read_text(encoding="utf-8"))]
    for label, p in (("用户文件", USER_FILE.expanduser()), ("GUJI_DB_CONFIG", os.environ.get("GUJI_DB_CONFIG"))):
        if not p:
            continue
        p = Path(p).expanduser()
        if p.is_file():
            out.append((f"{label} {p}", p.read_text(encoding="utf-8")))
        elif label == "GUJI_DB_CONFIG":
            raise SystemExit(f"GUJI_DB_CONFIG 指的文件不存在：{p}")
    return out


def load(*, with_sources: bool = False):
    """合并后的全部配置 {库名: {...}}（未展开 inherit、未套环境变量）。"""
    merged: dict[str, dict] = {}
    src: dict[str, list[str]] = {}
    for label, text in _files():
        for name, tbl in _loads(text).items():
            if not isinstance(tbl, dict):
                continue
            merged.setdefault(name, {}).update(tbl)
            src.setdefault(name, []).append(label)
    return (merged, src) if with_sources else merged


def get(name: str, *, env: bool = True) -> dict:
    """一个库的最终连法：展开 inherit，再套单项环境变量。"""
    allc = load()
    if name not in allc:
        raise SystemExit(f"databases.toml 里没有库 [{name}]（有：{', '.join(sorted(allc))}）")
    spec: dict = {}
    seen = set()
    chain = []
    n = name
    while n:
        if n in seen:
            raise SystemExit(f"databases.toml 的 inherit 成环：{' → '.join(chain + [n])}")
        seen.add(n)
        chain.append(n)
        n = allc.get(n, {}).get("inherit")
        if n and n not in allc:
            raise SystemExit(f"[{chain[-1]}] inherit 的库 [{n}] 不存在")
    for n in reversed(chain):
        spec.update({k: v for k, v in allc[n].items() if k != "inherit"})
    spec = copy.deepcopy(spec)
    spec["name"] = name
    if env:
        for ek, key in _ENV_KEYS.items():
            var = spec.get(ek)
            val = (os.environ.get(var) or "").strip() if var else ""
            if val:
                spec[key] = val
                if key == "path":
                    spec["driver"] = "sqlite"
    if spec.get("driver") not in DRIVERS:
        raise SystemExit(f"[{name}] driver 须为 {' / '.join(DRIVERS)}，现为 {spec.get('driver')!r}")
    return spec


def _names(v) -> list[str]:
    if not v:
        return []
    return [v] if isinstance(v, str) else list(v)


def token_names(name: str, *, branch: str | None = None, key: str = "token") -> list[str]:
    spec = get(name)
    names = _names(spec.get(key))
    b = branch or spec.get("db") or "main"
    if key == "token" and b != "main" and spec.get("exp_token"):
        names = names[:1] + _names(spec["exp_token"]) + names[1:]
    return names


def tokens(name: str, *, branch: str | None = None, key: str = "token") -> list[str]:
    """依次试的令牌值（去重、去空白）。"""
    out: list[str] = []
    for n in token_names(name, branch=branch, key=key):
        v = (os.environ.get(n) or "").strip()
        if v and v not in out:
            out.append(v)
    return out


def url(name: str) -> str:
    return str(get(name).get("url") or "").rstrip("/")


def describe() -> list[dict]:
    """给 ``guji db where``：每个库解析出的连法与来源；令牌只报变量名和「有没有设」，不报值。"""
    allc, src = load(with_sources=True)
    rows = []
    for name in allc:
        s = get(name)
        row = {"库": name, "driver": s["driver"], "来源": " + ".join(src.get(name, []))}
        for k in ("url", "db", "path", "user", "dsn_env"):
            if s.get(k):
                row[k] = s[k]
        if s.get("inherit") or allc[name].get("inherit"):
            row["inherit"] = allc[name]["inherit"]
        for k in ("token", "password"):
            names = _names(s.get(k))
            if names:
                row[k] = [f"{n}{'（已设）' if (os.environ.get(n) or '').strip() else '（未设）'}" for n in names]
        for ek in _ENV_KEYS:
            var = s.get(ek)
            if var and (os.environ.get(var) or "").strip():
                row.setdefault("环境变量覆盖", []).append(var)
        rows.append(row)
    return rows


def apply_env() -> None:
    """把配置里的中心库地址同步给还只认环境变量的下游（cv 的 datastore 客户端、子进程）。

    只在对应环境变量没设时才设，所以老用法（手动 export GUJI_DATA_URL）照旧优先。
    """
    try:
        s = get("central", env=False)
    except SystemExit:
        return
    if s.get("driver") == "d1-worker" and s.get("url") and not os.environ.get(s.get("env_url") or "GUJI_DATA_URL"):
        os.environ[s.get("env_url") or "GUJI_DATA_URL"] = str(s["url"]).rstrip("/")
