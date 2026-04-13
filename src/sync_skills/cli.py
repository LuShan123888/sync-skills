#!/usr/bin/env python3
"""sync-skills: 自定义 Skill 生命周期管理器

v1.0 — 基于 git + symlink + 状态文件管理用户自创建的 skill。
外部 skill（由 npx skills 管理）不受影响。

命令：
  sync-skills init           初始化 ~/Skills/ 仓库
  sync-skills link <name>    纳入野生 skill（--all 全部纳入）
  sync-skills unlink <name>  从管理中移除（--all 全部移除）
  sync-skills add <name>     创建新 skill
  sync-skills remove <name>  删除自定义 skill（支持多个）
  sync-skills fix            验证/修复异常状态
  sync-skills list           列出已管理 skill
  sync-skills status         显示 git 状态 + 管理状态
  sync-skills push           git commit + push
  sync-skills pull           git pull + 修复软链接
  sync-skills search <query> 搜索已管理 skill
  sync-skills info <name>    显示 skill 详情

旧版模式（copy）：
  sync-skills --copy       使用旧版 copy 同步逻辑
"""

import argparse
import sys
from pathlib import Path

from . import __version__
from .classification import classify_all_skills, get_external_skills
from .config import Config, _unexpand_home, load_config, save_config
from .git_ops import git_add_commit, git_is_repo, git_pull, git_push, git_status
from .lifecycle import add_skill, detect_wild_skills, init_repo, link_skill, remove_skill, unlink_skill
from .state import get_managed_skills
from .symlink import create_all_links, create_agents_link, sync_all_links

# ============================================================
# 重新导出旧版函数（保持测试兼容）
# ============================================================

# 数据结构
from .sync_legacy import (  # noqa: E402
    Color,
    ConflictResolution,
    Skill,
    SkillVersion,
    SyncOp,
    SyncPlan,
)

# 扫描与哈希
from .sync_legacy import (  # noqa: E402
    check_duplicate_names,
    find_skill_in_source_by_name,
    find_skill_in_targets,
    find_skill_path,
    find_skills_in_source,
    find_skills_in_target,
    skill_dir_hash,
)

# 预览/执行
from .sync_legacy import (  # noqa: E402
    ask_base_selection,
    ask_confirmation,
    ask_conflict_resolution,
    execute_bidirectional,
    execute_delete,
    execute_force,
    preview_bidirectional,
    preview_force,
    show_overview,
    show_preview,
    verify_sync,
    _build_skill_version,
    _resolve_conflicts,
)

# 删除/搜索/列表
from .sync_legacy import (  # noqa: E402
    _run_init_wizard,
)

# 颜色输出（metadata.py 也依赖）
from .sync_legacy import log_info, log_success, log_warning, log_error  # noqa: E402

# 其他旧版函数（测试可能直接 import）
from .sync_legacy import (  # noqa: E402
    _build_alias_map,
    _short_path,
    _fmt_time,
    parse_legacy_args as parse_args_legacy,
)


# ============================================================
# 新版命令处理
# ============================================================

def _load_config_or_default(args) -> Config:
    """加载配置，优先使用命令行参数。"""
    return load_config(args.config)


def _get_dry_run(args) -> bool:
    """获取 dry-run 标志。"""
    return getattr(args, "dry_run", False)


def cmd_init(args):
    """初始化 ~/Skills/ 仓库。"""
    config = _load_config_or_default(args)
    init_repo(config, auto_confirm=args.yes, dry_run=_get_dry_run(args))


def cmd_add(args):
    """创建新自定义 skill。"""
    config = _load_config_or_default(args)
    tags = [t.strip() for t in args.tags.split(",")] if args.tags else None
    if add_skill(args.name, config, description=args.description or "", tags=tags, dry_run=_get_dry_run(args)):
        _verify_after_change(config)


