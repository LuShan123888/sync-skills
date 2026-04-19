# sync-skills

> 自定义 Skill 生命周期管理器。
> 通过 git + symlink 管理你的 AI Skills。

sync-skills v1.1 通过 git + symlink 管理用户自建的 Skill。
sync-skills 只管理用户显式纳入的 Skill，其他 Skill（由任何工具管理）不受影响。

---

## 为什么需要它

AI 编码工具（Claude Code、Codex CLI、Gemini CLI 等）都有自己的 skills 目录。用户自建的 Skill 缺少统一的管理方式。

```text
:/  自己写的 skill 分散在各个工具目录里
:/  换台电脑，之前的自定义 skill 可能都丢失
:/  需要版本管理，但工具目录是平铺的，不适合直接 git 管理
```

sync-skills 的做法是 **git + symlink**：

```text
~/Skills/skills/             <-- 自定义 Skill 仓库（git 仓库，唯一真实来源）
├── english-buddy/
│   └── SKILL.md
└── git-commit/
    └── SKILL.md

~/.agents/skills/            <-- Agent Skill 目录（与 ~/.claude/skills 同等地位）
├── english-buddy/           --> ~/Skills/skills/english-buddy/  (symlink)
└── git-commit/              --> ~/Skills/skills/git-commit/     (symlink)

~/.claude/skills/            <-- Agent Skill 目录
├── english-buddy/           --> ~/Skills/skills/english-buddy/  (symlink)
└── git-commit/              --> ~/Skills/skills/git-commit/     (symlink)
```

- **自定义 Skill** 存放在 `~/Skills/` git 仓库中，并通过 symlink 关联到所有 Agent 目录。
- **版本控制** 所有自定义 Skill 均在 git 仓库中，天然支持版本管理和多设备同步。
- **零拷贝** symlink 不占额外空间，修改即刻生效。

---

## AI Agent 友好

sync-skills 专为 AI 编码工具设计，支持两种 Agent 集成方式。

### 内置 Skill

项目附带 `skills/sync-skills/SKILL.md`，可安装到任意 AI 编码工具中。安装后，Agent 可以根据自然语言直接操作：

```text
用户: "同步一下 skills"       --> Agent 执行: sync-skills push -y
用户: "拉取远程更新"          --> Agent 执行: sync-skills pull -y
用户: "新建一个 skill"        --> Agent 执行: sync-skills new my-skill
用户: "看看有什么 skill"      --> Agent 执行: sync-skills list
```

### Agent 友好的 CLI

- **`--help`** 输出结构化文本，包含完整示例，便于 Agent 解析。
- **`-y`** 跳过交互确认：Agent 无法操作 stdin，`-y` 确保非阻塞执行。
- **`list`**：结构化输出，便于 Agent 查询 skill 状态。
- **`status`**：显示 git 状态 + skill 管理状态，便于 Agent 全面了解。

---

## 快速开始

### 安装

```bash
# 推荐：通过 PyPI 安装
uv tool install sync-skills

# 或从源码安装
git clone https://github.com/LuShan123888/sync-skills.git
cd sync-skills
pip install -e .
```

> 要求 Python >= 3.11

### 初始化

```bash
sync-skills init    # 初始化 ~/Skills/ 仓库（支持 git clone 远程仓库，可重复执行）
```

配置文件保存在 `~/.config/sync-skills/config.toml`，也可以手动编辑。

### 使用

```bash
# 初始化
sync-skills init

# 纳入管理（按名称自动扫描）
sync-skills link my-skill

# 提交并推送（展示完整 git 命令）
sync-skills push

# 仅提交（展示变更 skill、时间、最近 commit）
sync-skills commit

# 拉取远程更新（展示完整 git 命令）
sync-skills pull

# 验证与修复 symlink + 检测异常
sync-skills doctor

# 列出自定义 Skill
sync-skills list

# 查看 git 状态 + skill 管理状态
sync-skills status

# 创建新 Skill（手动创建骨架）
sync-skills new my-skill

# 删除 Skill（彻底删除）
sync-skills remove my-skill

# 卸载 Skill（移除管理，还原文件）
sync-skills unlink my-skill
```

