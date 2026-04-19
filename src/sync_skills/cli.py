#!/usr/bin/env python3
"""sync-skills: 自定义 Skill 生命周期管理器

v1.1 — 基于 git + symlink + 状态文件管理用户自创建的 skill。

命令：
  sync-skills init              初始化 ~/Skills/ 仓库
  sync-skills link <name>       纳入 skill（按名称自动扫描）
  sync-skills unlink <name>     从管理中移除（--all 全部移除）
  sync-skills new <name>        创建新 skill
  sync-skills remove <name>     删除自定义 skill（支持多个）
  sync-skills doctor            验证/修复异常状态
  sync-skills list              列出已管理 skill
  sync-skills status            显示 git 状态 + 管理状态
  sync-skills commit            git add + commit
  sync-skills push              git commit + push
  sync-skills pull              git pull + 修复软链接

旧版模式（copy）：
  sync-skills --copy            使用旧版 copy 同步逻辑
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from .classification import classify_all_skills
from .config import Config, _unexpand_home, load_config, save_config
from .git_ops import (
    git_add_commit,
    git_collect_skill_changes,
    git_is_repo,
    git_pull,
    git_push,
    git_recent_commits,
    git_status,
)
from .lifecycle import add_skill, init_repo, link_skill, remove_skill, unlink_skill
from .state import align_state_with_repo, get_managed_skills
from .symlink import check_and_repair_links

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
    init_repo(config, auto_confirm=args.yes, dry_run=_get_dry_run(args), config_path=args.config)


def cmd_new(args):
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
    """将 skill 纳入管理（按名称自动扫描）。"""
    config = _load_config_or_default(args)

    if not args.name:
        print("用法: sync-skills link <name> [-y]", file=sys.stderr)
        print("  <name>  skill 名称（自动扫描所有 agent 目录和仓库）", file=sys.stderr)
        return

    if link_skill(args.name, config, auto_confirm=args.yes, dry_run=_get_dry_run(args)):
        _verify_after_change(config)


def cmd_list(args):
    """列出已管理 skill。"""
    config = _load_config_or_default(args)
    managed = get_managed_skills(config.state_file)

    if not managed:
        print("没有已管理的 skill")
        return

    # 收集所有 skill 分类
    all_skills = classify_all_skills(managed, config.repo_skills_dir, config.effective_agent_dirs)

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
    managed = get_managed_skills(config.state_file)
    all_classifications = classify_all_skills(managed, config.repo_skills_dir, config.effective_agent_dirs)

    custom = [c for c in all_classifications if c.managed]

    print(f"\n--- Skill 状态 ---")
    print(f"已管理: {len(custom)}")
    if custom:
        for c in custom:
            link = "✓" if c.has_custom_link else "✗"
            print(f"  {link} {c.name}")

    # === Symlink 健康 + 状态文件一致性 ===
    status_check = _check_state(config)

    if status_check["broken_links"]:
        print(f"\n断链/缺失 symlink: {len(status_check['broken_links'])}")
        for item in status_check["broken_links"]:
            print(f"  ✗ {item}")
    if status_check["orphaned"]:
        print(f"\n状态不一致: {len(status_check['orphaned'])} 个 skill 在状态文件中但仓库中不存在")
        for name in status_check["orphaned"]:
            print(f"  ! {name}")
    if status_check["unregistered"]:
        print(f"\n未登记: {len(status_check['unregistered'])} 个 skill 在仓库中但未纳入管理")
        for name in status_check["unregistered"]:
            print(f"  ? {name}")


def cmd_commit(args):
    """git add + commit。执行前展示变更摘要和 git 命令让用户确认。"""
    config = _load_config_or_default(args)
    repo = config.repo
    if not git_is_repo(repo):
        print(f"[ERROR] {repo} 不是 git 仓库")
        return

    status = git_status(repo)
    if status.is_clean:
        print("[OK] 无变更，跳过 commit")
        return

    message = args.message or _build_default_git_message(config)
    _show_git_preview(config, message, include_push=False)

    if _get_dry_run(args):
        print("\n[DRY-RUN] 以上命令不会执行")
        return

    if not _confirm_git_action(args):
        return

    _commit_repo(config, message)


def cmd_push(args):
    """git add + commit + push。执行前展示完整 git 命令让用户确认。"""
    config = _load_config_or_default(args)
    repo = config.repo

    if not git_is_repo(repo):
        print(f"[ERROR] {repo} 不是 git 仓库")
        return

    from .git_ops import git_get_remote_url, git_get_tracking_branch, git_has_remote

    status = git_status(repo)
    tracking = git_get_tracking_branch(repo)
    if status.is_clean and tracking and status.ahead == 0:
        print("[OK] 无待提交改动，当前分支未领先远程，跳过 commit/push")
        return

    has_remote = git_has_remote(repo)
    message = args.message or _build_default_git_message(config)
    _show_git_preview(config, message, include_push=has_remote)

    if _get_dry_run(args):
        print("\n[DRY-RUN] 以上命令不会执行")
        return

    if not _confirm_git_action(args):
        return

    if not _commit_repo(config, message):
        return

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

    from .git_ops import git_get_tracking_branch

    status = git_status(repo)
    tracking = git_get_tracking_branch(repo)
    no_remote_updates = tracking and status.is_clean and status.behind == 0

    # Pull 前：检查 skill 管理状态
    state = _check_state(config)
    has_issues = any([state["orphaned"], state["broken_links"]])
    if has_issues:
        print("⚠ 当前 skill 管理状态存在异常:")
        if state["orphaned"]:
            print(f"  - 孤儿 skill: {len(state['orphaned'])} 个")
        if state["broken_links"]:
            print(f"  - 断链/缺失 symlink: {len(state['broken_links'])} 个")
        if not args.yes:
            try:
                confirm = input("\n建议先执行 sync-skills doctor 修复异常。是否继续 pull? [y/N] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\n已取消")
                return
            if confirm != "y":
                return

    # 展示将要执行的 git 命令
    branch = status.branch or "(未命名)"
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

    if not args.yes and not no_remote_updates:
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
    _do_doctor(config, auto_confirm=args.yes)


def cmd_doctor(args):
    """验证/修复软链接和状态一致性。"""
    config = _load_config_or_default(args)

    managed = get_managed_skills(config.state_file)
    if not managed:
        current_status = _check_state(config)
        if not current_status["unregistered"] and not current_status["orphaned"]:
            print("没有已管理的 skill")
            return

    if _get_dry_run(args):
        _preview_doctor(config)
        return

    if not args.yes and _doctor_has_work(config):
        try:
            confirm = input("\n确认执行? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消")
            return
        if confirm != "y":
            print("已取消")
            return

    _do_doctor(config, auto_confirm=args.yes)


def _doctor_has_work(config: Config) -> bool:
    """判断 doctor 是否有可执行的修复项。"""
    status = _check_state(config)
    if status["orphaned"] or status["unregistered"]:
        return True

    managed = get_managed_skills(config.state_file)
    if not managed:
        return False

    from .symlink import verify_links

    for name in sorted(managed):
        repo_target = config.repo_skills_dir / name
        if not repo_target.is_dir():
            continue
        for agent_dir in config.effective_agent_dirs:
            link = agent_dir / name
            if link.exists() and not link.is_symlink():
                return True
        state = verify_links(name, config.repo_skills_dir, config.effective_agent_dirs)
        if (
            getattr(state, "agent_links_missing", [])
            or getattr(state, "agent_links_broken", [])
            or getattr(state, "agent_links_wrong_target", [])
        ):
            return True
    return False


def _preview_doctor(config: Config):
    """只读预演 doctor 将执行的动作，不修改任何状态。"""
    from .symlink import verify_links

    status = _check_state(config)
    managed = get_managed_skills(config.state_file)

    if not managed and not status["unregistered"] and not status["orphaned"]:
        print("没有已管理的 skill")
        return

    print("[DRY-RUN] 以下为 doctor 拟执行的修复，不会修改任何文件")

    if status["unregistered"]:
        print(f"状态文件对齐: 将补充登记 {len(status['unregistered'])} 个 skill")
        for name in status["unregistered"]:
            print(f"  + {name}")

    if status["orphaned"]:
        print(f"\n状态文件对齐: {len(status['orphaned'])} 个 skill 在状态文件中但仓库中不存在")
        for name in status["orphaned"]:
            print(f"  ! {name}（可能需要 sync-skills pull）")

    preview_managed = managed | set(status["unregistered"])
    if not preview_managed:
        print("\n[DRY-RUN] 未修改状态文件、symlink 或目录结构")
        return

    print(f"\n检查 symlink ({len(preview_managed)} 个 skill × {len(config.effective_agent_dirs)} 个 Agent 目录):")

    planned_repairs = []
    conflicts = []
    verified = 0

    for name in sorted(preview_managed):
        repo_target = config.repo_skills_dir / name
        if not repo_target.is_dir():
            continue

        state = verify_links(name, config.repo_skills_dir, config.effective_agent_dirs)
        verified += len(state.agent_links_ok)

        for agent_name in state.agent_links_missing:
            planned_repairs.append(f"{name}: {agent_name} 缺失 symlink → 将创建")
        for agent_name in state.agent_links_broken:
            planned_repairs.append(f"{name}: {agent_name} symlink 异常 → 将修复")
        for agent_name in getattr(state, "agent_links_wrong_target", []):
            planned_repairs.append(f"{name}: {agent_name} symlink 指向错误目标 → 将修复")

        for agent_dir in config.effective_agent_dirs:
            link = agent_dir / name
            if link.exists() and not link.is_symlink():
                agent_name = agent_dir.parent.name.lstrip(".")
                conflicts.append(f"{name}: {agent_name} 存在真实目录（非 symlink），需要确认是否替换")

    if verified:
        print(f"  ✓ {verified} 个 symlink 当前正常")
    if planned_repairs:
        print(f"  + 预计修复 {len(planned_repairs)} 个问题:")
        for item in planned_repairs:
            print(f"    - {item}")
    if conflicts:
        print(f"  ! {len(conflicts)} 个冲突需要手动确认:")
        for item in conflicts:
            print(f"    - {item}")
    if not planned_repairs and not conflicts and not status["unregistered"] and not status["orphaned"]:
        print("  ✓ 全部正常")

    print("\n[DRY-RUN] 未修改状态文件、symlink 或目录结构")


def _do_doctor(config: Config, auto_confirm: bool = False):
    """执行状态检查和修复：状态对齐 + Symlink 检查 + 覆盖风险检测。"""
    # 1. 状态文件 ↔ Repo 对齐
    managed = get_managed_skills(config.state_file)
    added, orphaned = align_state_with_repo(config.state_file, config.repo_skills_dir)

    if not managed and not added:
        print("没有已管理的 skill")
        return

    if added:
        print(f"状态文件对齐: 补充登记 {len(added)} 个 skill")
        for name in added:
            print(f"  + {name}")

    if orphaned:
        print(f"\n状态文件对齐: {len(orphaned)} 个 skill 在状态文件中但仓库中不存在")
        for name in orphaned:
            print(f"  ! {name}（可能需要 sync-skills pull）")

    # 更新 managed 集合
    managed = get_managed_skills(config.state_file)

    # 2. Agent 目录 Symlink 检查
    if not managed:
        return

    print(f"\n检查 symlink ({len(managed)} 个 skill × {len(config.effective_agent_dirs)} 个 Agent 目录):")
    result = check_and_repair_links(
        config.repo_skills_dir, config.effective_agent_dirs, managed, auto_confirm
    )

    if result["verified"]:
        print(f"  ✓ {result['verified']} 个 skill 全部正常")
    if result["repaired"]:
        print(f"  + 已修复 {len(result['repaired'])} 个问题:")
        for item in result["repaired"]:
            print(f"    - {item}")
    if result["conflicts"]:
        print(f"  ! {len(result['conflicts'])} 个冲突需要手动处理:")
        for item in result["conflicts"]:
            print(f"    - {item}")


def _check_state(config: Config) -> dict:
    """非交互式检查 skill 管理状态（仅检测，不修复）。"""
    from .symlink import verify_links

    managed = get_managed_skills(config.state_file)

    # 状态文件与 repo 对齐检查（仅检测，不自动注册）
    repo_skills = set()
    if config.repo_skills_dir.is_dir():
        for d in config.repo_skills_dir.iterdir():
            if d.name.startswith(".") or not d.is_dir():
                continue
            if (d / "SKILL.md").is_file():
                repo_skills.add(d.name)

    orphaned = sorted(managed - repo_skills)
    unregistered = sorted(repo_skills - managed)

    # Symlink 检查（仅检测）
    broken_links = []
    for name in sorted(managed):
        repo_target = config.repo_skills_dir / name
        if not repo_target.is_dir():
            continue
        state = verify_links(name, config.repo_skills_dir, config.effective_agent_dirs)
        for agent_name in (
            state.agent_links_broken
            + state.agent_links_missing
            + getattr(state, "agent_links_wrong_target", [])
        ):
            broken_links.append(f"{name}: {agent_name}")

    return {
        "orphaned": orphaned,
        "unregistered": unregistered,
        "broken_links": broken_links,
    }


def _verify_after_change(config: Config):
    """变更后验证 skill 管理状态（检测 + 自动修复）。"""
    from .symlink import verify_links

    managed = get_managed_skills(config.state_file)

    # 状态文件与 repo 对齐检查
    repo_skills = set()
    if config.repo_skills_dir.is_dir():
        for d in config.repo_skills_dir.iterdir():
            if d.name.startswith(".") or not d.is_dir():
                continue
            if (d / "SKILL.md").is_file():
                repo_skills.add(d.name)

    orphaned = sorted(managed - repo_skills)

    # Symlink 检查 + 自动修复
    repaired = []
    for name in sorted(managed):
        repo_target = config.repo_skills_dir / name
        if not repo_target.is_dir():
            continue
        state = verify_links(name, config.repo_skills_dir, config.effective_agent_dirs)
        if state.agent_links_missing or state.agent_links_broken:
            result = check_and_repair_links(
                config.repo_skills_dir, config.effective_agent_dirs, {name}, auto_confirm=True
            )
            repaired.extend(result["repaired"])

    issues = []
    if orphaned:
        issues.append(f"孤儿 skill（状态文件中有但 repo 中无）: {len(orphaned)} 个")
    if repaired:
        issues.append(f"已自动修复 symlink: {len(repaired)} 个")
    if issues:
        print(f"\n⚠ 检测到异常:")
        for issue in issues:
            print(f"  - {issue}")
        print("  建议执行 sync-skills doctor 检查并修复")


def _show_git_preview(config: Config, message: str, include_push: bool):
    """展示 commit/push 前的 git 风格预览。"""
    from .git_ops import git_get_remote_url, git_get_tracking_branch, git_has_remote

    repo = config.repo
    status = git_status(repo)
    branch = status.branch or "(未命名)"
    skill_changes = git_collect_skill_changes(repo, config.repo_skills_dir)
    recent_commits = git_recent_commits(repo)

    print(f"分支: {branch}")
    if status.ahead > 0:
        print(f"领先远程: {status.ahead} 个 commit")
    if status.behind > 0:
        print(f"落后远程: {status.behind} 个 commit")

    if skill_changes:
        print("\n待提交 Skill:")
        for change in skill_changes:
            print(f"  {change.status} {change.skill_name:<24} {change.modified_at}")
    else:
        suffix = "，可能只有非 skill 文件变更" if not status.is_clean else ""
        print(f"\n待提交 Skill: 无{suffix}")

    if recent_commits:
        print("\n最近 commit:")
        for commit in recent_commits:
            print(f"  {commit.short_hash} {commit.committed_at} {commit.subject}")

    print("\n即将执行:")
    print(f"  cd {_unexpand_home(repo)}")
    print("  git add -A")
    print(f"  git commit -m \"{message}\"")

    if include_push:
        tracking = git_get_tracking_branch(repo)
        push_target = tracking.replace("origin/", "") if tracking else branch
        print(f"  git push -u origin {push_target}")
        if tracking:
            print(f"\n追踪: {tracking}")
        if status.behind > 0:
            print("建议: 当前分支落后远程，优先执行 sync-skills pull")
        print(f"远程: {git_get_remote_url(repo)}")
    elif git_has_remote(repo):
        print("\n提示: 已检测到远程仓库，提交后可继续执行 sync-skills push")


def _build_default_git_message(config: Config) -> str:
    """根据当前变更生成默认 commit message。"""
    skill_changes = git_collect_skill_changes(config.repo, config.repo_skills_dir)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    if len(skill_changes) == 1:
        skill_part = skill_changes[0].skill_name
    elif len(skill_changes) > 1:
        skill_part = f"{len(skill_changes)} skills"
    else:
        skill_part = "workspace"

    return f"update: {skill_part} ({timestamp})"


def _confirm_git_action(args) -> bool:
    """统一处理 commit/push 前确认。"""
    if args.yes:
        return True

    try:
        confirm = input("\n确认执行? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n已取消")
        return False

    if confirm != "y":
        print("已取消")
        return False
    return True


def _commit_repo(config: Config, message: str) -> bool:
    """执行 commit，并统一输出结果。"""
    repo = config.repo
    status = git_status(repo)
    if status.is_clean:
        print("[OK] 无变更，跳过 commit")
        return True

    if not git_add_commit(repo, message, config.repo_skills_dir):
        print("[ERROR] 提交失败")
        return False

    print("[OK] 已提交")
    return True



# ============================================================
# 参数解析
# ============================================================

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sync-skills",
        description="sync-skills — 自定义 Skill 生命周期管理器 (v1.1)",
        epilog=(
            "examples:\n"
            "  sync-skills init                 initialize ~/Skills/ repo\n"
            "  sync-skills link my-skill        link skill into management (auto-scan)\n"
            "  sync-skills unlink my-skill     remove from management\n"
            "  sync-skills unlink --all -y     unlink all managed skills\n"
            "  sync-skills new my-skill        create new custom skill\n"
            "  sync-skills remove a b          remove multiple skills\n"
            "  sync-skills doctor              verify/repair symlinks\n"
            "  sync-skills list                list managed skills\n"
            "  sync-skills status              show git + management status\n"
            "  sync-skills commit -m 'update'  commit only\n"
            "  sync-skills push -m 'update'    commit and push\n"
            "  sync-skills pull                pull and rebuild links\n"
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

    # new
    sub_new = subparsers.add_parser("new", help="create new custom skill")
    sub_new.add_argument("name", help="skill name (kebab-case)")
    sub_new.add_argument("--description", "-d", default="", help="skill description")
    sub_new.add_argument("--tags", "-t", default="", help="comma-separated tags")
    sub_new.add_argument("--config", type=Path, default=None)
    sub_new.add_argument("--dry-run", action="store_true", dest="dry_run")
    sub_new.add_argument("-y", "--yes", action="store_true")

    # link
    sub_link = subparsers.add_parser("link", help="link a skill into management (auto-scan by name)")
    sub_link.add_argument("name", nargs="?", default=None, help="skill name to link (auto-scan all agent dirs and repo)")
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

    # commit
    sub_commit = subparsers.add_parser("commit", help="git add and commit")
    sub_commit.add_argument("--message", "-m", default="", help="commit message")
    sub_commit.add_argument("--config", type=Path, default=None)
    sub_commit.add_argument("--dry-run", action="store_true", dest="dry_run")
    sub_commit.add_argument("-y", "--yes", action="store_true")

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

    # doctor
    sub_doctor = subparsers.add_parser("doctor", help="verify/repair symlinks and state")
    sub_doctor.add_argument("--config", type=Path, default=None)
    sub_doctor.add_argument("--dry-run", action="store_true", dest="dry_run")
    sub_doctor.add_argument("-y", "--yes", action="store_true")

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
        # 旧版子命令：list/search/info 走旧版以保持兼容
        if not has_legacy_args and len(argv) > 0:
            first = argv[0] if argv else ""
            if first in ("list", "search", "info"):
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
        "new": cmd_new,
        "remove": cmd_remove,
        "list": cmd_list,
        "status": cmd_status,
        "commit": cmd_commit,
        "push": cmd_push,
        "pull": cmd_pull,
        "doctor": cmd_doctor,
    }

    handler = commands.get(args.command)
    if handler:
        handler(args)
    else:
        print(f"未知命令: {args.command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