def cmd_remove(args):
    """删除自定义 skill（支持多个）。"""
    config = _load_config_or_default(args)
    names = args.names if isinstance(args.names, list) else [args.names]
    success = True
    for name in names:
        if not remove_skill(name, config, auto_confirm=args.yes, dry_run=_get_dry_run(args)):
            success = False
        else:
            _verify_after_change(config)
    return success


def cmd_unlink(args):
    """从管理中移除 skill（支持多个，--all 全部移除）。"""
    config = _load_config_or_default(args)
    names = args.names if args.names else None
    if unlink_skill(names, config, auto_confirm=args.yes, dry_run=_get_dry_run(args)):
        _verify_after_change(config)


def cmd_link(args):
    """将野生 skill 纳入管理（支持多个，--all 全部纳入）。"""
    config = _load_config_or_default(args)

    if args.all:
        # link all wild skills
        wild = detect_wild_skills(config)
        if not wild:
            print("没有发现野生 skill")
            return
        success = True
        for item in wild:
            if not link_skill(item["name"], config, auto_confirm=args.yes, dry_run=_get_dry_run(args)):
                success = False
            else:
                _verify_after_change(config)
        return

    if args.names:
        # link specific skills
        success = True
        for name in args.names:
            if not link_skill(name, config, auto_confirm=args.yes, dry_run=_get_dry_run(args)):
                success = False
            else:
                _verify_after_change(config)
        return

    # 无参数：列出野生 skill
    wild = detect_wild_skills(config)
    if not wild:
        print("没有发现野生 skill")
        return
    print(f"发现 {len(wild)} 个野生 skill:\n")
    for item in wild:
        print(f"  {item['name']}")
        for src in item['sources']:
            print(f"      {_unexpand_home(src)}")
    print(f"\n使用 'sync-skills link <name> -y' 纳入管理")
    print(f"使用 'sync-skills link --all -y' 纳入全部")


def cmd_list(args):
    """列出已管理 skill。"""
    config = _load_config_or_default(args)
    external = get_external_skills(config.external.global_lock, config.external.local_lock)
    managed = get_managed_skills(config.state_file)

    if not managed:
        print("没有已管理的 skill")
        return

    # 收集所有 skill 分类
    all_skills = classify_all_skills(config.agents_dir, managed, external, config.repo_skills_dir)

    custom = [s for s in all_skills if s.managed]

    if not custom:
        print("没有已管理的 skill")
        return

    # 过滤 tags
    if args.tags:
        from .metadata import parse_frontmatter
        filtered = []
        for s in custom:
            if s.custom_path:
                meta = parse_frontmatter(s.custom_path / "SKILL.md")
                if any(t in meta.tags for t in args.tags):
                    filtered.append(s)
            else:
                filtered.append(s)
        custom = filtered

    print(f"已管理 skill ({len(custom)} 个):\n")
    for s in custom:
        link_status = "✓" if s.has_custom_link else "✗"
        print(f"  {link_status} {s.name}")
        if s.custom_path:
            print(f"      自定义 Skill 仓库: {s.custom_path}")

    # 提示孤儿
    orphans = [s for s in all_skills if s.skill_type == "orphan"]
    if orphans:
        print(f"\n未管理的 skill ({len(orphans)} 个):")
        for s in orphans:
            print(f"  ? {s.name}")


