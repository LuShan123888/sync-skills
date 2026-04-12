"""软链接管理

管理两层 symlink：
  ~/.agents/skills/<name> → ~/Skills/skills/<name>     （统一 Skill 目录）
  ~/.claude/skills/<name>  → ~/.agents/skills/<name>    （Agent Skill 目录）
"""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .constants import DEFAULT_AGENT_DIRS


# ============================================================
# 数据结构
# ============================================================

@dataclass
class LinkState:
    """单个 skill 的 symlink 状态"""
    name: str
    # ~/.agents/skills/<name> → ~/Skills/skills/<name>（统一 Skill 目录）
    agents_link_exists: bool = False
    agents_link_valid: bool = False
    agents_link_broken: bool = False
    agents_link_wrong_target: bool = False
    # Agent Skill 目录（~/.claude/skills/<name> 等）
    agent_links_ok: list[str] = None
    agent_links_missing: list[str] = None
    agent_links_broken: list[str] = None

    def __post_init__(self):
        if self.agent_links_ok is None:
            self.agent_links_ok = []
        if self.agent_links_missing is None:
            self.agent_links_missing = []
        if self.agent_links_broken is None:
            self.agent_links_broken = []


# ============================================================
# 软链接创建
# ============================================================

def create_agents_link(name: str, agents_dir: Path, repo_skills_dir: Path) -> bool:
    """创建统一 Skill 目录 symlink: ~/.agents/skills/<name> → ~/Skills/skills/<name>。

    返回 True 表示成功创建或已存在且正确。
    """
    link = agents_dir / name
    target = repo_skills_dir / name

    if not target.is_dir():
        return False

    # 已存在且正确
    if link.is_symlink():
        resolved = _resolve(link)
        if resolved == target.resolve():
            return True
        # 指向错误目标，需要重建
        link.unlink()

    # 如果是真实目录且内容一致，替换为软链接
    if link.is_dir() and not link.is_symlink():
        if _dirs_identical(link, target):
            # 检查 target 是否是反向 symlink（旧架构：Skills/skills → agents/skills）
            # 如果是，不能删除 link，否则会形成循环
            if target.is_symlink() and _resolve(target) == link.resolve():
                # 旧架构：翻转方向——先删除旧 symlink，把真实文件移到 repo
                target.unlink()
                shutil.copytree(str(link), str(target))
                shutil.rmtree(link)
            else:
                shutil.rmtree(link)
        else:
            # 内容不一致，不覆盖
            return False

    # 父目录不存在则创建
    link.parent.mkdir(parents=True, exist_ok=True)

    # 使用相对路径（更可移植）
    rel_target = os.path.relpath(target, link.parent)
    os.symlink(rel_target, link)
    return True


def create_agent_links(
    name: str,
    agents_dir: Path,
    agent_dirs: list[Path],
    external_skills: set[str] | None = None,
) -> dict[str, bool]:
    """创建 Agent Skill 目录 symlink: ~/.<agent>/skills/<name> → ~/.agents/skills/<name>。

    跳过外部 skill 已占用的目录。
    返回 {agent_name: success} 字典。
    """
    external = external_skills or set()
    results = {}
    agents_target = agents_dir / name

    for agent_dir in agent_dirs:
        agent_name = agent_dir.parent.name.lstrip(".")
        link = agent_dir / name

        # 外部 skill 已占用此位置，跳过
        if name in external:
            continue

        # 已存在且正确
        if link.exists() or link.is_symlink():
            if link.is_symlink() and _resolve(link) == agents_target.resolve():
                results[agent_name] = True
                continue
            # 指向错误目标或不是软链接，跳过（可能由 npx skills 管理）
            if link.is_symlink() and _resolve(link) != agents_target.resolve():
                results[agent_name] = True  # 已有指向其他位置的链接，不覆盖
                continue
            # 真实目录，不覆盖
            results[agent_name] = True
            continue

        # 不存在，创建
        link.parent.mkdir(parents=True, exist_ok=True)
        rel_target = os.path.relpath(agents_target, link.parent)
        try:
            os.symlink(rel_target, link)
            results[agent_name] = True
        except OSError:
            results[agent_name] = False

    return results


