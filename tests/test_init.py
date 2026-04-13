"""init 子命令测试"""

from pathlib import Path

from sync_skills.config import Config, save_config
from sync_skills.lifecycle import init_repo


def _make_config(tmp_path: Path, repo: Path | None = None) -> Config:
    """创建测试用 Config。"""
    return Config(
        repo=repo or (tmp_path / "Skills"),
        agent_dirs=[tmp_path / ".agents" / "skills", tmp_path / ".claude" / "skills"],
        state_file=tmp_path / "state" / "skills.json",
    )


def _config_path(tmp_path: Path) -> Path:
    """测试用配置文件路径。"""
    return tmp_path / "config.toml"


def _setup_git_repo(repo: Path) -> None:
    """在指定路径创建真实 git 仓库（git init）。"""
    import subprocess
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(repo)], capture_output=True, check=True)


def _setup_state(state_file: Path, skills: dict | None = None) -> None:
    """创建状态文件。"""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    import json
    data = {"skills": {k: {"source": "sync-skills"} for k in (skills or {})}}
    state_file.write_text(json.dumps(data))


def _setup_agent_dirs(agent_dirs: list[Path]) -> None:
    """创建 agent 目录。"""
    for ad in agent_dirs:
        ad.mkdir(parents=True, exist_ok=True)


