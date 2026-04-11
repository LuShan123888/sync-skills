# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv run python -m pytest tests/ -v          # run all tests (167 cases)
uv run python -m pytest tests/ -v -k test_collect_new_skill  # run single test
uv sync                          # install dependencies
sync-skills                      # run (after pip install -e .)
sync-skills --force -y           # force sync, skip confirm
sync-skills --dry-run            # preview changes without executing
sync-skills init                 # interactive config wizard
sync-skills --delete skill-name  # delete skill from source + all targets
sync-skills -d skill-name -y     # delete with auto-confirm
sync-skills --config /path/to/config.toml  # use custom config
sync-skills list                 # list all skills grouped by category
sync-skills list --tags code     # filter by tags
sync-skills search "review"      # full-text search
sync-skills info skill-name      # show skill details
```

## Architecture

Package-based CLI tool (`src/sync_skills/`, Python >= 3.11, depends on PyYAML) that syncs AI coding agent skills between a categorized source directory (`~/Skills/`) and multiple flat target directories (`~/.claude/skills/`, `~/.codex/skills/`, etc.).

### Package structure

```
src/sync_skills/
├── __init__.py      # version export (__version__ = "0.6.0")
├── constants.py     # DEFAULT_SOURCE, DEFAULT_TARGETS, KNOWN_TOOLS, CONFIG_FILE
├── config.py        # Config/Target dataclasses, load/save TOML, detect_installed_tools
├── metadata.py      # SKILL.md frontmatter parsing (PyYAML), SkillMetadata, search/filter
└── cli.py           # all sync logic, CLI parsing, init wizard, conflict resolution, list/search/info

skills/
└── sync-skills/
    └── SKILL.md     # AI skill: teaches AI models how to use this CLI tool