def cmd_status(args):
    """显示完整状态：git 状态 + skill 管理状态。"""
    config = _load_config_or_default(args)
    repo = config.repo

    # === Git 状态 ===
    if not git_is_repo(repo):
        print(f"[ERROR] {repo} 不是 git 仓库")
        return

    status = git_status(repo)

    print(f"分支: {status.branch or '(未命名)'}")
    if status.ahead > 0:
        print(f"领先远程: {status.ahead} 个 commit")
    if status.behind > 0:
        print(f"落后远程: {status.behind} 个 commit")

    if status.is_clean:
        print("\n工作区干净")
    else:
        if status.staged:
            print(f"\n已暂存 ({len(status.staged)}):")
            for f in status.staged:
                print(f"  {f}")
        if status.modified:
            print(f"\n已修改 ({len(status.modified)}):")
            for f in status.modified:
                print(f"  {f}")
        if status.untracked:
            print(f"\n未跟踪 ({len(status.untracked)}):")
            for f in status.untracked:
                print(f"  {f}")

    # === Skill 管理状态 ===
    external = get_external_skills(config.external.global_lock, config.external.local_lock)
    managed = get_managed_skills(config.state_file)
    all_classifications = classify_all_skills(config.agents_dir, managed, external, config.repo_skills_dir)

    custom = [c for c in all_classifications if c.managed]
    orphans = [c for c in all_classifications if c.skill_type == "orphan"]
    external_skills = [c for c in all_classifications if c.skill_type == "external"]

    print(f"\n--- Skill 状态 ---")
    print(f"已管理: {len(custom)}")
    if custom:
        for c in custom:
            link = "✓" if c.has_custom_link else "✗"
            print(f"  {link} {c.name}")

    if orphans:
        print(f"未管理 (孤儿): {len(orphans)}")
        for o in orphans:
            print(f"  ? {o.name}")

    print(f"外部 (npx skills): {len(external_skills)}")

    # === Symlink 健康 ===
    broken = _detect_broken_agent_links(config)
    if broken:
        print(f"\n断链 symlink: {len(broken)}")
        for path in broken:
            print(f"  ✗ {_unexpand_home(path)}")

    # === 状态文件一致性 ===
    inconsistencies = _detect_state_inconsistencies(config, managed, external)
    if inconsistencies:
        print(f"\n状态不一致: {len(inconsistencies)}")
        for item in inconsistencies:
            print(f"  ! {item}")


def cmd_push(args):
    """git add + commit + push。执行前展示完整 git 命令让用户确认。"""
    config = _load_config_or_default(args)
    repo = config.repo

    if not git_is_repo(repo):
        print(f"[ERROR] {repo} 不是 git 仓库")
        return

    from .git_ops import git_get_remote_url, git_get_tracking_branch, git_has_remote

    message = args.message or "update skills"
    status = git_status(repo)
    branch = status.branch or "(未命名)"

    # 展示将要执行的 git 命令
    print("即将执行:")
    print(f"  cd {_unexpand_home(repo)}")
    print(f"  git add -A")
    print(f"  git commit -m \"{message}\"")

    has_remote = git_has_remote(repo)
    if has_remote:
        tracking = git_get_tracking_branch(repo)
        push_target = tracking.replace("origin/", "") if tracking else branch
        print(f"  git push -u origin {push_target}")

        # 展示分支状态
        print(f"\n分支: {branch}")
        if tracking:
            print(f"追踪: {tracking}")
        if status.ahead > 0:
            print(f"领先远程: {status.ahead} 个 commit")
        if status.behind > 0:
            print(f"落后远程: {status.behind} 个 commit (建议先 sync-skills pull)")
        print(f"远程: {git_get_remote_url(repo)}")
    else:
        print(f"\n[WARNING] 尚未配置远程仓库，将仅执行本地 commit")

    if _get_dry_run(args):
        print("\n[DRY-RUN] 以上命令不会执行")
        return

    if not args.yes:
        try:
            confirm = input("\n确认执行? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消")
            return
        if confirm != "y":
            print("已取消")
            return

    # 执行 commit
    if git_add_commit(repo, message):
        print("[OK] 已提交")
    else:
        if not git_status(repo).is_clean:
            print("[ERROR] 提交失败")
            return
        # 无变更，继续 push

    # 执行 push
    if has_remote:
        success, reason = git_push(repo)
        if success:
            print("[OK] 已推送到远程")
        elif reason == "behind":
            print("[WARNING] 本地落后远程，请先执行 sync-skills pull")
        else:
            print("[WARNING] 推送失败，请检查远程仓库配置和网络")


