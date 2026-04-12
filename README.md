# sync-skills

> 自定义 Skill 生命周期管理器 -- 通过 git + symlink 管理你的 AI Skills。
>
> Custom Skill Lifecycle Manager -- manage your AI skills via git + symlink.

sync-skills v1.0 采用双类型架构：**外部 Skill**（由 `npx skills` 管理）和**自定义 Skill**（由 sync-skills 通过 git + symlink 管理）。sync-skills 只负责用户自建的 Skill，不触碰外部 Skill。

---

## 为什么需要它 / Why

AI 编码工具（Claude Code、Codex CLI、Gemini CLI 等）都有自己的 skills 目录。社区通过 `npx skills` 安装的外部 Skill 各工具自动管理，但用户自建的 Skill 缺少统一的管理方式：

```
:/  自己写的 skill 分散在各个工具目录里
:/  换台电脑，自定义 skill 全丢了
:/  想版本管理，但工具目录是平铺的，不适合直接 git 管理
```

sync-skills 的做法 -- **git + symlink 双类型架构**：

```
~/Skills/skills/             <-- 自定义 Skill 仓库（git 仓库，唯一真实来源）
├── english-buddy/
│   └── SKILL.md
└── git-commit/
    └── SKILL.md

~/.agents/skills/            <-- 统一 Skill 目录（所有 Agent 的读取入口）
├── docx/                    <-- 外部 Skill（真实文件，由 npx skills 管理）
├── english-buddy/           --> ~/Skills/skills/english-buddy/  (symlink)
└── git-commit/              --> ~/Skills/skills/git-commit/     (symlink)

~/.claude/skills/xxx  --> ~/.agents/skills/xxx  (Agent Skill 目录 symlink)
```

- **外部 Skill**（如 docx）由 `npx skills` 管理，sync-skills 不触碰
- **自定义 Skill** 存放在 `~/Skills/` git 仓库中，通过 symlink 关联到统一 Skill 目录
- **统一 Skill 目录** `~/.agents/skills/` 是所有 Agent 的统一读取入口
- **版本控制** -- 自定义 Skill 全部在 git 仓库中，天然支持版本管理、多设备同步
- **零拷贝** -- symlink 不占额外空间，修改即刻生效

---

## AI Agent 友好 / Agent-Friendly Design

sync-skills 专为 AI 编码工具设计，支持两种 Agent 集成方式：

### 内置 Skill

项目附带一个 `skills/sync-skills/SKILL.md`，可作为 skill 安装到任意 AI 编码工具中。安装后，Agent 可以根据自然语言直接操作：

```
用户: "同步一下 skills"       --> Agent 执行: sync-skills push -y
用户: "拉取远程更新"          --> Agent 执行: sync-skills pull -y
用户: "新建一个 skill"        --> Agent 执行: sync-skills add my-skill
用户: "看看有什么 skill"      --> Agent 执行: sync-skills list
用户: "查一下 code-review"    --> Agent 执行: sync-skills info code-review
```

### Agent 友好的 CLI

- **`--help`** 输出结构化英文文本，包含完整示例，便于 Agent 解析
- **`-y`** 跳过交互确认：Agent 无法操作 stdin，`-y` 确保非阻塞执行
- **`list` / `search` / `info`**：结构化输出，便于 Agent 查询 skill 状态
- **`status`**：显示 git 状态 + skill 管理状态，便于 Agent 全面了解

---

## 快速开始 / Quick Start

### 安装 / Install

```bash
# 推荐：通过 PyPI 安装
uv tool install sync-skills

# 或从源码安装
git clone https://github.com/LuShan123888/sync-skills.git
cd sync-skills
pip install -e .
```

> 要求 Python >= 3.11

### 初始化 / Init

```bash
sync-skills init    # 初始化 ~/Skills/ 仓库，迁移已有自定义 Skill，建立 symlink
```

配置文件保存在 `~/.config/sync-skills/config.toml`，也可以手动编辑。

### 使用 / Usage

