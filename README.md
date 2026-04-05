# sync-skills

> 一条命令，将你的 AI Skills 同步到所有编码工具。
>
> One command to sync your AI skills across all coding tools.

Claude Code、Codex CLI、Gemini CLI、OpenClaw……每个工具都有自己的 skills 目录，互不相通。**sync-skills** 让你在本地维护一份带分类的 skills 总目录，自动分发到所有工具。

---

## 为什么需要它 / Why

你可能遇到过这些问题：

```
😖 在 Claude Code 里写了个 skill，Codex 和 Gemini 里没有
😖 想给 skills 分类整理，但工具只支持平铺目录
😖 改了一个 skill，要手动复制到 4 个目录
```

sync-skills 的做法：

```
~/Skills/  (你的分类总目录)              各工具的 skills 目录 (平铺，自动同步)
├── Code/                               ┌─ ~/.claude/skills/
│   ├── code-review/                    ├─ ~/.codex/skills/
│   ├── git-commit/                     ├─ ~/.gemini/skills/
│   └── refactor/                       └─ ~/.openclaw/skills/
├── Writing/                                 │
│   └── blog-post/               ──────►    ├── code-review/
└── DevOps/                      sync       ├── git-commit/
    └── docker-deploy/           ◄──────    ├── refactor/
                                             ├── blog-post/
                                             └── docker-deploy/
```

- **分类管理** — 源目录支持任意层级的嵌套目录
- **双向同步** — 在任何工具中新建的 skill 自动回收到总目录
- **一键分发** — 一条命令同步到所有工具，无需手动操作

---

## AI Agent 友好 / Agent-Friendly Design

sync-skills 专为 AI 编码工具设计，支持两种 Agent 集成方式：

### 内置 Skill

项目附带一个 `skills/sync-skills/SKILL.md`，可作为 skill 安装到任意 AI 编码工具中。安装后，Agent 可以根据自然语言直接操作：

```
用户: "同步一下 skills"       → Agent 执行: sync-skills -y
用户: "强制同步"              → Agent 执行: sync-skills --force -y
用户: "看看有什么变化"        → Agent 执行: sync-skills --dry-run
用户: "删掉 code-review"      → Agent 执行: sync-skills --delete code-review -y
```

### Agent 友好的 CLI

- **`--help`** 输出结构化英文文本，包含完整示例，便于 Agent 解析
- **`--dry-run`** 预览模式：Agent 可先检查影响再决定是否执行
- **`-y`** 跳过交互确认：Agent 无法操作 stdin，`-y` 确保非阻塞执行
- **`--dry-run` + `--delete`**：安全预览删除范围
- **`list` / `search` / `info`**：结构化输出，便于 Agent 查询 skill 状态

---

## 对比其他方案 / Comparison

### vs 手动复制

每次新增或修改 skill 后，需要手动复制到 N 个目录。skill 数量多了之后极易遗漏。

### vs 软链接（Symlinks）

| | 软链接 | sync-skills |
|---|---|---|
| **工具兼容性** | OpenClaw 等工具不支持软链接 | 复制真实文件，所有工具兼容 |
| **新建 skill** | 在工具中创建后，需手动移动原文件、为每个工具建链接 | 自动收集回总目录，自动分发 |
| **删除 skill** | 留下断链，需手动清理 | `--force` 自动清理 |
| **分类组织** | 软链接仍是平铺，无法分类 | 源目录支持任意嵌套分类 |
| **每个 skill 的成本** | 需创建 N 条链接（N = 工具数） | 零成本，运行一次全部搞定 |

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

### 初始化配置 / Init Config

```bash
sync-skills init    # 交互式配置向导，自动检测已安装工具
```

配置文件保存在 `~/.config/sync-skills/config.toml`，也可以手动编辑。

### 使用 / Usage

