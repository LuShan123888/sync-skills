"""Skill 生命周期管理：add / remove / link / unlink / init"""

import hashlib
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

from .classification import classify_all_skills, classify_skill
from .config import Config
from .constants import DEFAULT_AGENT_DIRS, SKILL_SKELETON
from .git_ops import git_add_commit, git_has_remote, git_init
from .state import add_managed, get_managed_skills, remove_managed
from .symlink import check_and_repair_links, create_all_links, remove_agent_links, sync_all_links, verify_links


# ============================================================
# 自动提交
# ============================================================


def _auto_commit(config: Config, command: str, skills: list[str]) -> None:
    """修改 repo 后自动提交。"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    skill_part = skills[0] if len(skills) == 1 else f"{len(skills)} skills"
    msg = f"{command}: {skill_part} ({timestamp})"
    if git_add_commit(config.repo, msg):
        print(f"  [git] {msg}")


# ============================================================
# Skill 名称校验
# ============================================================

_VALID_SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]*[a-z0-9]$|^([a-z0-9])$")


def validate_skill_name(name: str) -> str | None:
    """校验 skill 名称。返回错误信息，None 表示合法。"""
    if not name:
        return "skill 名称不能为空"
    if not _VALID_SKILL_NAME.match(name):
        return "skill 名称只能包含小写字母、数字、点、连字符和下划线"
    return None


# ============================================================
# new：创建新 skill
# ============================================================

def add_skill(
    name: str,
    config: Config,
    description: str = "",
    tags: list[str] | None = None,
    dry_run: bool = False,
) -> bool:
    """创建新自定义 skill。

    1. 校验名称
    2. 检查不与已管理 skill 冲突
    3. 创建 SKILL.md 骨架
    4. 建立软链接
    5. 写入状态文件
    """
    from .config import _unexpand_home

    # 校验名称
    err = validate_skill_name(name)
    if err:
        print(f"[ERROR] {err}", file=sys.stderr)
        return False

    repo_skills_dir = config.repo_skills_dir
    skill_dir = repo_skills_dir / name

    # 检查是否已管理
    managed = get_managed_skills(config.state_file)
    if name in managed:
        print(f"[ERROR] '{name}' 已纳入管理", file=sys.stderr)
        return False

    # 检查是否已存在
    if skill_dir.is_dir():
        print(f"[ERROR] skill '{name}' 已存在于 {skill_dir}", file=sys.stderr)
        return False

    # 检查 agent 目录中是否已存在
    for ad in config.effective_agent_dirs:
        if (ad / name).is_dir():
            print(f"[ERROR] skill '{name}' 已存在于 {ad / name}", file=sys.stderr)
            return False

    if dry_run:
        print(f"[DRY-RUN] 将创建 skill '{name}':")
        print(f"  自定义 Skill 仓库: {_unexpand_home(skill_dir)}")
        print(f"  状态文件:          将添加 '{name}'")
        return True

    # 创建目录和 SKILL.md
    skill_dir.mkdir(parents=True, exist_ok=True)
    skeleton = SKILL_SKELETON.format(name=name)
    if description:
        skeleton = skeleton.replace('description: "Description of what this skill does"', f'description: "{description}"')
    if tags:
        tags_str = ", ".join(f'"{t}"' for t in tags)
        skeleton = skeleton.replace("---\n", f"---\ntags: [{tags_str}]\n", 1)

    (skill_dir / "SKILL.md").write_text(skeleton, encoding="utf-8")

    # 建立软链接（单层：repo → 各 agent 目录）
    state = create_all_links(name, repo_skills_dir, config.effective_agent_dirs)

    # 写入状态文件
    add_managed(name, config.state_file)

    print(f"[OK] 已创建 skill '{name}'")
    print(f"     自定义 Skill 仓库: {_unexpand_home(skill_dir)}")
    if state.agent_links_ok:
        for agent_name in state.agent_links_ok:
            print(f"     Agent Skill 目录: ~/{agent_name}/skills/{name}")

    _auto_commit(config, "add", [name])
    return True


# ============================================================
# remove：删除 skill
# ============================================================

def remove_skill(name: str, config: Config, auto_confirm: bool = False, dry_run: bool = False) -> bool:
    """删除自定义 skill。

    1. 验证是已管理 skill
    2. 删除软链接
    3. 删除仓库文件
    4. 从状态文件移除
    """
    from .config import _unexpand_home
    from .symlink import verify_links

    managed = get_managed_skills(config.state_file)
    classification = classify_skill(name, managed, config.repo_skills_dir, config.effective_agent_dirs)

    if not classification.managed:
        print(f"[ERROR] '{name}' 未被管理", file=sys.stderr)
        return False

    # 确认前先检查链接状态
    link_state = verify_links(name, config.repo_skills_dir, config.effective_agent_dirs)

    if not auto_confirm and not dry_run:
        print(f"将删除 skill '{name}':")
        if classification.custom_path:
            print(f"  自定义 Skill 仓库: {_unexpand_home(classification.custom_path)}")
        if link_state.agent_links_ok:
            for agent_name in link_state.agent_links_ok:
                print(f"  Agent Skill 目录: ~/{agent_name}/skills/{name} (symlink)")
        if link_state.agent_links_broken:
            print(f"  异常链接:   {', '.join(link_state.agent_links_broken)} (symlink 已损坏)")
        try:
            confirm = input("确认删除? [y/N] ").strip().lower()
            if confirm != "y":
                print("已取消")
                return False
        except (EOFError, KeyboardInterrupt):
            print("\n已取消")
            return False

    if dry_run:
        print(f"[DRY-RUN] 将删除 skill '{name}':")
        if classification.custom_path:
            print(f"  自定义 Skill 仓库: {_unexpand_home(classification.custom_path)}")
        if link_state.agent_links_ok:
            for agent_name in link_state.agent_links_ok:
                print(f"  Agent Skill 目录: ~/{agent_name}/skills/{name} (symlink)")
        print(f"  状态文件:          将移除 '{name}'")
        return True

    # 删除软链接
    removed_agent = remove_agent_links(name, config.effective_agent_dirs, config.repo_skills_dir)

    # 删除仓库中的 skill 目录
    if classification.custom_path and classification.custom_path.is_dir():
        shutil.rmtree(classification.custom_path)

    # 兜底：清理 agent 目录中的残留（不在 removed_agent 中的）
    for ad in config.effective_agent_dirs:
        entry = ad / name
        agent_name = ad.parent.name.lstrip(".")
        if (entry.exists() or entry.is_symlink()) and agent_name not in removed_agent:
            if entry.is_symlink():
                entry.unlink()
                removed_agent.append(agent_name)
            elif entry.is_dir():
                shutil.rmtree(entry)
                removed_agent.append(agent_name)

    # 从状态文件移除
    remove_managed(name, config.state_file)

    if not any([removed_agent, classification.custom_path]):
        print(f"[OK] skill '{name}' 已清理")
        return True

    print(f"[OK] 已删除 skill '{name}':")
    if removed_agent:
        print(f"  - Agent Skill 目录 symlink 已删除: {', '.join(removed_agent)}")
    if classification.custom_path:
        print(f"  - 自定义 Skill 仓库文件已删除")

    _auto_commit(config, "remove", [name])
    return True


# ============================================================
# link：将 skill 纳入管理（按名称自动扫描）
# ============================================================


def _compute_dir_hash(dir_path: Path) -> str:
    """计算目录的 MD5 哈希值（忽略隐藏文件）。"""
    h = hashlib.md5()
    for file_path in sorted(dir_path.rglob("*")):
        if file_path.is_file() and not file_path.name.startswith("."):
            rel = file_path.relative_to(dir_path)
            h.update(str(rel).encode())
            h.update(file_path.read_bytes())
    return h.hexdigest()


def _get_dir_mtime(dir_path: Path) -> float:
    """获取目录的最新修改时间（所有文件中的最大 mtime）。"""
    latest = dir_path.stat().st_mtime
    for f in dir_path.rglob("*"):
        if f.is_file():
            mtime = f.stat().st_mtime
            if mtime > latest:
                latest = mtime
    return latest


def _format_mtime(timestamp: float) -> str:
    """格式化 mtime 为可读字符串。"""
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y-%m-%d %H:%M")


def _scan_skill_sources(name: str, config: Config) -> list[Path]:
    """扫描所有 agent dir 和 repo，收集 name 的所有真实目录（非 symlink）。

    返回去重后的列表。
    """
    seen = set()
    sources = []
    for ad in config.effective_agent_dirs:
        p = ad / name
        if p.is_dir() and not p.is_symlink() and (p / "SKILL.md").is_file():
            resolved = p.resolve()
            if resolved not in seen:
                seen.add(resolved)
                sources.append(p)
    # 也检查 repo
    repo_skill = config.repo_skills_dir / name
    if repo_skill.is_dir() and (repo_skill / "SKILL.md").is_file():
        resolved = repo_skill.resolve()
        if resolved not in seen:
            seen.add(resolved)
            sources.append(repo_skill)
    return sources


def _resolve_link_conflict(
    name: str,
    sources: list[Path],
    auto_confirm: bool = False,
) -> Path | None:
    """多源 MD5 分组 + mtime 排序，让用户选择版本。

    返回选定的源路径，None 表示取消。
    """
    from .config import _unexpand_home

    # 计算每个源的 MD5 hash
    hash_map: dict[str, list[Path]] = {}
    for s in sources:
        h = _compute_dir_hash(s)
        hash_map.setdefault(h, []).append(s)

    # 如果只有一组，使用该组中 mtime 最大的源
    if len(hash_map) == 1:
        group = list(hash_map.values())[0]
        selected = max(group, key=_get_dir_mtime)
        # 展示找到的位置
        if len(group) > 1:
            print(f"\n  '{name}' 在 {len(group)} 个位置找到相同版本 (hash {list(hash_map.keys())[0][:8]}...)")
            for p in sorted(group, key=_get_dir_mtime, reverse=True):
                marker = "← 选定" if p.resolve() == selected.resolve() else ""
                print(f"    {_unexpand_home(p)} ({_format_mtime(_get_dir_mtime(p))}) {marker}")
        return selected

    # 多组：展示信息让用户选择
    groups = []
    for h, paths in sorted(hash_map.items()):
        latest_path = max(paths, key=_get_dir_mtime)
        latest_mtime = _get_dir_mtime(latest_path)
        groups.append({
            "hash": h,
            "paths": paths,
            "latest_path": latest_path,
            "latest_mtime": latest_mtime,
        })

    print(f"\n⚠ '{name}' 在 {len(sources)} 个位置找到 {len(groups)} 个不同版本：")

    for i, g in enumerate(groups, 1):
        print(f"\n  [{i}] hash {g['hash'][:8]}... (最新修改: {_format_mtime(g['latest_mtime'])})")
        for p in g["paths"]:
            print(f"      {_unexpand_home(p)}")

    if auto_confirm:
        # 自动选择 mtime 最大的组中的最新源
        best = max(groups, key=lambda g: g["latest_mtime"])
        print(f"\n[WARNING] 存在内容冲突但 -y 已跳过，将使用最新修改的版本")
        return best["latest_path"]

    try:
        choice = input(f"\n选择使用的版本 [1-{len(groups)}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n已取消")
        return None

    try:
        choice_idx = int(choice)
    except ValueError:
        print("已取消")
        return None

    if 1 <= choice_idx <= len(groups):
        return groups[choice_idx - 1]["latest_path"]

    print("已取消")
    return None


def link_skill(name: str, config: Config, auto_confirm: bool = False, dry_run: bool = False) -> bool:
    """将 skill 纳入管理（按名称自动扫描）。

    流程：
    1. 校验名称
    2. 检查是否已被管理
    3. 扫描所有 agent dir + repo，收集同名 skill
    4. MD5 分组 + mtime 排序，让用户选择版本
    5. 确认后：复制选定版本到 repo → 删除其他副本 → 创建 symlink → 写入状态文件
    """
    from .config import _unexpand_home

    # 校验名称
    err = validate_skill_name(name)
    if err:
        print(f"[ERROR] {err}", file=sys.stderr)
        return False

    managed = get_managed_skills(config.state_file)

    # 检查是否已被管理
    if name in managed:
        print(f"[ERROR] '{name}' 已纳入管理", file=sys.stderr)
        return False

    # 扫描所有位置
    sources = _scan_skill_sources(name, config)

    if not sources:
        print(f"[ERROR] 未找到 skill '{name}'", file=sys.stderr)
        return False

    # 解决冲突（只有一个源时自动选择）
    selected = _resolve_link_conflict(name, sources, auto_confirm)
    if selected is None:
        return False

    # 展示将执行的操作
    other_sources = [s for s in sources if s.resolve() != selected.resolve()]
    print(f"\n将 '{name}' 纳入管理：")
    print(f"  选定版本: {_unexpand_home(selected)}")
    print(f"  目标: {_unexpand_home(config.repo_skills_dir / name)}")
    if other_sources:
        print(f"  将删除的副本 ({len(other_sources)} 个):")
        for s in other_sources:
            print(f"    - {_unexpand_home(s)}")
    print(f"  操作: 复制到自定义 Skill 仓库 → 删除其他副本 → 创建 symlink")

    if dry_run:
        print(f"  状态文件: 将添加 '{name}'")
        return True

    if not auto_confirm:
        try:
            confirm = input("确认? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消")
            return False
        if confirm != "y":
            print("已取消")
            return False

    # 1. 确保 repo 目录存在
    config.repo_skills_dir.mkdir(parents=True, exist_ok=True)

    # 2. 如果选定版本不在 repo 中，复制到 repo
    target = config.repo_skills_dir / name
    if target.is_dir() and target.resolve() != selected.resolve():
        shutil.rmtree(target)
    if target.resolve() != selected.resolve():
        shutil.copytree(str(selected), str(target))
        print(f"  [OK] 已复制到 {_unexpand_home(target)}")

    # 3. 删除所有 agent dir 中的副本（包括选定源）
    for s in sources:
        if s.resolve() == target.resolve():
            continue  # repo 中的文件保留
        if s.is_dir() and not s.is_symlink():
            shutil.rmtree(s)
            print(f"  [OK] 已删除 {_unexpand_home(s)}")

    # 4. 创建 symlink（单层：repo → 各 agent 目录）
    state = create_all_links(name, config.repo_skills_dir, config.effective_agent_dirs)

    # 5. 写入状态文件
    add_managed(name, config.state_file)

    print(f"  [OK] symlink 已创建")
    if state.agent_links_ok:
        for agent_name in state.agent_links_ok:
            print(f"     Agent Skill 目录: ~/{agent_name}/skills/{name}")

    _auto_commit(config, "link", [name])
    return True


# ============================================================
# unlink：从管理中移除 skill（还原文件）
# ============================================================

def _unlink_one(name: str, config: Config, dry_run: bool = False) -> bool:
    """从管理中移除单个 skill 的核心逻辑。"""
    from .config import _unexpand_home

    managed = get_managed_skills(config.state_file)
    classification = classify_skill(name, managed, config.repo_skills_dir, config.effective_agent_dirs)

    if not classification.managed:
        return False

    if dry_run:
        print(f"[DRY-RUN] 将移除 '{name}':")
        if classification.custom_path and classification.custom_path.is_dir():
            print(f"  自定义 Skill 仓库: {_unexpand_home(classification.custom_path)} (将删除)")
        print(f"  Agent Skill 目录: 将还原为真实文件")
        print(f"  状态文件:          将移除 '{name}'")
        return True

    if not classification.custom_path or not classification.custom_path.is_dir():
        # 状态文件中有记录但 repo 中没有文件，直接从状态文件移除
        remove_managed(name, config.state_file)
        print(f"  [OK] {name}: 已从管理中移除（仓库中无文件）")
        return True

    # 1. 将文件从自定义仓库还原到所有 agent 目录
    source = classification.custom_path
    restored = 0

    for ad in config.effective_agent_dirs:
        target = ad / name
        if target.is_symlink():
            target.unlink()
            shutil.copytree(str(source), str(target))
            restored += 1
        elif not target.exists():
            shutil.copytree(str(source), str(target))
            restored += 1
        else:
            # 真实目录已存在，跳过
            print(f"[WARNING] {_unexpand_home(target)} 已存在且不是 symlink，跳过")

    # 2. 删除仓库中的文件
    shutil.rmtree(source)

    # 3. 从状态文件移除
    remove_managed(name, config.state_file)

    if restored > 0:
        print(f"  [OK] {name}: 文件已还原到 {restored} 个 Agent Skill 目录")
    else:
        print(f"  [OK] {name}: 已从管理中移除")

    return True


def unlink_skill(
    names: list[str] | None,
    config: Config,
    auto_confirm: bool = False,
    dry_run: bool = False,
) -> bool:
    """从管理中移除 skill：还原文件到 agent 目录，从状态文件移除。

    names 为 None 或包含 "--all" 时移除所有已管理 skill。
    """
    from .config import _unexpand_home

    managed = get_managed_skills(config.state_file)

    if names and "--all" in names:
        names = None

    if names is not None:
        # 移除指定的 skills
        results = {}
        for name in names:
            classification = classify_skill(name, managed, config.repo_skills_dir, config.effective_agent_dirs)
            if not classification.managed:
                print(f"[ERROR] '{name}' 未被管理", file=sys.stderr)
                results[name] = False
                continue
            if not classification.custom_path or not classification.custom_path.is_dir():
                if dry_run:
                    print(f"[DRY-RUN] 将从管理中移除 '{name}'（仓库中无文件）")
                    results[name] = True
                    continue
                remove_managed(name, config.state_file)
                print(f"  [OK] {name}: 已从管理中移除（仓库中无文件）")
                results[name] = True
                continue

            if not auto_confirm and not dry_run:
                print(f"将移除 '{name}':")
                print(f"  自定义 Skill 仓库: {_unexpand_home(classification.custom_path)} (将删除)")
                print(f"  Agent Skill 目录: 将还原为真实文件")
                try:
                    confirm = input("确认移除? [y/N] ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print("\n已取消")
                    results[name] = False
                    continue
                if confirm != "y":
                    print("已取消")
                    results[name] = False
                    continue

            results[name] = _unlink_one(name, config, dry_run=dry_run)

        if not dry_run:
            unlinked = [n for n, ok in results.items() if ok]
            if unlinked:
                _auto_commit(config, "unlink", unlinked)

        success = sum(1 for v in results.values() if v)
        total = len(results)
        if total > 1:
            print(f"\n移除完成: {success}/{total} 个 skill")
        return all(results.values()) if results else True
    else:
        # 移除所有已管理 skill
        all_classifications = classify_all_skills(managed, config.repo_skills_dir, config.effective_agent_dirs)
        custom = [c for c in all_classifications if c.managed]

        if not custom:
            print("没有已管理的 skill 可移除")
            return True

        if dry_run:
            print(f"[DRY-RUN] 将移除以下 {len(custom)} 个 skill:")
            for c in custom:
                print(f"  - {c.name}")
            return True

        if not auto_confirm:
            print(f"将移除以下 {len(custom)} 个 skill:")
            for c in custom:
                print(f"  - {c.name}")
            try:
                confirm = input(f"\n确认移除全部 {len(custom)} 个? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n已取消")
                return False
            if confirm != "y":
                print("已取消")
                return False

        success = 0
        unlinked_names = []
        for c in custom:
            if _unlink_one(c.name, config):
                success += 1
                unlinked_names.append(c.name)

        if unlinked_names:
            _auto_commit(config, "unlink", unlinked_names)

        print(f"\n移除完成: {success}/{len(custom)} 个 skill")
        return success == len(custom)


# ============================================================
# init：初始化自定义 skill 仓库（幂等）
# ============================================================

def _select_agents(config: Config) -> None:
    """交互式选择要管理的 Agent。"""
    from .config import _unexpand_home

    # 始终扫描所有已知 agent 目录（而非仅已配置的），确保用户能重新选择
    # config.agent_dirs 优先，再补充 DEFAULT_AGENT_DIRS 中没有的
    detected = []
    seen_names = set()
    all_scan_dirs = list(config.agent_dirs or [])
    for d in DEFAULT_AGENT_DIRS:
        if d not in all_scan_dirs:
            all_scan_dirs.append(d)

    for d in all_scan_dirs:
        name = d.parent.name.lstrip(".")
        if name in seen_names:
            continue
        seen_names.add(name)
        detected.append((name, d))

    if not detected:
        print("\n未检测到已安装的 Agent")
        return

    # 标记当前已配置的 agent
    configured_names = set()
    if config.agent_dirs:
        for d in config.agent_dirs:
            configured_names.add(d.parent.name.lstrip("."))

    print(f"\n可用的 Agent:")
    for i, (name, path) in enumerate(detected):
        marker = " *" if name in configured_names else ""
        print(f"  [{i}] {name}  {_unexpand_home(path)}{marker}")

    # 当前已选中的（仅已配置的）
    current_indices = [i for i, (name, _) in enumerate(detected) if name in configured_names]
    if not current_indices:
        current_indices = list(range(len(detected)))

    hint = ", ".join(str(i) for i in current_indices)
    prompt = f"\n选择要管理的 Agent (编号，逗号分隔，直接回车保持当前 [{hint}]): "

    try:
        select_input = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if select_input:
        # 支持中英文逗号
        indices = [int(x.strip()) for x in select_input.replace("，", ",").split(",") if x.strip().isdigit()]
        config.agent_dirs = [detected[i][1] for i in indices if 0 <= i < len(detected)]
    else:
        # 直接回车，保持当前选择
        if config.agent_dirs:
            config.agent_dirs = list(config.agent_dirs)
        else:
            config.agent_dirs = [d for _, d in detected]


def _confirm_repo_path(config: Config) -> None:
    """交互式确认仓库路径。"""
    from .config import _expand_home, _unexpand_home

    current = _unexpand_home(config.repo)
    try:
        repo_input = input(f"自定义 skill 仓库路径 (默认 {current}): ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if repo_input:
        config.repo = _expand_home(repo_input)


def _ask_has_remote() -> bool:
    """询问用户是否已有远程仓库。"""
    try:
        answer = input("\n是否已有远程仓库? (y/N): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer == "y"


def _ask_remote_url() -> str:
    """询问远程仓库 URL。"""
    try:
        url = input("请输入远程仓库 URL: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n已取消")
        return ""
    return url


def init_repo(config: Config, auto_confirm: bool = False, dry_run: bool = False, config_path: Path | None = None) -> bool:
    """初始化 ~/Skills/ 仓库（幂等，可多次执行）。

    首次执行：创建/克隆仓库 + 配置 Agent + 注册 skill + 创建 symlink
    后续执行：重新配置 Agent + 补充注册 + doctor 修复
    """
    from .config import _unexpand_home, save_config
    from .git_ops import git_clone, git_has_remote, git_init, git_is_repo

    print("=== sync-skills 初始化配置 ===\n")

    # 1. 确认仓库路径
    if not auto_confirm:
        _confirm_repo_path(config)

    repo = config.repo
    repo_skills_dir = config.repo_skills_dir
    is_git_repo = git_is_repo(repo)

    # 2. 仓库初始化
    if is_git_repo:
        has_remote = git_has_remote(repo)
        if has_remote:
            print(f"[OK] {_unexpand_home(repo)} 已是 git 仓库（已关联远程）")
        else:
            print(f"[OK] {_unexpand_home(repo)} 已是 git 仓库（本地仓库）")
    else:
        # 不是 git 仓库，询问是否有远程
        if not auto_confirm and _ask_has_remote():
            remote_url = _ask_remote_url()
            if not remote_url:
                print("已取消")
                return False

            if dry_run:
                print(f"[DRY-RUN] 将克隆 {remote_url} 到 {_unexpand_home(repo)}")
            else:
                # 检查目标路径是否已存在非空目录
                if repo.exists() and any(repo.iterdir()):
                    print(f"[ERROR] {_unexpand_home(repo)} 已存在且非空，无法克隆", file=sys.stderr)
                    return False
                if not git_clone(remote_url, repo):
                    return False
                print(f"[OK] 已克隆到 {_unexpand_home(repo)}")
        else:
            if dry_run:
                print(f"[DRY-RUN] 将初始化 git 仓库: {_unexpand_home(repo)}")
            else:
                git_init(repo)
                print(f"[OK] git init 完成: {_unexpand_home(repo)}")

    # 3. 选择要管理的 Agent
    if not auto_confirm:
        _select_agents(config)

    # 4. 确保目录存在
    repo_skills_dir.mkdir(parents=True, exist_ok=True)

    # 5. 扫描 repo 中所有 skill，自动注册
    managed = get_managed_skills(config.state_file)
    repo_skill_names = set()
    if repo_skills_dir.is_dir():
        for d in repo_skills_dir.iterdir():
            if d.name.startswith(".") or not d.is_dir():
                continue
            if (d / "SKILL.md").is_file():
                repo_skill_names.add(d.name)

    # 补充登记：repo 中有但状态文件中没有的 skill
    new_managed = sorted(repo_skill_names - managed)

    # 6. 汇总
    already_count = len(managed & repo_skill_names)
    print(f"\n  扫描完成: {already_count} 已管理, {len(new_managed)} 存量未登记")

    if not auto_confirm and not dry_run and (new_managed or not managed):
        if new_managed:
            print(f"\n  将自动登记以下 {len(new_managed)} 个 skill:")
            for name in new_managed:
                print(f"    - {name}")

    # 7. 预检 symlink 状态
    all_skills_for_links = sorted((managed & repo_skill_names) | set(new_managed))
    link_previews = {}
    for name in all_skills_for_links:
        link_previews[name] = verify_links(name, repo_skills_dir, config.effective_agent_dirs)

    # 8. 显示预览并确认
    verified_skills = []
    create_skills = []
    repair_skills = []
    for name in all_skills_for_links:
        s = link_previews[name]
        if s.agent_links_broken or s.agent_links_wrong_target:
            repair_skills.append(name)
        elif s.agent_links_missing:
            create_skills.append(name)
        else:
            verified_skills.append(name)

    if not auto_confirm and not dry_run:
        print(f"\n即将执行:")
        action_idx = 1
        if new_managed:
            print(f"  {action_idx}. 登记 {len(new_managed)} 个存量 skill")
            action_idx += 1
        if all_skills_for_links:
            parts = []
            if verified_skills:
                parts.append(f"✓ {len(verified_skills)} 已验证")
            if create_skills:
                parts.append(f"+ {len(create_skills)} 将创建")
            if repair_skills:
                parts.append(f"! {len(repair_skills)} 需修复")
            print(f"  {action_idx}. 创建/修复 symlink ({len(all_skills_for_links)} 个 skill): {'  '.join(parts)}")

            # 逐 skill 展示详情
            for name in all_skills_for_links:
                s = link_previews[name]
                if not s.agent_links_missing and not s.agent_links_broken and not s.agent_links_wrong_target:
                    print(f"     ✓ {name}")
                elif s.agent_links_broken or s.agent_links_wrong_target:
                    agents = ", ".join(s.agent_links_broken + s.agent_links_wrong_target)
                    print(f"     ! {name}  → 修复 {agents}")
                else:
                    agents = ", ".join(s.agent_links_missing)
                    print(f"     + {name}  → {agents}")

        if not all_skills_for_links and not new_managed:
            print(f"  1. 保存配置")

        try:
            confirm = input("\n确认执行? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消")
            return False
        if confirm != "y":
            print("已取消")
            return False

    if dry_run:
        print(f"\n[DRY-RUN] 将执行:")
        action_idx = 1
        if new_managed:
            print(f"  {action_idx}. 登记 {len(new_managed)} 个存量 skill")
            action_idx += 1
        if all_skills_for_links:
            parts = []
            if verified_skills:
                parts.append(f"✓ {len(verified_skills)} 已验证")
            if create_skills:
                parts.append(f"+ {len(create_skills)} 将创建")
            if repair_skills:
                parts.append(f"! {len(repair_skills)} 需修复")
            print(f"  {action_idx}. 创建/修复 symlink ({len(all_skills_for_links)} 个 skill): {'  '.join(parts)}")

            for name in all_skills_for_links:
                s = link_previews[name]
                if not s.agent_links_missing and not s.agent_links_broken and not s.agent_links_wrong_target:
                    print(f"     ✓ {name}")
                elif s.agent_links_broken or s.agent_links_wrong_target:
                    agents = ", ".join(s.agent_links_broken + s.agent_links_wrong_target)
                    print(f"     ! {name}  → 修复 {agents}")
                else:
                    agents = ", ".join(s.agent_links_missing)
                    print(f"     + {name}  → {agents}")

        if not all_skills_for_links and not new_managed:
            print(f"  1. 保存配置")
        return True

    # 8. 执行
    print()

    # 注册新 skill
    for name in new_managed:
        add_managed(name, config.state_file)
        print(f"  [登记] {name}")

    # 创建/修复 symlink
    all_managed = get_managed_skills(config.state_file)
    if all_managed:
        states = sync_all_links(repo_skills_dir, config.effective_agent_dirs, managed_skills=all_managed)

        verified = 0
        created = 0
        issues = 0
        for s in states:
            if not s.agent_links_missing and not s.agent_links_broken and not s.agent_links_wrong_target:
                verified += 1
            elif s.agent_links_broken or s.agent_links_wrong_target:
                issues += 1
            else:
                created += 1

        parts = []
        if verified:
            parts.append(f"✓ {verified} 已验证")
        if created:
            parts.append(f"+ {created} 已创建")
        if issues:
            parts.append(f"! {issues} 需要关注")
        if parts:
            print(f"  symlink: {'  '.join(parts)}")

    # 使用 check_and_repair_links 清理断链 + 检测冲突
    all_managed = get_managed_skills(config.state_file)
    if all_managed:
        repair_result = check_and_repair_links(
            config.repo_skills_dir, config.effective_agent_dirs, all_managed, auto_confirm=True
        )
        if repair_result["conflicts"]:
            for item in repair_result["conflicts"]:
                print(f"  ! 冲突: {item}")

    # 保存配置
    save_config(config, config_path)

    # 汇总
    total = already_count + len(new_managed)
    print(f"\n初始化完成:")
    print(f"  已管理 skill: {total}")

    return True
