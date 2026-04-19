# sync-skills 设计文档

本文档描述当前实现、当前产品边界以及当前架构选择。

- 历史版本演进写入 `CHANGELOG.md`
- 用户故事与阶段定义写入 `docs/USER_STORIES.md`

---

## 1. 产品定位

`sync-skills` 当前的核心定位是：

> 自建 Skill 的全生命周期管理器

它是一个 **author-first、Git-first、repo-first** 的工具，而不是一个 Skill 下载器或 Skill 商店。

它优先解决的问题是：

- 我自己创建了一个 Skill，如何开始管理它
- 我如何持续修改它并保留版本历史
- 我如何让多个 Agent 同时看到它
- 我如何把它推到 GitHub 做备份、分享和多机同步
- 我如何删除它、停止托管它或修复它的本地状态

它当前不优先解决的问题是：

- 如何搜索互联网上的 Skill
- 如何一键安装别人的单个 Skill
- 如何把单个 Skill 发布成独立 package

---

## 2. 生命周期模型

当前产品模型以“一个个人 Skill 仓库”为中心。

生命周期顺序是：

```text
创建 / 纳管
-> 迭代
-> 本地分发
-> 远程备份 / 分享
-> 多机同步
-> 删除 / 下线
```

### 2.1 生命周期单位

当前实现的生命周期单位是：

- 管理边界：单个 Skill
- 存储边界：整个 Skill 仓库
- 远程同步边界：整个 Skill 仓库

这意味着：

- 本地管理以 Skill 为单位
- 远程备份与分享以 repository 为单位
- 当前没有“单 Skill 独立发布 / 独立安装”这层抽象

### 2.2 为什么是 repo-first

因为当前最真实的主场景不是“消费外部 Skill”，而是“持续维护自己写的 Skill”。

repo-first 带来的直接收益：

- Skill 有明确唯一来源
- Git 天然承担历史和回滚
- symlink 天然承担多 Agent 可见性
- GitHub 远程仓库天然承担备份、分享和多机同步
- 不需要先设计 registry 才能让产品成立

---

## 3. 当前架构

### 3.1 核心组件

| 组件 | 默认路径 | 角色 |
|------|----------|------|
| Git 仓库 | `~/Skills` | 个人 Skill 仓库，也是远程同步单位 |
| Skill 真实目录 | `~/Skills/skills/<name>/` | managed Skill 的唯一真实来源 |
| Agent 目录 | `~/.agents/skills`、`~/.claude/skills`、`~/.codex/skills`、`~/.gemini/skills`、`~/.openclaw/skills` | 各 Agent 实际读取 Skill 的目录 |
| 状态文件 | `~/.config/sync-skills/skills.json` | 记录哪些 Skill 由本工具托管 |

### 3.2 单层 symlink 模型

当前实现使用 repo 到 Agent 目录的单层 symlink：

```text
~/Skills/skills/<name>/        ← 唯一真实文件
  ├── symlink → ~/.agents/skills/<name>/
  ├── symlink → ~/.claude/skills/<name>/
  ├── symlink → ~/.codex/skills/<name>/
  ├── symlink → ~/.gemini/skills/<name>/
  └── symlink → ~/.openclaw/skills/<name>/
```

设计含义：

- repo 是唯一真实来源
- Agent 目录只暴露入口，不存多份副本
- 本地“分发”由 symlink 完成，而不是复制同步

### 3.3 状态文件模型

状态文件格式：

```json
{
  "skills": {
    "my-skill": { "source": "sync-skills" }
  }
}
```

状态文件表达的是“托管边界”，而不是文件存在性。

当前实现中它用于：

- 区分 managed Skill 与 unknown Skill
- 支撑 `classification`
- 支撑 `doctor` 的对齐和修复逻辑
- 表达 `unlink` 之后的状态变化

设计结论：

- 是否有 symlink 不是 managed 的判定依据
- 是否在 repo 中出现也不是完整判定依据
- 托管关系必须由显式状态文件表达

### 3.4 GitHub / 远程仓库的角色

当前远程仓库承担的职责是：

- 个人 Skill 仓库备份
- 仓库级分享
- 多机同步

当前远程模型不是：

- 单 Skill registry
- 单 Skill package publish/install
- 远程依赖解析系统

### 3.5 项目自带 `SKILL.md` 的角色

仓库自带 `skills/sync-skills/SKILL.md`，它不是产品功能本身，而是项目对 Agent 的调用契约。

它当前承担的职责是：

- 提示 Agent 何时应该触发 `sync-skills`
- 在“创建 / 更新 / 删除 Skill”之后，把流程接管到正确的生命周期命令
- 约束 Agent 优先使用 `new`、`link`、`status`、`commit`、`push`、`pull`、`doctor`、`unlink`、`remove`
- 在执行前先做 `sync-skills` / `git` 可用性检查，并在缺失时提供安装指引

