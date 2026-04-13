---
name: sync-skills
description: "Manage custom AI coding agent skills via git + symlink. Use when the user wants to add/remove/list/search custom skills, check git status, push/pull skill changes, or verify symlinks. TRIGGER on: 'sync-skills', 'add skill', 'remove skill', 'skill management', 'list skills', 'custom skill'."
tools: [Bash]
---

# sync-skills

Custom skill lifecycle manager for AI coding agents. Manages user-created skills via git + symlink. Only manages skills explicitly added by the user.

## Prerequisites

The `sync-skills` CLI must be installed:

```bash
uv tool install sync-skills
```

## Important: Always Use `-y`

AI agents **cannot interact with stdin**. Always append `-y` to skip confirmation prompts.

## Commands Reference

| User intent | Command |
|---|---|
| Initialize ~/Skills/ repo | `sync-skills init -y` (clone from remote or git init, idempotent) |
| Link a skill (auto-scan by name) | `sync-skills link skill-name -y` |
| Unlink a skill (restore files) | `sync-skills unlink skill-name -y` |
| Unlink all skills | `sync-skills unlink --all -y` |
| Create new custom skill | `sync-skills new skill-name -d "description" -y` |
| Remove a skill permanently | `sync-skills remove skill-name -y` |
| Remove multiple skills | `sync-skills remove a b c -y` |
| Verify/repair symlinks | `sync-skills doctor -y` |
| List custom skills | `sync-skills list` |
| Show git status | `sync-skills status` |
| Commit and push | `sync-skills push -m "update" -y` |
| Pull and rebuild | `sync-skills pull -y` |
| Preview without executing | `sync-skills <command> --dry-run` |

## Common Workflows

### 1. Create a new custom skill

```bash
sync-skills new my-skill -d "My custom skill description" -t "tag1,tag2" -y
```

Creates `~/Skills/skills/my-skill/SKILL.md` with skeleton and symlinks to all agent directories.

### 2. Link a wild skill

```bash
sync-skills link my-skill -y
```

Adopts a skill (existing in any agent directory or repo) into management. Auto-scans all agent directories and the repo for the named skill. If multiple versions exist, groups by content hash and lets the user choose (auto-selects latest with `-y`).

### 3. Edit a skill (via agent)

The agent edits `~/Skills/skills/my-skill/SKILL.md` normally. Changes flow through symlinks to all agent directories automatically.

### 4. Push changes to GitHub

```bash
sync-skills status       # check what changed
sync-skills push -m "update my-skill" -y
```

Shows full git commands (`git add -A`, `git commit -m "..."`, `git push -u origin <branch>`) before confirming.

### 5. Pull changes from another machine

```bash
sync-skills pull -y      # git pull + rebuild symlinks
```

Shows full git command (`git pull --rebase`) before confirming. Automatically repairs symlinks after pull.

### 6. Unlink a skill

```bash
sync-skills unlink my-skill -y
```

Removes the skill from management. Files are restored to all agent directories as real files. The skill is removed from `~/Skills/skills/` and the state file.

### 7. Verify and repair symlinks

```bash
sync-skills doctor -y
```

Checks all managed skill symlinks, repairs broken links, detects state inconsistencies.

## Flags

| Flag | Purpose |
|---|---|
| `-y`, `--yes` | Skip confirmation |
| `--dry-run` | Preview without executing |
| `--copy` | Use legacy copy-based sync |
| `--config PATH` | Use custom config file |
| `--all` | Apply to all (unlink) |
| `--message`, `-m` | Commit message (push command) |
| `--description`, `-d` | Skill description (new command) |
| `--tags`, `-t` | Comma-separated tags (new command) |

## Architecture

- **Custom skills**: stored in `~/Skills/` git repo, symlinked to all agent directories
- **State file**: `~/.config/sync-skills/skills.json` tracks which skills are managed by sync-skills
- **Single-layer symlink**: `~/Skills/skills/<name>` → `<agent-dir>/skills/<name>` (all agent dirs including `~/.agents/skills/`)

## Config File

Location: `~/.config/sync-skills/config.toml`

```toml
repo = "~/Skills"
agents_dir = "~/.agents/skills"
state_file = "~/.config/sync-skills/skills.json"
```
