# sync-skills 设计规划文档

## 1. 项目定位

sync-skills 是一个 AI 编码工具的 skills 统一管理与同步工具。在本地维护一个中心化的 skills 仓库（支持分类目录），自动将 skills 分发/同步到各个 AI 编码工具（Claude Code、Codex CLI、Gemini CLI、OpenClaw 等）的平铺 skills 目录中。

### 1.1 目标用户

同时使用多个 AI 编码工具，并且积累了一定数量 skills 的开发者。

### 1.2 核心价值

| 价值 | 说明 |
|------|------|
| 单一真实来源 | 所有 skills 集中在 `~/Skills/`，避免多处维护 |
| 分类管理 | 源目录支持嵌套目录结构，按主题归类 |
| 自动同步 | 一条命令完成所有工具的 skills 同步 |
| 双向流动 | 在任意工具中新建的 skill 自动回收到中心仓库 |

---

## 2. 当前架构（v0.1）

### 2.1 核心概念

```
┌─────────────────────────────────────────────────────────┐
│                    源目录 ~/Skills/                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐               │
│  │  Code/    │  │  Lark/   │  │  Other/  │  ...          │
│  │  ├─ skill-a│  │  ├─ skill-c│  │  ├─ skill-e│           │
│  │  └─ skill-b│  │  └─ skill-d│  │  └─ ...   │           │
│  └──────────┘  └──────────┘  └──────────┘               │
└─────────────────────────────┬───────────────────────────┘
                              │
                    sync-skills (copy)
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ .claude/skills│  │ .codex/skills │  │ .gemini/skills│
│  ├─ skill-a   │  │  ├─ skill-a   │  │  ├─ skill-a   │
│  ├─ skill-b   │  │  ├─ skill-b   │  │  ├─ skill-b   │
│  ├─ skill-c   │  │  ├─ skill-c   │  │  ├─ skill-c   │
│  ├─ skill-d   │  │  ├─ skill-d   │  │  ├─ skill-d   │
│  └─ skill-e   │  │  └─ skill-e   │  │  └─ skill-e   │
└──────────────┘  └──────────────┘  └──────────────┘
     (平铺)             (平铺)             (平铺)
```

**关键设计决策**：源目录支持嵌套分类，目标目录始终是平铺结构（因为各工具只支持平铺）。同步时将分类"展平"——只保留 skill 的最末级目录名。

### 2.2 Skill 识别规则

一个目录被识别为 skill 的条件：**目录下存在 `SKILL.md` 文件**。

这是目前所有 AI 编码工具通用的 skill 标识方式。没有 `SKILL.md` 的目录会被忽略。

### 2.3 同步模式

#### 双向同步（默认）

```
阶段1：收集（目标 → 源）
  - 目标中存在但源中不存在的 skill → 复制到 ~/Skills/Other/
  - 目标中的 skill 比源中更新（mtime 更大 + 内容不同）→ 覆盖源

阶段2：分发（源 → 目标）
  - 源中存在但目标中缺少的 skill → 复制到目标
  - 目标中存在但源中不存在的 skill → 删除（此时应已被阶段1收集）
```

#### 强制同步（--force）

```
单向：源 → 目标
  - 源中存在但目标中缺少 → 复制到目标
  - 目标中存在但源中不存在 → 从目标删除
  - 不修改源目录
```

### 2.4 安全机制

1. **预览确认**：所有操作先展示 diff，用户确认后才执行
2. **重名检测**：源目录不同分类下存在同名 skill 时，直接报错退出（平铺后会冲突）
3. **执行后验证**：对比各目标目录的 skill 数量是否与源一致
4. **无变更跳过**：没有差异的目录不执行任何操作

### 2.5 技术选型

- **语言**：Python 3.14+，单文件实现（`sync_skills.py`，约 500 行）
- **依赖**：零外部依赖，仅使用标准库（pathlib, shutil, argparse）
- **包管理**：uv
- **测试**：pytest，26 个回归测试

---

## 3. 用户场景与预期行为

### 3.1 基本场景

| # | 场景 | 操作 | 预期行为 |
|---|------|------|----------|
| S1 | 源目录新增 skill | 在 `~/Skills/Code/` 下新建 `skill-x/SKILL.md` | 双向同步：分发到所有目标目录（平铺）；已有 skill 不受影响 |
| S2 | 目标目录新增 skill | 在 `~/.codex/skills/` 下新建 `skill-y/SKILL.md` | 双向同步：先收集到 `~/Skills/Other/skill-y`，再分发到其他目标 |
| S3 | 目标目录修改 skill | 在 `~/.codex/skills/skill-a/SKILL.md` 中修改内容 | 双向同步：检测到目标 mtime 更新且内容不同 → 覆盖源目录对应 skill → 再分发到其他目标 |
| S4 | 源目录修改 skill | 在 `~/Skills/Code/skill-a/SKILL.md` 中修改内容 | 双向同步：检测到源更新但不会自动覆盖目标，**输出警告提示用户使用 `--force` 同步** |

