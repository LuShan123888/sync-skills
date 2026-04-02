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
git clone https://github.com/LuShan123888/sync-skills.git
cd sync-skills
uv sync
```

> 要求 Python >= 3.14

### 使用 / Usage

```bash
# 双向同步：收集各工具的新 skill → 分发到所有工具
# Bidirectional: collect new skills from tools → distribute to all
sync-skills

# 强制同步：以源目录为准，删除目标中多余的 skill
# Force: source is truth, remove extras from targets
sync-skills --force

# 删除指定 skill：从源目录和所有目标目录中删除
# Delete a skill: remove from source and all targets
sync-skills --delete skill-name

# 跳过确认 / Skip confirmation
sync-skills -y

# 自定义目录 / Custom directories
sync-skills --source ~/my-skills --targets ~/.claude/skills,~/.codex/skills
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
| `--delete NAME`, `-d NAME` | 删除指定 skill（从源目录和所有目标目录） |
| `-y`, `--yes` | 跳过确认提示 |
| `--source DIR` | 源目录路径（默认 `~/Skills`） |
| `--targets DIR1,DIR2` | 目标目录，逗号分隔 |

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

- **预览确认** — 所有操作先展示变更清单，确认后才执行
- **重名检测** — 不同分类下存在同名 skill 时，直接报错退出
- **同步验证** — 执行后自动验证各目录的内容哈希是否一致
- **内容感知** — 基于 MD5 哈希比较，内容相同的 skill 不会重复覆盖
- **隐藏目录过滤** — 自动跳过 `.system/` 等隐藏目录
- **无变更跳过** — 已同步的目录不执行任何操作

---

## 开发 / Development

```bash
uv run pytest tests/ -v    # 运行测试（59 个用例）
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
git clone https://github.com/LuShan123888/sync-skills.git
cd sync-skills
uv sync
```

Requires Python >= 3.14.

## Usage

```bash
# Bidirectional sync (default): collect + distribute
sync-skills

# Force sync: source is the single source of truth
sync-skills --force

# Delete a skill: remove from source and all targets
sync-skills --delete skill-name

# Skip confirmation
sync-skills -y

# Custom directories
sync-skills --source ~/my-skills --targets ~/.claude/skills,~/.codex/skills
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
| `--delete NAME`, `-d NAME` | Delete a skill (from source and all targets) |
| `-y`, `--yes` | Skip confirmation |
| `--source DIR` | Source directory (default: `~/Skills`) |
| `--targets DIR1,DIR2` | Target directories, comma-separated |

## Safety

- Preview before execute — shows full diff before any changes
- Duplicate name detection — errors if same skill name exists in multiple categories
- Post-sync verification — confirms content hashes match across all directories
- Content-aware — MD5 hashing, identical skills are skipped
- Hidden directory filtering — automatically skips `.system/` etc.
- No-op skip — unchanged directories are skipped

## Development

```bash
uv run pytest tests/ -v    # 59 test cases
```

## License

MIT