"""Config `tui` section tests (plan task 2)."""

from neow.core.config import Config


def test_tui_config_defaults(tmp_path):
    cfg = Config(tmp_path / "missing.json")
    assert cfg.tui == {"effects": "full", "sidebar_default": False, "theme": "midnight"}


def test_tui_config_unknown_effects_falls_back(tmp_path):
    p = tmp_path / ".neow.json"
    p.write_text('{"tui": {"effects": "warp9"}}')
    assert Config(p).tui["effects"] == "full"


def test_theme_configuration_does_not_leak_into_other_instances(tmp_path):
    path = tmp_path / "light.json"
    path.write_text('{"tui": {"theme": "light"}}')
    assert Config(path).tui["theme"] == "light"
    assert Config(tmp_path / "missing.json").tui["theme"] == "midnight"
    assert Config.DEFAULT_CONFIG["tui"]["theme"] == "midnight"