```bash
# 初始化 / Initialize
sync-skills init

# 创建新 Skill / Create a new custom skill
sync-skills add my-skill

# 提交并推送（展示完整 git 命令） / Git commit + push (shows full git commands)
sync-skills push

# 拉取远程更新（展示完整 git 命令） / Git pull (shows full git commands)
sync-skills pull

# 验证/修复 symlink + 检测断链/缺失/孤儿 / Verify/repair + detect anomalies
sync-skills fix

# 列出自定义 Skill / List custom skills
sync-skills list

# 查看 git 状态 + skill 管理状态 / Show git status and skill management state
sync-skills status

# 搜索 / Search
sync-skills search "review"

# 查看详情（含外部/自定义分类）/ Show details (with external/custom classification)
sync-skills info skill-name

# 删除 Skill（彻底删除）/ Remove a custom skill permanently
sync-skills remove my-skill

# 卸载 Skill（还原文件）/ Uninstall a custom skill (restore files)
sync-skills uninstall my-skill

# 卸载所有自定义 Skill / Uninstall all custom skills
sync-skills uninstall -y
```

---

## 架构 / Architecture

### 双类型 Skill 架构

| 类型 | 来源 | 存储方式 | 管理工具 |
|------|------|----------|----------|
| 外部 Skill | `npx skills install` | 真实文件在 `~/.agents/skills/` | npx skills |
| 自定义 Skill | 用户创建 | git 仓库 `~/Skills/skills/` | sync-skills |

### 目录结构

```
~/Skills/                    # 自定义 Skill 仓库（git 仓库，唯一真实存储）
├── skills/
│   ├── english-buddy/
│   │   └── SKILL.md
│   └── git-commit/
│       └── SKILL.md
└── .git/

~/.agents/skills/            # 统一 Skill 目录（所有 Agent 的读取入口）
├── docx/                    # 外部 Skill（真实文件）
├── english-buddy/           # --> ~/Skills/skills/english-buddy/  (symlink)
└── git-commit/              # --> ~/Skills/skills/git-commit/     (symlink)

~/.claude/skills/            # Agent Skill 目录
├── docx/                    # --> ~/.agents/skills/docx/
├── english-buddy/           # --> ~/.agents/skills/english-buddy/
└── git-commit/              # --> ~/.agents/skills/git-commit/
```

### 工作流 / Workflow

1. **init** -- 初始化 `~/Skills/` git 仓库，扫描现有自定义 Skill 并迁移，建立 symlink 链路
2. **add** -- 在 `~/Skills/skills/` 中创建 Skill 骨架，建立 symlink，验证状态
3. **push** -- 展示完整 git 命令（`git add`/`commit`/`push`）+ 用户确认后执行
4. **pull** -- 展示完整 git 命令（`git pull --rebase`）+ 用户确认后执行 + 重建 symlink + 检测异常
5. **fix** -- 验证所有 symlink 是否完整，自动修复断裂链接，检测断链/缺失/孤儿 skill
6. **list** -- 列出所有自定义 Skill
7. **status** -- 显示 git 状态 + skill 管理状态（已管理/孤儿/外部）+ 断链检测
8. **search** -- 全文搜索自定义 Skill
9. **info** -- 显示 Skill 详情（含外部/自定义分类）
10. **remove** -- 彻底删除 Skill（git 仓库中的文件 + 所有 symlink）
11. **uninstall** -- 卸载 Skill（还原文件到统一 Skill 目录，保留数据）

---

## 对比其他方案 / Comparison

### vs 软链接（手动 Symlinks）

| | 手动 Symlink | sync-skills v1.0 |
|---|---|---|
| **版本控制** | 无，换设备就丢失 | git 仓库，天然支持版本管理和多设备同步 |
| **新建 Skill** | 手动创建目录、写文件、建 N 条链接 | `sync-skills add` 一条命令完成 |
| **删除 Skill** | 手动删文件、清除断链 | `sync-skills remove` 自动清理 |
| **卸载 Skill** | 手动还原文件、删除链接 | `sync-skills uninstall` 还原文件到统一 Skill 目录 |
| **多设备同步** | 不支持 | `push` / `pull` 一键同步 |
| **维护成本** | 每次变更手动操作 | 自动化，零维护 |

### vs v0.6 复制模式

| | v0.6 复制模式 | v1.0 git + symlink |
|---|---|---|
| **存储** | 复制 N 份真实文件 | symlink，零拷贝 |
| **版本管理** | 不支持 | git 原生支持 |
| **一致性** | 依赖同步执行 | symlink 保证实时一致 |
| **外部 Skill** | 可能被覆盖 | 自动识别，不触碰 |
| **磁盘占用** | N 倍（N = 工具数） | 1 倍 |

---

## 参数 / Options

### v1.0 命令

