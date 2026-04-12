# sync-skills 设计规划文档

## 1. 项目定位

sync-skills 是一个 AI 编码工具的 skills 统一管理与同步工具。在本地维护一个中心化的 skills 仓库（支持分类目录），自动将 skills 在各个 AI 编码工具（Claude Code、Codex CLI、Gemini CLI、OpenClaw 等）之间同步。采用去中心化的统一同步模型——扫描所有位置，找到最新版本，从最新位置直接分发到所有其他位置。

### 1.1 目标用户

同时使用多个 AI 编码工具，并且积累了一定数量 skills 的开发者。

### 1.2 核心价值

| 价值 | 说明 |
|------|------|
| 集中备份 | 所有 skills 备份到 `~/Skills/`，按主题分类管理 |
| 分类管理 | 源目录支持嵌套目录结构，按主题归类 |
| 自动同步 | 一条命令完成所有工具的 skills 同步 |
| 双向流动 | 在任意工具中新建或修改的 skill 自动同步到其他位置 |
| 去中心化 | 所有位置地位平等，从最新版本直接分发，无需中转 |

---

## 2. 当前架构（v1.0）

### 2.1 核心概念

v1.0 采用**两类 skill 分管**架构：外部 skill 由 `npx skills` 管理（真实文件），自定义 skill 由 sync-skills 通过 git 仓库 + 软链接管理。

**三层目录结构**：

| 层级 | 路径 | 说明 |
|------|------|------|
| 自定义 Skill 仓库 | `~/Skills/skills/<name>/` | git 仓库中的 skill 源文件（唯一真实来源，Agent 编辑即写入 git） |
| 统一 Skill 目录 | `~/.agents/skills/<name>/` | 所有 Agent 的统一读取入口 |
| Agent Skill 目录 | `~/.<agent>/skills/<name>/` | 各 Agent 的 skills 目录（如 `~/.claude/skills/`） |

```
~/.agents/skills/            ← 统一 Skill 目录（所有 Agent 的读取入口）
├── docx/                  ← 外部 skill（真实文件，npx skills 管理）
├── lark-base/             ← 外部 skill（真实文件，npx skills 管理）
├── english-buddy/         → ~/Skills/skills/english-buddy/  ← 自定义（软链接，sync-skills + git）
└── git-commit/            → ~/Skills/skills/git-commit/     ← 自定义（软链接，sync-skills + git）
```

**软链接链路**：
```
~/Skills/skills/<name>/    ← 自定义 Skill 仓库（git 仓库中的 skill 源文件，Agent 编辑即写入 git）
       ↓ (symlink)
~/.agents/skills/<name>/   ← 统一 Skill 目录（所有 Agent 的默认 skills 目录）
       ↓ (symlink)
<agent-dir>/skills/<name>/ ← Agent Skill 目录（如 ~/.claude/skills/）
```

**关键设计决策（v1.0.0）**：采用两类 skill 分管模型，彻底解决 v0.6 copy 同步模式与 npx skills 的冲突问题。外部 skill（如 docx、lark-base）由 `npx skills` 管理为真实文件，自定义 skill 由 sync-skills 通过 git 仓库 + 两层软链接管理。通过 lock 文件（`~/.agents/.skill-lock.json`、`~/skills-lock.json`）区分两类 skill——不在任何 lock 文件中的 skill 被判定为自定义 skill。

**关键设计决策（v1.0.1）**：强化外部 skill 隔离——所有 symlink 操作（`sync_all_links`、`create_agent_links`、`create_all_links`）接受 `external_skills` 参数，跳过外部 skill；`create_agents_link` 检测并修复旧架构遗留的循环软链接（Skills/skills → agents/skills → Skills/skills）；`remove` 命令增加兜底清理，确保 add→remove→add 循环正常工作。新增 `uninstall` 命令（还原文件到统一 Skill 目录），`status` 增强（显示 skill 管理状态），`sync` 增强（检测断链和缺失的 symlink），`push` 增加（推送前确认分支信息）。

**关键设计决策（v0.6.0）**：采用去中心化的统一同步模型。所有位置（源目录和目标目录）地位平等——sync-skills 扫描所有位置，找到每个 skill 的最新版本，从最新位置直接分发到所有其他位置。源目录只是支持嵌套分类的特殊目标目录，用于备份和分类管理，不再是权威中心。

**关键设计决策（v0.5 及之前）**：源目录支持嵌套分类，目标目录始终是平铺结构（因为各工具只支持平铺）。同步时将分类"展平"——只保留 skill 的最末级目录名。

### 2.2 Skill 识别规则

一个目录被识别为 skill 的条件：**目录下存在 `SKILL.md` 文件**。

这是目前所有 AI 编码工具通用的 skill 标识方式。没有 `SKILL.md` 的目录会被忽略。

### 2.3 同步模式

#### 软链接模式（默认，v1.0）

自定义 skill 通过两层软链接分发到各 Agent 目录：

```
sync-skills fix
  1. 扫描自定义 Skill 仓库（~/Skills/skills/）获取所有自定义 skill
  2. 确保统一 Skill 目录软链接：~/.agents/skills/<name> → ~/Skills/skills/<name>
  3. 确保 Agent Skill 目录软链接：<agent-dir>/skills/<name> → ~/.agents/skills/<name>
  4. 检测并修复断链 symlink（远程删除导致）
  5. 检测并创建缺失的统一 Skill 目录 symlink（远程新增导致）
  6. 检测孤儿 skill（未被管理），提示用户纳入管理
  7. 跳过外部 skill（由 npx skills 管理，sync-skills 不触碰）
```

**为什么用软链接替代文件复制？**
1. **与 npx skills 共存**：外部 skill 是真实文件，自定义 skill 是软链接，互不干扰
2. **编辑即入库**：Agent 在默认目录编辑 skill 时，修改直接写入 git 仓库，无需额外同步
3. **零开销**：无需扫描哈希、比较版本、复制文件
4. **单一真实来源**：git 仓库是唯一真实来源，所有链接都指向它

#### 外部 Skill 隔离机制

sync-skills 通过以下机制确保不触碰外部 skill：

1. **Lock 文件识别**：读取 `~/.agents/.skill-lock.json`（全局）和 `~/skills-lock.json`（本地），合并得到外部 skill 集合
2. **全链路隔离**：所有 symlink 操作（`sync_all_links`、`create_agent_links`、`create_all_links`）接受 `external_skills` 参数，跳过外部 skill
3. **命令级保护**：`add` 拒绝创建与外部 skill 同名的自定义 skill；`remove`/`uninstall` 拒绝操作外部 skill
4. **循环软链接修复**：`create_agents_link` 检测旧架构遗留的循环软链接（Skills/skills → agents/skills），自动翻转方向

#### 旧版 Copy 模式（--copy，兼容 v0.6）

通过 `--copy` flag 启用，保留 v0.6 的双向/强制同步逻辑（提取到 `sync_legacy.py`）：

```
sync-skills --copy           # 双向同步（v0.6 统一模型）
sync-skills --copy --force   # 强制同步
```

适用于不使用 npx skills 的纯 copy 同步场景。

### 2.4 安全机制

1. **预览确认**：所有操作先展示 diff，用户确认后才执行；`--dry-run` 可仅预览不执行
2. **重名检测**：源目录不同分类下存在同名 skill 时，直接报错退出（平铺后会冲突）
3. **执行后验证**：对比各目标目录的 skill 内容哈希是否一致
4. **无变更跳过**：没有差异的目录不执行任何操作

### 2.5 技术选型