```bash
# 双向同步：收集各工具的新 skill → 分发到所有工具
# Bidirectional: collect new skills from tools → distribute to all
sync-skills

# 强制同步：以源目录为准，删除目标中多余的 skill
# Force: source is truth, remove extras from targets
sync-skills --force

# 预览变更：显示计划但不执行
# Preview: show plan without executing
sync-skills --dry-run

# 删除指定 skill：从源目录和所有目标目录中删除
# Delete a skill: remove from source and all targets
sync-skills --delete skill-name

# 跳过确认 / Skip confirmation
sync-skills -y

# 自定义目录 / Custom directories
sync-skills --source ~/my-skills --targets ~/.claude/skills,~/.codex/skills

# 查询 skills
sync-skills list                     # 列出所有 skills（按分类分组）
sync-skills list --tags code         # 按标签过滤
sync-skills search "review"          # 全文搜索
sync-skills info skill-name         # 查看 skill 详情
```

所有操作执行前都会展示预览，确认后才执行。

---

## 同步模式 / Sync Modes

### 双向同步（默认） / Bidirectional (default)

1. **收集**：扫描各工具目录，将新增或更新的 skill 回收到 `~/Skills/Other/`
2. **分发**：将源目录中的所有 skill 同步到每个工具目录

适合日常使用。在任意工具中创建的 skill 会被自动收集并分发到其他工具。

### 强制同步 / Force (`--force`)

默认以源目录为基准。也支持交互式选择任意目录为基准同步到其他目录（不带 `-y` 时会先展示概览，然后让用户选择）。

补齐缺少的，覆盖内容不同的（基于 MD5 哈希比较），删除多余的。内容完全一致的自动跳过。

当源目录被选为目标时，保留其嵌套分类结构：新增的 skill 放到 `Other/`，删除在嵌套结构中定位。

适合删除或重组 skill 后使用。

---

## 参数 / Options

| 参数 | 说明 |
|------|------|
| `--force`, `-f` | 强制同步（可选择任意目录为基准，覆盖内容不同的，删除多余的） |
| `--dry-run` | 预览模式：显示变更计划但不执行 |
| `--delete NAME`, `-d NAME` | 删除指定 skill（从源目录和所有目标目录） |
| `-y`, `--yes` | 跳过确认提示 |
| `--source DIR` | 源目录路径（默认 `~/Skills`，覆盖配置文件） |
| `--targets DIR1,DIR2` | 目标目录，逗号分隔（覆盖配置文件） |
| `--config PATH` | 配置文件路径（默认 `~/.config/sync-skills/config.toml`） |
| `--tags TAG1,TAG2` | 按标签过滤（用于 `list` 命令） |
| `init` | 交互式初始化配置 |

### 默认目录 / Default Directories

| 角色 | 路径 |
|------|------|
| 源目录（分类结构） | `~/Skills` |
| Claude Code | `~/.claude/skills` |
| Codex CLI | `~/.codex/skills` |
| Gemini CLI | `~/.gemini/skills` |
| OpenClaw | `~/.openclaw/skills` |

---

## 安全机制 / Safety

- **预览确认** — 所有操作先展示变更清单，确认后才执行；`--dry-run` 可仅预览不执行
- **重名检测** — 不同分类下存在同名 skill 时，直接报错退出
- **同步验证** — 执行后自动验证各目录的内容哈希是否一致
- **内容感知** — 基于 MD5 哈希比较，内容相同的 skill 不会重复覆盖
- **隐藏目录过滤** — 自动跳过 `.system/` 等隐藏目录
- **无变更跳过** — 已同步的目录不执行任何操作

---

## 开发 / Development

```bash
uv run pytest tests/ -v    # 运行测试（162 个用例）
```

## License

MIT

---

# sync-skills

> One command to sync your AI skills across all coding tools.

AI coding agents (Claude Code, Codex CLI, Gemini CLI, OpenClaw, etc.) each maintain their own isolated, flat skills directory. **sync-skills** lets you maintain a single, organized skills repository with nested categories, and automatically distributes skills to every tool.

## Why

