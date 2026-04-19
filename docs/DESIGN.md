# sync-skills 设计文档

## 1. 项目定位

sync-skills 是一个面向多 Agent 环境的 **自定义 Skill 生命周期管理器**。

它解决的问题不是“把所有 skill 都同步一遍”，而是：

- 把用户自己维护的 custom skills 收敛到一个 git 仓库中统一管理
- 通过软链接把这些 custom skills 暴露给多个 AI Agent 目录
- 用状态文件明确哪些 skill 由 sync-skills 管理，避免误碰其他工具生成或安装的内容
- 保留旧版 copy 同步模式，兼容历史用法和旧配置

当前主架构是 **git + 单层 symlink + state file**。

---

## 2. 设计目标

### 2.1 当前目标

1. **单一真实来源**：custom skill 的真实文件只保存在 `~/Skills/skills/` 中
2. **多 Agent 可见**：Claude Code、Codex、Gemini、OpenClaw、Agents 等目录都能直接使用这些 skill
3. **最小侵入**：只管理明确纳入管理的 skill，不扫描即接管，不隐式覆盖其他真实目录
4. **可修复**：当 symlink 缺失、断链、状态文件不一致时，`doctor` 能发现并修复大部分异常
5. **向后兼容**：保留 `--copy` 旧模式和历史配置字段，避免一次性迁移成本过高

### 2.2 非目标

当前版本不追求：

- 自动管理所有外部 skill
- 自动监听文件变化并实时同步
- 内容级合并两个 skill 版本
- 在不确认来源的情况下接管 agent 目录中的任意 skill
- 替代通用 Git 工作流

---

## 3. 当前架构（v1.1）

### 3.1 核心模型

当前版本采用三部分模型：

| 组件 | 路径 | 角色 |
|------|------|------|
| Git 仓库 | `~/Skills/` | custom skills 的版本管理仓库 |
| Skill 真实目录 | `~/Skills/skills/<name>/` | custom skill 唯一真实来源 |
| Agent 目录 | `~/.agents/skills/`、`~/.claude/skills/`、`~/.codex/skills/`、`~/.gemini/skills/`、`~/.openclaw/skills/` | 各 Agent 实际读取 skill 的目录 |
| 状态文件 | `~/.config/sync-skills/skills.json` | 记录哪些 skill 由 sync-skills 管理 |

### 3.2 单层 symlink 关系

当前实现是 **repo 直接链接到各 agent 目录**，不再经过统一中转层。

```text
~/Skills/skills/<name>/      ← 真实文件（唯一来源）
       ├── symlink → ~/.agents/skills/<name>/
       ├── symlink → ~/.claude/skills/<name>/
       ├── symlink → ~/.codex/skills/<name>/
       ├── symlink → ~/.gemini/skills/<name>/
       └── symlink → ~/.openclaw/skills/<name>/
```

关键点：

- agent 目录里的 managed skill 正常情况下应当是一个 symlink
- 真实文件只存在于 repo 中
- agent 目录里的真实目录不会被默认覆盖
- 修复逻辑以“补链接”为主，不做无条件覆盖

### 3.3 状态文件是管理事实源

`skills.json` 的格式如下：

```json
{
  "skills": {
    "git-commit": {"source": "sync-skills"},
    "content-rewriter": {"source": "sync-skills"}
  }
}
```

状态文件的职责：

- 记录某个 skill 是否已纳入 sync-skills 管理
- 作为 `list`、`doctor`、`classification` 的主要依据
- 与 repo 做对齐：repo 里存在但未登记的 skill 可自动补登记

这意味着：

- “已管理”不是靠 lock file 判断
- “已管理”也不是靠 symlink 是否存在来反推
- 只要没有登记到 state file，sync-skills 默认不会把它当成 managed skill 处理

### 3.4 配置文件

配置文件位于：`~/.config/sync-skills/config.toml`

当前核心字段：

```toml
repo = "~/Skills"
state_file = "~/.config/sync-skills/skills.json"
agent_dirs = [
  "~/.agents/skills",
  "~/.claude/skills",
  "~/.codex/skills"
]
```

