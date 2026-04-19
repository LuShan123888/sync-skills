# sync-skills

> 自定义 Skill 生命周期管理器
> 通过 git + symlink 管理你的 AI Skills。
>
> Custom Skill Lifecycle Manager
> manage your AI skills via git + symlink.

sync-skills v1.1 通过 git + symlink 管理用户自建的 Skill。sync-skills 只管理用户显式纳入的 Skill，其他 Skill（由任何工具管理）不受影响。

---

## 为什么需要它
## Why

AI 编码工具（Claude Code、Codex CLI、Gemini CLI 等）都有自己的 skills 目录。用户自建的 Skill 缺少统一的管理方式：

```
:/  自己写的 skill 分散在各个工具目录里
:/  换台电脑，自定义 skill 全丢了
:/  想版本管理，但工具目录是平铺的，不适合直接 git 管理
```

sync-skills 的做法 -- **git + symlink**：

```
~/Skills/skills/             <-- 自定义 Skill 仓库（git 仓库，唯一真实来源）
├── english-buddy/
│   └── SKILL.md
└── git-commit/
    └── SKILL.md

~/.agents/skills/            <-- Agent Skill 目录（与 .claude/skills 同等地位）
├── english-buddy/           --> ~/Skills/skills/english-buddy/  (symlink)
└── git-commit/              --> ~/Skills/skills/git-commit/     (symlink)

~/.claude/skills/            <-- Agent Skill 目录
├── english-buddy/           --> ~/Skills/skills/english-buddy/  (symlink)
└── git-commit/              --> ~/Skills/skills/git-commit/     (symlink)
```

- **自定义 Skill** 存放在 `~/Skills/` git 仓库中，通过 symlink 关联到所有 Agent 目录
- **版本控制** -- 自定义 Skill 全部在 git 仓库中，天然支持版本管理、多设备同步
- **零拷贝** -- symlink 不占额外空间，修改即刻生效

---

## AI Agent 友好
## Agent-Friendly Design

sync-skills 专为 AI 编码工具设计，支持两种 Agent 集成方式：

### 内置 Skill

项目附带一个 `skills/sync-skills/SKILL.md`，可作为 skill 安装到任意 AI 编码工具中。安装后，Agent 可以根据自然语言直接操作：

```
用户: "同步一下 skills"       --> Agent 执行: sync-skills push -y
用户: "拉取远程更新"          --> Agent 执行: sync-skills pull -y
用户: "新建一个 skill"        --> Agent 执行: sync-skills new my-skill
用户: "看看有什么 skill"      --> Agent 执行: sync-skills list
```

### Agent 友好的 CLI

- **`--help`** 输出结构化英文文本，包含完整示例，便于 Agent 解析
- **`-y`** 跳过交互确认：Agent 无法操作 stdin，`-y` 确保非阻塞执行
- **`list`**：结构化输出，便于 Agent 查询 skill 状态
- **`status`**：显示 git 状态 + skill 管理状态，便于 Agent 全面了解

---

## 快速开始
## Quick Start

### 安装
### Install

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
### Init

```bash
sync-skills init    # 初始化 ~/Skills/ 仓库（支持 git clone 远程仓库，可重复执行）
```

配置文件保存在 `~/.config/sync-skills/config.toml`，也可以手动编辑。

### 使用
### Usage

```bash
# 初始化
# Initialize
sync-skills init

# 纳入管理
# Link a skill (auto-scan by name)
sync-skills link my-skill

# 提交并推送（展示完整 git 命令）
# Git commit + push (shows full git commands)
sync-skills push

# 仅提交（展示变更 skill、时间、最近 commit）
# Git commit only
sync-skills commit

# 拉取远程更新（展示完整 git 命令）
# Git pull (shows full git commands)
sync-skills pull

# 验证/修复 symlink + 检测异常
# Verify/repair + detect anomalies
sync-skills doctor

# 列出自定义 Skill
# List custom skills
sync-skills list

# 查看 git 状态 + skill 管理状态
# Show git status and skill management state
sync-skills status

# 创建新 Skill（手动创建骨架）/ Create a new custom skill (from template)
sync-skills new my-skill

# 删除 Skill（彻底删除）/ Remove a custom skill permanently
sync-skills remove my-skill

# 卸载 Skill（移除管理，还原文件）/ Unlink a custom skill (restore files)
sync-skills unlink my-skill
```

---

## 架构
## Architecture

### 目录结构

```
~/Skills/                    # 自定义 Skill 仓库（git 仓库，唯一真实存储）
├── skills/
│   ├── english-buddy/
│   │   └── SKILL.md
│   └── git-commit/
│       └── SKILL.md
└── .git/

~/.agents/skills/            # Agent Skill 目录（与 .claude/skills 同等地位）
├── english-buddy/           # --> ~/Skills/skills/english-buddy/  (symlink)
└── git-commit/              # --> ~/Skills/skills/git-commit/     (symlink)

~/.claude/skills/            # Agent Skill 目录
├── english-buddy/           # --> ~/Skills/skills/english-buddy/  (symlink)
└── git-commit/              # --> ~/Skills/skills/git-commit/     (symlink)
```

### 工作流
### Workflow

