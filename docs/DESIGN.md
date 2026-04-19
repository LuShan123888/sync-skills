# sync-skills 设计文档

本文档只描述当前代码实现与当前设计边界。
版本演进、历史变更和发布记录统一写入根目录 `CHANGELOG.md`。

---

## 1. 项目定位

`sync-skills` 当前是一个面向多 Agent 环境的 **自定义 Skill 生命周期管理器**。

它解决的问题不是“把所有目录做一遍同步”，而是：

- 将用户自己维护的 custom skills 收敛到一个 Git 仓库中统一管理
- 通过单层 symlink 将这些 custom skills 暴露给多个 Agent skills 目录
- 通过状态文件明确哪些 skill 由 `sync-skills` 托管
- 保留 legacy copy 模式，仅用于兼容历史命令和旧配置

当前主路径是 `git + state file + repo -> agent 单层 symlink`。

---

## 2. 当前架构

### 2.1 核心组件

| 组件 | 默认路径 | 角色 |
|------|----------|------|
| Git 仓库 | `~/Skills` | custom skills 的版本管理仓库 |
| Skill 真实目录 | `~/Skills/skills/<name>/` | managed skill 的唯一真实来源 |
| Agent 目录 | `~/.agents/skills`、`~/.claude/skills`、`~/.codex/skills`、`~/.gemini/skills`、`~/.openclaw/skills` | Agent 实际读取 skill 的目录 |
| 状态文件 | `~/.config/sync-skills/skills.json` | 记录哪些 skill 已纳入管理 |

### 2.2 单层 symlink 模型

当前实现不再使用中转目录，也不再使用两层软链。

```text
~/Skills/skills/<name>/        ← 唯一真实文件
  ├── symlink → ~/.agents/skills/<name>/
  ├── symlink → ~/.claude/skills/<name>/
  ├── symlink → ~/.codex/skills/<name>/
  ├── symlink → ~/.gemini/skills/<name>/
  └── symlink → ~/.openclaw/skills/<name>/
```

实现约束：

- 进入 managed 状态后，repo 是唯一真实来源
- Agent 目录中的 managed skill 正常情况下应当是指向 repo 的 symlink
- `doctor` 会修缺链、断链、错误目标 symlink
- `doctor` 默认不会自动覆盖现有真实目录

### 2.3 状态文件模型

状态文件格式如下：

```json
{
  "skills": {
    "git-commit": { "source": "sync-skills" },
    "content-rewriter": { "source": "sync-skills" }
  }
}
```

当前实现依赖它表达“谁被管理”：

- `classification` 以状态文件而不是隐式扫描来判断 managed / unknown
- `doctor` 会将 repo 中存在但未登记的 skill 自动补登记到状态文件
- repo 中不存在但状态文件仍保留的项会被视为 orphaned
- 是否存在 symlink 不是 managed 的判定依据

### 2.4 配置文件

配置文件位于 `~/.config/sync-skills/config.toml`。

当前主路径核心字段：

```toml
repo = "~/Skills"
state_file = "~/.config/sync-skills/skills.json"
agent_dirs = [
  "~/.agents/skills",
  "~/.claude/skills",
  "~/.codex/skills",
  "~/.gemini/skills",
  "~/.openclaw/skills",
]
```

字段说明：

- `repo`：Git 仓库根目录
- `state_file`：托管状态文件
- `agent_dirs`：显式启用的 Agent 目录；未配置时使用内置默认列表

为兼容 legacy copy 模式，配置中仍可能出现以下字段：

- `source`
- `targets`
- `sync.exclude_tags`

这些字段只在 legacy 路径中生效，不属于 v1 主架构事实源。

---

## 3. 当前命令模型

### 3.1 v1 主命令

当前解析器暴露的 v1 命令为：

```bash
sync-skills init
sync-skills new <name>
sync-skills link <name>
sync-skills unlink <name>
sync-skills unlink --all
sync-skills remove <name...>
sync-skills list
sync-skills status
sync-skills commit
sync-skills push
sync-skills pull
sync-skills doctor
```

命令职责：

| 命令 | 当前实现职责 |
|------|--------------|
| `init` | 初始化或接管 `repo`，选择 Agent 目录，扫描 repo 中已有 skill，补登记状态并预览/修复 symlink |
| `new` | 创建新的 skill 骨架，写入 `version: 0.0.1`，建链并自动提交 |
| `link` | 按名称扫描 repo 与 Agent 目录中的真实目录，选定一个版本纳管，删除其他副本，建链并自动提交 |
| `unlink` | 将 managed skill 从管理中移除，把 repo 中文件还原回 Agent 目录，再删除 repo 中该 skill，并自动提交 |
| `remove` | 删除 managed skill 的 repo 文件和 Agent 目录中的同名入口，并自动提交 |
| `list` | v1 代码中实现了“列出 managed skill”的逻辑 |
| `status` | 只读展示 Git 状态、托管状态、unregistered、orphaned、broken link 摘要 |
| `commit` | 预览后执行本地 `git add -A` + `commit` |
| `push` | 预览后执行 `commit`，有远程时再执行 `push` |
| `pull` | 预览后执行 `git pull --rebase`，成功后运行 `doctor` |
| `doctor` | 对齐 state / repo，并检查和修复 symlink |

