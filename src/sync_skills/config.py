"""配置文件加载、保存和工具检测"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .constants import (
    CONFIG_DIR,
    CONFIG_FILE,
    DEFAULT_AGENT_DIRS,
    DEFAULT_AGENTS_DIR,
    DEFAULT_GLOBAL_LOCK,
    DEFAULT_LOCAL_LOCK,
    DEFAULT_REPO,
    DEFAULT_SOURCE,
    DEFAULT_TARGETS,
    KNOWN_TOOLS,
)


# ============================================================
# 数据结构
# ============================================================

@dataclass
class ExternalConfig:
    """外部 skill lock 文件路径"""
    global_lock: Path = field(default_factory=lambda: DEFAULT_GLOBAL_LOCK)
    local_lock: Path = field(default_factory=lambda: DEFAULT_LOCAL_LOCK)


@dataclass
class Target:
    name: str
    path: Path


@dataclass
class Config:
    """v1.0 配置：自定义 skill 管理"""
    # 新字段
    repo: Path = field(default_factory=lambda: DEFAULT_REPO)
    agents_dir: Path = field(default_factory=lambda: DEFAULT_AGENTS_DIR)
    agent_dirs: list[Path] | None = None  # None = 使用内置默认值
    external: ExternalConfig = field(default_factory=ExternalConfig)

    # 旧版兼容字段（仅 --copy 模式）
    source: Path | None = None
    targets: list[Target] = field(default_factory=list)
    exclude_tags: list[str] = field(default_factory=list)

    @classmethod
    def from_defaults(cls) -> "Config":
        return cls(
            repo=DEFAULT_REPO,
            agents_dir=DEFAULT_AGENTS_DIR,
            external=ExternalConfig(),
            source=DEFAULT_SOURCE,
            targets=[Target(name="builtin", path=p) for p in DEFAULT_TARGETS],
        )

    @property
    def repo_skills_dir(self) -> Path:
        """自定义 skill 在仓库中的目录（~/Skills/skills/）。"""
        return self.repo / "skills"

    @property
    def effective_agent_dirs(self) -> list[Path]:
        """获取有效的 Agent 目录列表。None 时使用内置默认值。"""
        if self.agent_dirs is not None:
            return self.agent_dirs
        return list(DEFAULT_AGENT_DIRS)


# ============================================================
# 路径工具
# ============================================================

def _expand_home(p: str) -> Path:
    if p.startswith("~/"):
        return Path.home() / p[2:]
    return Path(p)


def _unexpand_home(p: Path) -> str:
    home = Path.home()
    try:
        return "~/" + str(p.relative_to(home))
    except ValueError:
        return str(p)


# ============================================================
# 配置加载
# ============================================================

def load_config(config_path: Path | None = None) -> Config:
    """加载配置文件。不存在或格式错误时回退到默认值。"""
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

    config = Config()

    # v1.0 新字段
    repo_raw = data.get("repo", "")
    if repo_raw:
        config.repo = _expand_home(repo_raw)

    agents_dir_raw = data.get("agents_dir", "")
    if agents_dir_raw:
        config.agents_dir = _expand_home(agents_dir_raw)

    # agent_dirs（选中的 Agent 目录列表）
    agent_dirs_raw = data.get("agent_dirs")
    if agent_dirs_raw is not None:
        config.agent_dirs = [_expand_home(p) for p in agent_dirs_raw]

    # [external] 段
    ext_section = data.get("external", {})
    if isinstance(ext_section, dict):
        gl = ext_section.get("global_lock", "")
        if gl:
            config.external.global_lock = _expand_home(gl)
        ll = ext_section.get("local_lock", "")
        if ll:
            config.external.local_lock = _expand_home(ll)

    # 旧版字段兼容
    source_raw = data.get("source", "")
    if source_raw:
        config.source = _expand_home(source_raw)

    for item in data.get("targets", []):
        p = _expand_home(item.get("path", ""))
        name = item.get("name", p.name)
        config.targets.append(Target(name=name, path=p))

    if not config.targets:
        config.targets = [Target(name="builtin", path=p) for p in DEFAULT_TARGETS]

    sync_section = data.get("sync", {})
    exclude_tags = sync_section.get("exclude_tags", [])
    if not isinstance(exclude_tags, list):
        exclude_tags = []
    config.exclude_tags = exclude_tags

    return config


# ============================================================
# 配置保存
# ============================================================

def save_config(config: Config, config_path: Path | None = None) -> None:
    """保存配置到 TOML 文件。同时写入新版和旧版字段以保持兼容。"""
    path = config_path or CONFIG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f'repo = "{_unexpand_home(config.repo)}"',
        f'agents_dir = "{_unexpand_home(config.agents_dir)}"',
    ]

    # agent_dirs（选中的 Agent 目录列表）
    if config.agent_dirs is not None:
        if config.agent_dirs:
            dirs_str = ", ".join(f'"{_unexpand_home(d)}"' for d in config.agent_dirs)
            lines.append(f'agent_dirs = [{dirs_str}]')
        else:
            lines.append('agent_dirs = []')
        lines.append("")

    # 旧版字段（保持兼容，必须在 section header 之前）
    if config.source:
        lines.append(f'source = "{_unexpand_home(config.source)}"')

    lines.append("")
    lines.append("[external]")
    lines.append(f'global_lock = "{_unexpand_home(config.external.global_lock)}"')
    lines.append(f'local_lock = "{_unexpand_home(config.external.local_lock)}"')
    lines.append("")

    if config.targets:
        lines.append("# 目标目录列表（旧版兼容）")
        for t in config.targets:
            lines.append(f'[[targets]]')
            lines.append(f'name = "{t.name}"')
            lines.append(f'path = "{_unexpand_home(t.path)}"')
            lines.append("")

    # exclude_tags
    if config.exclude_tags:
        lines.append("# 同步过滤")
        lines.append("[sync]")
        tags_str = ", ".join(f'"{tag}"' for tag in config.exclude_tags)
        lines.append(f'exclude_tags = [{tags_str}]')
        lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ============================================================
# 工具检测
# ============================================================

def detect_installed_tools() -> list[dict]:
    """检测已安装的工具（目录存在即为已安装）。"""
    installed = []
    for tool in KNOWN_TOOLS:
        path = _expand_home(tool["path"])
        if path.is_dir():
            installed.append(tool)
    return installed