| 命令 | 说明 |
|------|------|
| `sync-skills init` | 初始化 ~/Skills/ 仓库，迁移已有 Skill |
| `sync-skills add <name>` | 创建新的自定义 Skill |
| `sync-skills push [-m MSG]` | git commit + push（展示完整 git 命令，确认后执行） |
| `sync-skills pull` | git pull（展示完整 git 命令，确认后执行）+ 重建 symlinks |
| `sync-skills fix` | 验证/修复 symlink + 检测断链/缺失/孤儿 skill |
| `sync-skills list [--tags TAG]` | 列出所有自定义 Skill |
| `sync-skills status` | 显示 git 状态 + skill 管理状态 + 断链检测 |
| `sync-skills search <query>` | 搜索自定义 Skill |
| `sync-skills info <name>` | 显示 Skill 详情（含外部/自定义分类） |
| `sync-skills remove <name>` | 彻底删除自定义 Skill（-y 跳过确认） |
| `sync-skills uninstall [name]` | 卸载自定义 Skill，还原文件（省略 name 则卸载全部，-y 跳过确认） |

### 通用选项

| 参数 | 说明 |
|------|------|
| `-y`, `--yes` | 跳过交互确认 |
| `--config PATH` | 配置文件路径（默认 `~/.config/sync-skills/config.toml`） |

### 遗留命令（--copy 模式）

| 命令 | 说明 |
|------|------|
| `sync-skills --copy` | v0.6 双向复制同步 |
| `sync-skills --copy --force` | v0.6 强制同步 |
| `sync-skills --copy --delete <name>` | v0.6 删除 Skill |
| `sync-skills --copy --dry-run` | v0.6 预览模式 |

### 默认目录 / Default Directories

| 角色 | 路径 |
|------|------|
| 自定义 Skill 仓库 | `~/Skills` |
| 统一 Skill 目录 | `~/.agents/skills` |
| Claude Code | `~/.claude/skills` |
| Codex CLI | `~/.codex/skills` |
| Gemini CLI | `~/.gemini/skills` |

---

## 配置文件 / Config

配置文件保存在 `~/.config/sync-skills/config.toml`：

```toml
repo = "~/Skills"
agents_dir = "~/.agents/skills"

[external]
global_lock = "~/.agents/.skill-lock.json"
local_lock = "~/skills-lock.json"
```

- `repo` -- 自定义 Skill 的 git 仓库路径
- `agents_dir` -- 统一 Skill 目录路径
- `external.global_lock` -- 外部 Skill 的全局锁文件（npx skills 使用）
- `external.local_lock` -- 外部 Skill 的本地锁文件

---

## 安全机制 / Safety

- **外部 Skill 隔离** -- 通过 lock 文件自动识别外部 Skill，所有 symlink 操作跳过外部 Skill，永不触碰
- **Git 命令预览** -- `push` 和 `pull` 执行前展示完整 git 命令，用户确认后才执行
- **操作前后验证** -- `add`/`remove`/`uninstall` 后自动验证状态；`pull` 前检查状态，有异常则警告
- **Symlink 验证** -- `fix` 检查所有 symlink，修复断裂链接
- **断链检测** -- `fix` 和 `status` 自动检测远程删除导致的断链 symlink，提示用户清理
- **缺失检测** -- `fix` 自动检测缺少统一 Skill 目录 symlink 的自定义 skill，提示用户创建
- **孤儿检测** -- `fix` 自动检测未被管理的孤儿 skill，提示用户纳入管理
- **Git 保障** -- 所有自定义 Skill 变更都经过 git 版本控制，可随时回滚
- **存量仓库保护** -- `init` 时检查 git 状态，有未提交更改或落后远程时停下来让用户处理
- **隐藏目录过滤** -- 自动跳过 `.system/` 等隐藏目录

---

## 开发 / Development

```bash
uv run pytest tests/ -v    # 运行测试（186 个用例）
```

## License

MIT

---

# sync-skills

> Custom Skill Lifecycle Manager -- manage your AI skills via git + symlink.

sync-skills v1.0 uses a two-type architecture: **External Skills** (managed by `npx skills`) and **Custom Skills** (managed by sync-skills via git + symlink). sync-skills only manages user-created skills and never touches external skills.

## Why

AI coding agents (Claude Code, Codex CLI, Gemini CLI, etc.) each maintain their own skills directory. Community skills installed via `npx skills` are managed by the tooling, but user-created skills lack a unified management solution:

- **Scattered** -- Custom skills are spread across tool directories with no central management
- **No version control** -- Switch machines and your custom skills are gone
- **No organization** -- Flat tool directories aren't suitable for direct git management

