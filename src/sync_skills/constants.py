"""内置默认值和已知工具列表"""

from pathlib import Path

DEFAULT_SOURCE = Path.home() / "Skills"

DEFAULT_TARGETS = [
    Path.home() / ".claude" / "skills",
    Path.home() / ".codex" / "skills",
    Path.home() / ".gemini" / "skills",
    Path.home() / ".openclaw" / "skills",
]

KNOWN_TOOLS = [
    {"name": "Claude Code", "path": "~/.claude/skills"},
    {"name": "Codex CLI", "path": "~/.codex/skills"},
    {"name": "Gemini CLI", "path": "~/.gemini/skills"},
    {"name": "OpenClaw", "path": "~/.openclaw/skills"},
]

CONFIG_DIR = Path.home() / ".config" / "sync-skills"
CONFIG_FILE = CONFIG_DIR / "config.toml"
