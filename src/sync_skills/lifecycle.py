"""Skill 生命周期管理：add / remove / init"""

import re
import sys
from pathlib import Path

from .classification import classify_all_skills, classify_skill, get_external_skills
from .config import Config
from .constants import DEFAULT_AGENT_DIRS, SKILL_SKELETON
from .git_ops import git_add_commit, git_has_remote, git_init
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
) -> bool:
    """创建新自定义 skill。

    1. 校验名称
    2. 检查不与外部 skill 冲突
    3. 创建 SKILL.md 骨架
    4. 建立软链接
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

    # 检查是否已存在
    if skill_dir.is_dir():
        print(f"[ERROR] skill '{name}' 已存在于 {skill_dir}", file=sys.stderr)
        return False
    if (agents_dir / name).is_dir():
        print(f"[ERROR] skill '{name}' 已存在于 {agents_dir / name}", file=sys.stderr)
        return False

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

def remove_skill(name: str, config: Config, auto_confirm: bool = False) -> bool:
    """删除自定义 skill。

    1. 验证是自定义 skill（不是外部）
    2. 删除软链接
    3. git rm
    """
    external = get_external_skills(config.external.global_lock, config.external.local_lock)
    classification = classify_skill(name, config.agents_dir, config.repo_skills_dir, external)

    if classification.skill_type == "external":
        print(f"[ERROR] '{name}' 是外部 skill（由 npx skills 管理），不能通过 sync-skills 删除", file=sys.stderr)
        return False

    if classification.skill_type == "orphan":
        print(f"[ERROR] '{name}' 未被管理（不在自定义仓库中）", file=sys.stderr)
        return False

    # 确认前先检查各层链接状态
    from .symlink import verify_links
    link_state = verify_links(name, config.agents_dir, config.repo_skills_dir, config.effective_agent_dirs)

    if not auto_confirm:
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
# uninstall：卸载 skill（还原文件，不删除）
# ============================================================

def _uninstall_one(name: str, config: Config) -> bool:
    """卸载单个自定义 skill 的核心逻辑。"""
    import shutil
    from .config import _unexpand_home

    external = get_external_skills(config.external.global_lock, config.external.local_lock)
    classification = classify_skill(name, config.agents_dir, config.repo_skills_dir, external)

    if classification.skill_type != "custom":
        return False

    if not classification.custom_path or not classification.custom_path.is_dir():
        return False

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
        return True

    shutil.copytree(str(source), str(target))
    shutil.rmtree(source)

    print(f"  [OK] {name}: 文件已还原到 {_unexpand_home(target)}")
    return True


def uninstall_skill(name: str | None, config: Config, auto_confirm: bool = False) -> bool:
    """卸载自定义 skill：还原文件到统一 Skill 目录，从自定义仓库移除。

    name 为 None 时卸载所有自定义 skill。
    """
    from .config import _unexpand_home

    external = get_external_skills(config.external.global_lock, config.external.local_lock)

    if name is not None:
        # 卸载单个
        classification = classify_skill(name, config.agents_dir, config.repo_skills_dir, external)
        if classification.skill_type == "external":
            print(f"[ERROR] '{name}' 是外部 skill（由 npx skills 管理），不能通过 sync-skills 卸载", file=sys.stderr)
            return False
        if classification.skill_type == "orphan":
            print(f"[ERROR] '{name}' 未被管理（不在自定义仓库中）", file=sys.stderr)
            return False
        if not classification.custom_path or not classification.custom_path.is_dir():
            print(f"[ERROR] '{name}' 在自定义 Skill 仓库中不存在", file=sys.stderr)
            return False

        if not auto_confirm:
            print(f"将卸载 skill '{name}':")
            print(f"  自定义 Skill 仓库: {_unexpand_home(classification.custom_path)} (将删除)")
            print(f"  统一 Skill 目录:   {_unexpand_home(config.agents_dir / name)} (将还原为真实文件)")
            try:
                confirm = input("确认卸载? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n已取消")
                return False
            if confirm != "y":
                print("已取消")
                return False

        return _uninstall_one(name, config)
    else:
        # 卸载所有
        all_classifications = classify_all_skills(config.agents_dir, config.repo_skills_dir, external)
        custom = [c for c in all_classifications if c.skill_type == "custom"]

        if not custom:
            print("没有自定义 skill 可卸载")
            return True

        if not auto_confirm:
            print(f"将卸载以下 {len(custom)} 个自定义 skill:")
            for c in custom:
                print(f"  - {c.name}")
            print(f"  文件将还原到 {_unexpand_home(config.agents_dir)}")
            try:
                confirm = input(f"\n确认卸载全部 {len(custom)} 个? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n已取消")
                return False
            if confirm != "y":
                print("已取消")
                return False

        success = 0
        for c in custom:
            if _uninstall_one(c.name, config):
                success += 1

        print(f"\n卸载完成: {success}/{len(custom)} 个 skill")
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


def init_repo(config: Config) -> bool:
    """初始化 ~/Skills/ 仓库。

    存量仓库（已有 git）：只创建 symlink + 保存配置，不触碰 git 历史。
    全新仓库（无 git）：git init + 迁移 skill + 初始 commit。
    """
    from .config import _unexpand_home, save_config
    from .git_ops import git_has_remote, git_is_repo

    print("=== sync-skills 初始化配置 ===\n")

    # 1. 确认仓库路径
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
    _select_agents(config)

    # 4. 确保目录存在
    repo_skills_dir.mkdir(parents=True, exist_ok=True)

    # 5. 识别外部 skill 和分类
    external = get_external_skills(config.external.global_lock, config.external.local_lock)
    all_classifications = classify_all_skills(agents_dir, repo_skills_dir, external)

    custom_skills = [c for c in all_classifications if c.skill_type == "custom"]
    orphans = [c for c in all_classifications if c.skill_type == "orphan"]
    external_skills = [c for c in all_classifications if c.skill_type == "external"]

    print(f"\n  扫描完成: {len(custom_skills)} 自定义, {len(orphans)} 未管理, {len(external_skills)} 外部")

    # 6. 询问是否纳入孤儿 skill
    adopt_orphans: list = []
    if orphans:
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

    # 7. 汇总需要创建软链接的 skill
    skills_to_link = list(custom_skills)
    if adopt_orphans:
        skills_to_link.extend(adopt_orphans)

    # 构建操作预览
    actions = []
    if is_new_repo:
        actions.append(f"初始化 git 仓库: {_unexpand_home(repo)}")
    if adopt_orphans:
        actions.append(f"迁移 {len(adopt_orphans)} 个 skill → 自定义 Skill 仓库 {_unexpand_home(repo_skills_dir)}")
    if skills_to_link:
        actions.append(f"为 {len(skills_to_link)} 个 skill 创建 symlink")

    if not actions:
        print("\n没有需要执行的操作")
        save_config(config)
        return True

    # 8. 显示预览并确认
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

    # 处理已有的自定义 skill（只创建 symlink，不迁移）
    for skill in custom_skills:
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

    # 纳入孤儿 skill（迁移到自定义 Skill 仓库）
    for skill in adopt_orphans:
        name = skill.name
        target = repo_skills_dir / name
        source = agents_dir / name

        if source.is_dir() and not source.is_symlink():
            import shutil
            shutil.copytree(str(source), str(target))
            shutil.rmtree(source)
            create_all_links(name, agents_dir, repo_skills_dir, config.effective_agent_dirs, external_skills=external)
            migrated += 1
            print(f"  [迁移] {name}")
        elif source.is_symlink():
            from .symlink import create_agents_link, create_agent_links
            create_agents_link(name, agents_dir, repo_skills_dir)
            create_agent_links(name, agents_dir, config.effective_agent_dirs, external_skills=external)
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
    total_custom = len(custom_skills) + len(adopt_orphans)
    print(f"\n初始化完成:")
    print(f"  自定义 skill: {total_custom} ({migrated} 迁移, {linked} 已链接)")
    print(f"  外部 skill:   {len(external_skills)} (由 npx skills 管理，不受影响)")
    remaining_orphans = len(orphans) - len(adopt_orphans)
    if remaining_orphans > 0:
        print(f"  未管理 skill: {remaining_orphans}")

    return True