class TestInitNewRepo:
    """场景 A: 全新仓库（无 git）"""

    def test_init_new_repo(self, tmp_path, monkeypatch):
        """新仓库 init 应创建 git 仓库和配置"""
        config = _make_config(tmp_path)
        cp = _config_path(tmp_path)

        # inputs: repo_path(默认), has_remote(n), agent_select(默认), confirm(y)
        inputs = iter(["", "n", "", "y"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        result = init_repo(config, config_path=cp)

        assert result is True
        assert config.repo.is_dir()
        assert (config.repo / ".git").is_dir()

    def test_init_new_repo_saves_config(self, tmp_path, monkeypatch):
        """新仓库 init 应保存配置文件"""
        config = _make_config(tmp_path)
        cp = _config_path(tmp_path)

        inputs = iter(["", "n", "", "y"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        init_repo(config, config_path=cp)

        assert cp.is_file()

    def test_init_new_repo_custom_path(self, tmp_path, monkeypatch):
        """自定义仓库路径"""
        custom_repo = tmp_path / "MySkills"
        config = _make_config(tmp_path, repo=custom_repo)
        cp = _config_path(tmp_path)

        inputs = iter(["", "n", "", "y"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        init_repo(config, config_path=cp)

        assert cp.is_file()
        assert custom_repo.is_dir()
        assert (custom_repo / ".git").is_dir()


class TestInitCloneRemote:
    """场景 B: 有远程仓库"""

    def test_init_clone_remote(self, tmp_path, monkeypatch):
        """有远程仓库时应 git clone"""
        config = _make_config(tmp_path)
        cp = _config_path(tmp_path)

        # inputs: repo_path(默认), has_remote(y), remote_url, agent_select(默认), confirm(y)
        inputs = iter(["", "y", "git@github.com:user/Skills.git", "", "y"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        # mock git_clone
        def mock_clone(url, path):
            path.mkdir(parents=True, exist_ok=True)
            (path / ".git").mkdir()
            return True

        monkeypatch.setattr("sync_skills.git_ops.git_clone", mock_clone)

        result = init_repo(config, config_path=cp)

        assert result is True
        assert config.repo.is_dir()

    def test_init_clone_registers_repo_skills(self, tmp_path, monkeypatch):
        """clone 后应自动注册 repo 中已有的 skill"""
        config = _make_config(tmp_path)
        cp = _config_path(tmp_path)

        # 模拟已 clone 的 repo（带 skill）
        _setup_git_repo(config.repo)
        skills_dir = config.repo / "skills"
        skills_dir.mkdir()
        (skills_dir / "existing-skill").mkdir()
        (skills_dir / "existing-skill" / "SKILL.md").write_text("# existing\n")
        _setup_state(config.state_file)
        _setup_agent_dirs(config.agent_dirs)

        # inputs: repo_path(默认), agent_select(空), confirm(y)
        inputs = iter(["", "", "y"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        init_repo(config, config_path=cp)

        from sync_skills.state import get_managed_skills
        managed = get_managed_skills(config.state_file)
        assert "existing-skill" in managed

    def test_init_clone_rejects_empty_url(self, tmp_path, monkeypatch):
        """空 URL 应取消操作"""
        config = _make_config(tmp_path)

        inputs = iter(["", "y", ""])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        result = init_repo(config)
        assert result is False


class TestInitReconfigure:
    """场景 C: 已初始化，重新执行"""

    def test_init_already_initialized(self, tmp_path, monkeypatch):
        """已初始化的仓库再次 init 应正常工作（幂等）"""
        config = _make_config(tmp_path)
        cp = _config_path(tmp_path)

        # 预先创建 git repo + state file + skill
        _setup_git_repo(config.repo)
        skills_dir = config.repo / "skills"
        skills_dir.mkdir()
        (skills_dir / "skill-a").mkdir()
        (skills_dir / "skill-a" / "SKILL.md").write_text("# a\n")
        _setup_state(config.state_file, {"skill-a"})
        _setup_agent_dirs(config.agent_dirs)

        # inputs: repo_path(默认), agent_select(空), confirm(y)
        inputs = iter(["", "", "y"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        result = init_repo(config, config_path=cp)

        assert result is True
        from sync_skills.state import get_managed_skills
        managed = get_managed_skills(config.state_file)
        assert "skill-a" in managed

    def test_init_registers_new_repo_skills(self, tmp_path, monkeypatch):
        """重新 init 时应注册新增的 repo skill"""
        config = _make_config(tmp_path)
        cp = _config_path(tmp_path)

        # 预先创建 git repo + 已管理 skill
        _setup_git_repo(config.repo)
        skills_dir = config.repo / "skills"
        skills_dir.mkdir()
        (skills_dir / "skill-a").mkdir()
        (skills_dir / "skill-a" / "SKILL.md").write_text("# a\n")
        _setup_state(config.state_file, {"skill-a"})
        _setup_agent_dirs(config.agent_dirs)

        # 添加新 skill（模拟从其他电脑 pull 后）
        (skills_dir / "skill-b").mkdir()
        (skills_dir / "skill-b" / "SKILL.md").write_text("# b\n")

        # inputs: repo_path(默认), agent_select(空), confirm(y)
        inputs = iter(["", "", "y"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        init_repo(config, config_path=cp)

        from sync_skills.state import get_managed_skills
        managed = get_managed_skills(config.state_file)
        assert "skill-a" in managed
        assert "skill-b" in managed

    def test_init_creates_symlinks(self, tmp_path, monkeypatch):
        """init 应为所有已管理 skill 创建 symlink"""
        config = _make_config(tmp_path)
        cp = _config_path(tmp_path)

        _setup_git_repo(config.repo)
        skills_dir = config.repo / "skills"
        skills_dir.mkdir()
        (skills_dir / "my-skill").mkdir()
        (skills_dir / "my-skill" / "SKILL.md").write_text("# test\n")
        _setup_state(config.state_file)
        _setup_agent_dirs(config.agent_dirs)

        # inputs: repo_path(默认), agent_select(空), confirm(y)
        inputs = iter(["", "", "y"])
        monkeypatch.setattr("builtins.input", lambda _: next(inputs))

        init_repo(config, config_path=cp)

        for ad in config.agent_dirs:
            link = ad / "my-skill"
            assert link.is_symlink()


class TestInitAutoConfirm:
    """-y 自动确认模式"""

    def test_init_auto_confirm(self, tmp_path):
        """-y 应跳过所有交互"""
        config = _make_config(tmp_path)
        cp = _config_path(tmp_path)

        result = init_repo(config, auto_confirm=True, config_path=cp)

        assert result is True
        assert config.repo.is_dir()
        assert (config.repo / ".git").is_dir()
        assert cp.is_file()

    def test_init_auto_confirm_registers_skills(self, tmp_path):
        """-y 模式也应自动注册 repo 中的 skill"""
        config = _make_config(tmp_path)
        cp = _config_path(tmp_path)

        _setup_git_repo(config.repo)
        skills_dir = config.repo / "skills"
        skills_dir.mkdir()
        (skills_dir / "auto-skill").mkdir()
        (skills_dir / "auto-skill" / "SKILL.md").write_text("# auto\n")
        _setup_state(config.state_file)
        _setup_agent_dirs(config.agent_dirs)

        result = init_repo(config, auto_confirm=True, config_path=cp)

        assert result is True
        from sync_skills.state import get_managed_skills
        managed = get_managed_skills(config.state_file)
        assert "auto-skill" in managed

    def test_init_dry_run(self, tmp_path):
        """--dry-run 不应修改文件系统"""
        config = _make_config(tmp_path)

        result = init_repo(config, auto_confirm=True, dry_run=True)

        assert result is True
        assert not (config.repo / ".git").exists()