### 3.2 兼容路由

当前主入口仍保留一层 legacy 路由，优先级高于部分 v1 子命令：

- `--copy` 直接进入 `sync_legacy.py`
- 旧参数 `--source`、`--targets`、`--force`、`--delete`、`-d`、`-f` 会自动路由到 legacy
- 裸调用的 `list`、`search`、`info` 也会优先路由到 legacy

这意味着：

- 代码中同时存在 v1 `list` 和 legacy `list`
- 常规 `sync-skills list` 会优先走 legacy 兼容路径
- 设计上这是兼容行为，不是新的推荐主流程

### 3.3 无操作时的确认策略

当前实现已尽量避免“明明没有待执行项仍要求确认”：

- `commit`：工作区干净时直接跳过
- `push`：无待提交改动且当前分支未领先远程时直接跳过
- `doctor`：无可修复项时不会进入确认
- `pull`：无远端更新时不会再做多余确认

---

## 4. 核心工作流

### 4.1 `init`

`init` 的当前流程：

1. 确认 repo 路径
2. 若 repo 已存在 Git 仓库，则沿用现有仓库；否则选择 `git clone` 或 `git init`
3. 交互式选择需要管理的 Agent 目录
4. 扫描 `repo/skills/` 中已有 skill
5. 将 repo 中已有但未登记的 skill 补写入状态文件
6. 预览每个 skill 的 symlink 状态
7. 创建缺失 symlink，修复断链/错误目标，报告真实目录冲突
8. 保存配置文件

实现特征：

- `init` 是幂等的
- `init` 不会自动提交 Git
- `init` 在 dry-run 下只打印预览

### 4.2 `new`

`new` 的当前流程：

1. 校验 skill 名称
2. 检查 repo 与 Agent 目录中是否已存在同名项
3. 在 `repo/skills/<name>/SKILL.md` 中写入骨架
4. 默认写入 `name`、`version: 0.0.1` 和 description 模板
5. 创建指向 repo 的单层 symlink
6. 写入状态文件
7. 自动提交

### 4.3 `link`

`link` 的当前流程：

1. 在 repo 与所有 Agent 目录里扫描同名真实目录
2. 用目录 MD5 对候选版本分组
3. 若内容相同，自动选择最新修改版本
4. 若内容不同，交互选择；`-y` 下自动选最新修改版本
5. 将选中版本复制到 repo
6. 删除其他真实副本
7. 在所有 Agent 目录创建 symlink
8. 写入状态文件
9. 自动提交

实现约束：

- `link` 不做内容级 merge
- 一旦纳管，最终只保留 repo 中那一份真实目录

### 4.4 `unlink`

`unlink` 的当前流程：

1. 校验目标 skill 当前是否为 managed
2. 将 repo 中的真实文件复制回每个 Agent 目录
3. 删除原有 symlink
4. 删除 repo 中该 skill
5. 从状态文件移除
6. 自动提交

实现细节：

- 若某个 Agent 目录已有同名真实目录，则跳过，不覆盖
- 若状态文件中有记录但 repo 中无文件，则只移除状态记录
- 支持 `unlink --all`

### 4.5 `remove`

`remove` 是彻底删除命令，当前行为比 `doctor` 更具破坏性：

1. 删除指向 repo 的 symlink
2. 删除 repo 中的 skill 目录
3. 从状态文件移除
4. 清理 Agent 目录中残留的同名入口
5. 自动提交

实现约束：

- `remove` 要求目标已被管理
- 它会主动清理 Agent 目录中的同名残留目录，不仅仅是删除 symlink

### 4.6 `doctor`

`doctor` 分两步工作：

1. 对齐状态文件和 repo
2. 检查并修复所有 managed skill 的 symlink

当前会处理的问题：

- repo 中存在但状态文件未登记的 skill：自动补登记
- symlink 缺失：自动创建
- 断链 symlink：自动修复
- 指向错误目标的 symlink：自动修复
- 真实目录冲突：报告；非 `-y` 模式下会询问是否替换为 symlink

当前不会自动做的事：

- 不会自动删除 orphaned 状态记录
- 不会自动解决多个真实目录之间的内容冲突
- `-y` 模式下遇到真实目录冲突时会直接跳过

### 4.7 `status`

`status` 只做检测，不做修复，当前输出包括：

- Git 分支与 ahead / behind
- 工作区 staged / modified / untracked
- managed skill 列表
- orphaned 项
- unregistered 项
- 缺失、断链、错误目标 symlink 的汇总结果