sync-skills solves this with **git + symlink**:

```
~/Skills/skills/             <-- Custom Skill repo (git repo, single source of truth)
├── english-buddy/
│   └── SKILL.md
└── git-commit/
    └── SKILL.md

~/.agents/skills/            <-- Unified Skill directory (all agents read from here)
├── docx/                    <-- External skill (real file, managed by npx skills)
├── english-buddy/           --> ~/Skills/skills/english-buddy/  (symlink)
└── git-commit/              --> ~/Skills/skills/git-commit/     (symlink)

~/.claude/skills/xxx  --> ~/.agents/skills/xxx  (Agent Skill directory symlinks)
```

- **External skills** (e.g., docx) are managed by `npx skills` -- sync-skills leaves them alone
- **Custom skills** live in the `~/Skills/` git repo, linked into the unified Skill directory via symlinks
- **Unified Skill directory** `~/.agents/skills/` is the unified read entry point for all agents
- **Version control** -- All custom skills are in a git repo, naturally supporting versioning and multi-device sync
- **Zero-copy** -- Symlinks take no extra space; changes take effect immediately

## Agent-Friendly Design

### Built-in Skill

The project ships with `skills/sync-skills/SKILL.md` that can be installed as a skill in any AI coding tool. Once installed, agents can operate sync-skills via natural language:

```
User: "sync skills"              --> Agent runs: sync-skills push -y
User: "pull remote updates"      --> Agent runs: sync-skills pull -y
User: "create a new skill"       --> Agent runs: sync-skills add my-skill
User: "show me the skills"       --> Agent runs: sync-skills list
User: "check code-review"        --> Agent runs: sync-skills info code-review
```

### Agent-Friendly CLI

- **`--help`** outputs structured English text with full examples, easy for agents to parse
- **`-y`** skips interactive confirmation: agents can't interact with stdin, `-y` ensures non-blocking execution
- **`list` / `search` / `info`**: structured output for agents to query skill status
- **`status`**: shows git status + skill management state for comprehensive understanding

## Quick Start

```bash
# Recommended: install from PyPI
uv tool install sync-skills

# Or install from source
git clone https://github.com/LuShan123888/sync-skills.git
cd sync-skills
pip install -e .
```

Requires Python >= 3.11.

```bash
sync-skills init    # Initialize ~/Skills/ repo, migrate existing skills, create symlinks
```

## Usage

```bash
# Initialize
sync-skills init

# Create a new custom skill
sync-skills add my-skill

# Git commit + push (shows full git commands before confirming)
sync-skills push

# Git pull (shows full git commands before confirming) + rebuild symlinks
sync-skills pull

# Verify/repair + detect broken/missing/orphan skills
sync-skills fix

# List custom skills
sync-skills list

# Show git status + skill management state
sync-skills status

# Search
sync-skills search "review"

# Show details (with external/custom classification)
sync-skills info skill-name

# Remove a custom skill permanently
sync-skills remove my-skill

# Uninstall a custom skill (restore files to unified directory)
sync-skills uninstall my-skill

# Uninstall all custom skills
sync-skills uninstall -y
```

## Architecture

### Two-Type Skill Architecture

| Type | Source | Storage | Manager |
|------|--------|---------|---------|
| External | `npx skills install` | Real files in `~/.agents/skills/` | npx skills |
| Custom | User-created | Git repo `~/Skills/skills/` | sync-skills |

### Workflow

1. **init** -- Initialize `~/Skills/` git repo, scan and migrate existing custom skills, create symlink chains
2. **add** -- Create skill skeleton in `~/Skills/skills/`, create symlinks, verify state
3. **push** -- Show full git commands (`git add`/`commit`/`push`) + confirm + execute
4. **pull** -- Show full git command (`git pull --rebase`) + confirm + execute + rebuild symlinks + detect issues
5. **fix** -- Verify all symlinks, auto-repair broken links, detect broken/missing/orphan skills
6. **list** -- List all custom skills
7. **status** -- Show git status + skill management state (managed/orphan/external) + broken symlink detection
8. **search** -- Full-text search custom skills
9. **info** -- Show skill details (with external/custom classification)
10. **remove** -- Permanently delete skill (files in git repo + all symlinks)
11. **uninstall** -- Uninstall skill (restore files to unified Skill directory, preserve data)

## Comparison

### vs Manual Symlinks

