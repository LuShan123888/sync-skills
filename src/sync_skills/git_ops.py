"""Git 操作封装

提供对 ~/Skills/ 仓库的常用 git 操作。
"""

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


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


# ============================================================
# Git 命令
# ============================================================

def _run_git(repo_path: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    """执行 git 命令。"""
    result = subprocess.run(
        ["git", "-C", str(repo_path)] + list(args),
        capture_output=True,
        text=True,
        timeout=30,
    )
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
    result = subprocess.run(
        ["git", "clone", url, str(target_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
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


def git_add_commit(repo_path: Path, message: str) -> bool:
    """git add -A + commit。"""
    # 先检查是否有变更
    status = git_status(repo_path)
    if status.is_clean:
        return True  # 无变更，跳过

    add_result = _run_git(repo_path, "add", "-A")
    if add_result.returncode != 0:
        return False

    commit_result = _run_git(repo_path, "commit", "-m", message)
    return commit_result.returncode == 0


def git_push(repo_path: Path) -> tuple[bool, str]:
    """git push，首次推送自动设置 upstream。返回 (success, error_reason)。

    输出直接到终端（支持 SSH 交互），仅捕获 stderr 用于判断错误类型。
    error_reason: "" 成功, "behind" 落后远程, "auth" 认证失败, 其他为原始错误
    """
    # 获取当前分支名
    branch_result = _run_git(repo_path, "rev-parse", "--abbrev-ref", "HEAD", check=False)
    if branch_result.returncode != 0:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "push"],
            stderr=subprocess.PIPE, text=True, timeout=120,
        )
        return result.returncode == 0, _classify_push_error(result.stderr)

    branch = branch_result.stdout.strip()
    result = subprocess.run(
        ["git", "-C", str(repo_path), "push", "-u", "origin", branch],
        stderr=subprocess.PIPE, text=True, timeout=120,
    )
    return result.returncode == 0, _classify_push_error(result.stderr)


def _classify_push_error(stderr: str) -> str:
    """根据 git push 的 stderr 分类错误原因。"""
    if not stderr:
        return ""
    lower = stderr.lower()
    if "non-fast-forward" in lower or "behind" in lower:
        return "behind"
    if "permission denied" in lower or "authentication" in lower:
        return "auth"
    if "could not read" in lower or "does not appear to be a git" in lower:
        return "bad_url"
    return "unknown"


def git_pull(repo_path: Path) -> tuple[bool, str]:
    """git pull --rebase。无 tracking 时自动指定 origin <branch>。失败时自动 abort rebase。"""
    # 先尝试普通 pull
    result = subprocess.run(
        ["git", "-C", str(repo_path), "pull", "--rebase"],
        stderr=subprocess.PIPE, text=True, timeout=120,
    )
    if result.returncode == 0:
        return True, "pull 成功"

    # 任何失败都先检查是否需要 abort rebase
    if "no tracking information" in result.stderr.lower():
        branch_result = _run_git(repo_path, "rev-parse", "--abbrev-ref", "HEAD", check=False)
        if branch_result.returncode == 0:
            branch = branch_result.stdout.strip()
            result = subprocess.run(
                ["git", "-C", str(repo_path), "pull", "--rebase", "origin", branch],
                stderr=subprocess.PIPE, text=True, timeout=120,
            )
            if result.returncode == 0:
                return True, "pull 成功"

    # 所有失败路径：确保 rebase 被 abort，恢复干净状态
    subprocess.run(["git", "-C", str(repo_path), "rebase", "--abort"],
                   capture_output=True, timeout=30)
    return False, result.stderr.strip()


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