```

### Core flow: Scan → Plan → Conflict Resolution → Preview → Confirm → Execute → Verify

1. **Scan**: `find_skills_in_source()` (recursive, nested categories) and `find_skills_in_target()` (flat, skips hidden dirs)
2. **Plan**: `preview_bidirectional()` builds a `SyncPlan` using unified "find latest version → distribute" model. Scans all locations, groups by hash, identifies latest version per skill, generates `SyncOp` list. Respects `tools`/`exclude_tags` for selective sync.
3. **Conflict Resolution** (bidirectional mode): `_resolve_conflicts()` interactively resolves conflicts, directly generates `SyncOp` for chosen version
4. **Preview**: `show_preview()` displays the diff with conflict resolution results, all directories shown symmetrically
5. **Execute**: `execute_bidirectional()` or `execute_force()` applies the plan via `shutil.copytree`/`rmtree`
6. **Verify**: `verify_sync()` checks content hashes match across all directories

### Key concepts

- A **skill** is a directory containing a `SKILL.md` file
- **Source** (`~/Skills/`): nested category structure (e.g., `Code/skill-a/`, `Lark/skill-b/`). Treated as a special target directory — not a privileged authority, but a backup and category management location.
- **Targets** (flat): each tool's skills dir. Categories are flattened — only the leaf directory name matters
- **Bidirectional mode** (unified model, v0.6.0): scans all locations, finds the latest version of each skill (by hash grouping + mtime), and distributes from the latest location to all others. Source directory is just another destination. Interactive conflict resolution for ambiguous cases.
- **Force mode**: supports interactive base directory selection (`--force` without `-y`). When source dir is a target, preserves nested structure (new skills go to `Other/`, deletes use recursive lookup). Uses MD5 content hash comparison — identical skills are skipped without re-copying.
- **Selective sync**: `tools` field in SKILL.md frontmatter controls which targets a skill syncs to; `exclude_tags` in config.toml excludes skills with matching tags from all targets
- Duplicate skill names across categories are a fatal error (would conflict when flattened)

### SKILL.md frontmatter (optional)

```yaml
---
tags: [code, review]
description: "代码审查工具"
tools: [claude, codex]  # only sync to these targets (empty = all)
---
```

- Parsed by `metadata.py` using PyYAML
- `tools` maps to target path parent name: `~/.claude/skills` → `"claude"`
- Missing/empty fields → sync to all targets (backward compatible)

### Conflict detection (unified model, v0.6.0)

`preview_bidirectional()` uses pure hash grouping — no mtime for classification:

| Hash groups | Condition | Action |
|---|---|---|
| 1 group | All versions identical | Skip |
| 2 groups, 1 singleton, majority ≥ 2 | Safe auto-resolve | Use latest version (by mtime), generate `SyncOp` |
| 2 groups, both 1 member | No majority | Conflict → interactive resolution |
| 2 groups, 1 singleton, majority = 1 (source) | Source differs from 1 target | Conflict → interactive resolution |
| 3+ groups | Multi-version | Conflict → interactive resolution |

### Conflict resolution (v0.6.0)

- **Interactive mode** (default): `ask_conflict_resolution()` presents all versions with mtime hint and common SKILL.md preview (name/description shown once). User selects version or skips.
- **Auto mode** (`-y`): conflicts are converted to warnings (same as v0.2 behavior), sync proceeds without resolving conflicts.
- **Resolution**: `_resolve_conflicts()` directly generates `SyncOp` for the chosen version — no intermediate conversion step. Respects selective sync filtering.
- **Preview display**: resolved conflicts shown in a dedicated "冲突解决" section. All locations use human-readable target names (e.g., "Claude Code") from config/KNOWN_TOOLS.

### SyncOp (unified operation, v0.6.0)

- **`SyncOp(skill_name, origin_dir, dest_dir, dest_rel, origin_rel)`**: copies skill from latest version location to all outdated locations
- **`origin_dir`**: the directory containing the latest version (can be source or any target)
- **`dest_dir`**: the directory to update (can be source or any target)
- **`dest_rel`**: non-None only when `dest_dir` is source (nested path like `"Code/skill-a"`)
- **`origin_rel`**: non-None only when `origin_dir` is source (nested path for locating skill in source)
- Source directory is treated symmetrically with targets — it's just a destination with nested category support

### Content comparison

- **MD5 directory hashing** (`skill_dir_hash()`): computes hash of all files in a skill directory, excluding hidden files (`.DS_Store`, etc.)
- **Hidden directory filtering**: all scan functions skip directories with `.` prefix (e.g., `.system/`)
- **Conflict display**: `_build_version_warning_from_versions()` groups by hash, sorts by mtime, marks suggested version (git-like)
- **Path display**: target directories use human-readable names from config (e.g., "Claude Code") with `~/` short path as fallback; source directory always uses `~/` relative path

### Test structure

Tests in `tests/test_sync_skills.py` use `tmp_path` fixtures, organized by class: `TestScan`, `TestBidirectional`, `TestForce`, `TestDelete`, `TestErrors`, `TestPreview`, `TestMultiTarget`, `TestUserScenarios`, `TestBaseSelection`, `TestConflictResolution`, `TestSelectiveSync`, `TestListCommand`, `TestSearchCommand`, `TestInfoCommand`, `TestDryRun`. Helper functions `create_skill()` (flat) and `create_skill_in_category()` (nested) set up test fixtures. All tests pass `-y` to skip confirmation.

Additional test files:
- `tests/test_config.py` — Config module tests (load, save, path expand/unexpand, detect tools, exclude_tags): 18 tests
- `tests/test_init.py` — Init wizard tests (config creation, default/custom source): 3 tests
- `tests/test_metadata.py` — Metadata module tests (frontmatter parsing, filtering, search): 36 tests

Total: 167 tests.

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

# 同步过滤（可选）
[sync]
exclude_tags = ["experimental", "wip"]

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
- 演进规划（第 5 节）— Phase 3: 元数据与索引（已完成）
- 变更日志（第 7 节）— 每次讨论的关键决策和代码变更记录

## Cross-session workflow

每次对话结束前，用户会说"更新记忆"或触发 `/remember`，此时需要：
1. 更新 `docs/DESIGN.md` 第 7 节"变更日志"（按日期倒序追加本次决策和变更）
2. 更新本文件的 "Current status" 部分（如果项目状态有变化）
3. 更新 `~/.claude/projects/-Users-cian-Code-sync-skills/memory/MEMORY.md`

新会话开始时，先阅读 `docs/DESIGN.md` 第 7 节变更日志了解历史上下文。 `[added: 2026-03-21]`

## Current status

- **版本**: v0.6.0（统一同步模型重构）
- **v0.6.0 改进**: 去中心化统一 SyncOp 模型，源目录降级为特殊目标目录（备份+分类管理），去除了 collect→distribute 两阶段模型、`_apply_resolutions()`、`update_origins` 等中间层
- **Phase 4 已完成**: `--dry-run`、改进 help 输出（英文、epilog 示例）、`skills/sync-skills/SKILL.md`、167 个测试
- **下一步**: Phase 5 — 多端与协作（v1.0 远期）