| | Manual Symlinks | sync-skills v1.0 |
|---|---|---|
| **Version control** | None; lost on device switch | Git repo; natural versioning and multi-device sync |
| **New skill** | Manual: create dir, write file, create N symlinks | `sync-skills add` does it all |
| **Deletion** | Manual: delete files, clean broken links | `sync-skills remove` auto-cleans |
| **Uninstall** | Manual: restore files, delete links | `sync-skills uninstall` restores to unified directory |
| **Multi-device sync** | Not supported | `push` / `pull` one command |
| **Maintenance** | Manual for every change | Automated, zero maintenance |

### vs v0.6 Copy Mode

| | v0.6 Copy Mode | v1.0 git + symlink |
|---|---|---|
| **Storage** | N copies of real files | Symlinks, zero-copy |
| **Version control** | Not supported | Native git support |
| **Consistency** | Depends on sync execution | Symlinks guarantee real-time consistency |
| **External skills** | May be overwritten | Auto-detected, never touched |
| **Disk usage** | N times (N = number of tools) | 1 time |

## Options

### v1.0 Commands

| Command | Description |
|---------|-------------|
| `sync-skills init` | Initialize ~/Skills/ repo, migrate existing skills |
| `sync-skills add <name>` | Create a new custom skill |
| `sync-skills push [-m MSG]` | Git commit + push (shows full git commands, confirm before executing) |
| `sync-skills pull` | Git pull (shows full git command, confirm before executing) + rebuild symlinks |
| `sync-skills fix` | Verify/repair symlinks + detect broken/missing/orphan skills |
| `sync-skills list [--tags TAG]` | List all custom skills |
| `sync-skills status` | Show git status + skill management state + broken link detection |
| `sync-skills search <query>` | Search custom skills |
| `sync-skills info <name>` | Show skill details (with external/custom classification) |
| `sync-skills remove <name>` | Permanently remove a custom skill (-y to skip confirmation) |
| `sync-skills uninstall [name]` | Uninstall custom skill, restore files (omit name to uninstall all, -y to skip confirmation) |

### General Options

| Flag | Description |
|------|-------------|
| `-y`, `--yes` | Skip confirmation |
| `--config PATH` | Config file path (default: `~/.config/sync-skills/config.toml`) |

### Legacy Commands (--copy mode)

| Command | Description |
|---------|-------------|
| `sync-skills --copy` | v0.6 bidirectional copy sync |
| `sync-skills --copy --force` | v0.6 force sync |
| `sync-skills --copy --delete <name>` | v0.6 delete skill |
| `sync-skills --copy --dry-run` | v0.6 preview mode |

### Default Directories

| Role | Path |
|------|------|
| Custom Skill repo | `~/Skills` |
| Unified Skill directory | `~/.agents/skills` |
| Claude Code | `~/.claude/skills` |
| Codex CLI | `~/.codex/skills` |
| Gemini CLI | `~/.gemini/skills` |

## Config

Config file at `~/.config/sync-skills/config.toml`:

```toml
repo = "~/Skills"
agents_dir = "~/.agents/skills"

[external]
global_lock = "~/.agents/.skill-lock.json"
local_lock = "~/skills-lock.json"
```

- `repo` -- Git repo path for custom skills
- `agents_dir` -- Unified Skill directory path
- `external.global_lock` -- Global lock file for external skills (used by npx skills)
- `external.local_lock` -- Local lock file for external skills

## Safety

- **External skill isolation** -- Auto-detects external skills via lock files, all symlink operations skip them, never touches or overwrites
- **Git command preview** -- `push` and `pull` show full git commands before executing, user confirms first
- **Pre/post-operation verification** -- Auto-verify state after `add`/`remove`/`uninstall`; check state before `pull`
- **Symlink verification** -- `fix` checks all symlinks, repairs broken links
- **Broken link detection** -- `fix` and `status` detect broken symlinks caused by remote deletions, prompt user to clean up
- **Missing link detection** -- `fix` detects custom skills missing unified Skill directory symlinks, prompt user to create
- **Orphan detection** -- `fix` detects unmanaged orphan skills, prompt user to adopt
- **Git safety net** -- All custom skill changes go through git version control, rollback anytime
- **Existing repo protection** -- `init` checks git status, stops if there are uncommitted changes or behind remote
- **Hidden directory filtering** -- Automatically skips `.system/` etc.

## Development

```bash
uv run pytest tests/ -v    # 186 test cases
```

## License

MIT
