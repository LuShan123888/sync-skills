# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv run python -m pytest tests/ -v          # run all tests
uv run python -m pytest tests/ -v -k test_collect_new_skill  # run single test
uv sync                          # install dependencies
./sync_skills.py                 # run directly
./sync_skills.py --force -y      # force sync, skip confirm
./sync_skills.py --delete skill-name    # delete skill from source + all targets
./sync_skills.py -d skill-name -y       # delete with auto-confirm
```

## Architecture

Single-file CLI tool (`sync_skills.py`, ~900 lines, zero external dependencies) that syncs AI coding agent skills between a categorized source directory (`~/Skills/`) and multiple flat target directories (`~/.claude/skills/`, `~/.codex/skills/`, etc.).

### Core flow: Plan → Preview → Confirm → Execute → Verify

1. **Scan**: `find_skills_in_source()` (recursive, nested categories) and `find_skills_in_target()` (flat, skips hidden dirs)
2. **Plan**: `preview_bidirectional()` or `preview_force()` builds a `SyncPlan` dataclass
3. **Preview**: `show_preview()` displays the diff with relative paths per directory
4. **Execute**: `execute_bidirectional()` or `execute_force()` applies the plan via `shutil.copytree`/`rmtree`
5. **Verify**: `verify_sync()` checks content hashes match across all directories

### Key concepts

- A **skill** is a directory containing a `SKILL.md` file
- **Source** (`~/Skills/`): nested category structure (e.g., `Code/skill-a/`, `Lark/skill-b/`)
- **Targets** (flat): each tool's skills dir. Categories are flattened — only the leaf directory name matters
- **Bidirectional mode**: collects new/updated skills from targets into `~/Skills/Other/`, then distributes all skills to targets
- **Force mode**: supports interactive base directory selection (`--force` without `-y`). When source dir is a target, preserves nested structure (new skills go to `Other/`, deletes use recursive lookup). Uses MD5 content hash comparison — identical skills are skipped without re-copying.
- Duplicate skill names across categories are a fatal error (would conflict when flattened)

### Conflict handling (core design principle)

**只有无歧义的单向变更才自动处理，任何冲突都停下来让用户决定：**
- 仅目标修改 → 自动收集到源
- 仅源修改 → 警告，提示用 `--force`
- 源+目标都改了 → 警告跳过，用户手动处理
- 多目标都改了同一 skill → 警告跳过，用户手动处理
- 删除 skill → 从源删除 + `--force` 同步

### Content comparison

- **MD5 directory hashing** (`skill_dir_hash()`): computes hash of all files in a skill directory, excluding hidden files (`.DS_Store`, etc.)
- **Hidden directory filtering**: all scan functions skip directories with `.` prefix (e.g., `.system/`)
- **Conflict display**: `_build_version_warning()` groups by hash, sorts by mtime, marks suggested version (git-like)
- **Path display**: all output uses `~/` relative paths (e.g., `~/.claude/skills`), never full paths

### Test structure

Tests in `tests/test_sync_skills.py` use `tmp_path` fixtures, organized by class: `TestScan`, `TestBidirectional`, `TestForce`, `TestDelete`, `TestErrors`, `TestPreview`, `TestMultiTarget`, `TestUserScenarios`, `TestBaseSelection`. Helper functions `create_skill()` (flat) and `create_skill_in_category()` (nested) set up test fixtures. All tests pass `-y` to skip confirmation. 59 tests total.

### Delete command

**Usage:** `--delete <skill-name>` or `-d <skill-name>` removes a skill from both source and all target directories. Default mode shows preview and requires confirmation; `-y` flag auto-confirms.

**Safety:** Before deletion, verifies skill exists in at least one location. Shows detailed preview: which directories contain the skill, total deletion count. Non-existent skills trigger error message without side effects.

**When to use:** Removing obsolete or unwanted skills that exist in multiple locations. More efficient than manual deletion across 4+ directories.

## Design doc

See `docs/DESIGN.md` for:
- 用户场景与预期行为（第 3 节）— 所有同步场景的完整定义
- 当前已知限制（第 4 节）
- 演进规划（第 5 节）— Phase 1: PyPI 发布 + 配置化
- 变更日志（第 7 节）— 每次讨论的关键决策和代码变更记录

## Cross-session workflow

每次对话结束前，用户会说"更新记忆"或触发 `/remember`，此时需要：
1. 更新 `docs/DESIGN.md` 第 7 节"变更日志"（按日期倒序追加本次决策和变更）
2. 更新本文件的 "Current status" 部分（如果项目状态有变化）
3. 更新 `~/.claude/projects/-Users-cian-Code-sync-skills/memory/MEMORY.md`

新会话开始时，先阅读 `docs/DESIGN.md` 第 7 节变更日志了解历史上下文。 `[added: 2026-03-21]`

## Current status

- **版本**: v0.1（功能基本完整，未发布 PyPI）
- **下一步**: Phase 1 — PyPI 打包、首次启动引导、配置文件持久化
- **参考项目**: video-captions (`/Users/cian/Code/video-captions`) 的 PyPI 打包方式
