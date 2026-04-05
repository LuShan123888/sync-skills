---
name: sync-skills
description: "Sync, manage, and query AI coding agent skills across multiple tools (Claude Code, Codex CLI, Gemini CLI, OpenClaw). Use when the user wants to sync skills, check skill status, list/search/query skills, delete a skill, initialize skill config, or manage skill distribution. TRIGGER on: 'sync skills', '同步', 'force sync', '强制同步', 'skill management', 'list skills', 'search skills', 'delete skill', 'sync-skills'."
tools: [Bash]
---

# sync-skills

Unified skill management and sync tool for AI coding agents. Maintains a single categorized source directory (`~/Skills/`) and distributes skills to all installed tools.

## Prerequisites

The `sync-skills` CLI must be installed:

```bash
uv tool install sync-skills
```

## Important: Always Use `-y`

AI agents **cannot interact with stdin**. Always append `-y` to skip confirmation prompts. Never run sync-skills without `-y` unless the user explicitly asks for interactive mode.

## Commands Reference

| User intent | Command |
|---|---|
| Sync skills (bidirectional) | `sync-skills -y` |
| Force sync (source is truth) | `sync-skills --force -y` |
| Preview changes only | `sync-skills --dry-run` |
| Preview force sync only | `sync-skills --force --dry-run` |
| Initialize config | `sync-skills init` |
| List all skills | `sync-skills list` |
| List skills by tag | `sync-skills list --tags code` |
| Search skills | `sync-skills search "review"` |
| Show skill details | `sync-skills info skill-name` |
| Delete a skill | `sync-skills --delete skill-name -y` |
| Delete with dry-run | `sync-skills --delete skill-name --dry-run` |

## Common Workflows

### 1. Sync after editing a skill

```bash
sync-skills -y
```

Collects new/updated skills from all tools and redistributes.

### 2. Check what would change (safe preview)

```bash
sync-skills --dry-run
```

Shows the full plan (collect, create, update, delete) without executing anything.

### 3. Force sync after reorganization

```bash
sync-skills --force -y
```

Makes source directory the single source of truth: adds missing skills, overwrites different content, removes extras.

### 4. Delete an obsolete skill

```bash
sync-skills --delete skill-name -y
```

Removes from source directory and all target directories.

### 5. Find a specific skill

```bash
sync-skills search "review"
sync-skills info code-review
```

## Flags

| Flag | Purpose |
|---|---|
| `-y`, `--yes` | Skip confirmation (always use this) |
| `--dry-run` | Show plan without executing |
| `--force`, `-f` | Force sync mode |
| `--delete NAME`, `-d NAME` | Delete a skill |
| `--source DIR` | Override source directory |
| `--targets DIR1,DIR2` | Override target directories |
| `--config PATH` | Use custom config file |
| `--tags TAG1,TAG2` | Filter by tags (list command only) |

## Config File

Location: `~/.config/sync-skills/config.toml`

```toml
source = "~/Skills"

[sync]
exclude_tags = ["experimental", "wip"]

[[targets]]
name = "Claude Code"
path = "~/.claude/skills"
```

## Error Handling

| Error | Cause | Resolution |
|---|---|---|
| "源目录存在重名 skill" | Same skill name in multiple categories | Rename one of the duplicates in `~/Skills/` |
| "skill 'xxx' 不存在" | Delete target not found | Check spelling with `sync-skills list` |
| "源目录不存在" | Source directory missing | Create it or run `sync-skills init` |
| Conflict warnings | Multiple versions with different content | Run `sync-skills` without `-y` for interactive resolution, or manually reconcile |
