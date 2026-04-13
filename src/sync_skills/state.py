"""状态文件管理

通过 ~/.config/sync-skills/skills.json 跟踪哪些 skill 已纳入 sync-skills 管理。
格式与 npx skills 的 lock file 一致：{ "skills": { "name": { "source": "sync-skills" } } }
"""

import json
import sys
from pathlib import Path

from .constants import STATE_FILE


# ============================================================
# 状态文件读写
# ============================================================

def load_state(state_path: Path | None = None) -> dict:
    """加载状态文件，不存在或格式错误时返回空结构。

    返回: { "skills": { "name": { "source": "sync-skills" }, ... } }
    """
    path = state_path or STATE_FILE
    if not path.is_file():
        return {"skills": {}}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"skills": {}}
        if "skills" not in data or not isinstance(data["skills"], dict):
            data["skills"] = {}
        return data
    except (json.JSONDecodeError, OSError) as e:
        print(f"[WARNING] 状态文件读取失败 ({path}): {e}", file=sys.stderr)
        return {"skills": {}}


def save_state(state: dict, state_path: Path | None = None) -> None:
    """保存状态文件到磁盘。"""
    path = state_path or STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")


# ============================================================
# 查询操作
# ============================================================

def get_managed_skills(state_path: Path | None = None) -> set[str]:
    """获取所有已管理 skill 名称集合。"""
    state = load_state(state_path)
    return set(state["skills"].keys())


def is_managed(name: str, state_path: Path | None = None) -> bool:
    """检查 skill 是否已纳入管理。"""
    return name in get_managed_skills(state_path)


# ============================================================
# 写入操作
# ============================================================

def add_managed(name: str, state_path: Path | None = None) -> None:
    """将 skill 加入管理（写入状态文件）。"""
    path = state_path or STATE_FILE
    state = load_state(path)
    state["skills"][name] = {"source": "sync-skills"}
    save_state(state, path)


def remove_managed(name: str, state_path: Path | None = None) -> None:
    """将 skill 从管理中移除（写入状态文件）。"""
    path = state_path or STATE_FILE
    state = load_state(path)
    state["skills"].pop(name, None)
    save_state(state, path)