def create_all_links(
    name: str,
    agents_dir: Path,
    repo_skills_dir: Path,
    agent_dirs: list[Path],
    external_skills: set[str] | None = None,
) -> LinkState:
    """为一个 skill 创建完整的 symlink 链（自定义 Skill 仓库 → 统一 Skill 目录 → Agent Skill 目录）。"""
    state = LinkState(name=name)

    # 统一 Skill 目录
    state.agents_link_exists = create_agents_link(name, agents_dir, repo_skills_dir)
    state.agents_link_valid = state.agents_link_exists

    # Agent Skill 目录
    agent_results = create_agent_links(name, agents_dir, agent_dirs, external_skills)
    state.agent_links_ok = [a for a, ok in agent_results.items() if ok]
    state.agent_links_missing = [a for a, ok in agent_results.items() if not ok]

    return state


# ============================================================
# 软链接验证
# ============================================================

def verify_links(name: str, agents_dir: Path, repo_skills_dir: Path, agent_dirs: list[Path]) -> LinkState:
    """验证一个 skill 的 symlink 状态（不修改）。"""
    state = LinkState(name=name)
    agents_link = agents_dir / name
    target = repo_skills_dir / name

    # 统一 Skill 目录验证
    if agents_link.is_symlink():
        resolved = _resolve(agents_link)
        if resolved == target.resolve():
            state.agents_link_exists = True
            state.agents_link_valid = True
        elif not target.exists():
            state.agents_link_exists = True
            state.agents_link_broken = True
        else:
            state.agents_link_exists = True
            state.agents_link_wrong_target = True
    elif agents_link.is_dir():
        state.agents_link_exists = True
        # 真实目录，不是软链接
    # 不存在则 all False

    # Agent Skill 目录验证
    agents_target = agents_dir / name
    for agent_dir in agent_dirs:
        agent_name = agent_dir.parent.name.lstrip(".")
        link = agent_dir / name
        if not link.exists() and not link.is_symlink():
            state.agent_links_missing.append(agent_name)
        elif link.is_symlink() and not link.exists():
            state.agent_links_broken.append(agent_name)
        else:
            state.agent_links_ok.append(agent_name)

    return state


# ============================================================
# 软链接删除
# ============================================================

def remove_agents_link(name: str, agents_dir: Path, repo_skills_dir: Path) -> bool:
    """删除统一 Skill 目录 symlink: ~/.agents/skills/<name>。

    安全检查：只删除确实指向 repo_skills_dir 的软链接。
    返回 True 表示成功删除。
    """
    link = agents_dir / name
    target = repo_skills_dir / name

    if not link.is_symlink():
        return False

    resolved = _resolve(link)
    if resolved != target.resolve():
        return False  # 指向其他位置，不删除

    link.unlink()
    return True


def remove_agent_links(name: str, agent_dirs: list[Path], agents_dir: Path) -> list[str]:
    """删除 Agent Skill 目录 symlink。

    只删除指向 ~/.agents/skills/<name> 的软链接。
    返回成功删除的 agent 名列表。
    """
    removed = []
    agents_target = agents_dir / name

    for agent_dir in agent_dirs:
        link = agent_dir / name
        if link.is_symlink() and _resolve(link) == agents_target.resolve():
            link.unlink()
            removed.append(agent_dir.parent.name.lstrip("."))

    return removed


# ============================================================
# 批量同步
# ============================================================

def sync_all_links(
    agents_dir: Path,
    repo_skills_dir: Path,
    agent_dirs: list[Path],
    external_skills: set[str] | None = None,
) -> list[LinkState]:
    """扫描自定义 Skill 仓库中所有 skill，验证/修复 symlink。

    跳过 external_skills 中的外部 skill（由 npx skills 管理）。
    """
    external = external_skills or set()
    states = []

    if not repo_skills_dir.is_dir():
        return states

    for d in sorted(repo_skills_dir.iterdir()):
        if d.name.startswith(".") or not d.is_dir():
            continue
        if not (d / "SKILL.md").is_file():
            continue
        if d.name in external:
            continue  # 跳过外部 skill

        state = verify_links(d.name, agents_dir, repo_skills_dir, agent_dirs)

        # 修复统一 Skill 目录
        if not state.agents_link_valid and not state.agents_link_wrong_target:
            if create_agents_link(d.name, agents_dir, repo_skills_dir):
                state.agents_link_exists = True
                state.agents_link_valid = True

        # 修复 Agent Skill 目录（补充缺失的）
        if state.agent_links_missing:
            results = create_agent_links(d.name, agents_dir, agent_dirs)
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