---

## 架构

### 目录结构

```text
~/Skills/                    # 自定义 Skill 仓库（git 仓库，唯一真实存储）
├── skills/
│   ├── english-buddy/
│   │   └── SKILL.md
│   └── git-commit/
│       └── SKILL.md
└── .git/

~/.agents/skills/            # Agent Skill 目录（与 ~/.claude/skills 同等地位）
├── english-buddy/           --> ~/Skills/skills/english-buddy/  (symlink)
└── git-commit/              --> ~/Skills/skills/git-commit/     (symlink)

~/.claude/skills/            # Agent Skill 目录
├── english-buddy/           --> ~/Skills/skills/english-buddy/  (symlink)
└── git-commit/              --> ~/Skills/skills/git-commit/     (symlink)
```

### 工作流

1. **init**：初始化 `~/Skills/` git 仓库（可选 git clone 远程仓库），自动注册 repo 内全部 skill 并建立/修复 symlink。
2. **link**：按名称自动扫描 skill（复制到 git 仓库、清理其它副本、创建 symlink）；多版本时按 MD5 分组并按时间排序供用户选择。
3. **commit**：展示影响的 skill、修改时间、最近 commit，并预览 `git add`/`commit`，确认后执行。
4. **push**：展示完整 git 命令（`git add`/`commit`/`push`），确认后执行。
5. **pull**：展示完整 git 命令（`git pull --rebase`），确认后执行，并修复 symlink。
6. **doctor**：验证所有 symlink，自动修复断裂链接，并检测状态不一致。
7. **list**：列出所有自定义 Skill。
8. **status**：显示 git 状态 + skill 管理状态 + 断链检测。
9. **new**：在 `~/Skills/skills/` 创建 skill 骨架，并建立 symlink。
10. **remove**：彻底删除 skill（删除仓库文件 + 所有 symlink）。
11. **unlink**：移除管理关系，文件还原到所有 Agent 目录。

---

## 对比其他方案

### 与手动 Symlink 的对比

| 项目 | 手动 Symlink | sync-skills v1.1 |
|---|---|---|
| **版本控制** | 无，换设备就丢失 | git 仓库，支持版本管理和多设备同步 |
| **新建 Skill** | 手动创建目录、写文件、建 N 条链接 | `sync-skills new` 一条命令完成 |
| **删除 Skill** | 手动删文件、清除断链 | `sync-skills remove` 自动清理 |
| **卸载 Skill** | 手动还原文件、删除链接 | `sync-skills unlink` 还原文件到所有 Agent 目录 |
| **多设备同步** | 不支持 | `push` / `pull` 一键同步 |
| **维护成本** | 每次变更手动执行 | 自动化，近似零维护 |

### 与 v0.6 复制模式对比

| 项目 | v0.6 复制模式 | v1.1 git + symlink |
|---|---|---|
| **存储** | 复制 N 份真实文件 | symlink，零拷贝 |
| **版本管理** | 不支持 | git 原生支持 |
| **一致性** | 依赖手动或定时同步 | symlink 保证实时一致 |
| **磁盘占用** | N 倍（N = 工具数） | 1 倍 |

---

## 参数

### v1.1 命令

| 命令 | 说明 |
|------|------|
| `sync-skills init` | 初始化 ~/Skills/ 仓库（可重复执行；有远程仓库时自动 clone 并注册所有 skill） |
| `sync-skills link <name>` | 纳入 skill（按名称自动扫描，多版本时让用户选择；`-y` 跳过确认） |
| `sync-skills commit [-m MSG]` | `git add` + `commit`（预览变更 skill、时间、最近 commit，确认后执行） |
| `sync-skills push [-m MSG]` | `git commit` + `push`（展示完整 git 命令，确认后执行） |
| `sync-skills pull` | `git pull`（展示完整 git 命令，确认后执行）+ 修复 symlinks |
| `sync-skills doctor` | 验证/修复 symlink + 检测状态不一致 |
| `sync-skills list [--tags TAG]` | 列出所有自定义 Skill |
| `sync-skills status` | 显示 git 状态 + skill 管理状态 + 断链检测 |
| `sync-skills new <name>` | 创建新 custom skill（手动创建骨架） |
| `sync-skills remove <name>` | 彻底删除 custom skill（支持多个；`-y` 跳过确认） |
| `sync-skills unlink [name]` | 移除管理，还原文件（`name` 可省略或 `--all`） |

