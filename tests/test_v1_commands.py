import argparse
from pathlib import Path
from types import SimpleNamespace

from sync_skills.config import save_config
from sync_skills.git_ops import GitSkillChange, GitStatus, git_init
from sync_skills.lifecycle import add_skill
from sync_skills.state import get_managed_skills
from tests.test_sync_skills import _create_v1_env


def write_skill(skill_dir: Path, version: str | None, body: str = "# demo\n"):
    if version is None:
        content = f"---\nname: {skill_dir.name}\ndescription: \"demo\"\n---\n\n{body}"
    else:
        content = f"---\nname: {skill_dir.name}\nversion: {version}\ndescription: \"demo\"\n---\n\n{body}"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return content


def read_version(skill_dir: Path) -> str | None:
    content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    for line in content.splitlines():
        if line.startswith("version: "):
            return line.split(": ", 1)[1].strip()
    return None


def init_git_identity(repo: Path):
    import subprocess

    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@test.com"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "test"], capture_output=True, check=True)


def commit_all(repo: Path, message: str):
    import subprocess

    subprocess.run(["git", "-C", str(repo), "add", "-A"], capture_output=True, check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", message], capture_output=True, check=True)


def current_head_message(repo: Path) -> str:
    import subprocess

    result = subprocess.run(["git", "-C", str(repo), "log", "--oneline", "-1"], capture_output=True, text=True, check=True)
    return result.stdout


def make_args(config_path: Path, *, yes=False, dry_run=False, message=""):
    return argparse.Namespace(config=config_path, dry_run=dry_run, yes=yes, message=message)


class TestV1DoctorNoPendingWorkCommand:
    def test_doctor_dry_run_does_not_register_or_repair_links(self, tmp_path, capsys):
        from sync_skills.cli import cmd_doctor
        from sync_skills.state import add_managed

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        skill_dir = repo_skills / "unregistered"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# unregistered\n")
        add_managed("ghost-skill", config.state_file)

        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        cmd_doctor(argparse.Namespace(config=config_path, dry_run=True, yes=False))
        captured = capsys.readouterr()

        assert "补充登记" in captured.out
        assert "将清理" in captured.out
        assert "[DRY-RUN]" in captured.out
        assert "unregistered" not in get_managed_skills(config.state_file)
        assert "ghost-skill" in get_managed_skills(config.state_file)
        for agent_dir in agent_dirs:
            assert not (agent_dir / "unregistered").exists()


class TestV1StatusCommand:
    def test_status_shows_lifecycle_states(self, tmp_path, capsys):
        from sync_skills.cli import cmd_status
        from sync_skills.state import add_managed
        import os

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        add_skill("healthy-skill", config)
        add_skill("broken-skill", config)
        add_skill("isolated-skill", config)
        add_skill("conflict-skill", config)

        orphan = "orphan-skill"
        add_managed(orphan, config.state_file)

        unregistered_dir = repo_skills / "repo-only"
        unregistered_dir.mkdir()
        (unregistered_dir / "SKILL.md").write_text("# repo only\n")

        (agent_dirs[0] / "broken-skill").unlink()
        os.symlink(repo_skills / "missing-target", agent_dirs[0] / "broken-skill")

        for agent_dir in agent_dirs:
            (agent_dir / "isolated-skill").unlink()

        (agent_dirs[1] / "conflict-skill").unlink()
        (agent_dirs[1] / "conflict-skill").mkdir()
        (agent_dirs[1] / "conflict-skill" / "SKILL.md").write_text("# conflict\n")

        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        cmd_status(argparse.Namespace(config=config_path))
        captured = capsys.readouterr()

        assert "--- 生命周期状态 ---" in captured.out
        assert "managed:" in captured.out
        assert "unknown:" in captured.out
        assert "orphaned:" in captured.out
        assert "broken link:" in captured.out
        assert "real directory conflict:" in captured.out
        assert "managed but not exposed:" in captured.out
        assert "healthy-skill [managed]" in captured.out
        assert "broken-skill [managed, broken link]" in captured.out
        assert orphan in captured.out
        assert "repo-only [unknown]" in captured.out
        assert "isolated-skill [managed, broken link, managed but not exposed]" in captured.out
        assert "conflict-skill [managed, real directory conflict]" in captured.out


class TestV1CommitCommand:
    def test_commit_success_calls_git_add_commit_with_default_message(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_commit

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        called = []
        monkeypatch.setattr("sync_skills.cli.git_collect_skill_changes", lambda repo, repo_skills_dir: [GitSkillChange("M", "demo", "2026-04-19 10:00")])
        monkeypatch.setattr("sync_skills.cli.git_recent_commits", lambda repo: [])
        monkeypatch.setattr("sync_skills.cli.git_status", lambda repo: GitStatus(is_repo=True, branch="main", is_clean=False))
        monkeypatch.setattr("sync_skills.cli.git_add_commit", lambda repo, message, repo_skills_dir=None: called.append((message, repo_skills_dir)) or True)
        monkeypatch.setattr("sync_skills.cli.datetime", SimpleNamespace(now=lambda: SimpleNamespace(strftime=lambda fmt: "2026-04-19 12:34")))

        cmd_commit(make_args(config_path, yes=True))
        captured = capsys.readouterr()

        assert called == [("update: demo (2026-04-19 12:34)", config.repo_skills_dir)]
        assert "[OK] 已提交" in captured.out

    def test_commit_dry_run_does_not_call_git_add_commit(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_commit

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        monkeypatch.setattr("sync_skills.cli.git_collect_skill_changes", lambda repo, repo_skills_dir: [])
        monkeypatch.setattr("sync_skills.cli.git_recent_commits", lambda repo: [])
        monkeypatch.setattr("sync_skills.cli.git_status", lambda repo: GitStatus(is_repo=True, branch="main", is_clean=False))

        called = []
        monkeypatch.setattr("sync_skills.cli.git_add_commit", lambda repo, message, repo_skills_dir=None: called.append(message) or True)

        cmd_commit(make_args(config_path, dry_run=True))
        captured = capsys.readouterr()

        assert called == []
        assert "[DRY-RUN]" in captured.out

    def test_commit_bumps_patch_when_version_unchanged(self, tmp_path, capsys):
        from sync_skills.cli import cmd_commit

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        init_git_identity(repo)

        skill_dir = repo_skills / "demo"
        skill_dir.mkdir(parents=True)
        write_skill(skill_dir, "1.2.3", "# demo\n")
        commit_all(repo, "init")

        write_skill(skill_dir, "1.2.3", "# demo\n\nchanged\n")
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        cmd_commit(make_args(config_path, yes=True, message="update demo"))
        captured = capsys.readouterr()

        assert read_version(skill_dir) == "1.2.4"
        assert "[OK] 已提交" in captured.out
        assert "update demo" in current_head_message(repo)

    def test_commit_keeps_manually_updated_version(self, tmp_path):
        from sync_skills.cli import cmd_commit

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        init_git_identity(repo)

        skill_dir = repo_skills / "demo"
        skill_dir.mkdir(parents=True)
        write_skill(skill_dir, "1.2.3", "# demo\n")
        commit_all(repo, "init")

        write_skill(skill_dir, "1.3.0", "# demo\n\nchanged\n")
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        cmd_commit(make_args(config_path, yes=True, message="update demo"))

        assert read_version(skill_dir) == "1.3.0"

    def test_commit_sets_default_version_when_missing(self, tmp_path):
        from sync_skills.cli import cmd_commit

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        init_git_identity(repo)

        skill_dir = repo_skills / "demo"
        skill_dir.mkdir(parents=True)
        write_skill(skill_dir, None, "# demo\n\nchanged\n")
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        cmd_commit(make_args(config_path, yes=True, message="update demo"))

        assert read_version(skill_dir) == "0.0.1"

    def test_commit_bumps_each_skill_in_multi_skill_commit(self, tmp_path):
        from sync_skills.cli import cmd_commit

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        init_git_identity(repo)

        for name in ["a", "b"]:
            skill_dir = repo_skills / name
            skill_dir.mkdir(parents=True)
            write_skill(skill_dir, "1.0.0", f"# {name}\n")
        commit_all(repo, "init")

        write_skill(repo_skills / "a", "1.0.0", "# a\n\nchanged\n")
        write_skill(repo_skills / "b", "1.0.0", "# b\n\nchanged\n")
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        cmd_commit(make_args(config_path, yes=True, message="update both"))

        assert read_version(repo_skills / "a") == "1.0.1"
        assert read_version(repo_skills / "b") == "1.0.1"

    def test_commit_no_pending_changes_skips_confirmation(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_commit

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        def fail_input(prompt: str = "") -> str:
            raise AssertionError("commit should not request confirmation")

        monkeypatch.setattr("sync_skills.cli.git_status", lambda repo: GitStatus(is_repo=True, branch="main", is_clean=True))
        monkeypatch.setattr("builtins.input", fail_input)

        cmd_commit(make_args(config_path))
        captured = capsys.readouterr()

        assert "无变更，跳过 commit" in captured.out



class TestV1PushCommand:
    def test_push_success_commits_then_pushes_with_yes(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_push

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        monkeypatch.setattr("sync_skills.cli.git_collect_skill_changes", lambda repo, repo_skills_dir: [])
        monkeypatch.setattr("sync_skills.cli.git_recent_commits", lambda repo: [])
        monkeypatch.setattr("sync_skills.cli.git_status", lambda repo: GitStatus(is_repo=True, branch="main", is_clean=False))
        import sync_skills.git_ops as git_ops_module
        monkeypatch.setattr(git_ops_module, "git_has_remote", lambda repo: True)
        monkeypatch.setattr(git_ops_module, "git_get_tracking_branch", lambda repo: "origin/main")
        monkeypatch.setattr(git_ops_module, "git_get_remote_url", lambda repo: "git@example.com:repo.git")

        committed = []
        pushed = []
        monkeypatch.setattr("sync_skills.cli.git_add_commit", lambda repo, message, repo_skills_dir=None: committed.append(message) or True)
        monkeypatch.setattr("sync_skills.cli.git_push", lambda repo: pushed.append(repo) or (True, ""))
        monkeypatch.setattr("sync_skills.cli.datetime", SimpleNamespace(now=lambda: SimpleNamespace(strftime=lambda fmt: "2026-04-19 12:34")))

        cmd_push(make_args(config_path, yes=True))
        captured = capsys.readouterr()

        assert len(committed) == 1
        assert pushed == [repo]
        assert "[OK] 已推送到远程" in captured.out

    def test_push_dry_run_does_not_commit_or_push(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_push

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        monkeypatch.setattr("sync_skills.cli.git_collect_skill_changes", lambda repo, repo_skills_dir: [])
        monkeypatch.setattr("sync_skills.cli.git_recent_commits", lambda repo: [])
        monkeypatch.setattr("sync_skills.cli.git_status", lambda repo: GitStatus(is_repo=True, branch="main", is_clean=False))
        import sync_skills.git_ops as git_ops_module
        monkeypatch.setattr(git_ops_module, "git_has_remote", lambda repo: True)
        monkeypatch.setattr(git_ops_module, "git_get_tracking_branch", lambda repo: "origin/main")
        monkeypatch.setattr(git_ops_module, "git_get_remote_url", lambda repo: "git@example.com:repo.git")

        committed = []
        pushed = []
        monkeypatch.setattr("sync_skills.cli.git_add_commit", lambda repo, message, repo_skills_dir=None: committed.append(message) or True)
        monkeypatch.setattr("sync_skills.cli.git_push", lambda repo: pushed.append(repo) or (True, ""))

        cmd_push(make_args(config_path, dry_run=True))
        captured = capsys.readouterr()

        assert committed == []
        assert pushed == []
        assert "[DRY-RUN]" in captured.out

    def test_push_bumps_patch_before_push(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_push

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        init_git_identity(repo)

        skill_dir = repo_skills / "demo"
        skill_dir.mkdir(parents=True)
        write_skill(skill_dir, "1.2.3", "# demo\n")
        commit_all(repo, "init")
        write_skill(skill_dir, "1.2.3", "# demo\n\nchanged\n")

        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        import sync_skills.git_ops as git_ops_module
        monkeypatch.setattr(git_ops_module, "git_has_remote", lambda repo: True)
        monkeypatch.setattr(git_ops_module, "git_get_tracking_branch", lambda repo: "origin/main")
        monkeypatch.setattr(git_ops_module, "git_get_remote_url", lambda repo: "git@example.com:repo.git")
        monkeypatch.setattr("sync_skills.cli.git_push", lambda repo: (True, ""))

        cmd_push(make_args(config_path, yes=True, message="push demo"))
        captured = capsys.readouterr()

        assert read_version(skill_dir) == "1.2.4"
        assert "[OK] 已推送到远程" in captured.out

    def test_push_skips_confirmation_when_clean_and_no_pending_updates(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_push

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        def fail_input(prompt: str = "") -> str:
            raise AssertionError("push should not request confirmation")

        import sync_skills.git_ops as git_ops_module
        monkeypatch.setattr("sync_skills.cli.git_status", lambda repo: GitStatus(is_repo=True, branch="main", is_clean=True, ahead=0, behind=0))
        monkeypatch.setattr(git_ops_module, "git_get_tracking_branch", lambda repo: "origin/main")

        committed = []
        pushed = []
        monkeypatch.setattr("sync_skills.cli.git_add_commit", lambda repo, message, repo_skills_dir=None: committed.append(message) or True)
        monkeypatch.setattr("sync_skills.cli.git_push", lambda repo: pushed.append(repo) or (True, ""))
        monkeypatch.setattr("builtins.input", fail_input)

        cmd_push(make_args(config_path, yes=False))
        captured = capsys.readouterr()

        assert committed == []
        assert pushed == []
        assert "无待提交改动，当前分支未领先远程，跳过 commit/push" in captured.out

    def test_push_without_remote_keeps_local_commit_and_warns(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_push

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        monkeypatch.setattr("sync_skills.cli.git_collect_skill_changes", lambda repo, repo_skills_dir: [])
        monkeypatch.setattr("sync_skills.cli.git_recent_commits", lambda repo: [])
        monkeypatch.setattr("sync_skills.cli.git_status", lambda repo: GitStatus(is_repo=True, branch="main", is_clean=False))
        import sync_skills.git_ops as git_ops_module
        monkeypatch.setattr(git_ops_module, "git_has_remote", lambda repo: False)
        monkeypatch.setattr(git_ops_module, "git_get_tracking_branch", lambda repo: "")

        committed = []
        pushed = []
        monkeypatch.setattr("sync_skills.cli.git_add_commit", lambda repo, message, repo_skills_dir=None: committed.append(message) or True)
        monkeypatch.setattr("sync_skills.cli.git_push", lambda repo: pushed.append(repo) or (True, ""))

        cmd_push(make_args(config_path, yes=True))
        captured = capsys.readouterr()

        assert len(committed) == 1
        assert pushed == []
        assert "未配置 origin 远程" in captured.out

    def test_push_auth_failure_shows_clear_hint(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_push

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        monkeypatch.setattr("sync_skills.cli.git_collect_skill_changes", lambda repo, repo_skills_dir: [])
        monkeypatch.setattr("sync_skills.cli.git_recent_commits", lambda repo: [])
        monkeypatch.setattr("sync_skills.cli.git_status", lambda repo: GitStatus(is_repo=True, branch="main", is_clean=False))
        import sync_skills.git_ops as git_ops_module
        monkeypatch.setattr(git_ops_module, "git_has_remote", lambda repo: True)
        monkeypatch.setattr(git_ops_module, "git_get_tracking_branch", lambda repo: "origin/main")
        monkeypatch.setattr(git_ops_module, "git_get_remote_url", lambda repo: "git@example.com:repo.git")
        monkeypatch.setattr("sync_skills.cli.git_add_commit", lambda repo, message, repo_skills_dir=None: True)
        monkeypatch.setattr("sync_skills.cli.git_push", lambda repo: (False, "auth"))

        cmd_push(make_args(config_path, yes=True))
        captured = capsys.readouterr()

        assert "远程认证失败" in captured.out


class TestV1DoctorCommand:
    def test_doctor_no_pending_work_skips_confirmation(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_doctor
        from sync_skills.lifecycle import add_skill
        from sync_skills.config import save_config

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        add_skill("healthy-skill", config)

        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        def fail_input(prompt: str = "") -> str:
            raise AssertionError("doctor should not request confirmation")

        monkeypatch.setattr("builtins.input", fail_input)

        cmd_doctor(argparse.Namespace(config=config_path, dry_run=False, yes=False))
        captured = capsys.readouterr()
        combined = captured.out + captured.err

        assert "确认执行" not in combined
        assert "全部正常" in combined

    def test_doctor_dry_run_does_not_repair_missing_symlink(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_doctor
        from sync_skills.lifecycle import add_skill
        from sync_skills.config import save_config

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        add_skill("preview-skill", config)
        missing_link = agent_dirs[0] / "preview-skill"
        missing_link.unlink()

        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        def fail_input(prompt: str = "") -> str:
            raise AssertionError("doctor dry-run should not request confirmation")

        monkeypatch.setattr("builtins.input", fail_input)

        cmd_doctor(argparse.Namespace(config=config_path, dry_run=True, yes=False))
        captured = capsys.readouterr()
        combined = captured.out + captured.err

        assert "[DRY-RUN]" in combined
        assert "将创建" in combined
        assert not missing_link.exists()
        assert not missing_link.is_symlink()


class TestV1PullCommand:
    def test_pull_success_calls_git_pull_then_doctor(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_pull

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        monkeypatch.setattr("sync_skills.cli.git_status", lambda repo: GitStatus(is_repo=True, branch="main", is_clean=True))
        import sync_skills.git_ops as git_ops_module
        monkeypatch.setattr(git_ops_module, "git_get_tracking_branch", lambda repo: "origin/main")
        monkeypatch.setattr("sync_skills.cli.git_pull", lambda repo: (True, "pull 成功"))

        called = []
        monkeypatch.setattr("sync_skills.cli._do_doctor", lambda config, auto_confirm=False: called.append(auto_confirm))

        cmd_pull(argparse.Namespace(config=config_path, dry_run=False, yes=True))
        captured = capsys.readouterr()

        assert called == [True]
        assert "[OK] pull 成功" in captured.out

    def test_pull_dry_run_does_not_call_git_pull_or_doctor(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_pull

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        monkeypatch.setattr("sync_skills.cli.git_status", lambda repo: GitStatus(is_repo=True, branch="main", is_clean=True))
        import sync_skills.git_ops as git_ops_module
        monkeypatch.setattr(git_ops_module, "git_get_tracking_branch", lambda repo: "origin/main")

        pulled = []
        monkeypatch.setattr("sync_skills.cli.git_pull", lambda repo: pulled.append(repo) or (True, "pull 成功"))
        repaired = []
        monkeypatch.setattr("sync_skills.cli._do_doctor", lambda config, auto_confirm=False: repaired.append(auto_confirm))

        cmd_pull(argparse.Namespace(config=config_path, dry_run=True, yes=False))
        captured = capsys.readouterr()

        assert pulled == []
        assert repaired == []
        assert "[DRY-RUN]" in captured.out

    def test_pull_skips_confirmation_when_no_remote_updates(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_pull

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        def fail_input(prompt: str = "") -> str:
            raise AssertionError("pull should not request confirmation")

        import sync_skills.git_ops as git_ops_module
        monkeypatch.setattr("sync_skills.cli.git_status", lambda repo: GitStatus(is_repo=True, branch="main", is_clean=True, ahead=0, behind=0))
        monkeypatch.setattr(git_ops_module, "git_get_tracking_branch", lambda repo: "origin/main")

        pulled = []
        repaired = []
        monkeypatch.setattr("sync_skills.cli.git_pull", lambda repo: pulled.append(repo) or (True, "pull 成功"))
        monkeypatch.setattr("sync_skills.cli._do_doctor", lambda config, auto_confirm=False: repaired.append(auto_confirm) or None)
        monkeypatch.setattr("builtins.input", fail_input)

        cmd_pull(argparse.Namespace(config=config_path, dry_run=False, yes=False))
        captured = capsys.readouterr()

        assert pulled == [repo]
        assert repaired == [False]
        assert "确认执行" not in (captured.out + captured.err)
        assert "[OK] pull 成功" in captured.out

    def test_pull_without_remote_warns_and_returns(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_pull

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        monkeypatch.setattr("sync_skills.cli.git_status", lambda repo: GitStatus(is_repo=True, branch="main", is_clean=True))
        import sync_skills.git_ops as git_ops_module
        monkeypatch.setattr(git_ops_module, "git_get_tracking_branch", lambda repo: "")
        monkeypatch.setattr(git_ops_module, "git_has_remote", lambda repo: False)

        pulled = []
        monkeypatch.setattr("sync_skills.cli.git_pull", lambda repo: pulled.append(repo) or (True, "pull 成功"))

        cmd_pull(argparse.Namespace(config=config_path, dry_run=False, yes=False))
        captured = capsys.readouterr()

        assert pulled == []
        assert "未配置 origin 远程，无法 pull" in captured.out

    def test_pull_detached_head_warns_and_returns(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_pull

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        monkeypatch.setattr("sync_skills.cli.git_status", lambda repo: GitStatus(is_repo=True, branch="HEAD", is_clean=True))
        import sync_skills.git_ops as git_ops_module
        monkeypatch.setattr(git_ops_module, "git_get_tracking_branch", lambda repo: "")
        monkeypatch.setattr(git_ops_module, "git_has_remote", lambda repo: True)

        pulled = []
        repaired = []
        monkeypatch.setattr("sync_skills.cli.git_pull", lambda repo: pulled.append(repo) or (True, "pull 成功"))
        monkeypatch.setattr("sync_skills.cli._do_doctor", lambda config, auto_confirm=False: repaired.append(auto_confirm))

        cmd_pull(argparse.Namespace(config=config_path, dry_run=False, yes=False))
        captured = capsys.readouterr()

        assert pulled == []
        assert repaired == []
        assert "detached HEAD" in captured.out

    def test_pull_local_changes_failure_shows_clear_hint(self, tmp_path, capsys, monkeypatch):
        from sync_skills.cli import cmd_pull

        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)
        git_init(repo)
        config_path = tmp_path / "config.toml"
        save_config(config, config_path)

        monkeypatch.setattr("sync_skills.cli.git_status", lambda repo: GitStatus(is_repo=True, branch="main", is_clean=True))
        import sync_skills.git_ops as git_ops_module
        monkeypatch.setattr(git_ops_module, "git_get_tracking_branch", lambda repo: "origin/main")
        monkeypatch.setattr(git_ops_module, "git_has_remote", lambda repo: True)

        repaired = []
        monkeypatch.setattr("sync_skills.cli.git_pull", lambda repo: (False, "local_changes"))
        monkeypatch.setattr("sync_skills.cli._do_doctor", lambda config, auto_confirm=False: repaired.append(auto_confirm))

        cmd_pull(argparse.Namespace(config=config_path, dry_run=False, yes=True))
        captured = capsys.readouterr()

        assert repaired == []
        assert "本地有未提交改动" in captured.out


class TestV1AutoCommitVersion:
    def test_new_skill_defaults_to_version_0_0_1(self, tmp_path):
        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)

        add_skill("demo", config)

        assert read_version(repo_skills / "demo") == "0.0.1"

    def test_add_auto_commit_passes_repo_skills_dir(self, tmp_path, monkeypatch, capsys):
        repo, repo_skills, agent_dirs, config = _create_v1_env(tmp_path)

        called = []
        monkeypatch.setattr("sync_skills.lifecycle.git_add_commit", lambda repo, message, repo_skills_dir=None: called.append((message, repo_skills_dir)) or True)

        add_skill("demo", config)
        captured = capsys.readouterr()

        assert called == [(called[0][0], config.repo_skills_dir)]
        assert called[0][0].startswith("add: demo (")
        assert "[git]" in captured.out
