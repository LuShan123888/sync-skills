# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv run python -m pytest tests/ -v          # run all tests (232 cases)
uv run python -m pytest tests/ -v -k test_collect_new_skill  # run single test
uv sync                          # install dependencies
sync-skills                      # show help (no default command)
sync-skills init                 # initialize ~/Skills/ repo (clone from remote or git init), idempotent
sync-skills link my-skill        # link skill into management (auto-scan by name)
sync-skills new my-skill          # create new custom skill (from template)
sync-skills remove my-skill      # remove custom skill (permanently)
sync-skills unlink my-skill      # unlink custom skill (restore files to all agent dirs)
sync-skills unlink --all -y      # unlink all managed skills
sync-skills list                 # list managed skills
sync-skills status               # show git status + skill management state
sync-skills push -m "update"     # git commit + push (shows git commands, confirms before executing)
sync-skills pull                 # git pull + rebuild symlinks (shows git command, confirms before executing)
sync-skills doctor               # verify/repair symlinks + detect state inconsistencies
sync-skills <command> --dry-run  # preview without executing
sync-skills --copy               # legacy copy-based sync (v0.6)
sync-skills --copy --force -y    # legacy force sync
sync-skills --config /path/to/config.toml  # use custom config
```

## Architecture

v1.1 — Custom Skill Lifecycle Manager. Manages user-created skills via git + symlink + state file. Only manages skills explicitly added by the user; other skills (managed by any tool) are left untouched.

**Single-layer symlink chain** (v1.1 simplified):
```
~/Skills/skills/<name>/    ← git repo (real files, single source of truth)
       ↓ symlink
~/.agents/skills/<name>/   ← agent directory (treated as regular agent dir)
~/.claude/skills/<name>/   ← agent directory
~/.codex/skills/<name>/    ← agent directory
...
```

**State file**: `~/.config/sync-skills/skills.json` — tracks which skills are managed by sync-skills (source of truth for management status).

### Package structure

```
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
├── sync_legacy.py       # v0.6 copy sync logic (extracted from old cli.py, used via --copy)
└── cli.py               # command routing, argparse subparsers, re-exports legacy functions
```

### Core modules

| Module | Responsibility |
|--------|---------------|
| `classification.py` | Skill 类型检测：基于 state file 区分 custom/unknown，扫描所有 agent 目录 |
| `state.py` | skills.json 状态文件读写，管理 managed skills 集合，支持与 repo 自动对齐 |
| `symlink.py` | 单层 symlink 管理：repo → 所有 agent 目录，支持创建/验证/修复/删除 |
| `git_ops.py` | Git 操作封装：init/clone/status/add/commit/push/pull，push 返回错误分类，pull 自动 rebase fallback |
| `lifecycle.py` | Skill CRUD 命令实现：new/remove/link/unlink/init，操作后自动 commit |
| `sync_legacy.py` | v0.6 copy 同步逻辑（~1464 行），通过 `--copy` flag 进入 |
| `cli.py` | 命令路由：argparse 子命令，自动检测旧参数路由到 legacy 模式 |

### Key concepts

- A **skill** is a directory containing a `SKILL.md` file
- **Managed skills**: tracked in `~/.config/sync-skills/skills.json` state file, stored in `~/Skills/skills/` git repo, symlinked to all agent directories (including `~/.agents/skills/`)
- **State file**: `~/.config/sync-skills/skills.json` — the single source of truth for management status
- **~/.agents/skills/** is treated as a regular agent directory (no special handling)
- **doctor command**: three-layer detection — (1) state file ↔ repo alignment, (2) symlink check/repair per managed skill per agent dir, (3) overwrite risk detection (real dir → conflict); auto-repairs broken/missing symlinks, auto-registers unregistered repo skills
- **No default command**: `sync-skills` with no subcommand shows help
- **--dry-run**: all mutating commands support preview mode

### Config file

Stored at `~/.config/sync-skills/config.toml` (or custom path via `--config`):

```toml
repo = "~/Skills"
state_file = "~/.config/sync-skills/skills.json"

# Legacy fields (only used in --copy mode)
# source = "~/Skills"
# [[targets]]
# name = "builtin"
# path = "~/.claude/skills"
```

- `repo`: git repo path for custom skills
- `agent_dirs`: selected agent directories (defaults to `~/.agents/skills`, `~/.claude/skills`, etc.)
- `state_file`: state file path for management tracking
- Legacy fields (`source`, `targets`, `exclude_tags`) preserved for `--copy` mode

### SKILL.md frontmatter (optional)

```yaml
---
tags: [code, review]
description: "代码审查工具"
tools: [claude, codex]  # only sync to these targets in --copy mode
---
```

- Parsed by `metadata.py` using PyYAML
- `tools` maps to target path parent name: `~/.claude/skills` → `"claude"` (legacy --copy mode only)
- Missing/empty fields → sync to all targets (backward compatible)

### Test structure

Tests in `tests/test_sync_skills.py` use `tmp_path` fixtures, organized by class: `TestScan`, `TestBidirectional`, `TestForce`, `TestDelete`, `TestErrors`, `TestPreview`, `TestMultiTarget`, `TestUserScenarios`, `TestBaseSelection`, `TestConflictResolution`, `TestSelectiveSync`, `TestListCommand`, `TestSearchCommand`, `TestInfoCommand`, `TestDryRun`, `TestNewCommand`, `TestRemoveCommand`, `TestUnlinkCommand`, `TestLinkCommand`, `TestPushCommand`, `TestStatusCommand`, `TestDoctorCommand`, `TestPullCommand`. Helper functions `create_skill()` (flat) and `create_skill_in_category()` (nested) set up test fixtures. All tests pass `-y` to skip confirmation.

Additional test files:
- `tests/test_config.py` — Config module tests (load, save, path expand/unexpand, detect tools, exclude_tags): 18 tests
- `tests/test_init.py` — Init tests (new repo, clone remote, reconfigure, auto-confirm, dry-run): 12 tests
- `tests/test_metadata.py` — Metadata module tests (frontmatter parsing, filtering, search): 36 tests

Total: 232 tests. All legacy tests pass via auto-routing to `main_legacy()`.

## Design doc

See `docs/DESIGN.md` for:
- 当前架构（第 2 节）— v1.1 单层 symlink + 状态文件管理
- 用户场景与预期行为（第 3 节）— 所有同步场景的完整定义
- 当前已知限制（第 4 节）— 含 v1.0 新增限制
- 演进规划（第 5 节）— Phase 5: Git + 软链接管理（v1.0 已完成）
- 变更日志（第 7 节）— 每次讨论的关键决策和代码变更记录

## Cross-session workflow

每次对话结束前，用户会说"更新记忆"或触发 `/remember`，此时需要：
1. 更新 `docs/DESIGN.md` 第 7 节"变更日志"（按日期倒序追加本次决策和变更）
2. 更新本文件的 "Current status" 部分（如果项目状态有变化）
3. 更新 `~/.claude/projects/-Users-cian-Code-sync-skills/memory/MEMORY.md`

新会话开始时，先阅读 `docs/DESIGN.md` 第 7 节变更日志了解历史上下文。 `[added: 2026-03-21]`

## Current status

- **版本**: v0.5.20260412.2（自定义 Skill 生命周期管理器）
- **架构**: git + symlink + state file，单层 symlink（repo → agent dirs），`doctor` 为主要验证/修复命令
- **兼容**: 旧版 copy 同步逻辑在 sync_legacy.py，通过 `--copy` flag 进入