它不会主动报告真实目录冲突，因为 `_check_state()` 依赖的 `verify_links()` 会跳过非 symlink 真实目录。

---

## 5. Git 与版本号策略

### 5.1 Git 命令行为

当前 `commit` / `push` / `pull` 都会先输出预览，再决定是否执行。

`commit`：

- 工作区干净时直接返回
- 默认提交信息为 `update: <skill-or-count> (YYYY-MM-DD HH:MM)`

`push`：

- 若工作区干净且未领先远程，则直接跳过
- 无远程仓库时只做本地提交
- 有远程仓库时才执行 `git push`

`pull`：

- 执行前先检查 state / symlink 异常
- 发现异常时会建议先跑 `doctor`
- 成功后会自动执行一次 `doctor`

### 5.2 生命周期自动提交

以下命令成功后会自动提交：

- `new`
- `link`
- `unlink`
- `remove`

实现方式：

- 提交前统一调用 `git add -A`
- 自动提交是 repo 级提交，不限制到单个文件
- 自动提交 message 为 `<command>: <skill-or-count> (<timestamp>)`

注意：内部自动提交命令字目前来自实现层，`new` 对应的自动提交前缀仍是 `add`

### 5.3 Skill 版本号策略

当前所有提交流程共享同一套提交前版本处理逻辑：

- `new` 创建的新 skill 默认写入 `version: 0.0.1`
- `commit` / `push` / 生命周期自动提交都会在 `git add` 前检查变更 skill
- 如果某个 skill 的当前版本与 `HEAD` 中版本相同，则自动做 patch 递增
- 如果用户已经手动改过版本号，则不会再次自动递增
- 如果当前没有版本号，则会补写 `0.0.1`
- 如果版本号格式非法，会直接报错

这意味着版本号是“提交前对变更 skill 的自动维护”，而不是在编辑时即时维护。

---

## 6. 已知限制与实现边界

### 6.1 结构性限制

- managed 判定依赖状态文件；`skills.json` 被手工破坏时，系统会丢失精确边界
- `link` 只允许保留一个最终版本，不做 merge
- 进入 managed 状态后，repo 才是唯一真实来源；平行真实目录不再是受支持编辑入口
- legacy 与 v1 两条路径并存，理解成本高于纯单路径 CLI

### 6.2 当前实现限制

- `doctor --dry-run` 当前并未真正实现纯预览；现有代码仍会执行对齐和修复逻辑
- `status` 不会显式发现“Agent 目录中存在同名真实目录”的冲突
- v1 `list` 与 legacy `list` 同时存在，而主入口会优先把裸 `list` 路由到 legacy
- 自动提交使用 repo 级 `git add -A`，提交粒度不是文件级精确提交

---

## 7. Legacy Copy 模式

legacy copy 模式仍保留在 `sync_legacy.py` 中，当前定位是兼容层，而不是主架构。

它继续承载的能力包括：

- 基于 `source + targets` 的目录同步模型
- `--force`
- `--delete`
- 旧版 `list/search/info`
- frontmatter 过滤和历史测试场景

当前项目实际上是“双栈”：

- v1 主路径：custom skill lifecycle manager
- legacy 路径：历史 copy sync 执行后端

文档上必须明确区分两者，避免把 legacy 的叙事写成 v1 当前事实。

---

## 8. 技术决策

### 8.1 为什么使用状态文件

如果只靠 repo 或 Agent 目录扫描来反推“哪些 skill 归本工具管理”，会遇到三个问题：

- 无法区分用户手工目录与已纳管目录
- 无法表达 `unlink` 后的状态变化
- 出现异常时无法判断应由谁负责修复

因此当前实现坚持用显式状态文件表示 managed 边界。

### 8.2 为什么使用单层 symlink

单层 symlink 的主要收益：

- repo 是唯一真实来源，结构更直接
- `doctor` 更容易判断正确目标
- 避免两层 symlink 的中转复杂度和循环风险
- 与 Git 工作流自然贴合

### 8.3 为什么不让 `doctor` 默认覆盖真实目录

Agent 目录中的真实目录可能代表：

- 用户手工维护的 skill
- 其他工具生成的目录
- 尚未纳管的历史内容

因此当前策略是：

- symlink 异常自动修
- 真实目录冲突只提示或询问
- 真正的接管动作通过 `link` 完成

---

## 9. 维护约定

- `docs/DESIGN.md` 只描述当前实现、当前边界和当前设计约束
- `CHANGELOG.md` 负责记录历史演进、发布变化和用户可感知更新
- 两者冲突时，以代码实现为准
- 每次行为变化后，应同时判断是否需要更新 `CHANGELOG.md` 与 `docs/DESIGN.md`

文档冲突时的理解顺序：

1. 代码实现
2. `CHANGELOG.md`
3. `docs/DESIGN.md`
4. `README.md`
5. Agent 协作文档（`AGENTS.md` / `CLAUDE.md`）
