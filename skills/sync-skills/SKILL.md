---
name: sync-skills
description: "Manage custom AI coding agent skills via git + symlink. Use when the user wants to add/remove/list custom skills, check git status, push/pull skill changes, or verify symlinks. TRIGGER on: 'sync-skills', 'add skill', 'remove skill', 'skill management', 'list skills', 'custom skill'."
tools: [Bash]
---

# sync-skills

Custom skill lifecycle manager for AI coding agents. Manages user-created skills via git + symlink. Only manages skills explicitly added by the user.

## Prerequisites

The `sync-skills` CLI must be installed:

```bash
uv tool install sync-skills
```

## Important: Agent Execution Policy

AI agents **cannot interact with stdin**, so follow this two-step pattern for **all mutating commands** (init, link, unlink, new, remove, doctor, push, pull):

1. **First**: run with `--dry-run` to preview what will happen, show the output to the user
2. **Then**: only after user confirms, re-run with `-y` to execute

**Read-only commands** (`list`, `status`) are safe to run directly without `-y` or `--dry-run`.

## Commands Reference

| User intent | Command | Type |
|---|---|---|
| List custom skills | `sync-skills list` | read |
| Show git status | `sync-skills status` | read |
| Initialize ~/Skills/ repo | `sync-skills init` (clone from remote or git init, idempotent) | mutate |
| Link a skill (auto-scan by name) | `sync-skills link skill-name` | mutate |
| Unlink a skill (restore files) | `sync-skills unlink skill-name` | mutate |
| Unlink all skills | `sync-skills unlink --all` | mutate |
| Create new custom skill | `sync-skills new skill-name -d "description"` | mutate |
| Remove a skill permanently | `sync-skills remove skill-name` | mutate |
| Remove multiple skills | `sync-skills remove a b c` | mutate |
| Verify/repair symlinks | `sync-skills doctor` | mutate |
| Commit and push | `sync-skills push -m "update"` | mutate |
| Pull and rebuild | `sync-skills pull` | mutate |

## Common Workflows

### 1. Create a new custom skill

```bash
sync-skills new my-skill -d "My custom skill description" -t "tag1,tag2" --dry-run
# show preview to user, wait for confirmation
sync-skills new my-skill -d "My custom skill description" -t "tag1,tag2" -y
```

Creates `~/Skills/skills/my-skill/SKILL.md` with skeleton and symlinks to all agent directories.

### 2. Link a wild skill

```bash
sync-skills link my-skill --dry-run
# show preview to user, wait for confirmation
sync-skills link my-skill -y
```

Adopts a skill (existing in any agent directory or repo) into management. Auto-scans all agent directories and the repo for the named skill. If multiple versions exist, groups by content hash and lets the user choose (auto-selects latest with `-y`).

### 3. Edit a skill (via agent)

The agent edits `~/Skills/skills/my-skill/SKILL.md` normally. Changes flow through symlinks to all agent directories automatically.

### 4. Push changes to GitHub

```bash
sync-skills status       # check what changed (read-only, safe)
sync-skills push -m "update my-skill" --dry-run
# show preview to user, wait for confirmation
sync-skills push -m "update my-skill" -y
```

Shows full git commands (`git add -A`, `git commit -m "..."`, `git push -u origin <branch>`) before confirming.

### 5. Pull changes from another machine

```bash
sync-skills pull --dry-run
# show preview to user, wait for confirmation
sync-skills pull -y
```

Shows full git command (`git pull --rebase`) before confirming. Automatically repairs symlinks after pull.

### 6. Unlink a skill

```bash
sync-skills unlink my-skill --dry-run
# show preview to user, wait for confirmation
sync-skills unlink my-skill -y
```

Removes the skill from management. Files are restored to all agent directories as real files. The skill is removed from `~/Skills/skills/` and the state file.

### 7. Verify and repair symlinks

```bash
sync-skills doctor --dry-run
# show preview to user, wait for confirmation
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