说明：

- `repo`：git 仓库根目录
- `state_file`：状态文件路径
- `agent_dirs`：启用的 Agent skills 目录；缺省时使用内置默认值

为兼容旧版 `--copy` 模式，配置中仍可保留：

- `source`
- `targets`
- `sync.exclude_tags`

但这些字段只在 legacy copy 模式中使用。

---

## 4. 当前命令模型

### 4.1 主命令集

当前默认命令集：

```bash
sync-skills init
sync-skills new <name>
sync-skills link <name>
sync-skills unlink <name>
sync-skills unlink --all
sync-skills remove <name>
sync-skills list
sync-skills status
sync-skills commit
sync-skills push
sync-skills pull
sync-skills doctor
```

这些命令服务的是 **custom skill 生命周期管理**，而不是旧版的“目录间 copy 同步”。

### 4.2 命令职责

| 命令 | 作用 |
|------|------|
| `init` | 初始化 repo / 配置 / agent 目录选择，并将 repo 中已有 skill 补登记到 state，补建 symlink |
| `new` | 在 repo 中创建一个新的 custom skill，并为所有 agent 目录创建 symlink |
| `link` | 从现有真实目录中按名称扫描 skill，将其纳入 repo 管理并统一建链 |
| `unlink` | 将 skill 从管理中移除，并把 repo 中的真实文件复制回 agent 目录 |
| `remove` | 从 repo 和 agent 目录中彻底删除 managed skill |
| `list` | 列出 state file 中的 managed skills |
| `status` | 展示 git 状态、managed/unregistered/orphan/broken 等状态 |
| `commit` | 在 repo 上执行 git add + commit |
| `push` | 在 repo 上 commit 并 push；无 remote 时只 commit |
| `pull` | git pull 后执行 doctor 修复链接 |
| `doctor` | 校验 state/repo/symlink 的一致性并修复可自动修复的问题 |

### 4.3 兼容行为

当前仍保留以下兼容层：

- `sync` / `fix`：兼容别名，内部映射到 `doctor`
- `--copy`：进入旧版 copy 同步引擎
- 旧参数如 `--force`、`--delete`、`--source`、`--targets`：自动路由到 legacy 模式
- 旧版 `list/search/info`：在 legacy 路径中继续可用

这意味着当前项目是“双栈”状态：

- **主路径**：v1.1 lifecycle manager
- **兼容路径**：v0.5/v0.6 legacy copy sync

---

## 5. 核心工作流

### 5.1 新建 skill

```text
sync-skills new <name>
  1. 在 ~/Skills/skills/<name>/ 创建 skill 骨架
  2. 写入 state file，标记为 managed
  3. 在所有 agent_dirs 创建 symlink
  4. 自动 commit repo 变更
```

适用场景：从零开始创建新的 custom skill。

### 5.2 纳入已有 skill

```text
sync-skills link <name>
  1. 按名称扫描 repo 和各 agent 目录中的真实目录
  2. 识别候选版本；有冲突时提示用户选择
  3. 将选中版本复制到 ~/Skills/skills/<name>/
  4. 删除其他候选真实目录（由 symlink 替代）
  5. 写入 state file
  6. 为所有 agent_dirs 创建 symlink
  7. 自动 commit repo 变更
```

适用场景：已经在某个 agent 目录里手工创建了一个 skill，希望交给 sync-skills 托管。

### 5.3 退出管理但保留 skill

```text
sync-skills unlink <name>
  1. 删除 state 中的 managed 标记
  2. 将 repo 中真实文件复制回各 agent 目录
  3. 删除 agent 目录中的 symlink
  4. 删除 repo 中该 skill
  5. 自动 commit repo 变更
```

注意：

- 如果某个 agent 目录已经存在同名真实目录，则不会覆盖
- `unlink --all` 对所有 managed skills 执行同样逻辑

### 5.4 彻底删除 skill