1. **init** -- 初始化 `~/Skills/` git 仓库（可选 git clone 远程仓库），自动注册所有 repo 中的 skill，建立/修复 symlink
2. **link** -- 按名称自动扫描 Skill（复制到 git 仓库 + 删除其他副本 + 创建 symlink），多版本时 MD5 分组 + mtime 排序让用户选择
3. **commit** -- 展示变更 skill、修改时间、最近 commit，以及 `git add`/`commit` 预览，确认后执行
4. **push** -- 展示完整 git 命令（`git add`/`commit`/`push`）+ 用户确认后执行
5. **pull** -- 展示完整 git 命令（`git pull --rebase`）+ 用户确认后执行 + 修复 symlink
6. **doctor** -- 验证所有 symlink，自动修复断裂链接，检测状态不一致
7. **list** -- 列出所有自定义 Skill
8. **status** -- 显示 git 状态 + skill 管理状态 + 断链检测
9. **new** -- 在 `~/Skills/skills/` 中创建 Skill 骨架，建立 symlink
10. **remove** -- 彻底删除 Skill（git 仓库中的文件 + 所有 symlink）
11. **unlink** -- 移除 Skill 管理（还原文件到所有 Agent 目录，保留数据）

---

## 对比其他方案
## Comparison

### vs 软链接（手动 Symlinks）

| | 手动 Symlink | sync-skills v1.1 |
|---|---|---|
| **版本控制** | 无，换设备就丢失 | git 仓库，天然支持版本管理和多设备同步 |
| **新建 Skill** | 手动创建目录、写文件、建 N 条链接 | `sync-skills new` 一条命令完成 |
| **删除 Skill** | 手动删文件、清除断链 | `sync-skills remove` 自动清理 |
| **卸载 Skill** | 手动还原文件、删除链接 | `sync-skills unlink` 还原文件到所有 Agent 目录 |
| **多设备同步** | 不支持 | `push` / `pull` 一键同步 |
| **维护成本** | 每次变更手动操作 | 自动化，零维护 |

### vs v0.6 复制模式

| | v0.6 复制模式 | v1.1 git + symlink |
|---|---|---|
| **存储** | 复制 N 份真实文件 | symlink，零拷贝 |
| **版本管理** | 不支持 | git 原生支持 |
| **一致性** | 依赖同步执行 | symlink 保证实时一致 |
| **磁盘占用** | N 倍（N = 工具数） | 1 倍 |

---

## 参数
## Options

### v1.1 命令

| 命令 | 说明 |
|------|------|
| `sync-skills init` | 初始化 ~/Skills/ 仓库（可重复执行；有远程仓库时自动 clone 并注册所有 skill） |
| `sync-skills link <name>` | 纳入 Skill（按名称自动扫描，多版本时让用户选择，-y 跳过确认） |
| `sync-skills commit [-m MSG]` | git add + commit（预览变更 skill、时间、最近 commit，确认后执行） |
| `sync-skills push [-m MSG]` | git commit + push（展示完整 git 命令，确认后执行） |
| `sync-skills pull` | git pull（展示完整 git 命令，确认后执行）+ 修复 symlinks |
| `sync-skills doctor` | 验证/修复 symlink + 检测状态不一致 |
| `sync-skills list [--tags TAG]` | 列出所有自定义 Skill |
| `sync-skills status` | 显示 git 状态 + skill 管理状态 + 断链检测 |
| `sync-skills new <name>` | 创建新的自定义 Skill（手动创建骨架，-d/-t 参数） |
| `sync-skills remove <name>` | 彻底删除自定义 Skill（-y 跳过确认，支持多个） |
| `sync-skills unlink [name]` | 移除 Skill 管理，还原文件（省略 name 或 --all 则移除全部，-y 跳过确认） |

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
| `sync-skills --copy --delete <name>` | v0.6 删除 Skill |
| `sync-skills --copy --dry-run` | v0.6 预览模式 |

### 兼容别名

| 别名 | 等效命令 |
|------|----------|
| `sync-skills fix` | `sync-skills doctor` |
| `sync-skills sync` | `sync-skills doctor` |

### 默认目录
### Default Directories

| 角色 | 路径 |
|------|------|
| 自定义 Skill 仓库 | `~/Skills` |
| Agent Skill 目录 | `~/.agents/skills` |
| Claude Code | `~/.claude/skills` |
| Codex CLI | `~/.codex/skills` |
| Gemini CLI | `~/.gemini/skills` |

---

## 配置文件
## Config

配置文件保存在 `~/.config/sync-skills/config.toml`：

```toml
repo = "~/Skills"
agents_dir = "~/.agents/skills"
state_file = "~/.config/sync-skills/skills.json"
```

- `repo` -- 自定义 Skill 的 git 仓库路径
- `agents_dir` -- 保留字段（向后兼容）
- `state_file` -- 状态文件路径（记录已管理的 skill）

---

## 安全机制
## Safety

- **Git 命令预览** -- `push` 和 `pull` 执行前展示完整 git 命令，用户确认后才执行
- **操作前后验证** -- `new`/`remove`/`unlink` 后自动验证状态；`pull` 前检查状态，有异常则警告
- **Symlink 验证** -- `doctor` 检查所有 symlink，修复断裂链接
- **断链检测** -- `doctor` 和 `status` 自动检测断链 symlink，提示用户清理
- **状态一致性** -- `doctor` 自动检测状态文件与实际状态的不一致
- **Git 保障** -- 所有自定义 Skill 变更都经过 git 版本控制，可随时回滚
- **存量仓库保护** -- `init` 时检查 git 状态，有未提交更改或落后远程时停下来让用户处理
- **隐藏目录过滤** -- 自动跳过 `.system/` 等隐藏目录

---

## 开发
## Development

```bash
uv run pytest tests/ -v    # 运行测试（204 个用例）
```

## License

MIT
