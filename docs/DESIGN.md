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

## 12. 变更日志

按时间倒序记录每次讨论的关键决策、代码变更和待办事项。

### 2026-04-19 v1.1 文档重写：按当前实现整体校准 DESIGN.md

**讨论内容**：
旧版 DESIGN.md 已严重偏离当前实现，仍在描述 v1.0 两层 symlink、lock file、external skill、uninstall/fix 主流程等内容，容易误导后续开发与维护。

**关键决策**：
- 整体重写 DESIGN.md，而不是继续在旧结构上打补丁
- 以当前代码实现为准，明确主架构是 **git + 单层 symlink + state file**
- 明确区分两条路径：v1.1 lifecycle manager 与 legacy copy mode
- 将 `doctor` 定义为当前主架构下的核心修复命令
- 保留历史变更日志，但不再把过时架构叙述放在“当前架构”章节

**文档更新**：
- 重写第 1-11 节，替换为与当前实现一致的定位、架构、命令模型、限制和路线图
- 保留并追加第 12 节变更日志

### 2026-04-14 v1.1.1：init 预览增强 + 自动提交

**讨论内容**：
init 命令的预览只显示汇总数字（"为 14 个 skill 创建/修复 symlink"），无法看到具体哪些 skill 需要操作、涉及哪些 agent 目录。同时，add/remove/link/unlink 操作修改 repo 后需要手动 push，缺少自动 commit 步骤，容易遗忘提交。

**关键决策**：
- **init 预览展示 symlink 详情**：预检每个 skill 的 symlink 状态（通过 `verify_links`），在确认前逐行展示每个 skill 的操作类型（✓ 已验证 / + 将创建 / ! 需修复）和涉及的 agent 目录
- **自动 commit**：add/remove/link/unlink 四个修改 repo 的操作完成后自动调用 `git add -A + commit`，commit 消息包含命令名、skill 名和时间戳（如 `add: content-rewriter (2026-04-14 15:30)`）
- **无变更跳过**：`git_add_commit` 内置 `is_clean` 检查，无变更时不产生空 commit
- **dry_run 不触发**：预览模式直接 return，不会走到 commit 逻辑

**代码变更**：
- `lifecycle.py`：新增 `_auto_commit(config, command, skills)` 辅助函数；`add_skill`/`remove_skill`/`link_skill` 末尾调用 `_auto_commit`；`unlink_skill` 在指定 names 和 --all 两个分支中收集成功 unlinked 的 skill 名后调用 `_auto_commit`；`init_repo` 预览部分用 `verify_links` 预检每个 skill 的 symlink 状态，逐行展示 ✓/+/! 状态和涉及的 agent 目录
- `symlink.py`：`verify_links` 新增导出（lifecycle.py import）

**测试变更**：
- 无新增测试（209 个测试全部通过，现有测试覆盖 dry_run 路径不受影响）

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
