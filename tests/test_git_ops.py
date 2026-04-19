from pathlib import Path
from unittest.mock import Mock

from sync_skills.git_ops import (
    GitCommitSummary,
    GitSkillChange,
    GitStatus,
    _classify_pull_error,
    _classify_push_error,
    git_collect_skill_changes,
    git_pull,
    git_recent_commits,
    git_status,
)


def _cp(stdout: str = "", returncode: int = 0, stderr: str = ""):
    result = Mock()
    result.stdout = stdout
    result.returncode = returncode
    result.stderr = stderr
    return result


class TestGitOps:
    def test_git_status_parses_staged_modified_untracked_and_ahead_behind(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()

        monkeypatch.setattr(
            "sync_skills.git_ops.git_is_repo",
            lambda _: True,
        )

        responses = iter(
            [
                _cp(stdout="main\n"),
                _cp(stdout="M  skills/demo/SKILL.md\n M skills/demo/README.md\n?? scratch.txt\n"),
                _cp(stdout="2\t1\n"),
            ]
        )
        monkeypatch.setattr("sync_skills.git_ops._run_git", lambda *args, **kwargs: next(responses))

        status = git_status(repo)

        assert status == GitStatus(
            is_repo=True,
            branch="main",
            is_clean=False,
            modified=["skills/demo/README.md"],
            staged=["skills/demo/SKILL.md"],
            untracked=["scratch.txt"],
            ahead=2,
            behind=1,
        )

    def test_git_collect_skill_changes_groups_files_by_skill(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo_skills_dir = repo / "skills"
        skill_dir = repo_skills_dir / "demo"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# demo\n")
        (skill_dir / "extra.txt").write_text("x\n")

        monkeypatch.setattr("sync_skills.git_ops.git_is_repo", lambda _: True)
        monkeypatch.setattr(
            "sync_skills.git_ops._run_git",
            lambda *args, **kwargs: _cp(stdout="M  skills/demo/SKILL.md\n?? skills/demo/extra.txt\n M docs/readme.md\n"),
        )
        monkeypatch.setattr("sync_skills.git_ops._format_skill_modified_at", lambda _: "2026-04-19 12:00")

        changes = git_collect_skill_changes(repo, repo_skills_dir)

        assert changes == [
            GitSkillChange(
                status="A",
                skill_name="demo",
                modified_at="2026-04-19 12:00",
                paths=["skills/demo/SKILL.md", "skills/demo/extra.txt"],
            )
        ]

    def test_git_recent_commits_parses_pretty_log(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()

        monkeypatch.setattr("sync_skills.git_ops.git_is_repo", lambda _: True)
        monkeypatch.setattr(
            "sync_skills.git_ops._run_git",
            lambda *args, **kwargs: _cp(stdout="abc123\t2026-04-19 10:00\tfeat: first\ndef456\t2026-04-18 09:00\tfix: second\n"),
        )

        commits = git_recent_commits(repo, limit=2)

        assert commits == [
            GitCommitSummary("abc123", "2026-04-19 10:00", "feat: first"),
            GitCommitSummary("def456", "2026-04-18 09:00", "fix: second"),
        ]

    def test_git_pull_retries_without_tracking_and_aborts_on_failure(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[-2:] == ["pull", "--rebase"]:
                return _cp(returncode=1, stderr="There is no tracking information for the current branch.")
            if cmd[-4:] == ["pull", "--rebase", "origin", "main"]:
                return _cp(returncode=1, stderr="merge conflict")
            if cmd[-2:] == ["rebase", "--abort"]:
                return _cp(returncode=0)
            raise AssertionError(cmd)

        monkeypatch.setattr("sync_skills.git_ops.subprocess.run", fake_run)
        monkeypatch.setattr("sync_skills.git_ops._run_git", lambda *args, **kwargs: _cp(stdout="main\n"))

        success, msg = git_pull(repo)

        assert success is False
        assert msg == "conflict"
        assert any(cmd[-2:] == ["rebase", "--abort"] for cmd in calls)

    def test_git_pull_returns_detached_when_no_tracking_branch_on_head(self, tmp_path, monkeypatch):
        repo = tmp_path / "repo"
        repo.mkdir()

        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[-2:] == ["pull", "--rebase"]:
                return _cp(returncode=1, stderr="There is no tracking information for the current branch.")
            if cmd[-2:] == ["rebase", "--abort"]:
                return _cp(returncode=0)
            raise AssertionError(cmd)

        monkeypatch.setattr("sync_skills.git_ops.subprocess.run", fake_run)
        monkeypatch.setattr("sync_skills.git_ops._run_git", lambda *args, **kwargs: _cp(stdout="HEAD\n"))

        success, msg = git_pull(repo)

        assert success is False
        assert msg == "detached"
        assert any(cmd[-2:] == ["rebase", "--abort"] for cmd in calls)

    def test_classify_push_error_covers_known_categories(self):
        assert _classify_push_error("non-fast-forward update rejected") == "behind"
        assert _classify_push_error("Permission denied (publickey)") == "auth"
        assert _classify_push_error("fatal: No configured push destination.") == "no_remote"
        assert _classify_push_error("does not appear to be a git repository") == "bad_url"
        assert _classify_push_error("ssh: Could not resolve host github.com") == "network"
        assert _classify_push_error("some random failure") == "unknown"
        assert _classify_push_error("") == ""

    def test_classify_pull_error_covers_known_categories(self):
        assert _classify_pull_error("Please commit your changes or stash them before you merge.") == "local_changes"
        assert _classify_pull_error("Resolve all conflicts manually, mark them as resolved with git add") == "conflict"
        assert _classify_pull_error("Authentication failed for 'origin'") == "auth"
        assert _classify_pull_error("fatal: No such remote: 'origin'") == "no_remote"
        assert _classify_pull_error("fatal: couldn't find remote ref main") == "missing_remote_branch"
        assert _classify_pull_error("fatal: repository 'x' not found") == "bad_url"
        assert _classify_pull_error("ssh: Could not resolve host github.com") == "network"
        assert _classify_pull_error("some random failure") == "unknown"
