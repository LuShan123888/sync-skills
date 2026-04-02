"""配置文件加载、保存和工具检测"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .constants import CONFIG_FILE, DEFAULT_SOURCE, DEFAULT_TARGETS, KNOWN_TOOLS


@dataclass
class Target:
    name: str
    path: Path


@dataclass
class Config:
    source: Path = field(default_factory=lambda: DEFAULT_SOURCE)
    targets: list[Target] = field(default_factory=list)

    @classmethod
    def from_defaults(cls) -> "Config":
        return cls(
            source=DEFAULT_SOURCE,
            targets=[Target(name="builtin", path=p) for p in DEFAULT_TARGETS],
        )


def _expand_home(p: str) -> Path:
    """将 ~/ 开头的路径展开为实际路径"""
    if p.startswith("~/"):
        return Path.home() / p[2:]
    return Path(p)


def _unexpand_home(p: Path) -> str:
    """将实际路径转换回 ~/ 开头的相对路径"""
    home = Path.home()
    try:
        return "~/" + str(p.relative_to(home))
    except ValueError:
        return str(p)


def load_config(config_path: Path | None = None) -> Config:
    """加载配置文件，不存在或格式错误时回退到内置默认值"""
    path = config_path or CONFIG_FILE
    if not path.is_file():
        return Config.from_defaults()

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError) as e:
        import sys
        print(f"[WARNING] 配置文件读取失败 ({e})，使用默认值", file=sys.stderr)
        return Config.from_defaults()

    # 解析 source
    source_raw = data.get("source", str(DEFAULT_SOURCE))
    source = _expand_home(source_raw)

    # 解析 targets
    targets = []
    for item in data.get("targets", []):
        path = _expand_home(item.get("path", ""))
        name = item.get("name", path.name)
        targets.append(Target(name=name, path=path))

    if not targets:
        targets = [Target(name="builtin", path=p) for p in DEFAULT_TARGETS]

    return Config(source=source, targets=targets)


def save_config(config: Config, config_path: Path | None = None) -> None:
    """保存配置到 TOML 文件"""
    path = config_path or CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    source_str = _unexpand_home(config.source)
    targets_data = []
    for t in config.targets:
        targets_data.append({"name": t.name, "path": _unexpand_home(t.path)})

    lines = [
        f'source = "{source_str}"',
        "",
        "# 目标目录列表",
    ]
    for t in targets_data:
        lines.append(f'[[targets]]')
        lines.append(f'name = "{t["name"]}"')
        lines.append(f'path = "{t["path"]}"')
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def detect_installed_tools() -> list[dict]:
    """检测已安装的工具（目录存在即为已安装）"""
    installed = []
    for tool in KNOWN_TOOLS:
        path = _expand_home(tool["path"])
        if path.is_dir():
            installed.append(tool)
    return installed