### 通用选项

| 参数 | 说明 |
|------|------|
| `-y`, `--yes` | 跳过交互确认 |
| `--config PATH` | 配置文件路径（默认 `~/.config/sync-skills/config.toml`） |
| `--dry-run` | 预览模式，不执行任何操作 |

### 遗留命令（--copy 模式）

| 命令 | 说明 |
|------|------|
| `sync-skills --copy` | v0.6 双向复制同步 |
| `sync-skills --copy --force` | v0.6 强制同步 |
| `sync-skills --copy --delete <name>` | v0.6 删除 skill |
| `sync-skills --copy --dry-run` | v0.6 预览模式 |

### 默认目录

| 角色 | 路径 |
|------|------|
| 自定义 Skill 仓库 | `~/Skills` |
| Agent Skill 目录 | `~/.agents/skills` |
| Claude Code | `~/.claude/skills` |
| Codex CLI | `~/.codex/skills` |
| Gemini CLI | `~/.gemini/skills` |

---

## 配置文件

配置文件保存在 `~/.config/sync-skills/config.toml`：

```toml
repo = "~/Skills"
agents_dir = "~/.agents/skills"
state_file = "~/.config/sync-skills/skills.json"
```

- `repo`：自定义 Skill 的 git 仓库路径。
- `agents_dir`：保留字段（向后兼容）。
- `state_file`：状态文件路径（记录已管理的 skill）。

---

## 安全机制

- **Git 命令预览**：`push` 和 `pull` 执行前展示完整 git 命令，用户确认后才执行。
- **操作前后验证**：`new`/`remove`/`unlink` 后自动验证状态；`pull` 前检查状态，有异常则警告。
- **Symlink 验证**：`doctor` 检查所有 symlink，修复断裂链接。
- **断链检测**：`doctor` 和 `status` 自动检测断链并提示清理。
- **状态一致性**：`doctor` 检测状态文件与真实状态不一致。
- **Git 保障**：所有自定义 Skill 变更都有 git 历史可回溯。
- **存量仓库保护**：`init` 检查 git 状态，避免未提交或落后时误操作。
- **隐藏目录过滤**：自动跳过 `.system/` 等隐藏目录。

---

## 开发

```bash
uv run pytest tests/ -v    # 运行测试（204 个用例）
```

## 许可证

MIT

---

# sync-skills

> Custom Skill Lifecycle Manager.
> Manage your AI Skills via git + symlink.

sync-skills v1.1 manages user-created Skills via git + symlink.
sync-skills manages only explicitly adopted skills; other Skills managed by other tools are untouched.

## Why

AI coding tools (Claude Code, Codex CLI, Gemini CLI, etc.) each have their own skills directories. User-created skills lack a unified management approach.

```text
:/  User-created skills are scattered across tool directories.
:/  Switching machines may lose previously created custom skills.
:/  Version control is needed, but the flat tool directories are not suitable for direct git management.
```

sync-skills uses **git + symlink**:

```text
~/Skills/skills/             <-- Custom skill repository (git repository, single source of truth)
├── english-buddy/
│   └── SKILL.md
└── git-commit/
    └── SKILL.md

~/.agents/skills/            <-- Agent skill directory (same status as ~/.claude/skills)
├── english-buddy/           --> ~/Skills/skills/english-buddy/  (symlink)
└── git-commit/              --> ~/Skills/skills/git-commit/     (symlink)

~/.claude/skills/            <-- Agent skill directory
├── english-buddy/           --> ~/Skills/skills/english-buddy/  (symlink)
└── git-commit/              --> ~/Skills/skills/git-commit/     (symlink)
```

