# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv run python -m pytest tests/ -v          # run all tests (90 cases)
uv run python -m pytest tests/ -v -k test_collect_new_skill  # run single test
uv sync                          # install dependencies
sync-skills                      # run (after pip install -e .)
sync-skills --force -y           # force sync, skip confirm
sync-skills init                 # interactive config wizard
sync-skills --delete skill-name  # delete skill from source + all targets
sync-skills -d skill-name -y     # delete with auto-confirm
sync-skills --config /path/to/config.toml  # use custom config
```

## Architecture

Package-based CLI tool (`src/sync_skills/`, zero external dependencies, Python >= 3.11) that syncs AI coding agent skills between a categorized source directory (`~/Skills/`) and multiple flat target directories (`~/.claude/skills/`, `~/.codex/skills/`, etc.).

### Package structure

```
src/sync_skills/
├── __init__.py      # version export (__version__ = "0.3.0")
├── constants.py     # DEFAULT_SOURCE, DEFAULT_TARGETS, KNOWN_TOOLS, CONFIG_FILE
├── config.py        # Config/Target dataclasses, load/save TOML, detect_installed_tools
└── cli.py           # all sync logic, CLI parsing, init wizard, conflict resolution
```

### Core flow: Scan → Plan → Conflict Resolution → Preview → Confirm → Execute → Verify

1. **Scan**: `find_skills_in_source()` (recursive, nested categories) and `find_skills_in_target()` (flat, skips hidden dirs)
2. **Plan**: `preview_bidirectional()` builds a `SyncPlan` using pure hash-based conflict detection (no mtime dependency)
3. **Conflict Resolution** (bidirectional mode): `_resolve_conflicts()` interactively resolves conflicts; `_apply_resolutions()` converts choices to collect/create/update operations
4. **Preview**: `show_preview()` displays the diff with conflict resolution results
5. **Execute**: `execute_bidirectional()` or `execute_force()` applies the plan via `shutil.copytree`/`rmtree`
6. **Verify**: `verify_sync()` checks content hashes match across all directories

### Key concepts

- A **skill** is a directory containing a `SKILL.md` file
- **Source** (`~/Skills/`): nested category structure (e.g., `Code/skill-a/`, `Lark/skill-b/`)
- **Targets** (flat): each tool's skills dir. Categories are flattened — only the leaf directory name matters
- **Bidirectional mode**: collects new/updated skills from targets into `~/Skills/Other/`, then distributes all skills to targets. Interactive conflict resolution for ambiguous cases.
- **Force mode**: supports interactive base directory selection (`--force` without `-y`). When source dir is a target, preserves nested structure (new skills go to `Other/`, deletes use recursive lookup). Uses MD5 content hash comparison — identical skills are skipped without re-copying.
- Duplicate skill names across categories are a fatal error (would conflict when flattened)

### Conflict detection (pure hash, v0.3.0)

`preview_bidirectional()` uses pure hash grouping — no mtime for classification:

| Hash groups | Classification | Action |
|---|---|---|
| 1 group | No change | Skip |
| 2 groups, 1 singleton (single target differs) | Safe auto-resolve | `collect_update` |
| 2 groups, 1 singleton (source differs) | Conflict | Interactive resolution |
| 2 groups, both 2+ members | Conflict | Interactive resolution |
| 3+ groups | Multi-version conflict | Interactive resolution |

### Conflict resolution (v0.3.0)

- **Interactive mode** (default): `ask_conflict_resolution()` presents all versions with hash prefix, mtime hint, and SKILL.md preview. User selects version or skips.
- **Auto mode** (`-y`): conflicts are converted to warnings (same as v0.2 behavior), sync proceeds without resolving conflicts.
- **Resolution application**: `_apply_resolutions()` converts user choices to `collect_update`/`creates`/`updates` operations.
- **Preview display**: resolved conflicts shown in a dedicated "冲突解决" section.

### Content comparison

- **MD5 directory hashing** (`skill_dir_hash()`): computes hash of all files in a skill directory, excluding hidden files (`.DS_Store`, etc.)
- **Hidden directory filtering**: all scan functions skip directories with `.` prefix (e.g., `.system/`)
- **Conflict display**: `_build_version_warning_from_versions()` groups by hash, sorts by mtime, marks suggested version (git-like)
- **Path display**: all output uses `~/` relative paths (e.g., `~/.claude/skills`), never full paths

### Test structure

Tests in `tests/test_sync_skills.py` use `tmp_path` fixtures, organized by class: `TestScan`, `TestBidirectional`, `TestForce`, `TestDelete`, `TestErrors`, `TestPreview`, `TestMultiTarget`, `TestUserScenarios`, `TestBaseSelection`, `TestConflictResolution`. Helper functions `create_skill()` (flat) and `create_skill_in_category()` (nested) set up test fixtures. All tests pass `-y` to skip confirmation.

Additional test files:
- `tests/test_config.py` — Config module tests (load, save, path expand/unexpand, detect tools): 15 tests
- `tests/test_init.py` — Init wizard tests (config creation, default/custom source): 3 tests

Total: 90 tests.

### Delete command

**Usage:** `--delete <skill-name>` or `-d <skill-name>` removes a skill from both source and all target directories. Default mode shows preview and requires confirmation; `-y` flag auto-confirms.

**Safety:** Before deletion, verifies skill exists in at least one location. Shows detailed preview: which directories contain the skill, total deletion count. Non-existent skills trigger error message without side effects.

**When to use:** Removing obsolete or unwanted skills that exist in multiple locations. More efficient than manual deletion across 4+ directories.

### Init command

**Usage:** `sync-skills init` launches an interactive wizard that creates `~/.config/sync-skills/config.toml`.

Steps:
1. Source directory (default: `~/Skills`)
2. Detect installed tools and let user select targets
3. Optionally add custom target paths

**Custom config:** `sync-skills --config /path/to/config.toml` to use a non-default config file.

### Config file

Stored at `~/.config/sync-skills/config.toml` (or custom path via `--config`):

```toml
source = "~/Skills"

[[targets]]
name = "Claude Code"
path = "~/.claude/skills"
```

- CLI args (`--source`, `--targets`) override config values
- Missing config → falls back to built-in defaults (backward compatible)

## Design doc

See `docs/DESIGN.md` for:
- 用户场景与预期行为（第 3 节）— 所有同步场景的完整定义
- 当前已知限制（第 4 节）
- 演进规划（第 5 节）— Phase 2: 内容感知同步（已完成）
- 变更日志（第 7 节）— 每次讨论的关键决策和代码变更记录

## Cross-session workflow

每次对话结束前，用户会说"更新记忆"或触发 `/remember`，此时需要：
1. 更新 `docs/DESIGN.md` 第 7 节"变更日志"（按日期倒序追加本次决策和变更）
2. 更新本文件的 "Current status" 部分（如果项目状态有变化）
3. 更新 `~/.claude/projects/-Users-cian-Code-sync-skills/memory/MEMORY.md`

新会话开始时，先阅读 `docs/DESIGN.md` 第 7 节变更日志了解历史上下文。 `[added: 2026-03-21]`

## Current status

- **版本**: v0.3.0（内容感知同步 + 交互式冲突解决）
- **Phase 2 已完成**: 纯哈希冲突检测、交互式冲突选择界面、-y 模式兼容、90 个测试
- **下一步**: Phase 3 — Skill 元数据与索引（标签、搜索、选择性同步）
