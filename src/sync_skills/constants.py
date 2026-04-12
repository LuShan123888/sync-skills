"""内置默认值和已知工具列表"""

from pathlib import Path

# ============================================================
# 自定义 Skill 管理（v1.0）
# ============================================================

DEFAULT_REPO = Path.home() / "Skills"
REPO_SKILLS_DIR_NAME = "skills"  # 仓库内的 skills 子目录名

DEFAULT_AGENTS_DIR = Path.home() / ".agents" / "skills"

DEFAULT_AGENT_DIRS = [
    Path.home() / ".claude" / "skills",
    Path.home() / ".codex" / "skills",
    Path.home() / ".gemini" / "skills",
    Path.home() / ".openclaw" / "skills",
]

DEFAULT_GLOBAL_LOCK = Path.home() / ".agents" / ".skill-lock.json"
DEFAULT_LOCAL_LOCK = Path.home() / "skills-lock.json"

# ============================================================
# Skill 骨架模板
# ============================================================

SKILL_SKELETON = """\
---
name: {name}
description: "Description of what this skill does"
---

# {name}

## Description

...

## Instructions

...
"""

# ============================================================
# 旧版配置兼容（v0.5.x，仅 --copy 模式使用）
# ============================================================

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