def cmd_pull(args):
    """git pull + 修复软链接。"""
    config = _load_config_or_default(args)
    repo = config.repo

    if not git_is_repo(repo):
        print(f"[ERROR] {repo} 不是 git 仓库")
        return

    # Pull 前：检查 skill 管理状态
    state = _check_state(config)
    has_issues = any([state["broken_links"], state["missing_links"], state["orphans"], state["inconsistencies"]])
    if has_issues:
        print("⚠ 当前 skill 管理状态存在异常:")
        if state["broken_links"]:
            print(f"  - 断链 symlink: {len(state['broken_links'])} 个")
        if state["missing_links"]:
            print(f"  - 缺失 symlink: {len(state['missing_links'])} 个")
        if state["orphans"]:
            print(f"  - 未被管理的 skill: {len(state['orphans'])} 个")
        if state["inconsistencies"]:
            print(f"  - 状态不一致: {len(state['inconsistencies'])} 个")
        if not args.yes:
            try:
                confirm = input("\n建议先执行 sync-skills fix 修复异常。是否继续 pull? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n已取消")
                return
            if confirm != "y":
                return

    # 展示将要执行的 git 命令
    from .git_ops import git_get_tracking_branch
    branch = git_status(repo).branch or "(未命名)"
    tracking = git_get_tracking_branch(repo)
    if tracking:
        pull_cmd = "git pull --rebase"
    else:
        pull_cmd = f"git pull --rebase origin {branch}"

    print("即将执行:")
    print(f"  cd {_unexpand_home(repo)}")
    print(f"  {pull_cmd}")
    if tracking:
        print(f"\n追踪: {tracking}")
    else:
        print(f"\n[WARNING] 未设置追踪分支，将使用: {pull_cmd}")

    if _get_dry_run(args):
        print("\n[DRY-RUN] 以上命令不会执行")
        return

    if not args.yes:
        try:
            confirm = input("\n确认执行? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消")
            return
        if confirm != "y":
            print("已取消")
            return

    success, msg = git_pull(repo)
    if not success:
        print(f"[ERROR] pull 失败: {msg}")
        return

    print(f"[OK] {msg}")

    # Pull 后：修复软链接
    _do_sync(config, auto_confirm=args.yes)


def cmd_fix(args):
    """验证/修复软链接和状态一致性。"""
    config = _load_config_or_default(args)
    _do_sync(config, auto_confirm=args.yes)


def _do_sync(config: Config, auto_confirm: bool = False):
    """执行状态检查和修复。"""
    from .config import _unexpand_home

    external = get_external_skills(config.external.global_lock, config.external.local_lock)
    managed = get_managed_skills(config.state_file)

    # 1. 验证/修复已管理 skill 的 symlink
    states = sync_all_links(
        config.agents_dir,
        config.repo_skills_dir,
        config.effective_agent_dirs,
        external_skills=external,
        managed_skills=managed,
    )

    created = 0
    verified = 0
    issues = 0

    if states:
        for s in states:
            if s.agents_link_valid:
                verified += 1
            else:
                if s.agents_link_exists:
                    issues += 1
                else:
                    created += 1

        total = len(states)
        parts = []
        if verified:
            parts.append(f"✓ {verified} 已验证")
        if created:
            parts.append(f"+ {created} 已创建")
        if issues:
            parts.append(f"! {issues} 需要关注")

        print(f"已管理 skill ({total} 个): {'  '.join(parts)}")

        for s in states:
            if not s.agents_link_valid:
                print(f"  ! {s.name}: 统一 Skill 目录 symlink 异常")
            if s.agent_links_missing:
                print(f"  ! {s.name}: Agent Skill 目录 symlink 缺失 ({', '.join(s.agent_links_missing)})")
    else:
        print("没有已管理的 skill")

    # 2. 检测断链 symlink
    broken = _detect_broken_agent_links(config)
    if broken:
        print(f"\n⚠ 检测到 {len(broken)} 个断链 symlink:")
        for path in broken:
            print(f"  - {_unexpand_home(path)}")
        if auto_confirm:
            for path in broken:
                path.unlink()
            print(f"  [OK] 已清理 {len(broken)} 个断链 symlink")
        else:
            try:
                confirm = input("是否清理? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n已跳过")
                return
            if confirm == "y":
                for path in broken:
                    path.unlink()
                print(f"  [OK] 已清理 {len(broken)} 个断链 symlink")

    # 3. 检测状态文件与实际不一致
    inconsistencies = _detect_state_inconsistencies(config, managed, external)
    if inconsistencies:
        print(f"\n⚠ 检测到 {len(inconsistencies)} 个状态不一致:")
        for item in inconsistencies:
            print(f"  - {item}")

    # 4. 检测孤儿 skill（未被管理）
    orphans = _detect_orphan_skills(config, external, managed)
    if orphans:
        print(f"\n⚠ 检测到 {len(orphans)} 个未被管理的 skill:")
        for name in orphans:
            print(f"  - {name}")
        if auto_confirm:
            _adopt_orphans(config, orphans, external, managed)
        else:
            try:
                confirm = input("是否纳入管理（迁移到自定义 Skill 仓库）? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n已跳过")
                return
            if confirm == "y":
                _adopt_orphans(config, orphans, external, managed)


