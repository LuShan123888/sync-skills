"""Git 操作封装

提供对 ~/Skills/ 仓库的常用 git 操作。
"""

import subprocess
import sys
from shutil import which
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .skill_version import ensure_skill_version_bumped


# ============================================================
# 数据结构
# ============================================================

@dataclass
class GitStatus:
    """git status 结果"""
    is_repo: bool = False
    branch: str = ""
    is_clean: bool = True
    modified: list[str] = field(default_factory=list)
    staged: list[str] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)
    ahead: int = 0
    behind: int = 0


@dataclass
class GitSkillChange:
    """当前工作区中的 skill 变更摘要。"""
    status: str
    skill_name: str
    modified_at: str
    paths: list[str] = field(default_factory=list)


@dataclass
class GitCommitSummary:
    """最近的 commit 摘要。"""
    short_hash: str
    committed_at: str
    subject: str


# ============================================================
# Git 命令
# ============================================================

def git_is_available() -> bool:
    """判断 git 可执行文件是否可用。"""
    return which("git") is not None


def _git_not_found_result(command: list[str]) -> subprocess.CompletedProcess:
    """构造统一的 git 缺失结果，避免上层直接抛异常。"""
    return subprocess.CompletedProcess(command, 127, "", "git executable not found")


def _run_process(command: list[str], timeout: int) -> subprocess.CompletedProcess:
    """执行原始 git 命令，并在 git 缺失时返回统一结果。"""
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return _git_not_found_result(command)