```text
sync-skills remove <name>
  1. 删除 agent 目录中指向 repo 的 symlink
  2. 删除 repo 中 skill 真实目录
  3. 从 state file 中移除该 skill
  4. 自动 commit repo 变更
```

适用场景：该 custom skill 不再需要。

### 5.5 修复异常状态

```text
sync-skills doctor
  1. 对齐 repo 与 state：repo 中存在但未登记的 skill 自动补登记
  2. 检查每个 managed skill 在各 agent dir 中的 symlink 状态
  3. 自动修复缺失、断链、错误目标 symlink
  4. 对真实目录冲突只报告，不强制覆盖
  5. 输出摘要和后续建议
```

`doctor` 是当前主架构下最重要的运维命令。

---

## 6. Git 设计

### 6.1 为什么要有 Git 仓库

custom skills 本质上就是用户自己维护的文档与脚本集合，因此需要：

- 可追踪历史
- 可回滚
- 可 push / pull 到远端备份
- 可通过 commit 形成稳定版本点

### 6.2 Git 相关命令定位

| 命令 | 定位 |
|------|------|
| `commit` | 只做本地提交 |
| `push` | 本地提交后推送到远端 |
| `pull` | 从远端拉取并修复链接 |

### 6.3 自动提交策略

以下生命周期命令会在成功修改 repo 后自动提交：

- `new`
- `link`
- `unlink`
- `remove`

这样做的目的：

- 避免用户做完结构性操作后忘记提交
- 保持 repo 状态和管理动作一致

当前实现倾向于“每个生命周期操作产生一个独立 commit”。

---

## 7. doctor / status 的职责边界

### 7.1 doctor 负责什么

`doctor` 负责三类问题：

1. **state 与 repo 不一致**
   - repo 中有 skill，但 state 没登记 → 自动补登记
2. **symlink 缺失或损坏**
   - 某个 managed skill 在某个 agent 目录缺链接、断链、指向错误 → 自动修复
3. **冲突提示**
   - 发现 agent 目录中是同名真实目录 → 提示有覆盖风险，不自动处理

### 7.2 doctor 不负责什么

`doctor` 当前不会：

- 自动删除 state 中多余的 orphan 记录
- 自动覆盖真实目录冲突
- 自动解决两个真实目录内容冲突
- 自动迁移未命名或无法识别来源的 skill

### 7.3 status 负责什么

`status` 是只读视角，主要输出：

- Git 分支、ahead/behind、工作区状态
- managed skill 总数
- repo 中存在但 state 未登记的 skill
- state 中登记但 repo 中不存在的 orphan 项
- 缺失或断链的 symlink

它的目标是“让用户知道当前哪里不对”，不是自动修复。

---

## 8. legacy copy 模式的定位

### 8.1 为什么保留

项目早期版本基于“扫描多个目录并执行 copy 同步”的模型，支持：

- 默认双向同步
- `--force` 强制以某个目录为基准
- `--delete` 一键删除
- frontmatter 过滤与旧版 list/search/info

这些能力现在仍然被保留在 `sync_legacy.py` 中，通过 `--copy` 或旧参数路由进入。

### 8.2 当前角色

legacy 模式现在的角色不是“默认主流程”，而是：

- 历史用户兼容层
- 老配置继续可用的执行后端
- 部分旧测试与旧使用习惯的承载层

### 8.3 与主架构的关系

两者并存，但定位不同：

| 路径 | 适用问题 |
|------|----------|
| v1.1 lifecycle manager | 管理用户自己的 custom skills |
| legacy copy sync | 旧版目录同步工作流 |

设计上应尽量避免把两套叙事混写。

---

## 9. 当前已知限制

### 9.1 架构限制

1. **managed 的判定依赖 state file**
   - 如果 `skills.json` 被手工破坏或删除，系统对“哪些 skill 归 sync-skills 管”会失去精确信息

2. **不做内容级合并**
   - `link` 遇到多个候选版本时，只能选一个保留，不会自动 merge

