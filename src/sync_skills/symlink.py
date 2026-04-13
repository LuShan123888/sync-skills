"""软链接管理

管理单层 symlink：
  ~/Skills/skills/<name> → ~/.agents/skills/<name>     （Agent 目录）
  ~/Skills/skills/<name> → ~/.claude/skills/<name>      （Agent 目录）
  ~/Skills/skills/<name> → ~/.codex/skills/<name>       （Agent 目录）
  ...
"""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path


# ============================================================
# 数据结构
# ============================================================

@dataclass
class LinkState:
    """单个 skill 的 symlink 状态"""
    name: str
    # 各 agent 目录的 symlink 状态
    agent_links_ok: list[str] = None
    agent_links_missing: list[str] = None
    agent_links_broken: list[str] = None
    agent_links_wrong_target: list[str] = None

    def __post_init__(self):
        if self.agent_links_ok is None:
            self.agent_links_ok = []
        if self.agent_links_missing is None:
            self.agent_links_missing = []
        if self.agent_links_broken is None:
            self.agent_links_broken = []
        if self.agent_links_wrong_target is None:
            self.agent_links_wrong_target = []


# ============================================================
# 软链接创建
# ============================================================

def create_agent_links(
    name: str,
    repo_skills_dir: Path,
    agent_dirs: list[Path],
) -> dict[str, bool]:
    """为所有 agent 目录创建 symlink: <agent-dir>/<name> → ~/Skills/skills/<name>。

    返回 {agent_name: success} 字典。
    """
    results = {}
    target = repo_skills_dir / name

    if not target.is_dir():
        return results

    for agent_dir in agent_dirs:
        agent_name = agent_dir.parent.name.lstrip(".")
        link = agent_dir / name

        # 已存在且正确
        if link.exists() or link.is_symlink():
            if link.is_symlink() and _resolve(link) == target.resolve():
                results[agent_name] = True
                continue
            # 指向错误目标或不是软链接，跳过
            if link.is_symlink() and _resolve(link) != target.resolve():
                results[agent_name] = True
                continue
            # 真实目录，不覆盖
            results[agent_name] = True
            continue

        # 不存在，创建
        link.parent.mkdir(parents=True, exist_ok=True)
        rel_target = os.path.relpath(target, link.parent)
        try:
            os.symlink(rel_target, link)
            results[agent_name] = True
        except OSError:
            results[agent_name] = False

    return results


def create_all_links(
    name: str,
    repo_skills_dir: Path,
    agent_dirs: list[Path],
) -> LinkState:
    """为一个 skill 创建完整的 symlink 链（自定义 Skill 仓库 → 所有 agent 目录）。"""
    state = LinkState(name=name)

    agent_results = create_agent_links(name, repo_skills_dir, agent_dirs)
    state.agent_links_ok = [a for a, ok in agent_results.items() if ok]
    state.agent_links_missing = [a for a, ok in agent_results.items() if not ok]

    return state


# ============================================================
# 软链接验证
# ============================================================

def verify_links(name: str, repo_skills_dir: Path, agent_dirs: list[Path]) -> LinkState:
    """验证一个 skill 的 symlink 状态（不修改）。"""
    state = LinkState(name=name)
    target = repo_skills_dir / name

    for agent_dir in agent_dirs:
        agent_name = agent_dir.parent.name.lstrip(".")
        link = agent_dir / name

        if not link.exists() and not link.is_symlink():
            state.agent_links_missing.append(agent_name)
        elif link.is_symlink() and not link.exists():
            state.agent_links_broken.append(agent_name)
        elif link.is_symlink():
            resolved = _resolve(link)
            if target.exists() and resolved == target.resolve():
                state.agent_links_ok.append(agent_name)
            elif target.exists():
                state.agent_links_wrong_target.append(agent_name)
            else:
                state.agent_links_broken.append(agent_name)
        else:
            # 真实目录（非 symlink），跳过
            pass

    return state


# ============================================================
# 软链接删除
# ============================================================

def remove_agent_links(name: str, agent_dirs: list[Path], repo_skills_dir: Path) -> list[str]:
    """删除 agent 目录 symlink。

    只删除指向 repo_skills_dir/<name> 的软链接。
    返回成功删除的 agent 名列表。
    """
    removed = []
    target = repo_skills_dir / name

    for agent_dir in agent_dirs:
        link = agent_dir / name
        if link.is_symlink() and _resolve(link) == target.resolve():
            link.unlink()
            removed.append(agent_dir.parent.name.lstrip("."))

    return removed


# ============================================================
# 批量同步
# ============================================================

def sync_all_links(
    repo_skills_dir: Path,
    agent_dirs: list[Path],
    managed_skills: set[str] | None = None,
) -> list[LinkState]:
    """验证/修复所有已管理 skill 的 symlink。

    遍历 managed_skills（状态文件）而非扫描 repo 目录。
    """
    managed = managed_skills or set()
    states = []

    for name in sorted(managed):
        state = verify_links(name, repo_skills_dir, agent_dirs)

        # 修复缺失的 agent symlink
        if state.agent_links_missing:
            results = create_agent_links(name, repo_skills_dir, agent_dirs)
            state.agent_links_ok = [a for a, ok in results.items() if ok]
            state.agent_links_missing = [a for a, ok in results.items() if not ok]

        states.append(state)

    return states