**S4 补充说明**：双向模式检测到源目录的 skill 比目标更新且内容不同时，会输出警告提示用户使用 `--force` 模式来更新目标。这避免了静默忽略源目录修改的问题。

### 3.2 冲突场景

| # | 场景 | 操作 | 预期行为 |
|---|------|------|----------|
| S5 | 源目录重名 | `~/Skills/Code/dup/` 和 `~/Skills/Lark/dup/` 同时存在 | 报错退出，提示用户重命名（平铺后会冲突） |
| S6 | 多目标同时修改同一 skill | Codex 改了 `skill-a`，Claude Code 也改了 `skill-a` | 检测到冲突，**跳过自动合并并输出警告**，提示用户手动处理 |
| S6b | 源和目标同时修改同一 skill | 源目录改了 `skill-a`，同时 Codex 也改了 `skill-a` | 检测到冲突，**跳过自动合并并输出警告**，提示用户手动处理 |

### 3.3 删除场景

| # | 场景 | 操作 | 当前行为 | 推荐工作流 |
|---|------|------|----------|------------|
| S7 | 从目标删除 skill | 删除 `~/.codex/skills/skill-x/` | 双向同步时，源目录仍有该 skill → 下次同步又被分发回来 | 不推荐从目标侧删除 |
| S8 | 从源目录删除 skill | 删除 `~/Skills/Code/skill-x/` | 双向同步时，目标仍有该 skill → 被当作"新增"收集回 `Other/` | **从源目录删除 + `--force` 同步**：force 模式以源为准，会删除目标中多余的 skill |
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

## 4. 当前已知限制（v0.1）

### 4.1 设计约束（符合预期，不做调整）

| # | 约束 | 说明 |
|---|------|------|
| 1 | 同名检测基于目录名 | 目录名即唯一标识，不同分类下不能有同名 skill。平铺后会冲突，这是预期行为而非缺陷 |
| 4 | Skill 整目录原子同步 | Skill 是原子单位，目录内所有文件（SKILL.md、脚本、图片等）整体复制/整体替换，不支持部分同步 |
| 7 | 不支持内容级别的合并 | Skill 的描述与脚本高度耦合，只能整体覆盖。部分合并的心智负担和风险都太高 |

### 4.2 待优化（Phase 1 解决）

| # | 限制 | 影响 | 解决方案 |
|---|------|------|----------|
| 3 | 目标目录列表硬编码 | 新增工具需要改代码或用 `--targets` | Phase 1 配置化：`config.toml` + 首次启动引导 |

### 4.3 待优化（版本管理重构解决）

以下限制**同源于一个根因：基于 mtime 的变更检测不可靠**。mtime 在跨文件系统、git clone、批量复制等场景下会丢失或不准确，导致无法可靠判断"谁改了什么"，进而引发一系列连锁问题。需要整体重构版本管理机制来统一解决。

| # | 限制 | 影响 | 根因 |
|---|------|------|------|
| 2 | 变更检测依赖 mtime | 跨文件系统或 git clone 后 mtime 可能不准确 | 没有持久化的同步状态快照 |
| 8 | 双向模式不自动推送源修改 | 源修改后只能警告，需用户手动 `--force` | 无法可靠区分"源更新"和"目标未同步" |
| 9 | 多目标冲突需手动处理 | 多目标同时修改同一 skill 时只能跳过 | 无法确定哪个版本是"最新" |
| 10 | 删除只能通过 force 模式 | 双向模式无法判断"目标缺少"是删除还是新增 | 没有"上次同步时存在"的历史记录 |

**解决方向**（对应 Phase 2）：
- 引入内容哈希（SHA-256）替代 mtime，消除文件系统差异
- 持久化同步状态快照（`state.json`），记录每次同步后各 skill 的哈希值
- 通过"上次同步状态 vs 当前状态"的三方对比，精确判断：新增、修改、删除、冲突
- 在版本管理可靠之前，所有存疑场景继续保持"停下来让用户决定"的安全策略

### 4.4 待优化（其他）

| # | 限制 | 影响 | 备注 |
|---|------|------|------|
| 5 | 无增量同步 | 每次全量对比+复制，skill 数量极大时可能较慢 | 结合 Phase 2 的内容哈希，哈希一致则跳过复制 |
| 6 | 无 skill 元数据管理 | 分类靠目录结构，无标签/状态/历史追踪 | Phase 3 规划中，可结合 state.json 扩展 |

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

- [ ] 发布到 PyPI，支持 `uv tool install` 一键安装
- [ ] `requires-python` 降低到 `>=3.10`
- [ ] 首次启动交互式引导，零配置即可使用
- [ ] 自动检测已安装的 AI 编码工具
- [ ] 目标目录不再硬编码，用户可自由扩展
- [ ] 支持为不同工具命名，预览输出更直观

---

### 5.2 Phase 2：内容感知同步（v0.3）

**目标**：解决 mtime 不可靠和内容级冲突的问题。

#### 5.2.1 基于内容哈希的变更检测