def _run_git(repo_path: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """执行 git 命令。"""
    command = ["git", "-C", str(repo_path)] + list(args)
    result = _run_process(command, timeout=30)
    if check and result.returncode != 0:
        print(f"[ERROR] git {' '.join(args)} failed: {result.stderr.strip()}", file=sys.stderr)
    return result


def git_is_repo(repo_path: Path) -> bool:
    """判断是否是 git 仓库。"""
    return _run_git(repo_path, "rev-parse", "--is-inside-work-tree", check=False).returncode == 0


def git_init(repo_path: Path) -> bool:
    """初始化 git 仓库。"""
    repo_path.mkdir(parents=True, exist_ok=True)
    result = _run_git(repo_path, "init")
    return result.returncode == 0


def git_clone(url: str, target_path: Path) -> bool:
    """克隆仓库。"""
    command = ["git", "clone", url, str(target_path)]
    result = _run_process(command, timeout=60)
    if result.returncode != 0:
        print(f"[ERROR] git clone failed: {result.stderr.strip()}", file=sys.stderr)
    return result.returncode == 0


def git_status(repo_path: Path) -> GitStatus:
    """获取 git status。"""
    if not git_is_repo(repo_path):
        return GitStatus(is_repo=False)

    # 分支名
    branch_result = _run_git(repo_path, "rev-parse", "--abbrev-ref", "HEAD", check=False)
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else ""

    # porcelain status
    result = _run_git(repo_path, "status", "--porcelain", check=False)
    modified, staged, untracked = [], [], []
    if result.returncode == 0:
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            status = line[:2]
            filepath = line[3:]
            if status[0] == "?" and status[1] == "?":
                untracked.append(filepath)
            elif status[0] in "MADRC" and status[1] in " MADRC":
                staged.append(filepath)
            elif status[1] in "MADRC":
                modified.append(filepath)

    # ahead/behind
    ahead, behind = 0, 0
    ab_result = _run_git(repo_path, "rev-list", "--left-right", "--count", "HEAD...@{upstream}", check=False)
    if ab_result.returncode == 0:
        parts = ab_result.stdout.strip().split("\t")
        if len(parts) == 2:
            ahead = int(parts[0])
            behind = int(parts[1])

    is_clean = not modified and not staged and not untracked

    return GitStatus(
        is_repo=True,
        branch=branch,
        is_clean=is_clean,
        modified=modified,
        staged=staged,
        untracked=untracked,
        ahead=ahead,
        behind=behind,
    )


def git_collect_skill_changes(repo_path: Path, repo_skills_dir: Path) -> list[GitSkillChange]:
    """收集当前工作区涉及的 skill 变更，并附带最近修改时间。"""
    if not git_is_repo(repo_path):
        return []

    result = _run_git(repo_path, "status", "--porcelain", check=False)
    if result.returncode != 0:
        return []

    skill_paths: dict[str, list[str]] = {}
    skill_statuses: dict[str, set[str]] = {}
    skills_dir_name = repo_skills_dir.relative_to(repo_path).parts[0]

    for line in result.stdout.splitlines():
        if not line:
            continue

        status_code = line[:2]
        filepath = line[3:]
        if " -> " in filepath:
            filepath = filepath.split(" -> ", 1)[1]

        parts = Path(filepath).parts
        if parts and parts[0] == skills_dir_name and len(parts) == 1:
            if repo_skills_dir.is_dir():
                for skill_dir in repo_skills_dir.iterdir():
                    if skill_dir.is_dir() and (skill_dir / "SKILL.md").is_file():
                        skill_name = skill_dir.name
                        skill_paths.setdefault(skill_name, []).append(f"{skills_dir_name}/{skill_name}/SKILL.md")
                        skill_statuses.setdefault(skill_name, set()).update(_extract_status_tokens(status_code))
            continue

        if len(parts) < 2 or parts[0] != skills_dir_name:
            continue

        skill_name = parts[1]
        skill_paths.setdefault(skill_name, []).append(filepath)
        skill_statuses.setdefault(skill_name, set()).update(_extract_status_tokens(status_code))

    changes = []
    for skill_name in sorted(skill_paths):
        skill_path = repo_skills_dir / skill_name
        changes.append(
            GitSkillChange(
                status=_summarize_skill_status(skill_statuses.get(skill_name, set())),
                skill_name=skill_name,
                modified_at=_format_skill_modified_at(skill_path),
                paths=sorted(skill_paths[skill_name]),
            )
        )
    return changes


def git_recent_commits(repo_path: Path, limit: int = 3) -> list[GitCommitSummary]:
    """获取最近几条 commit，便于 push 前预览。"""
    if not git_is_repo(repo_path):
        return []

    result = _run_git(
        repo_path,
        "log",
        f"-{limit}",
        "--date=format:%Y-%m-%d %H:%M",
        "--pretty=format:%h%x09%ad%x09%s",
        check=False,
    )
    if result.returncode != 0:
        return []

    commits = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        commits.append(
            GitCommitSummary(
                short_hash=parts[0],
                committed_at=parts[1],
                subject=parts[2],
            )
        )
    return commits


def git_add_commit(repo_path: Path, message: str, repo_skills_dir: Path | None = None) -> bool:
    """git add -A + commit。"""
    # 先检查是否有变更
    status = git_status(repo_path)
    if status.is_clean:
        return True  # 无变更，跳过

    if repo_skills_dir is not None:
        for change in git_collect_skill_changes(repo_path, repo_skills_dir):
            ensure_skill_version_bumped(repo_path, repo_skills_dir, change.skill_name)

    add_result = _run_git(repo_path, "add", "-A")
    if add_result.returncode != 0:
        return False

    commit_result = _run_git(repo_path, "commit", "-m", message)
    return commit_result.returncode == 0


def git_push(repo_path: Path) -> tuple[bool, str]:
    """git push，首次推送自动设置 upstream。返回 (success, error_reason)。"""
    # 获取当前分支名
    branch_result = _run_git(repo_path, "rev-parse", "--abbrev-ref", "HEAD", check=False)
    if branch_result.returncode != 0:
        result = _run_process(["git", "-C", str(repo_path), "push"], timeout=120)
        return result.returncode == 0, _classify_push_error(result.stderr)

    branch = branch_result.stdout.strip()
    if not branch or branch == "HEAD":
        return False, "detached"
    result = _run_process(["git", "-C", str(repo_path), "push", "-u", "origin", branch], timeout=120)
    return result.returncode == 0, _classify_push_error(result.stderr)


def _classify_push_error(stderr: str) -> str:
    """根据 git push 的 stderr 分类错误原因。"""
    if not stderr:
        return ""
    lower = stderr.lower()
    if "git executable not found" in lower or ("no such file or directory" in lower and "git" in lower):
        return "unavailable"
    if "non-fast-forward" in lower or "behind" in lower:
        return "behind"
    if "permission denied" in lower or "authentication" in lower:
        return "auth"
    if "no configured push destination" in lower or "no such remote" in lower:
        return "no_remote"
    if "could not read" in lower or "does not appear to be a git" in lower:
        return "bad_url"
    if (
        "could not resolve host" in lower
        or "network is unreachable" in lower
        or "connection timed out" in lower
        or "operation timed out" in lower
        or "connection reset" in lower
    ):
        return "network"
    return "unknown"


def git_pull(repo_path: Path) -> tuple[bool, str]:
    """git pull --rebase。无 tracking 时自动指定 origin <branch>。失败时自动 abort rebase。"""
    # 先尝试普通 pull
    result = _run_process(["git", "-C", str(repo_path), "pull", "--rebase"], timeout=120)
    if result.returncode == 0:
        return True, "pull 成功"

    # 任何失败都先检查是否需要 abort rebase
    if "no tracking information" in result.stderr.lower():
        branch_result = _run_git(repo_path, "rev-parse", "--abbrev-ref", "HEAD", check=False)
        if branch_result.returncode == 0:
            branch = branch_result.stdout.strip()
            if branch and branch != "HEAD":
                result = _run_process(["git", "-C", str(repo_path), "pull", "--rebase", "origin", branch], timeout=120)
                if result.returncode == 0:
                    return True, "pull 成功"
            else:
                _run_process(["git", "-C", str(repo_path), "rebase", "--abort"], timeout=30)
                return False, "detached"

    # 所有失败路径：确保 rebase 被 abort，恢复干净状态
    _run_process(["git", "-C", str(repo_path), "rebase", "--abort"], timeout=30)
    return False, _classify_pull_error(result.stderr)


def _classify_pull_error(stderr: str) -> str:
    """根据 git pull 的 stderr 分类错误原因。"""
    if not stderr:
        return "unknown"
    lower = stderr.lower()
    if "git executable not found" in lower or ("no such file or directory" in lower and "git" in lower):
        return "unavailable"
    if (
        "please commit your changes or stash them" in lower
        or "your local changes to the following files would be overwritten" in lower
    ):
        return "local_changes"
    if (
        "conflict" in lower
        or "could not apply" in lower
        or "resolve all conflicts manually" in lower
    ):
        return "conflict"
    if "permission denied" in lower or "authentication failed" in lower:
        return "auth"
    if "no such remote" in lower:
        return "no_remote"
    if "couldn't find remote ref" in lower or "remote ref does not exist" in lower:
        return "missing_remote_branch"
    if (
        "does not appear to be a git repository" in lower
        or "repository not found" in lower
        or ("repository '" in lower and "' not found" in lower)
    ):
        return "bad_url"
    if (
        "could not resolve host" in lower
        or "network is unreachable" in lower
        or "connection timed out" in lower
        or "operation timed out" in lower
        or "connection reset" in lower
    ):
        return "network"
    return "unknown"


def git_has_remote(repo_path: Path) -> bool:
    """检查是否有远程仓库。"""
    result = _run_git(repo_path, "remote", "get-url", "origin", check=False)
    return result.returncode == 0


def git_add_remote(repo_path: Path, url: str) -> bool:
    """添加或更新远程仓库。"""
    if git_has_remote(repo_path):
        result = _run_git(repo_path, "remote", "set-url", "origin", url)
    else:
        result = _run_git(repo_path, "remote", "add", "origin", url)
    return result.returncode == 0


def git_get_remote_url(repo_path: Path) -> str:
    """获取当前远程仓库 URL。"""
    result = _run_git(repo_path, "remote", "get-url", "origin", check=False)
    if result.returncode == 0:
        return result.stdout.strip()
    return ""


def git_get_tracking_branch(repo_path: Path) -> str:
    """获取当前分支追踪的远程分支，如 'origin/main'。未设置追踪时返回空字符串。"""
    result = _run_git(repo_path, "rev-parse", "--abbrev-ref", "@{upstream}", check=False)
    if result.returncode == 0:
        return result.stdout.strip()
    return ""


def _extract_status_tokens(status_code: str) -> set[str]:
    """从 porcelain 状态中提取有效状态标记。"""
    if status_code == "??":
        return {"?"}
    return {ch for ch in status_code if ch.strip()}


def _summarize_skill_status(statuses: set[str]) -> str:
    """将多个文件状态压缩成单个 skill 状态。"""
    if "?" in statuses:
        return "A"
    if statuses and statuses <= {"A"}:
        return "A"
    if statuses and statuses <= {"D"}:
        return "D"
    if "R" in statuses:
        return "R"
    return "M"


def _format_skill_modified_at(skill_path: Path) -> str:
    """格式化 skill 最近修改时间。删除场景下返回占位符。"""
    if not skill_path.exists():
        return "-"

    latest_mtime = skill_path.stat().st_mtime
    for path in skill_path.rglob("*"):
        try:
            path_mtime = path.stat().st_mtime
        except OSError:
            continue
        if path_mtime > latest_mtime:
            latest_mtime = path_mtime
    return datetime.fromtimestamp(latest_mtime).strftime("%Y-%m-%d %H:%M")
