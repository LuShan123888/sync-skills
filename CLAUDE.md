# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv run python -m pytest tests/ -v          # run all tests (194 cases)
uv run python -m pytest tests/ -v -k test_collect_new_skill  # run single test
uv sync                          # install dependencies
sync-skills                      # show help (no default command)
sync-skills init                 # initialize ~/Skills/ repo, migrate custom skills
sync-skills link my-skill         # link wild skill into management
sync-skills link                  # list wild skills available for adoption
sync-skills add my-skill         # create new custom skill (from template)
sync-skills remove my-skill      # remove custom skill (permanently)
sync-skills uninstall my-skill   # uninstall custom skill (restore files)
sync-skills uninstall -y         # uninstall all custom skills
sync-skills list                 # list custom skills
sync-skills status               # show git status + skill management state
sync-skills push -m "update"     # git commit + push (shows git commands, confirms before executing)
sync-skills pull                 # git pull + rebuild symlinks (shows git command, confirms before executing)
sync-skills fix                  # verify/repair all symlinks + detect broken/missing/orphan skills
sync-skills search "review"      # search custom skills
sync-skills info skill-name      # show skill details (with classification)
sync-skills --copy               # legacy copy-based sync (v0.6)
sync-skills --copy --force -y    # legacy force sync
sync-skills --config /path/to/config.toml  # use custom config
```

## Architecture

v1.0 — Custom Skill Lifecycle Manager. Manages user-created skills via git + symlink, separate from external skills managed by `npx skills`.

### Two-type skill architecture

| Type | Source | Storage | Manager |
|------|--------|---------|---------|
| External | `npx skills install` | Real files in `~/.agents/skills/` | npx skills |
| Custom | User-created | Git repo `~/Skills/skills/` | sync-skills |

**Symlink chain**:
```
~/Skills/skills/<name>/    ← git repo (real files, single source of truth)
       ↓ symlink
~/.agents/skills/<name>/   ← central directory (all agents read from here)
       ↓ symlink
<agent-dir>/skills/<name>/ ← per-agent directory (e.g., ~/.claude/skills/)
```

### Package structure

```
src/sync_skills/
├── __init__.py          # version export (__version__ = "1.0.0")
├── constants.py         # defaults, lock file paths, SKILL_SKELETON, legacy constants
├── config.py            # Config/ExternalConfig dataclasses, load/save TOML, detect_installed_tools
├── metadata.py          # SKILL.md frontmatter parsing (PyYAML), SkillMetadata, search/filter
├── classification.py    # custom vs external skill classification via lock files
├── symlink.py           # two-layer symlink management (agents + agent dirs)
├── git_ops.py           # git operations wrapper (init/clone/status/add/commit/push/pull)
├── lifecycle.py         # add/remove/init skill commands
├── sync_legacy.py       # v0.6 copy sync logic (extracted from old cli.py, used via --copy)
└── cli.py               # command routing, argparse subparsers, re-exports legacy functions

skills/
└── sync-skills/
    └── SKILL.md     # AI skill: teaches AI models how to use this CLI tool