3. **真实目录默认不覆盖**
   - 这保证安全，但也意味着某些冲突无法自动修复，需要用户介入

4. **repo 是单一真实来源**
   - 一旦进入 managed 状态，后续正确编辑入口应当是 repo 或其 symlink，而不是在别处保留平行真实目录

### 9.2 当前实现限制

1. **`doctor --dry-run` 参数尚未真正生效**
   - CLI 暴露了参数，但当前 doctor 实现没有按 dry-run 分支执行预览逻辑

2. **`status` 的检查维度比 `doctor` 弱**
   - `doctor` 能修 wrong-target symlink，但 `status` 不一定完整报告这类问题

3. **自动提交粒度较粗**
   - 当前 Git 提交使用整体 add，文档层面应视为“提交 repo 中当前变更”，而不是精确到单个文件

4. **没有 watch / daemon 模式**
   - 当前仍是显式命令驱动，不会自动感知文件变化

### 9.3 兼容复杂性

由于当前同时维护 v1.1 和 legacy 两条路径，文档和实现都必须警惕以下问题：

- 不要把 legacy 的 `source/targets/exclude_tags/tools` 误写成 v1.1 主架构字段
- 不要把 v1.1 的 state file 模型误写成 lock file 模型
- 不要把 `doctor` 的职责与 legacy 的 `fix/sync` 复制语义混淆

---

## 10. 后续演进方向

### 10.1 近期

1. **补齐 DESIGN.md 与实现的一致性**
2. **让 `doctor --dry-run` 真正可用**
3. **让 `status` 覆盖 wrong-target 等更多异常类型**
4. **继续压缩 legacy 与主路径之间的认知混乱**

### 10.2 中期

1. 提供更清晰的 `link` 冲突交互
2. 为 `doctor` 增加更完整的机器可读报告
3. 优化 `unlink` / `remove` / `link` 的提交粒度与提示信息
4. 进一步明确“repo 初始化 / 远端仓库接入 / 首次迁移”的用户路径

### 10.3 远期

1. watch 模式或后台自动修复
2. 更细粒度的 state 校验与迁移工具
3. 在不破坏现有用户的前提下，逐步收缩 legacy copy 路径的表面积

---

## 11. 技术决策记录

### 11.1 为什么从 copy sync 转向 lifecycle manager

旧版 copy 模式适合“多个目录互相同步”，但不适合“明确管理一部分 custom skills”。

转向 lifecycle manager 的核心收益：

- 真实来源唯一
- Agent 目录不再存放一堆重复副本
- 可以通过 state file 明确管理边界
- 更适合和 Git 结合

### 11.2 为什么用 state file 而不是隐式扫描

如果只靠扫描 repo 或 agent 目录来反推“谁归谁管”，会有三个问题：

- 无法区分“用户手工放进去的真实目录”和“已纳入管理的 skill”
- 无法可靠表达 unlink 后的状态变化
- 一旦目录状态异常，很难判断应该修哪里

因此显式状态文件是必须的。

### 11.3 为什么不自动覆盖真实目录

真实目录可能代表：

- 用户手工维护的内容
- 其他工具生成的内容
- 尚未纳入管理的 skill

在来源不清楚时直接覆盖，风险太高。因此当前策略是：

- symlink 问题自动修
- 真实目录冲突只提示
- 需要迁移时用 `link` 明确接管

---

## 12. 设计演进记录

正式的发布与功能更新历史请查看仓库根目录的 `CHANGELOG.md`。

本节不再承担 changelog 职责，只保留设计演进层面的摘要，帮助后续理解“为什么会形成今天的结构”。

### 12.1 从目录同步工具到生命周期管理器

项目经历了三次核心叙事转换：

1. **v0.1 - v0.5**：以“源目录 + 多目标目录”的同步模型为主
2. **v0.6**：重构为去中心化 `SyncOp` 模型，源目录不再是绝对权威
3. **v1.0 - v1.1**：进一步转向 Git + symlink + state file 的 custom skill lifecycle manager