设计结论：

- `SKILL.md` 是 Agent 工作流入口，不是另一套产品模型
- `SKILL.md` 必须跟随当前实现同步更新，不能漂移到旧的 copy-mode 或单 Skill 发布叙事
- 文档与 `SKILL.md` 的定位必须一致：都服务于 repo-first 的自建 Skill 生命周期管理

---

## 4. 当前命令模型

### 4.1 生命周期命令

| 命令 | 生命周期角色 |
|------|--------------|
| `init` | 初始化或接管个人 Skill 仓库，并建立本地分发关系 |
| `new` | 创建新的自建 Skill |
| `link` | 将已有 Skill 纳入统一托管 |
| `unlink` | 停止托管某个 Skill，但保留 Agent 目录中的真实文件 |
| `remove` | 彻底删除已托管 Skill |
| `status` | 查看仓库状态、托管状态和异常摘要 |
| `doctor` | 修复状态文件与 symlink 异常 |
| `commit` | 做本地版本提交 |
| `push` | 将个人 Skill 仓库推到远程 |
| `pull` | 从远程拉取仓库更新并恢复本地可见性 |

### 4.2 这些命令如何对应生命周期

#### 创建 / 纳管

- `new`：从零创建一个 Skill
- `link`：把已有 Skill 收进 repo

#### 迭代 / 版本管理

- 直接编辑 repo 中的 Skill，或编辑其 symlink
- `commit` / `push`
- 生命周期命令成功后还会自动提交

#### 本地分发

- `init` 负责建立初始分发关系
- `doctor` 负责修复后续分发关系

#### 远程备份 / 分享 / 多机同步

- `push` 将整个 Skill 仓库推到远程
- `pull` 将整个 Skill 仓库拉回本地
- 另一台机器通过 `init` 接入该仓库，再用 `pull` 持续同步

#### 删除 / 下线

- `remove`：彻底删除
- `unlink`：停止托管但保留 Agent 目录中的内容

### 4.3 为什么当前不必须引入 `publish / import / install-from-git`

这些命令对应的是另一层产品能力：

- `publish`：把单个 Skill 抽象成一个独立发布单元
- `import`：从外部仓库引入单个 Skill 到当前 repo
- `install-from-git`：从 Git URL 直接安装单个 Skill

它们只有在你要支持 **单 Skill 粒度的公共分发与消费** 时才成为刚需。

而当前产品主模型是：

- 我维护自己的 Skill 仓库
- 我把自己的 Skill 分发给自己的多个 Agent
- 我把整个仓库推到 GitHub 做备份、分享和多机同步

在这个模型里，`init + push + pull` 已经足够支撑主场景。

所以设计结论是：

- 这些命令可以是未来扩展
- 但它们不是当前定位成立的前提

### 4.4 Agent 路由约束

项目当前要求 Agent 侧遵循如下路由：

- brand-new Skill -> `new`
- 已有真实 Skill 内容 -> `link`
- 已管理 Skill 被更新 -> `status` 后进入 `commit` 或 `push`
- 另一台机器恢复 -> `pull`，必要时继续 `doctor`
- 停止托管但保留内容 -> `unlink`
- 完整删除 -> `remove`

这是当前 `skills/sync-skills/SKILL.md` 与产品文档需要共同表达的最小契约。

---

## 5. 当前实现映射

### 5.1 创建与纳管

- `new` 会创建 Skill 骨架
- `link` 会扫描 repo 与 Agent 目录中的真实目录
- 多版本候选通过 MD5 分组和修改时间选择

### 5.2 迭代与版本

- 新 Skill 默认带 `version: 0.0.1`
- `commit` / `push` / 生命周期自动提交共享同一套提交前版本处理逻辑
- 当前版本递增策略是 patch bump

### 5.3 本地分发

- `init` 建立 symlink
- `doctor` 修复缺链、断链和错误目标
- `status` 提供只读状态视图

### 5.4 远程同步

- `push` 是仓库级推送
- `pull` 是仓库级拉取
- 当前分享粒度仍然是整个 repo，而不是单 Skill

### 5.5 删除与下线

- `remove` 是彻底删除
- `unlink` 是停止托管

---

## 6. 当前能力边界

### 6.1 明确支持的能力

- 自建 Skill 的创建
- 自建 Skill 的纳管
- Git 版本管理
- 多 Agent 本地可见
- GitHub 仓库级备份与分享
- 多机之间的仓库同步
- 删除 / 停止托管 / 状态修复

### 6.2 当前不作为主目标的能力

- 搜索公网 Skill
- 管理别人发布的 Skill 包
- 安装任意 Git URL 下的单个 Skill
- 单 Skill registry / package publish

### 6.3 当前已知缺口