```
~/.config/sync-skills/state.json

{
  "skills": {
    "code-review": {
      "source_hash": "sha256:abc123...",
      "last_sync": "2026-03-21T16:00:00Z",
      "source_path": "Code/code-review"
    }
  }
}
```

- 不再依赖 mtime，改用文件内容的 SHA-256 哈希
- 记录每次同步的状态快照，支持精确的变更检测

#### 5.2.2 冲突处理

当同一 skill 在源和目标都被修改时：

```
? skill-a 存在冲突:
  源:  ~/Skills/Code/skill-a (modified 2026-03-21 15:00)
  目标: ~/.claude/skills/skill-a (modified 2026-03-21 16:30)

  [s] 保留源版本
  [t] 保留目标版本
  [d] 查看 diff
  [S] 跳过
```

#### 5.2.3 要解决的问题

- [ ] 消除 mtime 依赖，跨文件系统/git clone 后仍能准确判断
- [ ] 冲突时给用户明确的选择，而非静默覆盖
- [ ] 支持查看具体 diff

---

### 5.3 Phase 3：Skill 元数据与索引（v0.4）

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

- [ ] skills 数量多时快速检索
- [ ] 某些 skill 只适用于特定工具，不需要全量同步
- [ ] 通过标签实现比目录结构更灵活的分类

---

### 5.4 Phase 4：Watch 模式与自动化（v0.5）

**目标**：减少手动执行同步的频率。

#### 5.4.1 文件监听

```bash
sync-skills watch    # 监听源目录和所有目标目录的变更，自动同步
```

使用 `watchdog` 或 `fsevents`（macOS）监听文件变更，检测到变化时自动执行同步。需要防抖（debounce）避免频繁触发。

#### 5.4.2 Git Hook 集成

```bash
sync-skills install-hook    # 在 ~/Skills 的 git repo 中安装 post-commit hook
```

每次在 skills 仓库提交后自动同步到所有目标。

#### 5.4.3 LaunchAgent（macOS）/ Systemd（Linux）

```bash
sync-skills service install    # 安装为系统服务，开机自动运行 watch 模式
sync-skills service status     # 查看服务状态
sync-skills service uninstall  # 卸载服务
```

#### 5.4.4 要解决的问题

- [ ] 消除"忘记同步"的问题
- [ ] 在任意工具中修改 skill 后实时生效到其他工具
- [ ] 支持作为后台服务运行

---

### 5.5 Phase 5：多端与协作（v1.0 远期）

**目标**：支持跨设备同步、团队共享。

#### 5.5.1 Git 仓库作为远程存储

`~/Skills/` 本身就是一个 git 仓库，通过 git push/pull 实现跨设备同步：

```bash
sync-skills remote setup     # 初始化 ~/Skills 为 git 仓库并关联远程
sync-skills remote push      # 推送本地变更
sync-skills remote pull      # 拉取远程变更
```

#### 5.5.2 Skill 市场 / 共享仓库

```bash
sync-skills install gh:username/skill-name    # 从 GitHub 安装单个 skill
sync-skills install gh:username/skill-pack    # 安装 skill 合集
sync-skills publish code-review               # 发布到共享仓库
```

#### 5.5.3 要解决的问题

- [ ] 多台设备间的 skills 同步
- [ ] 团队内部共享 skills
- [ ] 从社区获取优质 skills

---

### 5.6 Phase 6：Skill 化封装（v1.1 远期）

**目标**：将 sync-skills CLI 工具本身封装为一个 skill，让 AI 编码工具可以代替用户操作。

#### 5.6.1 动机

- CLI 工具是基础层，面向有命令行经验的开发者
- 但很多用户没有命令行基础，更习惯用自然语言交互
- AI 编码工具（Claude Code、Codex 等）天然适合作为中间层，将用户意图翻译为 CLI 命令
- 形成自举闭环：sync-skills 管理所有 skill，其中一个 skill 就是 sync-skills 自身的操作指南

#### 5.6.2 设计思路

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

#### 5.6.3 前置条件

- Phase 1 完成（PyPI 发布，用户已通过 `uv tool install` 安装）
- CLI 命令接口稳定

#### 5.6.4 要解决的问题

- [ ] 编写清晰的 SKILL.md，覆盖所有常用操作场景
- [ ] 处理交互式确认（skill 中需指导 AI 使用 `-y` 跳过确认，或正确处理 stdin）
- [ ] 错误场景的自然语言反馈

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

- 降低安装门槛，可以直接 `./sync_skills.py` 运行
- skill 文件都是小文本文件，不需要复杂的并发或流式处理
- 零外部依赖，避免环境问题
- 后续如果复杂度增长，再拆分模块

### 6.3 为什么默认收集到 `Other/` 分类？

双向同步时，目标目录中发现的新 skill 无法自动推断它应该属于哪个分类。放到 `Other/` 是最安全的默认行为，用户可以随后手动移动到合适的分类目录。

---

## 7. 变更日志

按时间倒序记录每次讨论的关键决策、代码变更和待办事项。

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

### 2026-03-28 新增 delete 命令

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
