"""config 模块测试"""

from pathlib import Path

import pytest

from sync_skills.config import (
    Config,
    Target,
    _expand_home,
    _unexpand_home,
    detect_installed_tools,
    load_config,
    save_config,
)
from sync_skills.constants import DEFAULT_SOURCE, DEFAULT_TARGETS


class TestExpandUnexpandHome:
    def test_expand_home(self):
        result = _expand_home("~/test/dir")
        assert result == Path.home() / "test" / "dir"

    def test_expand_home_no_tilde(self):
        result = _expand_home("/absolute/path")
        assert result == Path("/absolute/path")

    def test_unexpand_home(self):
        p = Path.home() / "test" / "dir"
        result = _unexpand_home(p)
        assert result == "~/test/dir"

    def test_unexpand_home_not_under_home(self):
        result = _unexpand_home(Path("/tmp/something"))
        assert result == "/tmp/something"

    def test_roundtrip(self):
        original = "~/Skills/Code"
        expanded = _expand_home(original)
        collapsed = _unexpand_home(expanded)
        assert collapsed == original


class TestLoadConfig:
    def test_missing_file_returns_defaults(self, tmp_path):
        config = load_config(tmp_path / "nonexistent.toml")
        assert config.source == DEFAULT_SOURCE
        assert len(config.targets) == len(DEFAULT_TARGETS)

    def test_valid_config(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'source = "~/CustomSkills"\n'
            '\n'
            '[[targets]]\n'
            'name = "test-tool"\n'
            'path = "~/.test-tool/skills"\n'
        )
        config = load_config(config_file)
        assert config.source == Path.home() / "CustomSkills"
        assert len(config.targets) == 1
        assert config.targets[0].name == "test-tool"
        assert config.targets[0].path == Path.home() / ".test-tool" / "skills"

    def test_empty_targets_falls_back(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text('source = "~/Skills"\n')
        config = load_config(config_file)
        # 空 targets 回退到默认值
        assert len(config.targets) == len(DEFAULT_TARGETS)

    def test_invalid_toml_returns_defaults(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("this is not valid toml {{{")
        config = load_config(config_file)
        assert config.source == DEFAULT_SOURCE

    def test_from_defaults(self):
        config = Config.from_defaults()
        assert config.source == DEFAULT_SOURCE
        assert len(config.targets) == len(DEFAULT_TARGETS)
        assert all(t.name == "builtin" for t in config.targets)


class TestSaveConfig:
    def test_save_and_load_roundtrip(self, tmp_path):
        config = Config(
            source=Path.home() / "MySkills",
            targets=[
                Target(name="tool-a", path=Path.home() / ".tool-a" / "skills"),
                Target(name="tool-b", path=Path.home() / ".tool-b" / "skills"),
            ],
        )
        config_file = tmp_path / "config.toml"
        save_config(config, config_path=config_file)
        assert config_file.is_file()

        loaded = load_config(config_file)
        assert loaded.source == config.source
        assert len(loaded.targets) == 2
        assert loaded.targets[0].name == "tool-a"
        assert loaded.targets[1].name == "tool-b"

    def test_save_creates_parent_dir(self, tmp_path):
        config = Config(source=Path.home() / "Skills")
        config_file = tmp_path / "sub" / "dir" / "config.toml"
        save_config(config, config_path=config_file)
        assert config_file.is_file()

    def test_save_uses_tilde_paths(self, tmp_path):
        config = Config(
            source=Path.home() / "Skills",
            targets=[Target(name="test", path=Path.home() / ".test" / "skills")],
        )
        config_file = tmp_path / "config.toml"
        save_config(config, config_path=config_file)
        content = config_file.read_text()
        assert "~/Skills" in content
        assert "~/.test/skills" in content


class TestDetectInstalledTools:
    def test_detect_existing(self, tmp_path, monkeypatch):
        """目录存在时应检测到"""
        from sync_skills.constants import KNOWN_TOOLS

        # 让 KNOWN_TOOLS 指向 tmp_path 下的目录
        fake_tools = [
            {"name": "Fake Tool", "path": str(tmp_path / "fake-tool" / "skills")},
        ]
        # 创建目录
        (tmp_path / "fake-tool" / "skills").mkdir(parents=True)

        monkeypatch.setattr("sync_skills.config.KNOWN_TOOLS", fake_tools)
        installed = detect_installed_tools()
        assert len(installed) == 1
        assert installed[0]["name"] == "Fake Tool"

    def test_detect_missing(self, tmp_path, monkeypatch):
        """目录不存在时不应检测到"""
        fake_tools = [
            {"name": "Missing Tool", "path": str(tmp_path / "missing" / "skills")},
        ]
        monkeypatch.setattr("sync_skills.config.KNOWN_TOOLS", fake_tools)
        installed = detect_installed_tools()
        assert len(installed) == 0