- **语言**：Python >= 3.11，src/ 包结构（`src/sync_skills/`，9 个模块）
- **依赖**：PyYAML（frontmatter 解析），其余使用标准库（pathlib, shutil, argparse, tomllib, hashlib）
- **构建**：hatchling，通过 `uv tool install sync-skills` 安装
- **包管理**：uv
- **测试**：pytest，186 个回归测试（4 个测试文件）
- **CI/CD**：GitHub Actions 自动构建发布到 PyPI（版本号自动递增）

---

## 3. 用户场景与预期行为

### 3.1 基本场景

| # | 场景 | 操作 | 预期行为 |
|---|------|------|----------|
| S1 | 源目录新增 skill | 在 `~/Skills/Code/` 下新建 `skill-x/SKILL.md` | 分发到所有目标目录（平铺）；已有 skill 不受影响 |
| S2 | 目标目录新增 skill | 在 `~/.codex/skills/` 下新建 `skill-y/SKILL.md` | 默认模式下先收集到 `~/Skills/Other/skill-y`，再分发到其他目标 |
| S3 | 目标目录修改 skill | 在 `~/.codex/skills/skill-a/SKILL.md` 中修改内容 | 默认模式下检测到目标内容不同 → 收集更新到源目录 → 再分发到其他目标 |
| S4 | 源目录修改 skill | 在 `~/Skills/Code/skill-a/SKILL.md` 中修改内容 | 默认模式下检测到内容不同 → 自动分发源版本到所有目标 |

**S4 补充说明**：默认模式下，当源目录的 skill 内容不同于所有目标时（源是唯一不同的版本），自动识别为最新版本并分发到所有目标，无需用户干预。

### 3.2 冲突场景

| # | 场景 | 操作 | 预期行为 |
|---|------|------|----------|
| S5 | 源目录重名 | `~/Skills/Code/dup/` 和 `~/Skills/Lark/dup/` 同时存在 | 报错退出，提示用户重命名（平铺后会冲突） |
| S6 | 多目标同时修改同一 skill | Codex 改了 `skill-a`，Claude Code 也改了 `skill-a` | 检测到冲突，**跳过自动合并并输出警告**，提示用户手动处理 |
| S6b | 源和目标同时修改同一 skill | 源目录改了 `skill-a`，同时 Codex 也改了 `skill-a` | 检测到冲突，**跳过自动合并并输出警告**，提示用户手动处理 |

### 3.3 删除场景

| # | 场景 | 操作 | 当前行为 | 推荐工作流 |
|---|------|------|----------|------------|
| S7 | 从目标删除 skill | 删除 `~/.codex/skills/skill-x/` | 默认模式下源目录仍有该 skill → 下次同步又被分发回来 | 不推荐从目标侧删除 |
| S8 | 从源目录删除 skill | 删除 `~/Skills/Code/skill-x/` | 默认模式下目标仍有该 skill → 被当作"新增"收集回 `Other/` | **从源目录删除 + `--force` 同步**：force 模式以源为准，会删除目标中多余的 skill |
| S9 | 彻底删除 skill | 要从所有地方删除 `skill-x` | **推荐方式**：使用 `sync-skills --delete skill-x -y` 一键删除；或先删源，再 `--force` 同步 |

**删除策略总结**：
- 删除操作应始终从源目录发起
- **推荐使用 `--delete` 命令**：一条命令删除源目录和所有目标目录中的 skill，自动确认模式使用 `-y`
- 手动删除方式：删除源目录中的 skill，然后使用 `--force` 模式同步，确保所有目标目录也被清理
- 不建议在目标目录侧删除，因为双向模式会重新分发

### 3.4 边界场景

| # | 场景 | 预期行为 |
|---|------|----------|
| S10 | 源目录为空 | 双向模式：仅收集目标中的 skill 到 Other/；force 模式：报错退出 |
| S11 | 目标目录不存在 | 自动创建目标目录，分发所有 skill |
| S12 | 所有目录内容一致 | 输出"无需同步"，不执行任何操作 |
| S13 | 多目标独立性 | target_a 已同步，target_b 缺少 skill → 只对 target_b 执行操作 |

---

## 4. 当前已知限制（v1.0）

### 4.0 v1.0 新增限制

| # | 限制 | 影响 | 备注 |
|---|------|------|------|
| 11 | npx skills 可能覆盖 sync-skills 软链接 | `npx skills install` 或 `npx skills update` 可能将软链接替换为真实文件 | 运行 `sync-skills fix` 可自动修复 |
| 12 | 自定义 skill 判定依赖 lock 文件 | 如果 lock 文件被删除或损坏，外部 skill 可能被误判为自定义 skill | classification.py 同时检查两个 lock 文件降低误判风险 |

### 4.1 设计约束（符合预期，不做调整）

| # | 约束 | 说明 |
|---|------|------|
| 1 | 同名检测基于目录名 | 目录名即唯一标识，不同分类下不能有同名 skill。平铺后会冲突，这是预期行为而非缺陷 |
| 4 | Skill 整目录原子同步 | Skill 是原子单位，目录内所有文件（SKILL.md、脚本、图片等）整体复制/整体替换，不支持部分同步 |
| 7 | 不支持内容级别的合并 | Skill 的描述与脚本高度耦合，只能整体覆盖。部分合并的心智负担和风险都太高 |

### 4.2 已解决（Phase 1）

| # | 限制 | 解决方案 |
|---|------|----------|
| 3 | 目标目录列表硬编码 | 配置文件 `~/.config/sync-skills/config.toml` + `sync-skills init` 交互式引导 + CLI 参数覆盖 |

### 4.3 已解决（Phase 2）

以下限制通过纯哈希冲突检测 + 交互式冲突解决解决：

| # | 限制 | 解决方案 |
|---|------|----------|
| 2 | 变更检测依赖 mtime | 纯哈希分组替代 mtime 分类，mtime 仅作为展示提示 |
| 8 | 双向模式不自动推送源修改 | ✅ 已解决：统一模型中所有位置平等，源修改自动识别为 singleton（唯一不同的版本），自动分发 |
| 9 | 多目标冲突需手动处理 | 交互式冲突选择界面，展示所有版本让用户选 |
| 10 | 删除只能通过 force 模式 | 冲突检测不再影响删除行为；删除仍推荐 `--delete` 或 `--force` |

### 4.4 已解决（Phase 3）

| # | 限制 | 解决方案 |
|---|------|----------|
| 6 | 无 skill 元数据管理 | SKILL.md frontmatter 解析 + list/search/info 命令 + 选择性同步 |

### 4.5 待优化（其他）

| # | 限制 | 影响 | 备注 |
|---|------|------|------|
| 5 | 无增量同步 | 每次全量对比+复制，skill 数量极大时可能较慢 | 结合 Phase 2 的内容哈希，哈希一致则跳过复制 |

---

## 5. 演进规划

### 5.1 Phase 1：PyPI 发布 + 配置化（v0.2）

**目标**：作为标准 Python CLI 工具发布到 PyPI，消除硬编码配置。

#### 5.1.1 PyPI 打包发布