def _adopt_orphans(config: Config, orphans: list[str], external: set[str], managed: set[str]):
    """纳入孤儿 skill 到管理中。"""
    import shutil
    from .config import _unexpand_home
    from .state import add_managed

    adopted = 0
    for name in orphans:
        source = config.agents_dir / name
        target = config.repo_skills_dir / name
        if source.is_dir() and not source.is_symlink():
            shutil.copytree(str(source), str(target))
            shutil.rmtree(source)
            create_all_links(name, config.agents_dir, config.repo_skills_dir,
                             config.effective_agent_dirs, external_skills=external)
            add_managed(name, config.state_file)
            adopted += 1
            print(f"  [OK] {name}: 已迁移到 {_unexpand_home(target)}")
        elif source.is_symlink():
            create_agents_link(name, config.agents_dir, config.repo_skills_dir)
            create_all_links(name, config.agents_dir, config.repo_skills_dir,
                             config.effective_agent_dirs, external_skills=external)
            add_managed(name, config.state_file)
            adopted += 1
            print(f"  [OK] {name}: 已重建 symlink")
    if adopted:
        print(f"\n  已纳入 {adopted}/{len(orphans)} 个 skill")


def _detect_broken_agent_links(config: Config) -> list[Path]:
    """检测 Agent Skill 目录中指向统一 Skill 目录的断链 symlink。"""
    broken = []
    agents_dir = config.agents_dir
    for agent_dir in config.effective_agent_dirs:
        if not agent_dir.is_dir():
            continue
        for d in agent_dir.iterdir():
            if not d.is_symlink():
                continue
            # 只检测指向 agents_dir 的 symlink（由 sync-skills 创建的）
            try:
                resolved = d.resolve()
                if resolved.parent == agents_dir:
                    # 目标在 agents_dir 中，检查目标是否存在
                    if not resolved.exists() or not resolved.is_dir():
                        broken.append(d)
            except OSError:
                broken.append(d)
    return broken


def _detect_missing_agents_links(config: Config, external_skills: set[str], managed_skills: set[str]) -> list[str]:
    """检测已管理 skill 中缺少统一 Skill 目录 symlink 的 skill。"""
    missing = []
    agents_dir = config.agents_dir
    repo_skills_dir = config.repo_skills_dir
    for name in managed_skills:
        if name in external_skills:
            continue
        # 如果 repo 中没有文件，跳过（可能是远程删除了）
        if not (repo_skills_dir / name).is_dir():
            continue
        link = agents_dir / name
        if not link.exists() and not link.is_symlink():
            missing.append(name)
    return missing


