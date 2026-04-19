# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv run python -m pytest tests/ -v          # run all tests
uv run python -m pytest tests/ -v -k test_collect_new_skill  # run single test
uv sync                          # install dependencies
sync-skills                      # show help (no default command)
sync-skills init                 # initialize ~/Skills/ repo (clone from remote or git init), idempotent
sync-skills link my-skill        # link skill into management (auto-scan by name)
sync-skills new my-skill         # create new custom skill (from template)
sync-skills remove my-skill      # remove custom skill (permanently)
sync-skills unlink my-skill      # unlink custom skill (restore files to all agent dirs)
sync-skills unlink --all -y      # unlink all managed skills
sync-skills list                 # list managed skills
sync-skills status               # show git status + skill management state
sync-skills commit -m "update"  # git commit only (shows git commands, confirms before executing)
sync-skills push -m "update"    # git commit + push (shows git commands, confirms before executing)
sync-skills pull                 # git pull + rebuild symlinks (shows git command, confirms before executing)
sync-skills doctor               # verify/repair symlinks + detect state inconsistencies
sync-skills <command> --dry-run  # preview without executing
sync-skills --copy               # legacy copy-based sync (v0.6)
sync-skills --copy --force -y    # legacy force sync
sync-skills --config /path/to/config.toml  # use custom config
```

## Architecture

v1.1 — Custom Skill Lifecycle Manager. Manages user-created skills via git + symlink + state file. Only manages skills explicitly added by the user; other skills are left untouched.

**Single-layer symlink chain**:
```text
~/Skills/skills/<name>/    ← git repo (real files, single source of truth)
       ↓ symlink
~/.agents/skills/<name>/   ← agent directory
~/.claude/skills/<name>/   ← agent directory
~/.codex/skills/<name>/    ← agent directory
...
```

**State file**: `~/.config/sync-skills/skills.json` — tracks which skills are managed by sync-skills (source of truth for management status).

### Package structure

```text
src/sync_skills/
├── __init__.py          # version export
├── constants.py         # defaults, SKILL_SKELETON, legacy constants
├── config.py            # Config dataclass, load/save TOML, detect_installed_tools
├── metadata.py          # SKILL.md frontmatter parsing (PyYAML), SkillMetadata, search/filter
├── classification.py    # custom vs unknown skill classification via state file
├── state.py             # skills.json state file management (load/save/query/update)
├── symlink.py           # single-layer symlink management (repo → all agent dirs)
├── git_ops.py           # git operations wrapper (init/clone/status/add/commit/push/pull)
├── lifecycle.py         # new/remove/link/unlink/init skill commands
├── sync_legacy.py       # v0.6 copy sync logic (used via --copy)
└── cli.py               # command routing, argparse subparsers, re-exports legacy functions
```

### Core modules

| Module | Responsibility |
|--------|---------------|
| `classification.py` | Skill 类型检测：基于 state file 区分 custom/unknown，扫描所有 agent 目录 |
| `state.py` | skills.json 状态文件读写，管理 managed skills 集合，支持与 repo 自动对齐 |
| `symlink.py` | 单层 symlink 管理：repo → 所有 agent 目录，支持创建/验证/修复/删除 |
| `git_ops.py` | Git 操作封装：init/clone/status/add/commit/push/pull |
| `lifecycle.py` | Skill CRUD 命令实现：new/remove/link/unlink/init，操作后自动 commit |
| `metadata.py` | SKILL.md frontmatter 解析、搜索和选择性同步元数据 |
| `sync_legacy.py` | v0.6 copy 同步逻辑，通过 `--copy` flag 进入 |
| `cli.py` | 命令路由：argparse 子命令，自动检测旧参数路由到 legacy 模式 |

### Key concepts

- A **skill** is a directory containing a `SKILL.md` file.
- **Managed skills** are tracked in `~/.config/sync-skills/skills.json`, stored in `~/Skills/skills/`, and symlinked to all selected agent directories.
- **doctor** is the main verification/repair command for the v1.1 path.
- **No default command**: `sync-skills` with no subcommand shows help.
- **--dry-run**: mutating commands support preview mode.

### Test structure

Main test files:
- `tests/test_sync_skills.py` — legacy copy mode and lifecycle command regression
- `tests/test_config.py` — config parsing and persistence
- `tests/test_init.py` — init command flows
- `tests/test_metadata.py` — frontmatter parsing and metadata behavior
- `tests/test_state.py` — state file behavior
- `tests/test_symlink.py` — symlink safety behavior
- `tests/test_git_ops.py` — git parsing and git-related helpers
- `tests/test_cli_routing.py` — CLI routing and glue logic
- `tests/test_v1_commands.py` — current v1 command stories
- `tests/test_skill_version.py` — skill version bump logic

## Design and history docs

See `docs/DESIGN.md` for:
- 当前架构（第 3 节）— v1.1 单层 symlink + 状态文件管理
- 当前命令模型（第 4 节）— lifecycle manager 与 legacy copy 的职责边界
- 当前已知限制（第 9 节）— 当前实现与兼容复杂性说明
- 设计演进记录（第 12 节）— 为什么会形成现在的架构

See `CHANGELOG.md` for:
- 各版本/阶段的功能更新、修复与行为变化
- 历史迭代时间线（按时间倒序）
- 里程碑版本与 package version 的对应关系

## Cross-session workflow

每次对话结束前，用户会说“更新记忆”或触发 `/remember`，此时需要：
1. 更新根目录 `CHANGELOG.md`（补充本次用户可感知的功能变更、修复和行为变化）
2. 如涉及架构/设计决策，再更新 `docs/DESIGN.md`
3. 更新本文件的 “Current status” 部分（如果项目状态有变化）
4. 更新 `~/.claude/projects/-Users-cian-Code-sync-skills/memory/MEMORY.md`

新会话开始时，先阅读 `CHANGELOG.md` 了解近期变更，再按需阅读 `docs/DESIGN.md` 了解架构背景。 `[updated: 2026-04-19]`

## Current status

- **版本**: v0.5.20260418.4（自定义 Skill 生命周期管理器）
- **架构**: git + symlink + state file，单层 symlink（repo → agent dirs），`doctor` 为主要验证/修复命令
- **兼容**: 旧版 copy 同步逻辑在 `sync_legacy.py`，通过 `--copy` flag 进入