通过 `uv tool install sync-skills` 安装为本地命令行工具，参考 [video-captions](https://github.com/LuShan123888/Video-Captions) 的打包方式。

```bash
# 用户安装
uv tool install sync-skills

# 直接使用
sync-skills          # 双向同步
sync-skills --force  # 强制同步
sync-skills --delete skill-name  # 删除指定 skill
sync-skills --delete skill-name -y  # 删除并跳过确认
```

关键配置项：
- `[build-system]`：使用 hatchling
- `[project.scripts]`：注册 `sync-skills` 入口命令
- `requires-python`：降低到 `>=3.10` 以覆盖更多用户
- 保持零外部依赖的优势

#### 5.1.2 首次启动引导（Init）

首次运行时检测到无配置文件，自动进入交互式引导流程：

```
$ sync-skills

未检测到配置文件，开始初始化引导...

[1/2] 请输入 skills 源目录路径 (默认: ~/Skills):
  → ~/Skills

[2/2] 选择要同步的目标工具:
  [✓] Claude Code   (~/.claude/skills)    ← 检测到已安装
  [✓] Codex CLI     (~/.codex/skills)     ← 检测到已安装
  [ ] Gemini CLI    (~/.gemini/skills)
  [✓] OpenClaw      (~/.openclaw/skills)  ← 检测到已安装
  [ ] 自定义路径...

配置已保存到 ~/.config/sync-skills/config.toml
```

引导逻辑：
- **源目录**：提供默认值 `~/Skills`，用户可修改
- **目标目录**：内置常见工具的默认路径（如 `~/.claude/skills`、`~/.codex/skills`），自动检测本机已安装的工具并默认勾选
- **自定义扩展**：支持用户手动添加自定义路径，应对新工具或非标准安装位置
- 后续可随时通过 `sync-skills init` 重新配置，或直接编辑 TOML 文件

#### 5.1.3 配置文件

持久化存储于 `~/.config/sync-skills/config.toml`：

```toml
# 源目录
source = "~/Skills"

# 目标目录列表
[[targets]]
name = "Claude Code"
path = "~/.claude/skills"

[[targets]]
name = "Codex CLI"
path = "~/.codex/skills"

[[targets]]
name = "OpenClaw"
path = "~/.openclaw/skills"

# 用户可随时添加新工具
# [[targets]]
# name = "My Tool"
# path = "~/my-tool/skills"
```

#### 5.1.4 要解决的问题

- [x] 发布到 PyPI，支持 `uv tool install` 一键安装
- [x] `requires-python` 降低到 `>=3.11`（使用 tomllib，零外部依赖）
- [x] 首次启动交互式引导，零配置即可使用
- [x] 自动检测已安装的 AI 编码工具
- [x] 目标目录不再硬编码，用户可自由扩展
- [x] 支持为不同工具命名，预览输出更直观

---

### 5.2 Phase 2：内容感知同步（v0.3）✅ 已完成

**目标**：解决 mtime 不可靠和内容级冲突的问题。

#### 5.2.1 基于内容哈希的变更检测

采用纯哈希分组替代 mtime 归因，不引入 `state.json`（冲突时直接交互解决）：

- 使用 MD5 目录哈希（`skill_dir_hash()`）判断内容一致性
- 按哈希分组所有版本（源 + 目标），自动识别安全场景和冲突场景
- mtime 保留为展示提示，帮助用户判断哪个版本更新

#### 5.2.2 冲突处理

当同一 skill 存在多个不同版本时，提供交互式选择界面：

```
  冲突: 'skill-a' 存在 2 个不同版本

  [0] ★ 建议版本 — 2处一致 (含源)
      哈希: a1b2c3d4  位置: ~/Skills, ~/.codex/skills
      修改: 2026-04-03 15:30:00
      # skill-a
      这是源目录的版本...

  [1] 版本 1 — 1处一致
      哈希: e5f6g7h8  位置: ~/.claude/skills
      修改: 2026-04-03 16:00:00
      # skill-a
      这是 Claude 里的版本...

  [s] 跳过此 skill

  选择要保留的版本 (输入编号, s 跳过):
```

#### 5.2.3 已解决的问题

- [x] 消除 mtime 依赖，纯哈希分组检测变更
- [x] 冲突时给用户明确的选择，交互式选择保留哪个版本
- [x] `-y` 模式兼容，冲突转为 warning（和 v0.2 行为一致）

---

### 5.3 Phase 3：Skill 元数据与索引（v0.4）✅ 已完成

**目标**：在 skills 数量较多时，提供更好的检索和管理能力。

#### 5.3.1 SKILL.md 前置元数据

在 SKILL.md 中支持可选的 frontmatter：

```markdown
---
tags: [code, review, quality]
description: "代码审查工具，对比分支差异生成结构化报告"
tools: [claude-code, codex]  # 仅同步到指定工具（可选）
---

# code-review

...
```

#### 5.3.2 索引与搜索

```bash
sync-skills list                    # 列出所有 skills，按分类分组
sync-skills list --tags code        # 按标签过滤
sync-skills search "review"         # 全文搜索
sync-skills info code-review        # 查看某个 skill 的详细信息
```

#### 5.3.3 选择性同步

通过 `tools` 字段控制某些 skill 只同步到特定工具：

```toml
# config.toml 中也可以设置全局排除
[sync]
exclude_tags = ["experimental", "wip"]
```

#### 5.3.4 要解决的问题

- [x] skills 数量多时快速检索
- [x] 某些 skill 只适用于特定工具，不需要全量同步
- [x] 通过标签实现比目录结构更灵活的分类

---

### 5.4 Phase 4：Skill 化封装（v0.5）✅ 已完成

**目标**：将 sync-skills CLI 工具本身封装为一个 skill，让 AI 编码工具可以代替用户操作。

#### 5.4.1 动机

- CLI 工具是基础层，面向有命令行经验的开发者
- 但很多用户没有命令行基础，更习惯用自然语言交互
- AI 编码工具（Claude Code、Codex 等）天然适合作为中间层，将用户意图翻译为 CLI 命令
- 形成自举闭环：sync-skills 管理所有 skill，其中一个 skill 就是 sync-skills 自身的操作指南

#### 5.4.2 设计思路

创建一个 `sync-skills` skill（包含 `SKILL.md`），描述如何使用 CLI 工具：

```markdown
# sync-skills

Skills 统一管理与同步工具。当用户需要同步、查看、管理 skills 时使用。

## 使用方式

- "同步一下 skills" → `sync-skills`
- "强制同步" → `sync-skills --force -y`
- "查看 skills 状态" → `sync-skills --dry-run`
- ...
```

AI 编码工具读取该 skill 后，即可根据用户的自然语言请求调用对应的 CLI 命令，用户无需了解底层细节。

#### 5.4.3 前置条件

- Phase 1 完成（PyPI 发布，用户已通过 `uv tool install` 安装）
- CLI 命令接口稳定

#### 5.4.4 要解决的问题

- [x] 编写清晰的 SKILL.md，覆盖所有常用操作场景
- [x] 处理交互式确认（skill 中需指导 AI 使用 `-y` 跳过确认，或正确处理 stdin）
- [x] 错误场景的自然语言反馈

---

### 5.5 Phase 5：Git + 软链接管理（v1.0）✅ 已完成

**目标**：重构同步机制，通过 git 仓库 + 软链接实现自定义 skill 的生命周期管理，与 npx skills 共存。

#### 5.5.1 两类 skill 分管

- **外部 skill**：由 `npx skills` 管理，在 `~/.agents/skills/` 中为真实文件
- **自定义 skill**：由 sync-skills 管理，在 `~/Skills/skills/` git 仓库中维护，通过软链接分发

通过 lock 文件（`~/.agents/.skill-lock.json`、`~/skills-lock.json`）区分两类 skill。

#### 5.5.2 两层软链接管理

```
~/Skills/skills/<name>/    ← git 仓库（真实文件，唯一来源）
       ↓ symlink
~/.agents/skills/<name>/   ← 统一 Skill 目录
       ↓ symlink
<agent-dir>/skills/<name>/ ← 各 Agent 目录
```

#### 5.5.3 生命周期命令

```bash
sync-skills add <name>       # 从模板创建新 skill 并链接
sync-skills remove <name>    # 彻底删除 skill（git 仓库文件 + 所有 symlink）
sync-skills uninstall [name] # 卸载 skill，还原文件到统一 Skill 目录（省略 name 则卸载全部）
sync-skills init             # 初始化 git 仓库（存量仓库检查 git 状态）
sync-skills status           # 显示 git 状态 + skill 管理状态（已管理/孤儿/外部）+ 断链
sync-skills push             # 展示完整 git 命令 + 确认后执行 git commit + push
sync-skills pull             # 展示完整 git 命令 + 确认后执行 git pull + 重建链接
sync-skills fix              # 验证/修复软链接 + 检测断链/缺失/孤儿 skill
```

#### 5.5.4 旧版兼容

- 旧版 copy 同步逻辑提取到 `sync_legacy.py`，通过 `--copy` flag 保持兼容
- 旧版子命令（init/list/search/info）自动路由到旧版以保持测试兼容
- 167 个旧测试 + 19 个新测试 = 186 个测试全部通过

#### 5.5.5 要解决的问题

- [x] 与 npx skills 共存（两类 skill 分管 + lock 文件区分 + 全链路隔离）
- [x] Agent 编辑 skill 时自动写入 git 仓库（软链接穿透）
- [x] 自定义 skill 的完整生命周期管理（add/remove/uninstall/init/status/push/pull/fix）
- [x] 旧版 copy 同步兼容（--copy flag）
- [x] Git 操作健壮性（git 命令预览、push/pull 确认、无 tracking 回退、rebase 冲突自动 abort）
- [x] 存量仓库兼容（init 检查 git 状态，不碰 git 历史）
- [x] 操作前后自动验证（add/remove/uninstall 后验证，pull 前检查 + 后验证）
- [x] 孤儿 skill 检测（未被管理的 skill 提示纳入管理）
- [x] 无默认命令（无子命令时显示帮助，避免语义歧义）

---

### 5.6 Phase 6：Watch 模式与自动化（v1.1 远期）

**目标**：减少手动执行同步的频率。

#### 5.6.1 文件监听

```bash
sync-skills watch    # 监听源目录和所有目标目录的变更，自动同步
```

使用 `watchdog` 或 `fsevents`（macOS）监听文件变更，检测到变化时自动执行同步。需要防抖（debounce）避免频繁触发。

#### 5.6.2 Git Hook 集成

```bash
sync-skills install-hook    # 在 ~/Skills 的 git repo 中安装 post-commit hook
```

每次在 skills 仓库提交后自动同步到所有目标。

#### 5.6.3 LaunchAgent（macOS）/ Systemd（Linux）

```bash
sync-skills service install    # 安装为系统服务，开机自动运行 watch 模式
sync-skills service status     # 查看服务状态
sync-skills service uninstall  # 卸载服务
```

#### 5.6.4 要解决的问题

- [ ] 消除"忘记同步"的问题
- [ ] 在任意工具中修改 skill 后实时生效到其他工具
- [ ] 支持作为后台服务运行

---

## 6. 技术决策记录

### 6.1 为什么用文件复制而非软链接？

| 维度 | 文件复制 | 软链接 |
|------|---------|--------|
| 兼容性 | 所有工具都支持 | OpenClaw 不支持；部分工具可能有未知限制 |
| 新建 skill | 双向同步自动收集 | 需手动移动原文件 + 创建链接 |
| 删除 skill | `--force` 自动清理 | 留下断链，需手动清理 |
| 性能 | 需要复制文件 | 零开销 |
| 跨文件系统 | 正常工作 | 可能不支持 |

结论：兼容性和易用性优先，性能开销在 skill 文件量级（通常几百个小文本文件）下可以忽略。

### 6.2 为什么是单文件实现？

~~降低安装门槛，可以直接 `./sync_skills.py` 运行~~

v0.2 已迁移到 `src/sync_skills/` 包结构。迁移原因：
- PyPI 发布需要标准的包布局
- 配置模块独立为 `config.py`，职责清晰
- 常量抽取到 `constants.py`，便于多模块共享
- hatchling 的 `sources = {"src" = ""}` 保证了 src 布局对用户透明

### 6.3 为什么默认收集到 `Other/` 分类？

~~双向同步时，目标目录中发现的新 skill 无法自动推断它应该属于哪个分类。放到 `Other/` 是最安全的默认行为，用户可以随后手动移动到合适的分类目录。~~

v0.6.0 统一模型下，新 skill 直接从其所在位置分发到所有其他位置（包括源目录的 `Other/` 分类）。`Other/` 仍然是新 skill 在源目录中的默认分类，用户可以随后手动移动到合适的分类目录。

---

## 7. 变更日志

按时间倒序记录每次讨论的关键决策、代码变更和待办事项。

### 2026-04-12 v1.0.1：增强健壮性 + uninstall 命令 + 外部 Skill 隔离

**讨论内容**：
v1.0.0 发布后在实际使用中发现多个问题：git push/pull 在存量仓库上失败（无 tracking、rebase 冲突、non-fast-forward），init 在存量仓库上破坏 git 历史，外部 skill 的 symlink 被错误删除，remove→add 循环失败，status 信息不完整等。后续进一步增强：sync 命令重命名为 fix（语义更明确），push/pull 执行前展示完整 git 命令，移除无子命令默认行为，新增孤儿 skill 检测和操作前后自动验证。

**关键决策**：
- **外部 Skill 全链路隔离**：所有 symlink 操作接受 `external_skills` 参数，跳过外部 skill；新增/删除/卸载命令拒绝操作外部 skill
- **存量仓库兼容**：init 检查 git 状态（dirty tree → 报错，behind remote → 报错），不碰 git 历史
- **Git 命令预览**：push 和 pull 执行前打印完整 git 命令（`git add -A`、`git commit -m "..."`、`git push -u origin <branch>`、`git pull --rebase`），用户确认后才执行
- **Git 操作健壮性**：pull 自动处理无 tracking 回退（`git pull --rebase origin <branch>`）、rebase 冲突自动 abort；push 返回错误分类（behind/auth/bad_url）
- **uninstall vs remove 语义区分**：uninstall 还原文件到统一 Skill 目录（保留数据），remove 彻底删除（不保留）
- **术语统一**：自定义 Skill 仓库 / 统一 Skill 目录 / Agent Skill 目录
- **循环软链接修复**：`create_agents_link` 检测旧架构遗留的循环软链接，自动翻转方向
- **sync → fix 重命名**：原 `sync` 命令重命名为 `fix`，语义更明确（包含验证 + 修复能力）；`sync` 保留为兼容别名
- **无默认命令**：无子命令时显示帮助信息（而非执行 fix），避免用户不知道后果
- **孤儿 skill 检测**：`fix` 命令检测未被管理的孤儿 skill，提示用户纳入管理（迁移到自定义 Skill 仓库 + 创建 symlink）
- **操作前后自动验证**：`add`/`remove`/`uninstall` 后自动调用 `_verify_after_change`（非交互，仅警告）；`pull` 前调用 `_check_state`（有异常则警告并询问是否继续），后执行完整 `_do_sync`

**代码变更**：
- `git_ops.py`：`git_push` 返回 `tuple[bool, str]`，使用 `-u origin <branch>`，stdout 到终端仅 stderr 捕获；`git_pull` 无 tracking 回退 + rebase 自动 abort；新增 `git_get_tracking_branch`、`git_get_remote_url`、`_classify_push_error`
- `symlink.py`：`create_agents_link` 检测旧架构循环软链接并翻转；`sync_all_links`/`create_agent_links`/`create_all_links` 接受 `external_skills` 参数
- `lifecycle.py`：新增 `uninstall_skill`/`_uninstall_one`（支持卸载单个或全部）；`remove_skill` 增加兜底清理；`add_skill` 输出使用三层术语
- `cli.py`：新增 `cmd_uninstall`/`uninstall` 子parser；`cmd_push` 重写为展示完整 git 命令（`git add -A`/`git commit -m`/`git push -u origin <branch>`）+ 分支信息 + 确认后执行；`cmd_pull` 重写为展示完整 git 命令（`git pull --rebase`）+ tracking 信息 + pull 前状态检查 + 确认后执行 + 完整 `_do_sync`；`cmd_status` 增加 skill 管理状态和断链检测；`_do_sync` 增加断链/缺失/孤儿检测与交互式修复；新增 `_detect_broken_agent_links`/`_detect_missing_agents_links`/`_detect_orphan_skills`/`_check_state`/`_verify_after_change`；`cmd_add`/`cmd_remove`/`cmd_uninstall` 增加操作后 `_verify_after_change` 验证；`sync` 子命令重命名为 `fix`，`sync` 保留为兼容别名；无子命令时显示帮助（移除默认执行 fix 的行为）
- `config.py`：`agent_dirs` 支持 None（使用默认值）和空列表（无 Agent）

**测试变更**：
- 新增 19 个测试（167 → 186）：
  - `TestAddCommand`（7 个）：创建、symlink、重复/外部拒绝、tags
  - `TestRemoveCommand`（4 个）：完整删除、remove→add 循环、外部/孤儿拒绝
  - `TestUninstallCommand`（5 个）：文件还原、Agent symlink 保留、卸载全部、外部拒绝、无自定义 skill
  - `TestSymlinkIsolation`（2 个）：sync 不触碰外部、add 不覆盖外部
  - `TestPushCommand`（1 个）：commit + 分支信息显示

**踩坑记录**：
- `capture_output=True` 导致 git push 卡住（stdout 管道阻塞）→ 改为仅 `stderr=subprocess.PIPE`
- `create_agents_link` 在旧架构下删除真实目录后形成循环软链接 → 检测并翻转方向
- `remove_skill` 未清理统一 Skill 目录残留（真实目录）→ 增加兜底清理
- init 在存量仓库上直接执行导致问题 → 增加 git 状态预检查

### 2026-04-12 v1.0.0：自定义 Skill 生命周期管理器（MAJOR REFACTOR）

**讨论内容**：
v0.6 的 copy 同步模式无法与 npx skills 共存（两者都管理 ~/.agents/skills/，会冲突）。需要重构为只管理用户自创建的 skill，外部 skill 由 npx skills 管理。采用 git + symlink 方案，让 Agent 在默认目录编辑 skill 时自动写入 git 仓库。

**关键决策**：
- 两类 skill 分管：外部（npx skills 管理，真实文件）+ 自定义（sync-skills 管理，git 仓库 + 软链接）
- 通过 lock 文件（~/.agents/.skill-lock.json、~/skills-lock.json）区分自定义和外部 skill
- 默认使用软链接替代文件复制（避免冲突，Agent 编辑直接写入 git 仓库）
- 新增 lifecycle 命令：add、remove、init、status、push、pull、fix
- 旧版 copy 同步逻辑提取到 sync_legacy.py，通过 --copy flag 保持兼容
- 旧版子命令（init/list/search/info）自动路由到旧版以保持测试兼容

**模块结构变更**：
- 新增 classification.py：lock 文件解析 + skill 分类判定（custom/external/orphan）
- 新增 symlink.py：两层软链接管理（中央层 ~/.agents/skills/ + Agent 层）
- 新增 git_ops.py：git 操作封装（init/clone/status/add_commit/push/pull）
- 新增 lifecycle.py：add/remove/uninstall/init 命令实现
- 新增 sync_legacy.py：从 cli.py 提取旧版 copy 同步逻辑
- 重写 cli.py：subparser 命令结构 + 旧版自动路由 + 新版命令分发
- 更新 config.py：新增 repo/agents_dir/external 配置段
- 更新 constants.py：新增 DEFAULT_REPO、DEFAULT_AGENTS_DIR、SKILL_SKELETON
- 更新 metadata.py：移除对 cli.py 的循环导入依赖

**配置格式变更**：
```toml
repo = "~/Skills"
agents_dir = "~/.agents/skills"

[external]
global_lock = "~/.agents/.skill-lock.json"
local_lock = "~/skills-lock.json"
```

**测试变更**：
- 167 个旧测试通过（通过旧版自动路由机制保持兼容）
- 19 个新测试（v1.0.1 新增），总计 186 个测试
- 旧版 subcommands（init/list/search/info）自动检测并路由到 sync_legacy.main_legacy()

**版本更新**：
- 版本号：0.5.20260411.1 → 1.0.0（MAJOR VERSION）
- pyproject.toml description 更新

### 2026-04-11 v0.6.0：统一同步模型重构（BREAKING CHANGE）

**讨论内容**：
双向同步采用两阶段模型（收集→分发），隐含"源目录是权威中心"的假设。但实际上 skill 的创建和迭代都发生在目标目录，源目录只是备份和分类管理。两阶段模型导致预览显示误导（"从源分发"但实际源头是目标）、需要 `update_origins` 额外追踪变更源头、旧版可能覆盖新版。

**关键决策**：
- 用统一的"从最新版本分发"模型替代"收集→分发"两阶段模型
- 源目录降级为支持嵌套分类的特殊目标目录，不再有特权
- 新增 `SyncOp(skill_name, origin_dir, dest_dir, dest_rel, origin_rel)` 统一数据结构
- 简化 `SyncPlan`：删除 `collect_new`、`collect_update`、`creates`、`updates`、`update_origins`、`auto_distribute`，仅保留 `sync_ops`、`deletes`、`warnings`、`conflicts`、`resolutions`
- 简化 `ConflictResolution`：删除 `chosen_source_rel`（信息已在 `SkillVersion.source_rel` 中）
- `_resolve_conflicts()` 直接生成 `SyncOp`，删除 `_apply_resolutions()` 中间层
- `preview_bidirectional()` 改为单 pass 算法：扫描 → 哈希分组 → 生成 SyncOp
- `_build_sync_ops_for_skill()` 辅助函数：给定最新版本和所有版本列表，生成 SyncOp 列表
- 自动解决条件调整：2 组有 singleton 且 majority ≥ 2 才自动解决（旧模型中源 singleton 是冲突，新模型中源只是普通位置）

**代码变更**：
- `cli.py` 新增 `SyncOp` 数据类
- `cli.py` 简化 `SyncPlan`：删除 6 个字段，新增 `sync_ops`
- `cli.py` 简化 `ConflictResolution`：删除 `chosen_source_rel`
- `cli.py` 新增 `_build_sync_ops_for_skill()`：统一生成 SyncOp
- `cli.py` 重写 `preview_bidirectional()`：单 pass 算法
- `cli.py` 重写 `_resolve_conflicts()`：直接生成 SyncOp，删除 `_apply_resolutions()`
- `cli.py` 重写 `execute_bidirectional()`：遍历 sync_ops 执行
- `cli.py` 重写 `show_preview()`：对称显示所有目录
- `cli.py` 修复 `execute_force()` 多处 bug（`UnboundLocalError`、`ValueError`）
- `cli.py` 修复 1-hash-group 跳过 bug（部分位置缺失时未生成 SyncOp）
- `cli.py` 修复源目录路径匹配 bug（`v.is_source and dest_dir == source_dir`）
- `cli.py` 修复 `origin_rel` 未传播 bug（origin 是源目录时必须携带嵌套路径）

**测试变更**：
- `tests/test_sync_skills.py` 全量重写（106 个测试，原 106 个更新为 SyncOp 模型）
- 删除 `_apply_resolutions` 相关测试，新增 `ConflictResolution` 导入
- 冲突测试调整：源 singleton + majority ≥ 2 改为测试自动解决（不再是冲突）
- 测试数量从 167 个保持不变（106 + 61）

**版本更新**：
- 版本号：`0.5.x` → `0.6.0`（BREAKING CHANGE：内部 API 变更）

### 2026-04-11 v0.5.1：预览显示优化 + 变更源头追踪

**讨论内容**：
双向同步预览存在多处误导：1）目标目录变更显示为"从源目录分发"，实际源头是目标；2）冲突界面重复显示哈希和 name/description；3）标题栏显示内部模式名称；4）所有路径显示为文件系统路径而非可读工具名。

**关键决策**：
- `SyncPlan` 新增 `update_origins: dict[str, Path]` 字段，追踪每个 skill 的实际变更源头目录
- `_build_alias_map()` 接受 `name_map` 参数，优先使用 KNOWN_TOOLS 中的可读名称（如 "Claude Code"）而非文件系统路径
- 冲突界面：去掉哈希显示，name/description 只在顶部显示一次，每个版本仅显示位置和修改时间
- 标题栏从 "双向同步 · Skills 同步" 改为 "sync-skills v{version}"
- `execute_bidirectional()` 对有 `update_origins` 的操作直接从源头目标复制，跳过源目录中转

**代码变更**：
- `cli.py` `SyncPlan`：新增 `update_origins` 字段
- `cli.py` `preview_bidirectional()`：`collect_new` 和 `collect_update` 时填充 `update_origins`
- `cli.py` `_apply_resolutions()`：用户选择目标版本时填充 `update_origins`
- `cli.py` `show_preview()`：creates/updates 查找 `update_origins` 显示实际源头
- `cli.py` `execute_bidirectional()`：有 origin 时直接从源头复制
- `cli.py` `ask_conflict_resolution()`：接收 `alias_map`，位置显示使用可读名称；去掉哈希，公共信息只显示一次
- `cli.py` `_build_version_warning_from_versions()`：接收 `alias_map`，位置显示使用可读名称
- `cli.py` `_resolve_conflicts()`：传递 `alias_map`
- `cli.py` `_build_alias_map()`：新增 `name_map` 参数，支持可读名称映射
- `cli.py` `main()`：构建 `target_name_map`（KNOWN_TOOLS 优先），传入 `_build_alias_map` 和 `_resolve_conflicts`
- `cli.py` 标题栏：显示 `sync-skills v{__version__}`

**测试变更**：
- `tests/test_sync_skills.py` 新增 2 个测试：`test_preview_shows_actual_origin_for_target_update`、`test_preview_shows_actual_origin_for_new_skill`
- `test_collect_update_distributes_to_other_targets` 新增 `update_origins` 断言
- 测试数量从 162 个增加到 164 个

### 2026-04-05 Phase 4 完成：Skill 化封装 + AI 友好 CLI

**讨论内容**：
将 sync-skills CLI 工具封装为 skill，让 AI 编码工具可以代替用户操作；改进 CLI help 输出使其对 AI 更友好。

**关键决策**：
- argparse help 文本改为英文（AI 解析更可靠），运行时输出保持中文
- 使用 `RawDescriptionHelpFormatter` + epilog 添加命令示例
- 新增 `--dry-run` 参数：在 show_preview() 之后、execute 之前插入检查，预览变更但不执行
- SKILL.md 放在项目 `skills/sync-skills/` 目录，纳入 git 版本控制
- 版本号从 0.3.x 跳至 0.5.0（Phase 3 中间版本未正式发布）

**代码变更**：
- `cli.py` 修改 `parse_args()`：`RawDescriptionHelpFormatter`、多行 description、epilog 示例、英文 help 文本、新增 `--dry-run` 参数
- `cli.py` 修改 `execute_delete()`：新增 `dry_run` 参数
- `cli.py` 修改 `main()`：force/bidirectional/delete 三个路径添加 dry-run 检查
- 新建 `skills/sync-skills/SKILL.md`：AI 使用的 skill 操作指南
- `__init__.py`、`pyproject.toml`：版本号 → 0.5.0
- `.github/workflows/publish.yml`：CI 版本前缀 0.3 → 0.5
- `tests/test_sync_skills.py`：新增 `TestDryRun` 测试类（8 个测试）

### 2026-04-05 Phase 3 完成：Skill 元数据与索引 + 选择性同步

**讨论内容**：
实现 SKILL.md frontmatter 解析、list/search/info 查询命令、基于 tags/tools 的选择性同步。

**关键决策**：
- 引入 PyYAML 作为首个外部依赖，用于 YAML frontmatter 解析
- 不引入索引文件，按需解析（~50 个 skill，解析延迟 < 100ms）
- `tools` 字段映射目标路径的父目录名（去掉前导点）：`~/.claude/skills` → `"claude"`
- 收集阶段（Stage 1）不受选择性同步影响，始终收集目标中的新 skill
- 分发阶段（Stage 2）按 skill 粒度过滤目标
- 已在目标中存在但不应同步的 skill → 删除
- 阶段编号调整：Phase 4 Skill 化封装提前，Phase 6 Watch 模式移到最后

**代码变更**：
- 新建 `metadata.py`：`SkillMetadata` 数据结构、`parse_frontmatter()`、`get_target_tool_name()`、`should_sync_to_target()`、`collect_all_metadata()`、`search_skills()`、`warn_unknown_tools()`
- `config.py`：`Config` 添加 `exclude_tags` 字段、`load_config()` 解析 `[sync]` 段、`save_config()` 写入 `[sync]` 段
- `cli.py` 新增辅助函数：`_get_skill_metadata()`、`_should_sync_to()`、`_should_delete_from_target()`
- `cli.py` 修改 `preview_bidirectional()`：添加 `exclude_tags` 参数，分发阶段按 skill 粒度过滤目标，新增"源和目标都有但不应同步"的删除逻辑
- `cli.py` 修改 `preview_force()`：同上
- `cli.py` 修改 `_apply_resolutions()`：添加 `exclude_tags` 参数，分发时过滤目标
- `cli.py` 修改 `main()`：传递 `exclude_tags`、未知工具警告、list/search/info 子命令路由
- `cli.py` 新增命令：`_cmd_list()`（按分类分组列出）、`_cmd_search()`（全文搜索）、`_cmd_info()`（skill 详情）
- `cli.py` 修改 `parse_args()`：添加 `choices=["init", "list", "search", "info"]`、`query` 位置参数、`--tags` 参数
- `pyproject.toml`：添加 `pyyaml>=6.0` 依赖

**测试变更**：
- 新建 `tests/test_metadata.py`（36 个测试）：frontmatter 解析、工具名映射、同步过滤、搜索、收集、未知工具警告
- `tests/test_config.py` 新增 3 个测试：exclude_tags 加载/保存
- `tests/test_sync_skills.py` 新增 19 个测试：`TestSelectiveSync`（10 个）、`TestListCommand`（4 个）、`TestSearchCommand`（3 个）、`TestInfoCommand`（3 个）
- 测试数量从 90 个增加到 154 个

**版本更新**：
- 版本号：`0.3.0` → `0.4.0`

**阶段编号调整**：
- Phase 4（原 Phase 6）：Skill 化封装
- Phase 6（原 Phase 4）：Watch 模式与自动化

---

### 2026-04-03 Phase 2 完成：内容感知同步 + 交互式冲突解决

**讨论内容**：
去掉 mtime 依赖，改为纯哈希冲突检测。冲突时提供交互式选择界面，让用户决定保留哪个版本。

**关键决策**：
- 不引入 `state.json`：冲突时直接展示所有版本让用户选，不需要持久化上次同步状态
- mtime 保留为展示提示（不用于自动分类），帮助用户判断哪个版本更新
- 不实现 diff 功能：展示 SKILL.md 前 3 行 + 哈希前 8 位 + 修改时间，让用户选即可
- `-y` 模式兼容：自动跳过冲突，转为 warning 输出（和 v0.2 行为一致）
- 冲突检测规则：按哈希分组，2 组且 singleton 不是源 → 自动收集；其他 → 冲突

**代码变更**：
- 新增数据结构：`SkillVersion`（版本描述信息）、`ConflictResolution`（用户选择）
- `SyncPlan` 扩展：新增 `conflicts`、`resolutions` 字段和 `has_conflicts` 属性
- 新增辅助函数：`_build_skill_version()`、`_build_version_warning_from_versions()`
- 新增交互函数：`ask_conflict_resolution()`（冲突选择界面）、`_resolve_conflicts()`（遍历解决）、`_apply_resolutions()`（选择转操作）
- 重写 `preview_bidirectional()`：去掉 mtime 分类，改为纯哈希分组 + 自动解决/冲突分类
- 改造 `show_preview()`：新增"冲突解决"section
- 改造 `main()` 双向流程：预览前插入冲突解决步骤
- 改造 `execute_bidirectional()`：新增 `plan.updates` 处理（冲突解决后的覆盖操作）
- 删除废弃函数：`_build_version_warning()`、`_alias_of()`（被新函数替代）

**测试变更**：
- 更新 3 个现有测试（S4/S6/S6b）：从检查 `plan.warnings` 改为检查 `plan.conflicts`
- 新增 `TestConflictResolution` 类（15 个测试）：安全收集、各类冲突检测、交互选择、跳过、自动模式、resolution 应用、端到端
- 测试数量从 77 个增加到 90 个

**版本更新**：
- 版本号：`0.2.0` → `0.3.0`
- GitHub Actions 版本前缀更新为 `0.3.`

---

### 2026-04-03 Phase 1 完成：PyPI 打包 + 配置化 + init 向导

**讨论内容**：
将项目从根目录单文件迁移到 src/ 包结构，实现 PyPI 打包、配置文件持久化和首次启动引导。

**关键决策**：
- `requires-python = ">=3.11"`：利用内置 `tomllib`，零外部依赖
- `src/sync_skills/` 包布局：`__init__.py`、`constants.py`、`config.py`、`cli.py`
- hatchling 构建后端，`sources = {"src" = ""}` 映射 src 到包根
- `sync-skills init` 交互式向导：源目录 + 检测已安装工具 + 自定义目标
- CLI 参数覆盖配置：`--source`/`--targets` 非空时覆盖 config 值
- 配置缺失时回退内置默认值，完全向后兼容
- 删除根目录 `sync_skills.py`，避免与 `src/sync_skills/` 包冲突

**代码变更**：
- 新建 `src/sync_skills/__init__.py`：版本号导出 `__version__ = "0.2.0"`
- 新建 `src/sync_skills/constants.py`：提取 `DEFAULT_SOURCE`、`DEFAULT_TARGETS`、`KNOWN_TOOLS`、`CONFIG_DIR`、`CONFIG_FILE`
- 新建 `src/sync_skills/config.py`：`Config`/`Target` 数据类、`load_config()`/`save_config()`、`_expand_home()`/`_unexpand_home()`、`detect_installed_tools()`
- 新建 `src/sync_skills/cli.py`：从 `sync_skills.py` 迁移全部逻辑，新增 `_run_init_wizard()`、`--config` 参数、`init` 子命令、config→CLI 覆盖逻辑
- 更新 `pyproject.toml`：hatchling 构建、`requires-python >= 3.11`、`sources = {"src" = ""}`
- 新建 `.github/workflows/publish.yml`：GitHub Actions 自动构建发布，版本号按日期+序号自动递增
- 删除根目录 `sync_skills.py`

**测试变更**：
- 更新 `tests/test_sync_skills.py`：所有 import 改为 `from sync_skills.cli import`
- 新建 `tests/test_config.py`（15 个测试）：路径展开/缩回、配置加载/保存/回退、工具检测
- 新建 `tests/test_init.py`（3 个测试）：init 创建配置、默认/自定义源目录
- 测试数量从 59 个增加到 77 个

**发布**：
- v0.2.0 发布到 PyPI：`uv tool install sync-skills`
- GitHub Actions 配置 Trusted Publishing，推送到 main 自动构建发布
- 创建 git tag `v0.2.0`

---

### 2026-04-03 MD5 内容比较 + 冲突展示增强 + Force 基准选择 + 隐藏目录过滤

**讨论内容**：
1. 添加整个 skill 目录的 MD5 校验，替代仅比较 SKILL.md 内容的方式
2. 改进冲突警告展示，使用 git 风格的版本分组 + mtime 建议版本
3. Force 模式支持交互式选择任意目录为基准
4. 修复 `.codex/skills/.system/` 下 skill 被错误收集的问题

**关键决策**：
- 内容比较用 MD5（`skill_dir_hash()`），排除隐藏文件（`.DS_Store` 等）
- 哈希相同 → 内容一致，哈希不同 → 内容不一致；mtime 仅用于归因修改方向
- 冲突警告按 hash 分组，列出每个目录的版本和修改时间，标记建议版本
- 目标目录实现别名映射（源、.claude、.codex 等），输出更简洁
- Force 模式支持选择基准目录：概览 → 选基准 → 预览 → 确认 → 执行
- 目标目录使用扁平扫描（`iterdir`），不递归；所有扫描函数跳过隐藏目录

**代码变更**：
- 新增 `skill_dir_hash()`：计算 skill 目录 MD5，排除隐藏文件
- 新增 `_build_alias_map()`、`_alias_of()`、`_short_path()`、`_fmt_time()`：目录别名和显示工具
- 新增 `_build_version_warning()`：多行冲突警告，按 hash 分组，mtime 排序，标记建议版本
- 新增 `show_overview()`：展示所有目录概览（skill 数量、不一致数）
- 新增 `ask_base_selection()`：交互式基准目录选择
- 改造 `preview_bidirectional()`：用 hash 比较 + 版本警告替代旧警告格式
- 改造 `preview_force()`：增加 hash 检测内容不同的同名 skill，填充 `plan.updates`
- 改造 `execute_force()`：处理 updates（删除+复制），使用 `find_skill_path()` 定位
- 改造 `main()` force 流程：概览 → 选基准 → 预览 → 确认 → 执行
- `find_skills_in_target()`：从 `rglob` 改回 `iterdir` 扁平扫描，跳过隐藏目录
- `find_skills_in_source()`、`find_skill_in_source_by_name()`：添加隐藏目录过滤
- `find_skill_path()`：简化为直接路径查找（目标目录平铺）
- `show_preview()`：支持多行警告缩进显示
- `verify_sync()`：基于内容 hash 校验替代仅比较数量

**测试变更**：
- 新增 `TestScan` 中 4 个 hash 测试（identical, different, extra_file, order_independent）
- 新增 `TestForce` 中 2 个覆盖测试（different_content, with_extra_files）
- 新增 `TestBaseSelection` 类（7 个测试）：基准选择、概览展示、`-y` 向后兼容
- 更新 `TestUserScenarios` 中 3 个断言适配新警告文本
- 测试数量从 46 个增加到 59 个

**踩坑记录**：
- `.DS_Store` 文件导致所有 skill 哈希不一致 → `skill_dir_hash()` 排除 `.` 开头文件
- 目标目录都用 `iterdir` 但别名显示不区分 → 引入 `_build_alias_map()` 别名系统
- `.codex/skills/.system/` 下 skill 被错误收集 → 目标目录扁平扫描 + 隐藏目录过滤

---

### 2026-04-03 修复 Force 模式嵌套结构处理 + 预览输出优化

**讨论内容**：
1. Force 模式以目标为基准时，源目录的嵌套结构未被正确处理
2. 预览输出可读性差：全路径过长、skill 压缩在一行、别名不够直观
3. 验证步骤对嵌套目录使用扁平扫描，导致误报 0 个 skill
4. 执行日志应使用相对路径

**关键决策**：
- 源目录作为目标时，新增写到 `Other/`、删除在嵌套结构中定位、覆盖也是先删后写 `Other/`
- `preview_force()` 和 `execute_force()` 通过 `original_source_dir` 参数识别嵌套目录
- `verify_sync()` 同样支持嵌套目录验证
- 所有目录别名统一用 `~/` 相对路径（如 `~/.claude/skills`），不再用"源"或父目录名
- Force 预览改为按目录分组，每个目录独立显示新增/覆盖/删除的逐行 skill 列表
- 新增/覆盖显示 `← 基准路径/相对路径`，删除显示完整相对路径，跳过只显示数量
- 执行日志全部改为相对路径

**代码变更**：
- `preview_force()` 新增 `original_source_dir` 参数，嵌套目标用 `find_skills_in_source()` 扫描，哈希比较用 `target_map[name]` 定位实际路径
- `execute_force()` 新增 `original_source_dir` 参数，嵌套目标：新增→`Other/`、删除→`find_skill_in_source_by_name()`、更新→删除旧版+写 `Other/`
- `show_preview()` 新增 `alias_map`、`nested_targets` 参数；force 模式预览重构为按目录分组列表
- `verify_sync()` 新增 `nested_targets` 参数，支持嵌套目录扫描和哈希校验
- `_build_alias_map()` 所有目录统一用 `_short_path()`，不再用 `"源"` 或 `parent.name`
- `main()` force 流程传入 `orig_source` 和 `nested` 到各函数
- 执行日志 `execute_force()` 中 `target_dir` 改为 `_short_path(target_dir)`

**测试变更**：
- 更新 `test_force_with_target_as_base`：验证嵌套结构写入 `Other/`
- 更新 `test_force_base_syncs_to_source`：验证新增→`Other/`、删除→嵌套定位

---

**讨论内容**：用户请求添加 `--delete` 命令用于一键删除 skill。

**关键决策**：
- 命令格式：`sync-skills --delete <skill_name>` 或 `sync-skills -d <skill_name>`
- 删除范围：从源目录和所有目标目录中删除该 skill
- 安全机制：需要二次确认，`-y` 可跳过确认
- 错误处理：skill 不存在时报错退出

**代码变更**：
- 新增辅助函数 `find_skill_in_targets()`：查找 skill 在哪些目标目录中存在
- 新增命令行参数 `--delete/-d`：接受 skill 名称作为参数
- 新增 `execute_delete()` 函数：执行删除操作，包含预览、确认和执行流程
- 在 `main()` 中处理删除模式：`--delete` 参数存在时直接执行删除并退出
- 新增 `TestDelete` 测试类：6 个测试覆盖各种删除场景
- 测试数量从 40 个增加到 46 个

**测试覆盖**：
- `test_delete_skill_from_all_locations`：skill 存在于所有位置 → 全部删除
- `test_delete_skill_partial_exist`：skill 只存在于部分位置 → 删除存在的，忽略不存在的
- `test_delete_nonexistent_skill`：skill 不存在 → 报错退出
- `test_delete_only_in_targets`：skill 只在目标存在 → 删除所有目标中的 skill
- `test_delete_with_other_skills_untouched`：删除不影响其他 skill
- `test_find_skill_in_targets`：辅助函数测试

**文档更新**：
- 第 3.3 节"删除场景"（S9）：更新为推荐使用 `--delete` 命令
- 第 5.1.1 节"PyPI 打包发布"：示例中增加 `--delete` 用法

**后续优化**：
- 全局 gitignore 配置：将 `.claude` 目录添加到 `~/.gitignore_global`，所有项目自动忽略
- sync-skills 仓库清理：从版本控制中移除 `.claude/settings.local.json`，保留本地配置

---

### 2026-03-21 开放问题决议 + Skill 化封装规划 + 限制分类

**讨论内容**：
1. 逐一讨论并关闭了第 8 节的 6 个开放问题
2. 新增 Phase 6 远期规划——将 CLI 工具封装为 skill
3. 重新审视第 4 节的 10 个已知限制，分类为：设计约束、待优化、版本管理根因

**开放问题决议**：
1. 配置文件格式：TOML
2. Skill 内附件管理：整目录原子操作，不单独追踪
3. 多层嵌套分类深度：不限制
4. 各工具 CLI 集成：暂不需要，避免耦合
5. Python 版本要求：`>=3.10`
6. 发布渠道：PyPI + `uv tool install`

详见第 8 节。

**已知限制重新分类**（第 4 节重构）：
- **设计约束**（#1, #4, #7）：同名检测、原子同步、不支持内容合并——这些是预期行为，不做调整
- **Phase 1 解决**（#3）：目标目录硬编码 → 配置化
- **版本管理根因**（#2, #8, #9, #10）：都源于 mtime 不可靠，需 Phase 2 引入内容哈希 + 状态快照整体解决
- **其他待优化**（#5, #6）：增量同步、元数据管理

**新增规划**：
- Phase 6（5.6 节）：将 sync-skills 封装为一个 skill，让 AI 编码工具代替用户操作 CLI
- 核心思路：CLI 是基础层，skill 是面向非命令行用户的自然语言交互层
- 前置条件：Phase 1 完成后 CLI 接口稳定

---

### 2026-03-21 场景梳理 + 冲突策略

**讨论内容**：梳理了所有用户使用场景（S1-S13），重点讨论了冲突和删除场景的处理策略。

**关键决策**：
- **冲突策略**：所有存在歧义的场景都停下来让用户决定，不做默认覆盖行为
  - S3（仅目标修改）：安全收集到源 → 唯一无歧义的自动操作
  - S4（仅源修改）：警告提示用 `--force`
  - S6（多目标冲突）：跳过 + 警告
  - S6b（源+目标冲突）：跳过 + 警告
- **删除策略**：从源目录删除 + `--force` 同步，后续可加 `sync-skills delete <name>` 命令
- **发布方式**：PyPI + `uv tool install`，参考 video-captions 打包方式
- **配置化**：首次启动交互式引导，配置持久化到 `~/.config/sync-skills/config.toml`

**代码变更**：
- 重构 `preview_bidirectional()` 冲突检测逻辑，统一为 4 种情况分类
- `SyncPlan` 增加 `warnings` 字段，支持非阻塞警告
- 修复 `execute_bidirectional()` 中 `collect_new` 重复收集导致 `FileExistsError` 的 bug
- 新增 `TestUserScenarios` 测试类（12 个场景测试），测试从 26 个增加到 40 个
- 设计文档新增"用户场景与预期行为"章节（第 3 节）

**下一步**：
- [ ] Phase 1 实施：PyPI 打包 + 首次启动引导 + 配置化
- [ ] `requires-python` 降低到 `>=3.10`
- [ ] 考虑增加 `sync-skills delete <name>` 命令

---

## 8. 已关闭的开放问题

以下问题已在 2026-03-21 讨论中全部达成共识，不再是开放问题。

| # | 问题 | 决定 | 理由 |
|---|------|------|------|
| 1 | 配置文件格式 | **TOML** | Python 3.11+ 标准库自带 `tomllib`，简洁清晰 |
| 2 | Skill 内附件管理 | **整目录原子操作** | Skill 是原子单位，包含脚本/图片等附件时整体复制/整体替换，不单独追踪 |
| 3 | 多层嵌套分类深度限制 | **不限制** | Skills 数量膨胀后可能出现两级三级甚至更深的分类，按用户实际组织方式即可，目标侧都是平铺 |
| 4 | 各工具 CLI 集成 | **暂不需要** | 发布 PyPI 后用户直接当本地命令使用；各 AI 编码工具也可直接调用本地命令，无需额外集成，避免耦合 |
| 5 | Python 版本要求 | **`>=3.10`** | 降低门槛，覆盖更多用户的 Python 版本 |
| 6 | 发布渠道 | **PyPI + `uv tool install`** | 参考 video-captions 打包方式 |