- **Fragmented storage** — Create a skill in Claude Code, and it doesn't exist in Codex or Gemini. You end up manually copying between directories.
- **No organization** — Tools only support flat directories. With dozens of skills, there's no way to categorize.
- **Sync headache** — Edit a skill in one tool, and every other tool has the stale version.

## Agent-Friendly Design

sync-skills is designed for AI coding agents with two integration approaches:

### Built-in Skill

The project ships with `skills/sync-skills/SKILL.md` that can be installed as a skill in any AI coding tool. Once installed, agents can operate sync-skills via natural language:

```
User: "sync skills"              → Agent runs: sync-skills -y
User: "force sync"               → Agent runs: sync-skills --force -y
User: "check what would change"  → Agent runs: sync-skills --dry-run
User: "delete code-review"       → Agent runs: sync-skills --delete code-review -y
```

### Agent-Friendly CLI

- **`--help`** outputs structured English text with full examples, easy for agents to parse
- **`--dry-run`** preview mode: agents can inspect impact before executing
- **`-y`** skips interactive confirmation: agents can't interact with stdin, `-y` ensures non-blocking execution
- **`--dry-run` + `--delete`**: safely preview deletion scope
- **`list` / `search` / `info`**: structured output for agents to query skill status

### vs Symlinks

Symlinks seem like the obvious solution, but they fall short:

| | Symlinks | sync-skills |
|---|---|---|
| **Compatibility** | Some tools (e.g., OpenClaw) don't follow symlinks | Copies real files — works everywhere |
| **New skills** | Must manually move file + create N symlinks | Auto-collects and distributes |
| **Deletion** | Broken symlinks left behind | `--force` cleans up automatically |
| **Organization** | Still flat | Full nested categories in source |
| **Per-skill cost** | N symlinks per skill | Zero — one command does it all |

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
sync-skills init    # Interactive config wizard, auto-detects installed tools
```

## Usage

```bash
# Bidirectional sync (default): collect + distribute
sync-skills

# Force sync: source is the single source of truth
sync-skills --force

# Preview changes without executing
sync-skills --dry-run

# Delete a skill: remove from source and all targets
sync-skills --delete skill-name

# Skip confirmation
sync-skills -y

# Custom directories
sync-skills --source ~/my-skills --targets ~/.claude/skills,~/.codex/skills

# Query skills
sync-skills list                     # List all skills (grouped by category)
sync-skills list --tags code         # Filter by tags
sync-skills search "review"          # Full-text search
sync-skills info skill-name         # Show skill details
```

## Sync Modes

**Bidirectional (default)**
1. **Collect**: Scans target directories for new/modified skills, copies them to `~/Skills/Other/`
2. **Distribute**: Syncs all skills from source to every target

**Force (`--force`)**
Source directory is the default base. Supports interactive base selection — choose any directory as the base to sync to all others (without `-y`). Uses MD5 content hashing to detect differences; identical skills are skipped. When source is a target, preserves its nested category structure.

## Options

| Flag | Description |
|------|-------------|
| `--force`, `-f` | Force sync (selectable base, content-aware, removes extras) |
| `--dry-run` | Preview mode: show plan without executing |
| `--delete NAME`, `-d NAME` | Delete a skill (from source and all targets) |
| `-y`, `--yes` | Skip confirmation |
| `--source DIR` | Source directory (default: `~/Skills`, overrides config) |
| `--targets DIR1,DIR2` | Target directories, comma-separated (overrides config) |
| `--config PATH` | Config file path (default: `~/.config/sync-skills/config.toml`) |
| `--tags TAG1,TAG2` | Filter by tags (for `list` command) |
| `init` | Interactive init wizard |

## Safety

- Preview before execute — shows full diff before any changes; `--dry-run` for preview-only mode
- Duplicate name detection — errors if same skill name exists in multiple categories
- Post-sync verification — confirms content hashes match across all directories
- Content-aware — MD5 hashing, identical skills are skipped
- Hidden directory filtering — automatically skips `.system/` etc.
- No-op skip — unchanged directories are skipped

## Development

```bash
uv run pytest tests/ -v    # 162 test cases
```

## License

MIT