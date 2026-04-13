"""Skill 生命周期管理：add / remove / link / unlink / init"""

import re
import sys
from pathlib import Path

from .classification import classify_all_skills, classify_skill, get_external_skills
from .config import Config
from .constants import DEFAULT_AGENT_DIRS, SKILL_SKELETON
from .git_ops import git_add_commit, git_has_remote, git_init
from .state import add_managed, get_managed_skills, remove_managed
from .symlink import create_all_links, remove_agent_links, remove_agents_link


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
# add：创建新 skill
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
    2. 检查不与外部 skill 冲突
    3. 创建 SKILL.md 骨架
    4. 建立软链接
    5. 写入状态文件
    """
    # 校验名称
    err = validate_skill_name(name)
    if err:
        print(f"[ERROR] {err}", file=sys.stderr)
        return False

    repo_skills_dir = config.repo_skills_dir
    skill_dir = repo_skills_dir / name
    agents_dir = config.agents_dir

    # 检查外部 skill 冲突
    external = get_external_skills(config.external.global_lock, config.external.local_lock)
    if name in external:
        print(f"[ERROR] '{name}' 已作为外部 skill 由 npx skills 管理", file=sys.stderr)
        return False

    # 检查是否已管理
    managed = get_managed_skills(config.state_file)
    if name in managed:
        print(f"[ERROR] '{name}' 已纳入管理", file=sys.stderr)
        return False

    # 检查是否已存在
    if skill_dir.is_dir():
        print(f"[ERROR] skill '{name}' 已存在于 {skill_dir}", file=sys.stderr)
        return False
    if (agents_dir / name).is_dir():
        print(f"[ERROR] skill '{name}' 已存在于 {agents_dir / name}", file=sys.stderr)
        return False

    if dry_run:
        from .config import _unexpand_home
        print(f"[DRY-RUN] 将创建 skill '{name}':")
        print(f"  自定义 Skill 仓库: {_unexpand_home(skill_dir)}")
        print(f"  统一 Skill 目录:   {_unexpand_home(agents_dir / name)}")
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

    # 建立软链接
    state = create_all_links(name, agents_dir, repo_skills_dir, config.effective_agent_dirs, external_skills=external)

    # 写入状态文件
    add_managed(name, config.state_file)

    from .config import _unexpand_home
    print(f"[OK] 已创建 skill '{name}'")
    print(f"     自定义 Skill 仓库: {_unexpand_home(skill_dir)}")
    if state.agents_link_valid:
        print(f"     统一 Skill 目录:   {_unexpand_home(agents_dir / name)} → 自定义 Skill 仓库")
    if state.agent_links_ok:
        for agent_name in state.agent_links_ok:
            print(f"     Agent Skill 目录: ~/{agent_name}/skills/{name} → 统一 Skill 目录")

    return True


# ============================================================
# remove：删除 skill
# ============================================================

def remove_skill(name: str, config: Config, auto_confirm: bool = False, dry_run: bool = False) -> bool:
    """删除自定义 skill。

    1. 验证是已管理 skill（不是外部）
    2. 删除软链接
    3. 删除仓库文件
    4. 从状态文件移除
    """
    external = get_external_skills(config.external.global_lock, config.external.local_lock)
    managed = get_managed_skills(config.state_file)
    classification = classify_skill(name, config.agents_dir, managed, external, config.repo_skills_dir)

    if classification.skill_type == "external":
        print(f"[ERROR] '{name}' 是外部 skill（由 npx skills 管理），不能通过 sync-skills 删除", file=sys.stderr)
        return False

    if not classification.managed:
        print(f"[ERROR] '{name}' 未被管理", file=sys.stderr)
        return False

    # 确认前先检查各层链接状态
    from .symlink import verify_links
    link_state = verify_links(name, config.agents_dir, config.repo_skills_dir, config.effective_agent_dirs)

    if not auto_confirm and not dry_run:
        from .config import _unexpand_home

        print(f"将删除 skill '{name}':")
        if classification.custom_path:
            print(f"  自定义 Skill 仓库: {_unexpand_home(classification.custom_path)}")
        if link_state.agents_link_exists:
            print(f"  统一 Skill 目录:   {_unexpand_home(config.agents_dir / name)} (symlink)")
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
        from .config import _unexpand_home
        print(f"[DRY-RUN] 将删除 skill '{name}':")
        if classification.custom_path:
            print(f"  自定义 Skill 仓库: {_unexpand_home(classification.custom_path)}")
        if link_state.agents_link_exists:
            print(f"  统一 Skill 目录:   {_unexpand_home(config.agents_dir / name)} (symlink)")
        if link_state.agent_links_ok:
            for agent_name in link_state.agent_links_ok:
                print(f"  Agent Skill 目录: ~/{agent_name}/skills/{name} (symlink)")
        print(f"  状态文件:          将移除 '{name}'")
        return True

    # 删除软链接
    removed_agents = remove_agents_link(name, config.agents_dir, config.repo_skills_dir)
    removed_agent = remove_agent_links(name, config.effective_agent_dirs, config.agents_dir)

    # 删除仓库中的 skill 目录
    if classification.custom_path and classification.custom_path.is_dir():
        import shutil
        shutil.rmtree(classification.custom_path)

    # 兜底：如果统一 Skill 目录仍有残留（真实目录或断链 symlink），清理掉
    import shutil
    agents_entry = config.agents_dir / name
    if agents_entry.exists() or agents_entry.is_symlink():
        if agents_entry.is_symlink() or (agents_entry.is_dir() and not agents_entry.is_symlink()):
            if agents_entry.is_dir() and not agents_entry.is_symlink():
                shutil.rmtree(agents_entry)
            else:
                agents_entry.unlink()
            if not removed_agents:
                removed_agents = True

    # 从状态文件移除
    remove_managed(name, config.state_file)

    if not any([removed_agents, removed_agent, classification.custom_path]):
        print(f"[OK] skill '{name}' 已清理")
        return True

    print(f"[OK] 已删除 skill '{name}':")
    if removed_agents:
        print(f"  - 统一 Skill 目录 symlink 已删除")
    if removed_agent:
        print(f"  - Agent Skill 目录 symlink 已删除: {', '.join(removed_agent)}")
    if classification.custom_path:
        print(f"  - 自定义 Skill 仓库文件已删除")

    return True


# ============================================================
# link：将野生 skill 纳入管理
# ============================================================


def detect_wild_skills(config: Config) -> list[dict]:
    """检测所有 Agent 目录和统一 Skill 目录中的野生 skill。

    野生 skill：真实目录（非 symlink），包含 SKILL.md，
    不在状态文件中，不在外部 skill lock 文件中。

    返回 [{"name": str, "sources": [Path]}] 列表。
    """
    external = get_external_skills(config.external.global_lock, config.external.local_lock)
    managed = get_managed_skills(config.state_file)
    wild_skills: dict[str, list[Path]] = {}

    def _check_dir(directory: Path):
        """扫描单个目录中的野生 skill。"""
        if not directory.is_dir():
            return
        for d in directory.iterdir():
            if d.name.startswith(".") or not d.is_dir():
                continue
            if not (d / "SKILL.md").is_file():
                continue
            if d.is_symlink():
                continue
            if d.name in external:
                continue
            if d.name in managed:
                continue
            wild_skills.setdefault(d.name, []).append(d)

    # 扫描所有 Agent 目录
    for agent_dir in config.effective_agent_dirs:
        _check_dir(agent_dir)

    # 扫描统一 Skill 目录
    _check_dir(config.agents_dir)

    # 去重（resolve 后去重，处理 agent dir 和 agents_dir 重叠的情况）
    result = []
    for name, srcs in wild_skills.items():
        unique = list({str(s.resolve()): s for s in srcs}.values())
        result.append({"name": name, "sources": unique})

    return result


def _compute_dir_hash(dir_path: Path) -> str:
    """计算目录的 MD5 哈希值（忽略隐藏文件）。"""
    import hashlib
    h = hashlib.md5()
    for file_path in sorted(dir_path.rglob("*")):
        if file_path.is_file() and not file_path.name.startswith("."):
            rel = file_path.relative_to(dir_path)
            h.update(str(rel).encode())
            h.update(file_path.read_bytes())
    return h.hexdigest()


def _resolve_link_conflict(
    name: str,
    sources: list[Path],
    repo_skill: Path | None,
    auto_confirm: bool = False,
) -> Path | None:
    """解决 link 时的内容冲突。

    1. 计算每个源的 MD5 hash
    2. 如果 repo 中已有同名 skill，比较 hash
    3. 如果多个源 hash 不同，让用户选择
    4. 返回选定的源路径，或 None 表示取消
    """
    from .config import _unexpand_home

    # 计算每个源的 hash
    hash_groups: dict[str, list[Path]] = {}
    for s in sources:
        h = _compute_dir_hash(s)
        hash_groups.setdefault(h, []).append(s)

    # 如果只有一个版本，直接使用
    if len(hash_groups) == 1:
        return sources[0]

    # 检查 repo 中是否已有同名 skill
    if repo_skill and repo_skill.is_dir():
        repo_hash = _compute_dir_hash(repo_skill)
        matching_sources = hash_groups.get(repo_hash, [])

        if matching_sources:
            # repo 中的版本与某个源一致
            print(f"[OK] '{name}' 仓库版本与以下源一致:")
            for s in matching_sources:
                print(f"  {_unexpand_home(s)}")
            return matching_sources[0]
        else:
            # repo 中的版本与所有源都不同，冲突！
            print(f"\n⚠ '{name}' 仓库中已有版本，但内容与所有源不同！")
            print(f"  仓库版本 hash: {repo_hash[:8]}...")
            for h, srcs in hash_groups.items():
                print(f"  源版本 hash {h[:8]}... ({len(srcs)} 个):")
                for s in srcs:
                    print(f"    {_unexpand_home(s)}")
            print(f"\n  仓库版本将被覆盖，请确认使用的版本：")
            print(f"  [1] 保留仓库版本（取消 link）")
            idx = 2
            hash_list = sorted(hash_groups.keys())
            for h in hash_list:
                srcs = hash_groups[h]
                print(f"  [{idx}] 使用源版本 {h[:8]}... ({', '.join(_unexpand_home(s).split('/')[-1] + '/..' for s in srcs)})")
                idx += 1

            if auto_confirm:
                print("[WARNING] 存在内容冲突但 -y 已跳过，将保留仓库版本")
                return None

            try:
                choice = input("\n选择 [1]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n已取消")
                return None

            if not choice or choice == "1":
                print("已取消 link，保留仓库版本")
                return None

            try:
                choice_idx = int(choice)
            except ValueError:
                print("已取消")
                return None

            if 2 <= choice_idx < 2 + len(hash_list):
                selected_hash = hash_list[choice_idx - 2]
                return hash_groups[selected_hash][0]

            print("已取消")
            return None

    # repo 中没有同名 skill，但多个源 hash 不同
    print(f"\n⚠ '{name}' 在不同位置的内容不一致：")
    hash_list = sorted(hash_groups.keys())
    for i, h in enumerate(hash_list, 1):
        srcs = hash_groups[h]
        print(f"  [{i}] hash {h[:8]}... ({len(srcs)} 个):")
        for s in srcs:
            print(f"      {_unexpand_home(s)}")

    if auto_confirm:
        # 自动选择第一个版本（出现最早的）
        print(f"[WARNING] 存在内容冲突但 -y 已跳过，将使用第一个版本")
        return sources[0]

    try:
        choice = input(f"\n选择使用的版本 [1-{len(hash_list)}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n已取消")
        return None

    try:
        choice_idx = int(choice)
    except ValueError:
        print("已取消")
        return None

    if 1 <= choice_idx <= len(hash_list):
        selected_hash = hash_list[choice_idx - 1]
        return hash_groups[selected_hash][0]

    print("已取消")
    return None


def link_skill(name: str, config: Config, auto_confirm: bool = False, dry_run: bool = False) -> bool:
    """将野生 skill（Agent 目录或统一 Skill 目录中的真实文件目录）纳入管理。

    流程：
    1. 检查是否已被管理（状态文件/外部）
    2. 在 Agent 目录和统一 Skill 目录中查找野生 skill
    3. 检查内容冲突（MD5），让用户选择版本
    4. 确认后：copy 到自定义 Skill 仓库 → 删除原文件 → 创建 symlink → 写入状态文件
    """
    import shutil
    from .config import _unexpand_home

    external = get_external_skills(config.external.global_lock, config.external.local_lock)
    managed = get_managed_skills(config.state_file)

    # 检查是否已被管理
    if name in external:
        print(f"[ERROR] '{name}' 是外部 skill（由 npx skills 管理），不能纳入管理", file=sys.stderr)
        return False

    if name in managed:
        print(f"[ERROR] '{name}' 已纳入管理", file=sys.stderr)
        return False

    # 在 Agent 目录和统一 Skill 目录中查找
    sources = []
    for agent_dir in config.effective_agent_dirs:
        skill_path = agent_dir / name
        if skill_path.is_dir() and not skill_path.is_symlink() and (skill_path / "SKILL.md").is_file():
            sources.append(skill_path)

    # 也检查统一 Skill 目录
    agents_skill = config.agents_dir / name
    if agents_skill.is_dir() and not agents_skill.is_symlink() and (agents_skill / "SKILL.md").is_file():
        sources.append(agents_skill)

    # 去重
    sources = list({str(s.resolve()): s for s in sources}.values())

    if not sources:
        print(f"[ERROR] 未找到野生 skill '{name}'", file=sys.stderr)
        return False

    # 检查 repo 中是否已有同名 skill（不在 managed 中但文件存在）
    repo_skill = config.repo_skills_dir / name
    if repo_skill.is_dir() and not (config.repo_skills_dir / name / "SKILL.md").is_file():
        repo_skill = None  # 不是有效 skill

    # 解决内容冲突
    selected = _resolve_link_conflict(name, sources, repo_skill if repo_skill and repo_skill.is_dir() else None, auto_confirm)
    if selected is None:
        return False  # 用户取消或冲突未解决

    # 展示将执行的操作
    print(f"\n将 '{name}' 纳入管理：")
    print(f"  源: {_unexpand_home(selected)}")
    if len(sources) > 1:
        print(f"  （共 {len(sources)} 个位置，已选择上述版本）")
    print(f"  目标: {_unexpand_home(config.repo_skills_dir / name)}")
    print(f"  操作: 复制到自定义 Skill 仓库 → 删除原文件 → 创建 symlink")

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

    # 2. 复制到自定义 Skill 仓库（使用选定的源版本）
    shutil.copytree(str(selected), str(repo_skill))
    print(f"  [OK] 已复制到 {_unexpand_home(repo_skill)}")

    # 3. 删除所有原文件
    for s in sources:
        shutil.rmtree(s)
        print(f"  [OK] 已删除 {_unexpand_home(s)}")

    # 4. 创建 symlink
    state = create_all_links(name, config.agents_dir, config.repo_skills_dir, config.effective_agent_dirs, external_skills=external)

    # 5. 写入状态文件
    add_managed(name, config.state_file)

    print(f"  [OK] symlink 已创建")
    if state.agents_link_valid:
        print(f"     统一 Skill 目录: {_unexpand_home(config.agents_dir / name)} → 自定义 Skill 仓库")
    if state.agent_links_ok:
        for agent_name in state.agent_links_ok:
            print(f"     Agent Skill 目录: ~/{agent_name}/skills/{name} → 统一 Skill 目录")

    return True


# ============================================================
# unlink：从管理中移除 skill（还原文件）
# ============================================================

def _unlink_one(name: str, config: Config, dry_run: bool = False) -> bool:
    """从管理中移除单个 skill 的核心逻辑。"""
    import shutil
    from .config import _unexpand_home

    external = get_external_skills(config.external.global_lock, config.external.local_lock)
    managed = get_managed_skills(config.state_file)
    classification = classify_skill(name, config.agents_dir, managed, external, config.repo_skills_dir)

    if not classification.managed:
        return False

    if dry_run:
        print(f"[DRY-RUN] 将移除 '{name}':")
        if classification.custom_path and classification.custom_path.is_dir():
            print(f"  自定义 Skill 仓库: {_unexpand_home(classification.custom_path)} (将删除)")
        print(f"  统一 Skill 目录:   {_unexpand_home(config.agents_dir / name)} (将还原为真实文件)")
        print(f"  状态文件:          将移除 '{name}'")
        return True

    if not classification.custom_path or not classification.custom_path.is_dir():
        # 状态文件中有记录但 repo 中没有文件，直接从状态文件移除
        remove_managed(name, config.state_file)
        print(f"  [OK] {name}: 已从管理中移除（仓库中无文件）")
        return True

    # 1. 删除统一 Skill 目录 symlink
    remove_agents_link(name, config.agents_dir, config.repo_skills_dir)

    # 2. 将文件从自定义仓库移到统一 Skill 目录
    source = classification.custom_path
    target = config.agents_dir / name

    if target.is_symlink():
        target.unlink()
    elif target.is_dir():
        print(f"[WARNING] {_unexpand_home(target)} 已存在且不是 symlink，跳过文件还原")
        shutil.rmtree(source)
        remove_managed(name, config.state_file)
        return True

    shutil.copytree(str(source), str(target))
    shutil.rmtree(source)

    # 3. 从状态文件移除
    remove_managed(name, config.state_file)

    print(f"  [OK] {name}: 文件已还原到 {_unexpand_home(target)}")
    return True


def unlink_skill(
    names: list[str] | None,
    config: Config,
    auto_confirm: bool = False,
    dry_run: bool = False,
) -> bool:
    """从管理中移除 skill：还原文件到统一 Skill 目录，从状态文件移除。

    names 为 None 或包含 "--all" 时移除所有已管理 skill。
    """
    from .config import _unexpand_home

    external = get_external_skills(config.external.global_lock, config.external.local_lock)
    managed = get_managed_skills(config.state_file)

    if names and "--all" in names:
        names = None

    if names is not None:
        # 移除指定的 skills
        results = {}
        for name in names:
            classification = classify_skill(name, config.agents_dir, managed, external, config.repo_skills_dir)
            if classification.skill_type == "external":
                print(f"[ERROR] '{name}' 是外部 skill（由 npx skills 管理），不能通过 sync-skills 移除", file=sys.stderr)
                results[name] = False
                continue
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
                print(f"  统一 Skill 目录:   {_unexpand_home(config.agents_dir / name)} (将还原为真实文件)")
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

        success = sum(1 for v in results.values() if v)
        total = len(results)
        if total > 1:
            print(f"\n移除完成: {success}/{total} 个 skill")
        return all(results.values()) if results else True
    else:
        # 移除所有已管理 skill
        all_classifications = classify_all_skills(config.agents_dir, managed, external, config.repo_skills_dir)
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
            print(f"  文件将还原到 {_unexpand_home(config.agents_dir)}")
            try:
                confirm = input(f"\n确认移除全部 {len(custom)} 个? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n已取消")
                return False
            if confirm != "y":
                print("已取消")
                return False

        success = 0
        for c in custom:
            if _unlink_one(c.name, config):
                success += 1

        print(f"\n移除完成: {success}/{len(custom)} 个 skill")
        return success == len(custom)


# ============================================================
# init：初始化自定义 skill 仓库
# ============================================================

def _select_agents(config: Config) -> None:
    """交互式选择要管理的 Agent。"""
    from .config import _unexpand_home

    detected = []
    for d in DEFAULT_AGENT_DIRS:
        if d.is_dir():
            name = d.parent.name.lstrip(".")
            detected.append((name, d))

    if not detected:
        print("\n未检测到已安装的 Agent")
        return

    print(f"\n检测到已安装的 Agent:")
    for i, (name, path) in enumerate(detected):
        print(f"  [{i}] {name}  {_unexpand_home(path)}")

    # 显示当前选择
    current_indices = []
    if config.agent_dirs is not None:
        for i, (_, path) in enumerate(detected):
            if path in config.agent_dirs:
                current_indices.append(i)

    if current_indices:
        hint = ", ".join(str(i) for i in current_indices)
        prompt = f"\n选择要管理的 Agent (编号，逗号分隔，直接回车保持当前 [{hint}]): "
    else:
        prompt = "\n选择要管理的 Agent (编号，逗号分隔，直接回车全选): "

    try:
        select_input = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if select_input:
        # 支持中英文逗号
        indices = [int(x.strip()) for x in select_input.replace("，", ",").split(",") if x.strip().isdigit()]
        config.agent_dirs = [detected[i][1] for i in indices if 0 <= i < len(detected)]
    elif current_indices:
        # 直接回车，保持当前选择
        config.agent_dirs = [detected[i][1] for i in current_indices]
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


def init_repo(config: Config, auto_confirm: bool = False, dry_run: bool = False) -> bool:
    """初始化 ~/Skills/ 仓库。

    存量仓库（已有 git）：只创建 symlink + 保存配置，不触碰 git 历史。
    全新仓库（无 git）：git init + 迁移 skill + 初始 commit。
    """
    from .config import _unexpand_home, save_config
    from .git_ops import git_has_remote, git_is_repo

    print("=== sync-skills 初始化配置 ===\n")

    # 1. 确认仓库路径
    if not auto_confirm:
        _confirm_repo_path(config)

    repo = config.repo
    repo_skills_dir = config.repo_skills_dir
    agents_dir = config.agents_dir

    # 2. 检查 git 状态
    is_new_repo = not git_is_repo(repo)
    has_remote = False
    if is_new_repo:
        print(f"\n  {_unexpand_home(repo)} 不是 git 仓库，将创建新仓库")
    else:
        has_remote = git_has_remote(repo)
        if has_remote:
            print(f"\n[OK] {_unexpand_home(repo)} 已是 git 仓库（已关联远程）")
        else:
            print(f"\n[OK] {_unexpand_home(repo)} 已是 git 仓库（本地仓库）")

    # 3. 选择要管理的 Agent
    if not auto_confirm:
        _select_agents(config)

    # 4. 确保目录存在
    repo_skills_dir.mkdir(parents=True, exist_ok=True)

    # 5. 识别外部 skill 和分类（基于状态文件）
    external = get_external_skills(config.external.global_lock, config.external.local_lock)
    managed = get_managed_skills(config.state_file)
    all_classifications = classify_all_skills(agents_dir, managed, external, repo_skills_dir)

    # 已管理的 skill（状态文件中已有）
    already_managed = [c for c in all_classifications if c.managed]
    # 在 repo 中但不在状态文件中的 skill（存量仓库，需要补充到状态文件）
    in_repo_not_managed = []
    if repo_skills_dir.is_dir():
        for d in repo_skills_dir.iterdir():
            if d.name.startswith(".") or not d.is_dir():
                continue
            if not (d / "SKILL.md").is_file():
                continue
            if d.name not in managed and d.name not in external:
                in_repo_not_managed.append(d.name)
    # 孤儿 skill
    orphans = [c for c in all_classifications if c.skill_type == "orphan"]
    external_skills = [c for c in all_classifications if c.skill_type == "external"]

    print(f"\n  扫描完成: {len(already_managed)} 已管理, {len(in_repo_not_managed)} 存量未登记, {len(orphans)} 未管理, {len(external_skills)} 外部")

    # 6. 询问是否纳入孤儿 skill
    adopt_orphans: list = []
    if orphans and not auto_confirm:
        print(f"\n检测到 {len(orphans)} 个未管理的 skill:")
        for o in orphans:
            print(f"  - {o.name}")
        try:
            adopt_input = input("\n是否将这些 skill 纳入管理? (y/N) ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消")
            return False
        if adopt_input == "y":
            adopt_orphans = orphans
    elif orphans and auto_confirm:
        adopt_orphans = orphans

    # 7. 汇总需要创建软链接的 skill
    skills_to_link = list(already_managed) + [classify_skill(n, agents_dir, managed, external, repo_skills_dir) for n in in_repo_not_managed]
    if adopt_orphans:
        skills_to_link.extend(adopt_orphans)

    # 构建操作预览
    actions = []
    if is_new_repo:
        actions.append(f"初始化 git 仓库: {_unexpand_home(repo)}")
    if in_repo_not_managed:
        actions.append(f"补充登记 {len(in_repo_not_managed)} 个存量 skill 到状态文件")
    if adopt_orphans:
        actions.append(f"迁移 {len(adopt_orphans)} 个 skill → 自定义 Skill 仓库 {_unexpand_home(repo_skills_dir)}")
    if skills_to_link:
        actions.append(f"为 {len(skills_to_link)} 个 skill 创建 symlink")

    if not actions:
        print("\n没有需要执行的操作")
        save_config(config)
        return True

    # 8. 显示预览并确认
    if not auto_confirm and not dry_run:
        print(f"\n即将执行以下操作:")
        for i, action in enumerate(actions, 1):
            print(f"  {i}. {action}")

        if skills_to_link and config.effective_agent_dirs:
            agent_names = [d.parent.name.lstrip(".") for d in config.effective_agent_dirs]
            print(f"\n  为以下 {len(skills_to_link)} 个 skill 创建 symlink:")
            print(f"    统一 Skill 目录: {_unexpand_home(agents_dir)}")
            print(f"    Agent Skill 目录: {', '.join(f'~/{n}/skills' for n in agent_names)}")
            print()
            for s in skills_to_link:
                print(f"    - {s.name}")

        try:
            confirm = input("\n确认执行? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消")
            return False
        if confirm != "y":
            print("已取消")
            return False

    if dry_run:
        print(f"\n[DRY-RUN] 将执行以下操作:")
        for i, action in enumerate(actions, 1):
            print(f"  {i}. {action}")
        return True

    # 9. 执行
    print()

    # 存量仓库：检查 git 状态，有冲突就停下来
    if not is_new_repo:
        from .git_ops import git_status
        status = git_status(repo)
        if not status.is_clean:
            print("[ERROR] 仓库有未提交的更改，请先处理后再执行 init：")
            if status.staged:
                print(f"  已暂存: {', '.join(status.staged)}")
            if status.modified:
                print(f"  已修改: {', '.join(status.modified)}")
            if status.untracked:
                print(f"  未跟踪: {', '.join(status.untracked)}")
            return False
        if has_remote and status.behind > 0:
            print(f"[ERROR] 本地落后远程 {status.behind} 个 commit，请先执行 sync-skills pull")
            return False

    if is_new_repo:
        git_init(repo)
        print("[OK] git init 完成")

    migrated = 0
    linked = 0

    # 处理已管理的 skill（只创建 symlink）
    for skill in already_managed:
        name = skill.name
        target = repo_skills_dir / name
        if target.is_dir():
            from .symlink import create_agents_link, create_agent_links
            create_agents_link(name, agents_dir, repo_skills_dir)
            create_agent_links(name, agents_dir, config.effective_agent_dirs, external_skills=external)
            linked += 1
        elif (agents_dir / name).is_symlink():
            from .symlink import create_agents_link, create_agent_links
            create_agents_link(name, agents_dir, repo_skills_dir)
            create_agent_links(name, agents_dir, config.effective_agent_dirs, external_skills=external)
            linked += 1

    # 存量未登记的 skill（补充到状态文件 + 创建 symlink）
    for name in in_repo_not_managed:
        target = repo_skills_dir / name
        if target.is_dir():
            from .symlink import create_agents_link, create_agent_links
            create_agents_link(name, agents_dir, repo_skills_dir)
            create_agent_links(name, agents_dir, config.effective_agent_dirs, external_skills=external)
            add_managed(name, config.state_file)
            linked += 1
            print(f"  [登记] {name}")

    # 纳入孤儿 skill（迁移到自定义 Skill 仓库 + 写入状态文件）
    for skill in adopt_orphans:
        name = skill.name
        target = repo_skills_dir / name
        source = agents_dir / name

        if source.is_dir() and not source.is_symlink():
            import shutil
            shutil.copytree(str(source), str(target))
            shutil.rmtree(source)
            create_all_links(name, agents_dir, repo_skills_dir, config.effective_agent_dirs, external_skills=external)
            add_managed(name, config.state_file)
            migrated += 1
            print(f"  [迁移] {name}")
        elif source.is_symlink():
            from .symlink import create_agents_link, create_agent_links
            create_agents_link(name, agents_dir, repo_skills_dir)
            create_agent_links(name, agents_dir, config.effective_agent_dirs, external_skills=external)
            add_managed(name, config.state_file)
            linked += 1

    # 有文件变更时尝试 commit
    if migrated > 0:
        if git_add_commit(repo, "init: add custom skills via sync-skills"):
            print(f"[OK] 已提交 {migrated} 个迁移的 skill")
        else:
            print("[WARNING] git commit 失败，请手动提交")

    # 保存配置
    save_config(config)

    # 汇总
    total_managed = len(already_managed) + len(in_repo_not_managed) + len(adopt_orphans)
    print(f"\n初始化完成:")
    print(f"  已管理 skill: {total_managed} ({migrated} 迁移, {linked} 已链接)")
    print(f"  外部 skill:   {len(external_skills)} (由 npx skills 管理，不受影响)")
    remaining_orphans = len(orphans) - len(adopt_orphans)
    if remaining_orphans > 0:
        print(f"  未管理 skill: {remaining_orphans}")

    return True
