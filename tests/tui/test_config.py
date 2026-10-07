"""Config `tui` section tests (plan task 2)."""

from neow.core.config import Config


def test_tui_config_defaults(tmp_path):
    cfg = Config(tmp_path / "missing.json")
    assert cfg.tui == {"effects": "full", "sidebar_default": False, "theme": "midnight"}


def test_tui_config_unknown_effects_falls_back(tmp_path):
    p = tmp_path / ".neow.json"
    p.write_text('{"tui": {"effects": "warp9"}}')
    assert Config(p).tui["effects"] == "full"