- **Custom skills** are stored in the `~/Skills/` git repository and linked to all Agent directories.
- **Version control**: all custom skills are in git, with built-in versioning and multi-device sync.
- **Zero-copy**: symlinks use no extra space and take effect immediately.

---

## Agent-Friendly Design

sync-skills is designed for AI coding tools and supports two integration patterns.

### Built-in Skill

The project includes `skills/sync-skills/SKILL.md`, which can be installed as a skill in any AI coding tool. After installation, Agents can operate it using natural language:

```text
User: "Sync skills"            --> Agent executes: sync-skills push -y
User: "Pull remote updates"    --> Agent executes: sync-skills pull -y
User: "Create a skill"         --> Agent executes: sync-skills new my-skill
User: "Show available skills"  --> Agent executes: sync-skills list
```

### Agent-friendly CLI

- **`--help`** outputs structured English text with examples, optimized for Agent parsing.
- **`-y`** skips interactive confirmation: Agents cannot provide stdin input, so `-y` ensures non-blocking execution.
- **`list`** provides structured output for querying skill states.
- **`status`** shows git and management state for full visibility.

---

## Quick Start

### Install

```bash
# Install from PyPI
uv tool install sync-skills

# Or install from source
git clone https://github.com/LuShan123888/sync-skills.git
cd sync-skills
pip install -e .
```

> Python >= 3.11 required

### Init

```bash
sync-skills init    # Initialize the ~/Skills/ repo (supports remote clone, idempotent)
```

Config is stored at `~/.config/sync-skills/config.toml`, and can be edited manually.

### Usage

```bash
# Initialize
sync-skills init

# Adopt a skill by name
sync-skills link my-skill

# Commit and push (shows full git commands)
sync-skills push

# Commit only (show changed skills, timestamps, recent commits)
sync-skills commit

# Pull remote updates (shows full git commands)
sync-skills pull

# Verify and repair symlinks
sync-skills doctor

# List custom skills
sync-skills list

# Show git status and skill management status
sync-skills status

# Create a new skill skeleton
sync-skills new my-skill

# Remove a skill permanently
sync-skills remove my-skill

# Unlink a custom skill (restore files)
sync-skills unlink my-skill
```

---

## Architecture

### Directory Layout

```text
~/Skills/                    # Custom skill repository (git repository, single source of truth)
├── skills/
│   ├── english-buddy/
│   │   └── SKILL.md
│   └── git-commit/
│       └── SKILL.md
└── .git/

~/.agents/skills/            # Agent skill directory (same status as ~/.claude/skills)
├── english-buddy/           --> ~/Skills/skills/english-buddy/  (symlink)
└── git-commit/              --> ~/Skills/skills/git-commit/     (symlink)

~/.claude/skills/            # Agent skill directory
├── english-buddy/           --> ~/Skills/skills/english-buddy/  (symlink)
└── git-commit/              --> ~/Skills/skills/git-commit/     (symlink)
```

### Workflow

1. **init**: Initialize the `~/Skills/` git repository (optionally clone remote), register all skills in repo, and create/repair symlinks.
2. **link**: auto-scan by name, move/copy into git repo, clean other copies, create symlink; when there are multiple versions, group by MD5 and sort by mtime for user selection.
3. **commit**: show affected skills, timestamps, recent commit, and preview `git add`/`commit` before confirmation.
4. **push**: show full git commands (`git add`/`commit`/`push`) and execute after confirmation.
5. **pull**: show full git command (`git pull --rebase`), execute after confirmation, then repair symlinks.
6. **doctor**: verify all symlinks and auto-repair broken links, detect inconsistent state.
7. **list**: list all custom skills.
8. **status**: show git state, skill management state, and broken-link checks.
9. **new**: create skill skeleton under `~/Skills/skills/` and create symlinks.
10. **remove**: remove the skill completely (delete repo files and all symlinks).
11. **unlink**: remove management and restore files to all Agent directories.

---

## Comparison

### vs manual symlink

