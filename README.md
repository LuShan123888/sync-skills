# Skills 同步工具

Skills 双向/强制同步工具，Python 实现。所有操作预览后需用户确认。

## 使用方法

```bash
# 双向同步（预览 + 确认）
./sync_skills.py

# 强制同步：以源目录为准，覆盖所有目标目录
./sync_skills.py --force

# 跳过确认
./sync_skills.py -y
./sync_skills.py --force -y

# 指定自定义源目录和目标目录
./sync_skills.py --source /path/to/source --targets /path/to/t1,/path/to/t2
```

## 参数

| 参数 | 说明 |
|------|------|
| `--force`, `-f` | 强制同步模式 |
| `-y`, `--yes` | 跳过确认 |
| `--source DIR` | 源目录路径（默认 `~/Skills`） |
| `--targets DIR1,DIR2` | 目标目录路径，逗号分隔 |

## 两种模式

**默认（双向同步）**：收集目标目录的新增/修改到源，再从源分发到所有目标。

**--force（强制同步）**：以源目录为准，删除目标中多余的、补齐缺少的。

无变更的目录直接跳过，不执行任何操作。

## 推荐工作流

```bash
# 日常同步
./sync_skills.py

# 删除某个 skill 后强制同步
rm -rf ~/Skills/某分类/某skill
./sync_skills.py --force
```

## 目录结构

```
sync-skills/
├── sync_skills.py      # 主程序
├── tests/
│   └── test_sync_skills.py  # 26 个回归测试
├── pyproject.toml       # uv 项目配置
└── README.md
```

- **源目录** `~/Skills`：分类结构（Code/、Lark/、Other/ 等）
- **目标目录**（平铺）：`~/.claude/skills`、`~/.codex/skills`、`~/.gemini/skills`、`~/.openclaw/skills`

## 开发

```bash
# 运行测试
uv run pytest tests/ -v

# 安装为命令行工具
uv pip install -e .
```
