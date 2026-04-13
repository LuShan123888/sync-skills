# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv run python -m pytest tests/ -v          # run all tests (209 cases)
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
├── __init__.py          # version export (__version__ = "1.1.0")
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

#### classification.py — Skill type detection

- State file: `~/.config/sync-skills/skills.json` (managed by sync-skills)
- `classify_skill(name, managed_skills, repo_skills_dir, agent_dirs)`: returns `SkillClass` with `skill_type` (custom/unknown)
- `classify_all_skills()`: scans all agent dirs + repo and classifies them
- `get_managed_skills()`: loads state file and returns set of managed skill names (in `state.py`)

#### state.py — State file management

- `load_state(path)` / `save_state(state, path)`: read/write `skills.json`
- `get_managed_skills(path)` → `set[str]`: all managed skill names
- `is_managed(name, path)` → `bool`: check if skill is managed
- `add_managed(name, path)` / `remove_managed(name, path)`: update state file
- `align_state_with_repo(state_path, repo_skills_dir)`: align state file with repo (auto-register missing, report orphaned)
- Format: `{ "skills": { "name": { "source": "sync-skills" } } }`

#### symlink.py — Single-layer symlink management

- `create_all_links()`: create symlinks in all agent directories pointing to repo
- `verify_links()`: check symlink integrity, report broken/missing links
- `remove_agent_links()`: remove symlinks pointing to repo
- `sync_all_links()`: batch verify/repair for all managed skills
- `safe_create_link()`: create symlink with overwrite risk detection
- `check_and_repair_links()`: batch check/repair with conflict detection (used by doctor)
- No intermediate "unified directory" layer — direct repo → agent dir symlinks

#### git_ops.py — Git operations

- `git_is_repo()`, `git_init()`, `git_clone()`: repo management
- `git_status()` → `GitStatus`: branch, clean/dirty, modified/staged/untracked, ahead/behind
- `git_add_commit()`, `git_push()`, `git_pull()`: sync operations
- `git_push()` returns `tuple[bool, str]` with error classification ("behind", "auth", "bad_url", "unknown")
- `git_pull()` auto-detects missing tracking and falls back to `git pull --rebase origin <branch>`, auto-aborts on rebase failure
- `git_has_remote()`, `git_add_remote()`, `git_get_remote_url()`, `git_get_tracking_branch()`: remote management

#### lifecycle.py — Skill CRUD

- `_auto_commit(config, command, skills)`: auto-commit after repo-modifying operations (add/remove/link/unlink); message format: `{command}: {skills} ({timestamp})`; skips if no changes
- `add_skill(name, config, description, tags, dry_run)`: validate name, check no conflict, create SKILL.md skeleton, create symlinks, write state file, auto-commit
- `link_skill(name, config, auto_confirm, dry_run)`: auto-scan by name across all agent dirs + repo, MD5 group + mtime sort for conflict resolution, copy selected to repo, delete other copies, create symlinks, write state file, auto-commit
- `unlink_skill(names, config, auto_confirm, dry_run)`: remove from management, restore files to all agent dirs, remove symlinks, remove from state file, auto-commit. `names=None` or `["--all"]` for all
- `remove_skill(name, config, auto_confirm, dry_run)`: classify → must be managed, remove symlinks, delete repo files, remove from state file, auto-commit
- `init_repo(config, auto_confirm, dry_run, config_path)`: initialize `~/Skills/` git repo (clone from remote or git init), idempotent — can be re-run to reconfigure agents, register new repo skills, repair symlinks; all repo skills auto-registered to state file; preview shows per-skill symlink status (✓/+/! with agent dirs)

#### cli.py — Command routing

- `main()` auto-detects legacy arguments (`--source`, `--force`, `--delete`, old subcommands) and routes to `main_legacy()`
- Commands: `init`, `link`, `unlink`, `new`, `remove`, `list`, `status`, `push`, `pull`, `doctor`
- `doctor` is the primary verification/repair command; `fix` and `sync` are kept as compatibility aliases
- No default command: `sync-skills` with no subcommand shows help
- All commands support `--dry-run` and `-y` flags
- Git command preview: `push` and `pull` show full git commands before execution
- Pre/post operation verification: `_check_state()` before pull (detection only), `_verify_after_change()` after new/remove/unlink (detection + auto-repair)
- `_do_doctor()`: three-layer verification + repair: (1) state file ↔ repo alignment (auto-register orphaned), (2) per-skill per-agent-dir symlink check with auto-repair, (3) overwrite risk detection (real dir → conflict, skip with -y)
- `link` takes a skill name and auto-scans; `unlink` supports `--all`
- `remove` supports multiple skill names
- `--copy` flag enters legacy copy sync mode
- Re-exports all legacy functions from `sync_legacy` for backward compatibility

#### sync_legacy.py — Legacy copy sync

- Complete v0.6 copy sync logic extracted from old `cli.py` (~1464 lines)
- Renamed entry points: `main_legacy()`, `parse_legacy_args()`
- All old data structures (`Skill`, `SyncPlan`, `SyncOp`, `Color`, etc.) and functions preserved

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

Total: 209 tests. All legacy tests pass via auto-routing to `main_legacy()`.

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

- **版本**: v1.1.1（自定义 Skill 生命周期管理器）
- **v1.1.1 增强**: init 预览展示逐 skill symlink 详情（✓/+/! + agent 目录）、add/remove/link/unlink 操作后自动 commit（含命令名、skill 名、时间戳）
- **v1.1.0 增强**: 单层 symlink 架构（移除统一目录概念）、fix→doctor 重命名、link 改为按名称自动扫描（MD5 分组 + mtime 排序）、删除 search/info 命令、移除外部 skill 检测（lock 文件）
- **v1.0.0 重构**: 从 copy 同步工具重构为 git + symlink 自定义 skill 管理器
- **模块**: 10 个模块（state.py、classification.py、symlink.py、git_ops.py、lifecycle.py、sync_legacy.py）
- **兼容**: 旧版 copy 同步逻辑提取到 sync_legacy.py，通过 `--copy` flag 保持兼容；`fix`/`sync` 作为 `doctor` 的兼容别名
- **文档**: README.md、docs/DESIGN.md、SKILL.md、CLAUDE.md 均已更新至 v1.1.1