- v1 `list` 与 legacy `list/search/info` 还存在入口竞争
- `status` 已有生命周期摘要，但还缺少按 Agent 维度的暴露明细
- `init` / `pull` / `doctor` 的多机恢复链路还可以继续收敛成更直接的恢复体验
- 当前远程分享仍然是 repo 级，而不是单 Skill 粒度

---

## 7. Legacy Copy 模式

legacy copy 模式仍保留在 `sync_legacy.py` 中，但它只是兼容层，不代表当前产品主叙事。

它继续存在的原因是：

- 兼容旧命令
- 保留旧测试场景
- 平滑承接历史行为

但它不应该再主导产品定位。

当前推荐叙事始终是：

```text
自建 Skill 生命周期管理
+ Git
+ symlink
+ repo-first
```

---

## 8. 技术决策

### 8.1 为什么使用状态文件

如果只靠 repo 或 Agent 目录扫描来推断托管边界，会出现：

- 无法区分用户手工目录和已托管目录
- 无法准确表达 `unlink` 之后的状态
- 出现异常时难以判断修复责任

所以状态文件是必要的。

### 8.2 为什么使用单层 symlink

因为它最直接地服务了“本地多 Agent 分发”这个主场景：

- repo 唯一真实来源
- Agent 可见性低成本
- 修复逻辑简单
- 不需要复制多份内容

### 8.3 为什么当前坚持 repo-first

因为 repo-first 更贴近“个人 Skill 资产”的实际使用方式：

- 它本来就会持续演化
- 它本来就需要历史
- 它本来就需要备份和多机同步

相比之下，“单 Skill 包发布 / 消费”是后续更高一层的分发模型，而不是第一步。

---

## 9. 维护约定

- `README.md` 负责对外说明产品定位和使用方式
- `docs/DESIGN.md` 负责说明当前产品边界与架构选择
- `docs/USER_STORIES.md` 负责记录使用阶段和用户故事
- `CHANGELOG.md` 负责记录历史变更

文档冲突时，以代码实现为准。

## Roadmap

当前 roadmap 只补强 `author-first`、`Git-first`、`repo-first` 这条主线，不扩展单 Skill 包发布模型。
Roadmap 暂不单独拆文档：`docs/DESIGN.md` 保留产品级条目，`docs/USER_STORIES.md` 保留故事级条目，两者一起作为当前状态的最新表达。
其中 P0-1 到 P0-3 已完成，保留在此作为里程碑记录，避免状态长期滞后。

### P0-1 `doctor --dry-run` 真正只读（已完成）

已实现为纯预演模式。执行时只输出拟修复动作、跳过原因和无操作结果，不改写 state，不创建或删除 symlink，也不修改目录结构。没有待修复项时直接成功退出，不再要求额外确认。

### P0-2 `status` 生命周期状态补全（已完成）

`status` 已显式报告 `managed`、`unknown`、`broken link`、`real directory conflict`、`orphaned`、`managed but not exposed` 等状态，已经成为生命周期健康视图，而不是简单列表输出。

### P0-3 state 残留与 orphaned 收口（已完成）

已为 orphaned 和残留 state 建立明确修复路径。`status` 负责暴露异常，`doctor` 负责收口与修复，当前实现、测试和文档已按这一状态转移规则对齐。

### P1-1 Git 异常恢复路径（已完成）

当前已经具备 `commit`、`push`、`pull` 主流程，并已覆盖这条主线下的关键失败场景：`git` 不可用、首次 upstream 建立、未配置远程、无改动提交、本地领先或落后、与远程分叉、认证失败、detached HEAD、`pull --rebase` 冲突、本地未提交改动和远程分支缺失等。当前策略不是自动处理所有问题，而是准确识别、明确提示并安全退出。

### P1-2 现有仓库接入与多机恢复体验

在 repo-first 模型下，更重要的问题不是“安装一个 Skill”，而是“如何接管一个已有 Skill 仓库并恢复本机可见性”。后续需要继续优化 `init`、`pull`、`doctor` 这条恢复链路，让换机或新环境接入更直接。

### P1-3 多 Agent 目标管理可见性

随着同一个 Skill 同时服务多个 Agent，工具需要更明确地呈现每个 Skill 当前暴露到了哪些 Agent、哪些目标缺失、哪些目标不可写，以及 `link` 和 `unlink` 实际影响了哪些路径。

### P1-4 统一 v1 与 legacy 查询入口

当前 `list` 与 legacy `list/search/info` 还存在入口竞争。后续需要明确两套模式的命令边界，避免新旧路由共享同一入口而造成行为歧义。

### 长期方向（已记录，但暂不纳入当前阶段）

以下方向已经在 roadmap 中留档，但不属于当前主线，因此暂不纳入本阶段实现：

- 搜索公网 Skill
- 管理别人发布的 Skill 包
- 安装任意 Git URL 下的单个 Skill
- 将当前 repo 级远程分享扩展为单 Skill 粒度
- 单 Skill registry / package publish