这三次转换的根本原因是：
- 早期模型适合同步目录，但不适合明确管理一部分 custom skills
- 进入多 Agent、多工具共存后，需要清晰的管理边界和唯一真实来源
- 需要把“同步”问题转化为“托管、自举、修复、提交”问题

### 12.2 为什么最终选择 state file + 单层 symlink

当前架构选择了：
- `skills.json` 作为管理事实源
- repo 作为唯一真实来源
- repo 直接 symlink 到各 Agent 目录

保留这一方案的主要原因：
- 能明确区分 managed skill 与其他真实目录
- 能在 `doctor` 中稳定判断应该修哪里
- 避免两层中转 symlink 带来的复杂度和循环风险
- 更适合和 Git 工作流结合

### 12.3 为什么保留 legacy copy 模式

虽然主架构已经转向 lifecycle manager，但 legacy copy 模式仍被保留在 `sync_legacy.py` 中。

保留它的原因：
- 要兼容早期用户的 `--source / --targets / --force / --delete` 使用方式
- 旧版设计中的用户场景（S1-S13）仍然有回归价值
- 一次性移除 legacy 路径会让历史配置和历史测试全部失效

因此当前项目长期处于“双栈”状态：
- 主路径：v1.1 lifecycle manager
- 兼容路径：legacy copy sync

### 12.4 当前设计演进关注点

后续在设计层面仍应重点关注：
- 如何继续压缩 legacy 与主路径之间的认知混乱
- 如何让 `doctor` / `status` 的职责边界更稳定
- 如何让 Git 工作流、Skill 版本号、生命周期命令保持统一行为
- 如何在不破坏现有用户的前提下继续收敛表面积

如果需要查看具体某个版本改了什么、增加了哪些命令或修复了哪些行为，请直接查阅 `CHANGELOG.md`。

---

## 13. 历史里程碑索引

为了便于从设计角度快速定位历史阶段，保留一个最简索引：

- `v0.1`：初始同步模型与用户场景驱动设计
- `v0.2`：delete 命令
- `v0.3`：哈希冲突检测、基准目录选择、src/ 包结构、init
- `v0.4.0`：元数据、搜索、选择性同步
- `v0.5.0`：dry-run 与 Skill 化封装
- `v0.6.0`：去中心化 SyncOp 同步模型
- `v1.0.0`：自定义 Skill 生命周期管理器
- `v1.0.1`：健壮性增强、外部 Skill 隔离、fix/push/pull 完善
- `v1.1.0`：单层 symlink + state file 主架构定型
- `v1.1.1`：init 预览增强 + 自动提交；后续新增独立 commit 命令与 Git 预览增强
- `v1.1.2`：doctor 交互修复 + 测试体系补强
- `v1.1.3`：提交前自动维护 Skill 版本号

完整版本说明与用户可感知变更，请看 `CHANGELOG.md`。

---

## 14. 维护约定

- **正式更新历史**：写入根目录 `CHANGELOG.md`
- **架构/设计背景**：写入 `docs/DESIGN.md`
- **每次功能迭代后**：同时检查两者是否需要更新
- **历史遗漏补写**：优先通过 Git 记录回溯后补齐

未来如果再次出现“CHANGELOG 和 DESIGN 混在一起”的倾向，应优先把职责拆清，而不是继续在一个文档里叠加两种用途。

---

## 15. 参考

- 正式更新历史：`CHANGELOG.md`
- 当前架构与设计背景：本文件
- Agent 使用方式与项目协作约束：`CLAUDE.md` / `AGENTS.md`
- 面向用户的使用说明：`README.md`

如果文档间出现冲突，优先按以下顺序理解：
1. 代码实现
2. `CHANGELOG.md`（历史变化）
3. `docs/DESIGN.md`（当前架构与设计背景）
4. `README.md`（使用说明）
5. Agent 协作文档（`CLAUDE.md` / `AGENTS.md`）

发现历史遗漏时，应先从 Git 记录回溯，再决定是补写到 `CHANGELOG.md` 还是 `docs/DESIGN.md`。