def _detect_orphan_skills(config: Config, external_skills: set[str], managed_skills: set[str]) -> list[str]:
    """检测未被管理的 skill（在统一 Skill 目录中但不在状态文件中且不是外部 skill）。"""
    all_classifications = classify_all_skills(config.agents_dir, managed_skills, external_skills, config.repo_skills_dir)
    return [c.name for c in all_classifications if c.skill_type == "orphan"]


def _detect_state_inconsistencies(config: Config, managed_skills: set[str], external_skills: set[str]) -> list[str]:
    """检测状态文件与实际文件系统的不一致。"""
    issues = []
    repo_skills_dir = config.repo_skills_dir

    for name in managed_skills:
        if name in external_skills:
            issues.append(f"{name}: 已管理但同时是外部 skill（冲突）")
            continue
        # 状态文件中有记录但 repo 中没有文件
        if not (repo_skills_dir / name).is_dir():
            issues.append(f"{name}: 已管理但仓库中无文件（可能需要 sync-skills pull）")

    return issues


def _check_state(config: Config) -> dict:
    """非交互式检查 skill 管理状态，返回各类异常。"""
    external = get_external_skills(config.external.global_lock, config.external.local_lock)
    managed = get_managed_skills(config.state_file)
    return {
        "broken_links": _detect_broken_agent_links(config),
        "missing_links": _detect_missing_agents_links(config, external, managed),
        "orphans": _detect_orphan_skills(config, external, managed),
        "inconsistencies": _detect_state_inconsistencies(config, managed, external),
    }


def _verify_after_change(config: Config):
    """变更后验证 skill 管理状态（非交互式，仅报告）。"""
    state = _check_state(config)
    issues = []
    if state["broken_links"]:
        issues.append(f"断链 symlink: {len(state['broken_links'])} 个")
    if state["missing_links"]:
        issues.append(f"缺失 symlink: {len(state['missing_links'])} 个")
    if state["orphans"]:
        issues.append(f"未被管理的 skill: {len(state['orphans'])} 个")
    if state["inconsistencies"]:
        issues.append(f"状态不一致: {len(state['inconsistencies'])} 个")
    if issues:
        print(f"\n⚠ 检测到异常:")
        for issue in issues:
            print(f"  - {issue}")
        print("  建议执行 sync-skills fix 检查并修复")


def cmd_search(args):
    """搜索已管理 skill。"""
    config = _load_config_or_default(args)
    managed = get_managed_skills(config.state_file)
    repo_skills_dir = config.repo_skills_dir

    if not managed:
        print("没有已管理的 skill")
        return

    from .metadata import search_skills
    results = search_skills(repo_skills_dir, args.query)

    # 只显示已管理的 skill
    managed_results = [(s, m) for s, m in results if s.name in managed]

    if not managed_results:
        print(f"没有找到匹配 '{args.query}' 的已管理 skill")
        return

    print(f"找到 {len(managed_results)} 个结果:\n")
    for skill, meta in managed_results:
        print(f"  {skill.name}")
        if meta.description:
            print(f"    {meta.description[:80]}")
        if meta.tags:
            print(f"    tags: {', '.join(meta.tags)}")