# ============================================================
# 辅助函数
# ============================================================

def _resolve(link: Path) -> Path:
    """解析软链接目标。"""
    try:
        return link.resolve()
    except OSError:
        return link


def _dirs_identical(dir1: Path, dir2: Path) -> bool:
    """简单比较两个目录是否包含相同的文件和内容。"""
    if not dir1.is_dir() or not dir2.is_dir():
        return False

    files1 = {f.relative_to(dir1) for f in dir1.rglob("*") if f.is_file() and not f.name.startswith(".")}
    files2 = {f.relative_to(dir2) for f in dir2.rglob("*") if f.is_file() and not f.name.startswith(".")}

    if files1 != files2:
        return False

    for rel in files1:
        try:
            if (dir1 / rel).read_bytes() != (dir2 / rel).read_bytes():
                return False
        except OSError:
            return False

    return True


# ============================================================
# 安全创建 + 批量检查修复（doctor 使用）
# ============================================================

def safe_create_link(
    name: str,
    repo_skills_dir: Path,
    agent_dir: Path,
    auto_confirm: bool = False,
) -> tuple[bool, str]:
    """安全创建 symlink，带覆盖风险检测。

    返回 (success, status):
    - (True, "created") — 新创建
    - (True, "repaired") — 修复断链/错误指向
    - (False, "conflict") — 存在真实目录，跳过
    - (False, "error") — 创建失败
    """
    import shutil

    link = agent_dir / name

    # 目标不存在 → 安全创建
    if not link.exists() and not link.is_symlink():
        link.parent.mkdir(parents=True, exist_ok=True)
        rel_target = os.path.relpath(repo_skills_dir / name, link.parent)
        try:
            os.symlink(rel_target, link)
            return True, "created"
        except OSError:
            return False, "error"

    # 是 symlink 但无效（断链或错误目标）→ 删除后重建
    if link.is_symlink():
        try:
            resolved = link.resolve()
            if not resolved.exists() or not resolved.is_dir():
                link.unlink()
        except OSError:
            link.unlink()
        link.parent.mkdir(parents=True, exist_ok=True)
        rel_target = os.path.relpath(repo_skills_dir / name, link.parent)
        try:
            os.symlink(rel_target, link)
            return True, "repaired"
        except OSError:
            return False, "error"

    # 存在真实目录 → 冲突，需要用户确认
    if auto_confirm:
        return False, "conflict"

    from .config import _unexpand_home

    try:
        confirm = input(
            f"  ⚠ {name}: {_unexpand_home(link)} 已存在且非 symlink，"
            f"是否替换为 symlink? [y/N] "
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n已跳过")
        return False, "conflict"
    if confirm == "y":
        shutil.rmtree(link)
        link.parent.mkdir(parents=True, exist_ok=True)
        rel_target = os.path.relpath(repo_skills_dir / name, link.parent)
        try:
            os.symlink(rel_target, link)
            return True, "repaired"
        except OSError:
            return False, "error"
    print("已跳过")
    return False, "conflict"


def check_and_repair_links(
    repo_skills_dir: Path,
    agent_dirs: list[Path],
    managed_skills: set[str],
    auto_confirm: bool = False,
) -> dict:
    """检查并修复 agent 目录中的 symlink，带覆盖风险检测。

    返回 {"repaired": [str], "conflicts": [str], "verified": int}
    """
    repaired = []
    conflicts = []
    verified = 0

    for name in sorted(managed_skills):
        repo_target = repo_skills_dir / name
        if not repo_target.is_dir():
            continue

        for agent_dir in agent_dirs:
            agent_name = agent_dir.parent.name.lstrip(".")
            link = agent_dir / name

            if not link.exists() and not link.is_symlink():
                # 缺失 symlink
                success, _ = safe_create_link(name, repo_skills_dir, agent_dir, auto_confirm)
                if success:
                    repaired.append(f"{name}: {agent_name} 缺失 symlink → 已创建")
                continue

            if not link.is_symlink():
                # 存在真实目录 → 冲突
                conflicts.append(f"{name}: {agent_name} 存在真实目录（非 symlink），跳过")
                continue

            # 是 symlink，检查状态
            try:
                resolved = link.resolve()
            except OSError:
                resolved = link

            if resolved == repo_target.resolve():
                # 正确指向 repo
                verified += 1
                continue

            # 断链或指向错误目标 → 尝试修复
            success, status = safe_create_link(name, repo_skills_dir, agent_dir, auto_confirm)
            if success:
                repaired.append(f"{name}: {agent_name} symlink 异常 → 已修复")
            elif status == "conflict":
                conflicts.append(f"{name}: {agent_name} 存在冲突，跳过")

    return {"repaired": repaired, "conflicts": conflicts, "verified": verified}