| Item | Manual symlink | sync-skills v1.1 |
|---|---|---|
| **Version control** | None; lost when switching devices | git repo with built-in versioning and multi-device sync |
| **Create a skill** | Manually create directories/files and N links | `sync-skills new` completes it in one command |
| **Delete a skill** | Manually delete files and clear broken links | `sync-skills remove` auto-cleans |
| **Uninstall a skill** | Manual restore files and delete links | `sync-skills unlink` restores files to all Agent dirs |
| **Multi-device sync** | Not supported | One-command sync via `push` / `pull` |
| **Maintenance cost** | Manual execution for every change | Automated, near-zero maintenance |

### vs v0.6 copy mode

| Item | v0.6 copy mode | v1.1 git + symlink |
|---|---|---|
| **Storage** | N copies of real files | symlink, zero-copy |
| **Version control** | Not supported | Supported by git natively |
| **Consistency** | Depends on manual/periodic sync | symlink keeps state synchronized in real time |
| **Disk usage** | Nx (N = number of tools) | 1x |

---

## Options

### v1.1 Commands

| Command | Description |
|------|------|
| `sync-skills init` | Initialize the ~/Skills repo (idempotent; auto clone remote and register all skills) |
| `sync-skills link <name>` | Adopt a skill by name (auto scan; choose from multi-version candidates; `-y` skips confirmation) |
| `sync-skills commit [-m MSG]` | `git add` + `commit` (preview changed skills, timestamps, recent commits, execute on confirmation) |
| `sync-skills push [-m MSG]` | `git commit` + `push` (show full git commands, execute on confirmation) |
| `sync-skills pull` | `git pull` (show full git command, execute on confirmation) + repair symlinks |
| `sync-skills doctor` | Verify and repair symlinks, detect state inconsistencies |
| `sync-skills list [--tags TAG]` | List all custom skills |
| `sync-skills status` | Show git status + management state + broken-link checks |
| `sync-skills new <name>` | Create a new skill skeleton |
| `sync-skills remove <name>` | Remove a skill permanently (multiple names supported; `-y` skips confirmation) |
| `sync-skills unlink [name]` | Remove management and restore files (`name` optional or `--all`) |

### Common Options

| Option | Description |
|------|------|
| `-y`, `--yes` | Skip interactive confirmation |
| `--config PATH` | Config file path (default `~/.config/sync-skills/config.toml`) |
| `--dry-run` | Preview mode; no changes are applied |

### Legacy Commands (`--copy`)

| Command | Description |
|------|------|
| `sync-skills --copy` | v0.6 bidirectional copy sync |
| `sync-skills --copy --force` | v0.6 forced sync |
| `sync-skills --copy --delete <name>` | v0.6 delete skill |
| `sync-skills --copy --dry-run` | v0.6 dry-run mode |

### Default Directories

| Role | Path |
|------|------|
| Custom skill repository | `~/Skills` |
| Agent skill directory | `~/.agents/skills` |
| Claude Code | `~/.claude/skills` |
| Codex CLI | `~/.codex/skills` |
| Gemini CLI | `~/.gemini/skills` |

---

## Config

Config is stored in `~/.config/sync-skills/config.toml`:

```toml
repo = "~/Skills"
agents_dir = "~/.agents/skills"
state_file = "~/.config/sync-skills/skills.json"
```

- `repo`: path to custom skill git repository.
- `agents_dir`: reserved field for backward compatibility.
- `state_file`: path to state file (records managed skills).

---

## Safety

- **Git command preview**: `push` and `pull` show full git commands before execution and require user confirmation.
- **Pre/Post verification**: `new`/`remove`/`unlink` auto-verify state; `pull` checks state beforehand and warns on abnormalities.
- **Symlink checks**: `doctor` checks all symlinks and repairs broken links.
- **Broken-link detection**: `doctor` and `status` detect broken links and suggest cleanup.
- **State consistency**: `doctor` detects mismatch between state file and actual filesystem.
- **Git-backed safety**: all managed skill changes are fully traceable and rollback-safe.
- **Legacy-repo protection**: `init` validates git state and avoids operating on dirty or stale repos.
- **Hidden directory filtering**: automatically skip `.system/` and other hidden directories.

---

## Development

```bash
uv run pytest tests/ -v    # run tests (204 cases)
```

## License

MIT