def cmd_info(args):
    """显示 skill 详情。"""
    config = _load_config_or_default(args)
    name = args.name
    external = get_external_skills(config.external.global_lock, config.external.local_lock)
    managed = get_managed_skills(config.state_file)

    from .classification import classify_skill, get_lock_source
    classification = classify_skill(name, config.agents_dir, managed, external, config.repo_skills_dir)

    if classification.skill_type == "orphan" and not classification.agents_path:
        print(f"skill '{name}' 不存在")
        return

    print(f"Skill: {name}")
    print(f"类型: {classification.skill_type}")

    if classification.skill_type == "external":
        source = get_lock_source(name, config.external.global_lock, config.external.local_lock)
        print(f"来源: {source or '未知'}")
        print(f"管理: npx skills")
    elif classification.managed:
        if classification.custom_path:
            print(f"自定义 Skill 仓库: {classification.custom_path}")
        print(f"统一 Skill 目录: {'✓ 正常' if classification.has_custom_link else '✗ 缺失'}")
        print(f"管理: sync-skills")
    else:
        print(f"管理: 未管理（孤儿）")

    # 显示元数据
    skill_md = None
    if classification.custom_path:
        skill_md = classification.custom_path / "SKILL.md"
    elif classification.agents_path:
        skill_md = classification.agents_path / "SKILL.md"

    if skill_md and skill_md.is_file():
        from .metadata import parse_frontmatter
        meta = parse_frontmatter(skill_md)
        if meta.description:
            print(f"描述: {meta.description}")
        if meta.tags:
            print(f"标签: {', '.join(meta.tags)}")
        if meta.tools:
            print(f"工具: {', '.join(meta.tools)}")


# ============================================================
# 参数解析
# ============================================================

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sync-skills",
        description="sync-skills — 自定义 Skill 生命周期管理器 (v1.0)",
        epilog=(
            "examples:\n"
            "  sync-skills init                 initialize ~/Skills/ repo\n"
            "  sync-skills link my-skill       link wild skill into management\n"
            "  sync-skills link --all -y       link all wild skills\n"
            "  sync-skills unlink my-skill     remove from management\n"
            "  sync-skills unlink --all -y     unlink all managed skills\n"
            "  sync-skills add my-skill        create new custom skill\n"
            "  sync-skills remove a b          remove multiple skills\n"
            "  sync-skills fix                 verify/repair symlinks\n"
            "  sync-skills list                list managed skills\n"
            "  sync-skills status              show git + management status\n"
            "  sync-skills push -m 'update'    commit and push\n"
            "  sync-skills pull                pull and rebuild links\n"
            "  sync-skills search 'review'     search managed skills\n"
            "  sync-skills info my-skill       show skill details\n"
            "  sync-skills --copy              legacy copy-based sync\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--copy", action="store_true", help="use legacy copy-based sync mode")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run", help="preview without executing")
    parser.add_argument("-y", "--yes", action="store_true", help="skip confirmation")
    parser.add_argument("-v", "--version", action="version", version=f"sync-skills {__version__}")

    subparsers = parser.add_subparsers(dest="command")

    # init
    sub_init = subparsers.add_parser("init", help="initialize ~/Skills/ repo")
    sub_init.add_argument("--config", type=Path, default=None)
    sub_init.add_argument("--dry-run", action="store_true", dest="dry_run")
    sub_init.add_argument("-y", "--yes", action="store_true")

    # add
    sub_add = subparsers.add_parser("add", help="create new custom skill")
    sub_add.add_argument("name", help="skill name (kebab-case)")
    sub_add.add_argument("--description", "-d", default="", help="skill description")
    sub_add.add_argument("--tags", "-t", default="", help="comma-separated tags")
    sub_add.add_argument("--config", type=Path, default=None)
    sub_add.add_argument("--dry-run", action="store_true", dest="dry_run")
    sub_add.add_argument("-y", "--yes", action="store_true")

    # link
    sub_link = subparsers.add_parser("link", help="link wild skill(s) into management")
    sub_link.add_argument("names", nargs="*", default=None, help="skill name(s) (omit to list, --all for all)")
    sub_link.add_argument("--all", action="store_true", help="link all wild skills")
    sub_link.add_argument("--config", type=Path, default=None)
    sub_link.add_argument("--dry-run", action="store_true", dest="dry_run")
    sub_link.add_argument("-y", "--yes", action="store_true")

    # unlink
    sub_unlink = subparsers.add_parser("unlink", help="unlink skill(s) from management")
    sub_unlink.add_argument("names", nargs="*", default=None, help="skill name(s) (omit to unlink all)")
    sub_unlink.add_argument("--all", action="store_true", help="unlink all managed skills")
    sub_unlink.add_argument("--config", type=Path, default=None)
    sub_unlink.add_argument("--dry-run", action="store_true", dest="dry_run")
    sub_unlink.add_argument("-y", "--yes", action="store_true")

    # remove
    sub_remove = subparsers.add_parser("remove", help="remove custom skill(s)")
    sub_remove.add_argument("names", nargs="+", help="skill name(s)")
    sub_remove.add_argument("--config", type=Path, default=None)
    sub_remove.add_argument("--dry-run", action="store_true", dest="dry_run")
    sub_remove.add_argument("-y", "--yes", action="store_true")

    # list
    sub_list = subparsers.add_parser("list", help="list managed skills")
    sub_list.add_argument("--tags", type=str, default=None, help="filter by tags")
    sub_list.add_argument("--config", type=Path, default=None)

    # status
    sub_status = subparsers.add_parser("status", help="show git + management status")
    sub_status.add_argument("--config", type=Path, default=None)

    # push
    sub_push = subparsers.add_parser("push", help="git commit and push")
    sub_push.add_argument("--message", "-m", default="", help="commit message")
    sub_push.add_argument("--config", type=Path, default=None)
    sub_push.add_argument("--dry-run", action="store_true", dest="dry_run")
    sub_push.add_argument("-y", "--yes", action="store_true")

    # pull
    sub_pull = subparsers.add_parser("pull", help="git pull and rebuild links")
    sub_pull.add_argument("--config", type=Path, default=None)
    sub_pull.add_argument("--dry-run", action="store_true", dest="dry_run")
    sub_pull.add_argument("-y", "--yes", action="store_true")

    # fix
    sub_fix = subparsers.add_parser("fix", help="verify/repair symlinks and state")
    sub_fix.add_argument("--config", type=Path, default=None)
    sub_fix.add_argument("--dry-run", action="store_true", dest="dry_run")
    sub_fix.add_argument("-y", "--yes", action="store_true")

    # search
    sub_search = subparsers.add_parser("search", help="search managed skills")
    sub_search.add_argument("query", help="search query")
    sub_search.add_argument("--config", type=Path, default=None)

    # info
    sub_info = subparsers.add_parser("info", help="show skill details")
    sub_info.add_argument("name", help="skill name")
    sub_info.add_argument("--config", type=Path, default=None)

    args = parser.parse_args(argv)
    return args


