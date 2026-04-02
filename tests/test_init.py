"""init 子命令测试"""

from pathlib import Path

from sync_skills.cli import main


def test_init_creates_config(tmp_path, monkeypatch):
    """init 子命令应创建配置文件"""
    config_file = tmp_path / "config.toml"
    # 模拟用户输入：默认源目录、空选择（全选）、空额外目录
    inputs = iter(["", "", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    main(["init", "--config", str(config_file)])

    assert config_file.is_file()
    content = config_file.read_text()
    assert "source" in content


def test_init_default_source(tmp_path, monkeypatch):
    """不输入时使用默认源目录 ~/Skills"""
    config_file = tmp_path / "config.toml"
    inputs = iter(["", "", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    main(["init", "--config", str(config_file)])

    content = config_file.read_text()
    assert "~/Skills" in content


def test_init_custom_source(tmp_path, monkeypatch):
    """自定义源目录路径"""
    config_file = tmp_path / "config.toml"
    inputs = iter(["~/MyCustomSkills", "", ""])
    monkeypatch.setattr("builtins.input", lambda _: next(inputs))

    main(["init", "--config", str(config_file)])

    content = config_file.read_text()
    assert "~/MyCustomSkills" in content