```

### Core modules

#### classification.py — Skill type detection

- Lock files: `~/.agents/.skill-lock.json` (global) and `~/skills-lock.json` (local)
- `classify_skill(name, agents_dir, repo_skills_dir, external)`: returns `SkillClass` with `skill_type` (custom/external/orphan)
- `classify_all_skills()`: scans all skills and classifies them
- `get_external_skills()`: loads both lock files and returns set of external skill names

#### symlink.py — Two-layer symlink management

- `create_agents_link()`: `~/.agents/skills/<name>` → `~/Skills/skills/<name>`
- `create_agent_links()`: `<agent-dir>/skills/<name>` → `~/.agents/skills/<name>`
- `sync_all_links()`: scan all custom skills, create/verify/repair symlinks; accepts `external_skills` to skip external skills
- `verify_links()`: check symlink integrity, report broken/missing links
- `remove_agents_link()` / `remove_agent_links()`: only removes symlinks pointing to expected targets
- `create_agents_link()`: detects and fixes circular symlinks from old architecture

#### git_ops.py — Git operations

- `git_is_repo()`, `git_init()`, `git_clone()`: repo management
- `git_status()` → `GitStatus`: branch, clean/dirty, modified/staged/untracked, ahead/behind
- `git_add_commit()`, `git_push()`, `git_pull()`: sync operations
- `git_push()` returns `tuple[bool, str]` with error classification ("behind", "auth", "bad_url", "unknown")
- `git_pull()` auto-detects missing tracking and falls back to `git pull --rebase origin <branch>`, auto-aborts on rebase failure
- `git_has_remote()`, `git_add_remote()`, `git_get_remote_url()`, `git_get_tracking_branch()`: remote management

#### lifecycle.py — Skill CRUD

- `add_skill(name, config, description, tags)`: validate name, check no external conflict, create SKILL.md skeleton, create symlinks
- `link_skill(name, config, auto_confirm)`: find wild skill in agent directories, confirm, copy to repo, remove originals, create symlinks
- `detect_wild_skills(config)`: scan agent directories for unmanaged real-directory skills
- `remove_skill(name, config, auto_confirm)`: classify → must be custom, remove symlinks, delete repo files, fallback cleanup
- `uninstall_skill(name, config, auto_confirm)`: classify → must be custom, restore files to agents_dir (preserve data), supports `name=None` for all
- `init_repo(config)`: initialize `~/Skills/` git repo, check git status for existing repos, migrate existing custom skills from `~/.agents/skills/`, create symlinks, initial commit

#### cli.py — Command routing

- `main()` auto-detects legacy arguments (`--source`, `--force`, `--delete`, old subcommands) and routes to `main_legacy()`
- New commands: `init`, `link`, `add`, `remove`, `uninstall`, `list`, `status`, `push`, `pull`, `fix`, `search`, `info`
- `fix` is the primary verification/repair command; `sync` is kept as compatibility alias
- No default command: `sync-skills` with no subcommand shows help
- Git command preview: `push` and `pull` show full git commands before execution
- Pre/post operation verification: `_check_state()` before pull, `_verify_after_change()` after add/remove/uninstall
- `_do_sync()`: interactive verification + repair (broken links, missing links, orphan adoption)
- `--copy` flag enters legacy copy sync mode
- Re-exports all legacy functions from `sync_legacy` for backward compatibility

#### sync_legacy.py — Legacy copy sync

- Complete v0.6 copy sync logic extracted from old `cli.py` (~1464 lines)
- Renamed entry points: `main_legacy()`, `parse_legacy_args()`
- All old data structures (`Skill`, `SyncPlan`, `SyncOp`, `Color`, etc.) and functions preserved

### Key concepts

- A **skill** is a directory containing a `SKILL.md` file
- **Custom skills**: stored in `~/Skills/skills/` git repo, symlinked to `~/.agents/skills/`
- **External skills**: managed by `npx skills`, stored as real files in `~/.agents/skills/`
- **Orphan skills**: exist in `~/.agents/skills/` but not tracked by either system
- **Detection**: external skills identified via lock files (`~/.agents/.skill-lock.json`, `~/skills-lock.json`)
- **fix command**: verifies and repairs all custom skill symlinks; detects broken links, missing links, and orphan skills
- **No default command**: `sync-skills` with no subcommand shows help

### Config file

Stored at `~/.config/sync-skills/config.toml` (or custom path via `--config`):

```toml
repo = "~/Skills"
agents_dir = "~/.agents/skills"

[external]
global_lock = "~/.agents/.skill-lock.json"
local_lock = "~/skills-lock.json"

# Legacy fields (only used in --copy mode)
# source = "~/Skills"
# [[targets]]
# name = "builtin"
# path = "~/.claude/skills"
```

- `repo`: git repo path for custom skills
- `agents_dir`: central directory path
- `external.global_lock` / `external.local_lock`: lock files for external skill detection
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

Tests in `tests/test_sync_skills.py` use `tmp_path` fixtures, organized by class: `TestScan`, `TestBidirectional`, `TestForce`, `TestDelete`, `TestErrors`, `TestPreview`, `TestMultiTarget`, `TestUserScenarios`, `TestBaseSelection`, `TestConflictResolution`, `TestSelectiveSync`, `TestListCommand`, `TestSearchCommand`, `TestInfoCommand`, `TestDryRun`, `TestAddCommand`, `TestRemoveCommand`, `TestUninstallCommand`, `TestSymlinkIsolation`, `TestPushCommand`. Helper functions `create_skill()` (flat) and `create_skill_in_category()` (nested) set up test fixtures. All tests pass `-y` to skip confirmation.

Additional test files:
- `tests/test_config.py` — Config module tests (load, save, path expand/unexpand, detect tools, exclude_tags): 18 tests
- `tests/test_init.py` — Init wizard tests (config creation, default/custom source): 3 tests
- `tests/test_metadata.py` — Metadata module tests (frontmatter parsing, filtering, search): 36 tests

Total: 204 tests. All legacy tests pass via auto-routing to `main_legacy()`.

## Design doc

See `docs/DESIGN.md` for:
- 当前架构（第 2 节）— v1.0 两类 skill 分管 + 软链接链路
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

- **版本**: v1.0.1（自定义 Skill 生命周期管理器）
- **v1.0.1 增强**: 外部 Skill 全链路隔离、uninstall 命令、增强 status/fix/push、git 命令预览、孤儿 skill 检测、操作前后自动验证、sync→fix 重命名、无默认命令
- **v1.0.0 重构**: 从 copy 同步工具重构为 git + symlink 自定义 skill 管理器，与 npx skills 共存（两类 skill 分管）
- **模块**: 9 个模块（新增 classification.py、symlink.py、git_ops.py、lifecycle.py、sync_legacy.py）
- **兼容**: 旧版 copy 同步逻辑提取到 sync_legacy.py，通过 `--copy` flag 保持兼容；167 个旧测试全部通过
- **文档**: README.md、docs/DESIGN.md、SKILL.md、CLAUDE.md 均已更新至 v1.0.1