# ============================================================
# 主入口
# ============================================================

def main(argv: list[str] | None = None):
    # 自动检测旧版参数格式（--source, --force, --delete, --targets）
    # 或旧版子命令（init/list/search/info），路由到 --copy 模式
    if argv is not None:
        has_legacy_args = any(
            a in argv for a in ("--source", "--force", "--delete", "--targets", "-d", "-f")
        )
        # 旧版子命令：init/list/search/info 全部走旧版以保持兼容
        if not has_legacy_args and len(argv) > 0:
            first = argv[0] if argv else ""
            if first in ("init", "list", "search", "info"):
                has_legacy_args = True
        if has_legacy_args:
            from .sync_legacy import main_legacy
            main_legacy(argv)
            return

    args = parse_args(argv)

    # --copy 模式：使用旧版 copy 同步
    if args.copy:
        from .sync_legacy import main_legacy
        main_legacy(argv)
        return

    # 无子命令 → 显示帮助
    if not args.command:
        parse_args(["--help"])
        return

    # 命令分发
    commands = {
        "init": cmd_init,
        "link": cmd_link,
        "unlink": cmd_unlink,
        "add": cmd_add,
        "remove": cmd_remove,
        "list": cmd_list,
        "status": cmd_status,
        "push": cmd_push,
        "pull": cmd_pull,
        "fix": cmd_fix,
        "sync": cmd_fix,  # 兼容旧名
        "search": cmd_search,
        "info": cmd_info,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        print(f"未知命令: {args.command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
