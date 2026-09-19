"""Register scope tests: project-local default, --global opt-in (no writes)."""

import importlib.util
import os
import sys

import pytest

REPO = os.path.join(os.path.dirname(__file__), "..", "scripts")
spec = importlib.util.spec_from_file_location(
    "mg_register", os.path.join(REPO, "register.py"))
mg_register = importlib.util.module_from_spec(spec)
sys.modules["mg_register"] = mg_register
spec.loader.exec_module(mg_register)


def test_paths_default_is_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for agent, folder in (("claude", ".claude"),
                          ("codex", ".codex"),
                          ("cursor", ".cursor"),
                          ("antigravity", ".agents")):
        (p,) = mg_register._paths(agent, "project")
        assert p == os.path.join(str(tmp_path), folder,
                                 "settings.json" if agent == "claude"
                                 else "hooks.json")


def test_normalize_scope_user_alias_warns(capsys):
    assert mg_register._normalize_scope("user") == "global"
    assert "deprecated" in capsys.readouterr().err


def test_global_flag_maps_to_home(capsys, monkeypatch):
    monkeypatch.chdir("/tmp")
    home = os.path.expanduser("~")
    # capture resolved scope + paths without writing
    seen = {}

    def fake_install(agent, path, hook_bin, fc):
        seen[agent] = path
        return "ok"

    monkeypatch.setattr(mg_register, "_install", fake_install)
    assert mg_register.main(["--agent", "claude", "--global"]) == 0
    assert seen["claude"] == os.path.join(
        home, ".claude", "settings.json")


def test_scope_global_explicit_maps_to_home(monkeypatch):
    monkeypatch.chdir("/tmp")
    home = os.path.expanduser("~")
    seen = {}

    def fake_install(agent, path, hook_bin, fc):
        seen[agent] = path
        return "ok"

    monkeypatch.setattr(mg_register, "_install", fake_install)
    assert mg_register.main(["--agent", "codex",
                             "--scope", "global"]) == 0
    assert seen["codex"] == os.path.join(home, ".codex", "hooks.json")


def test_global_conflicts_with_scope_project():
    with pytest.raises(SystemExit):
        mg_register.main(["--agent", "all", "--global",
                          "--scope", "project"])


def test_uninstall_roundtrip_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from scripts.register_lib import TAG
    assert mg_register.main(
        ["--agent", "all", "--hook-bin", "model-guard-hook"]) == 0
    assert (tmp_path / ".claude" / "settings.json").is_file()
    assert mg_register.main(["--agent", "all", "--uninstall"]) == 0
    for rel in (".claude/settings.json", ".codex/hooks.json",
                ".cursor/hooks.json", ".agents/hooks.json"):
        text = (tmp_path / rel).read_text()
        assert TAG not in text, rel


def test_default_scope_is_project_when_flag_absent(monkeypatch):
    monkeypatch.chdir("/tmp")
    seen = {}

    def fake_install(agent, path, hook_bin, fc):
        seen[agent] = path
        return "ok"

    monkeypatch.setattr(mg_register, "_install", fake_install)
    assert mg_register.main(["--agent", "cursor"]) == 0
    assert seen["cursor"].startswith(os.getcwd())
    assert ".cursor" in seen["cursor"]
