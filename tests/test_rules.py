from model_guard.core import deterministic_pre_screen


def test_rules_sensitive_path_forces_approval():
    d = deterministic_pre_screen(
        {"tool": "Bash", "command": "cat ~/client-secrets/notes.txt",
         "sensitive_paths": ["~/client-secrets"]})
    assert d and d.verdict == "REQUIRE_APPROVAL"
    assert d.deterministic_hit == "rules:sensitive"


def test_rules_loader_defaults_and_parse(tmp_path):
    from model_guard.rules import load_user_rules, parse_rules_file
    rules = load_user_rules(cwd=str(tmp_path))
    assert rules["allow"] and rules["ask"] and rules["block"]
    p = tmp_path / "RULES.md"
    p.write_text("## Always allow\n- hug the cat\n\n## Never block\n- rm everything\n")
    parsed = parse_rules_file(str(p))
    assert parsed["allow"] == ["hug the cat"]
    assert parsed["block"] == ["rm everything"]
    found = load_user_rules(cwd=str(tmp_path))
    assert found["source"] == str(p)


def test_jev_state_carries_user_rules():
    from model_guard.jev_client import build_state
    s = build_state({"command": "x",
                     "user_rules": {"allow": ["a"], "ask": ["b"],
                                    "block": ["c"]}})
    assert s["policy"]["user_rules"]["block"] == ["c"]
