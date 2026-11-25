"""Tests for the .slopcheck.toml configuration loader."""

import pytest

from slopcheck.config import ConfigError, SlopcheckConfig, load_config


class TestMissingConfig:
    def test_returns_defaults_when_no_file(self, tmp_path):
        cfg = load_config(tmp_path)
        assert cfg == SlopcheckConfig()
        assert cfg.disabled_rules == frozenset()
        assert cfg.exclude == ()
        assert cfg.obvious_comment_threshold == 0.70
        assert cfg.micro_wrapper_max_statements == 2


class TestFullConfig:
    def test_all_settings_overridden(self, tmp_path):
        (tmp_path / ".slopcheck.toml").write_text(
            """\
[slopcheck]
disabled_rules = ["obvious-comment", "filler-docstring"]
exclude = ["tests/*", "vendor/*"]

[rules.obvious_comment]
threshold = 0.85

[rules.micro_wrapper]
max_statements = 5
""",
            encoding="utf-8",
        )
        cfg = load_config(tmp_path)
        assert cfg.disabled_rules == frozenset({"obvious-comment", "filler-docstring"})
        assert cfg.exclude == ("tests/*", "vendor/*")
        assert cfg.obvious_comment_threshold == 0.85
        assert cfg.micro_wrapper_max_statements == 5


class TestPartialConfig:
    def test_only_disabled_rules(self, tmp_path):
        (tmp_path / ".slopcheck.toml").write_text(
            '[slopcheck]\ndisabled_rules = ["micro-wrapper"]\n',
            encoding="utf-8",
        )
        cfg = load_config(tmp_path)
        assert cfg.disabled_rules == frozenset({"micro-wrapper"})
        assert cfg.exclude == ()
        assert cfg.obvious_comment_threshold == 0.70
        assert cfg.micro_wrapper_max_statements == 2

    def test_only_threshold(self, tmp_path):
        (tmp_path / ".slopcheck.toml").write_text(
            "[rules.obvious_comment]\nthreshold = 0.5\n",
            encoding="utf-8",
        )
        cfg = load_config(tmp_path)
        assert cfg.disabled_rules == frozenset()
        assert cfg.obvious_comment_threshold == 0.5

    def test_only_max_statements(self, tmp_path):
        (tmp_path / ".slopcheck.toml").write_text(
            "[rules.micro_wrapper]\nmax_statements = 1\n",
            encoding="utf-8",
        )
        cfg = load_config(tmp_path)
        assert cfg.micro_wrapper_max_statements == 1
        assert cfg.obvious_comment_threshold == 0.70

    def test_threshold_as_integer(self, tmp_path):
        (tmp_path / ".slopcheck.toml").write_text(
            "[rules.obvious_comment]\nthreshold = 1\n",
            encoding="utf-8",
        )
        cfg = load_config(tmp_path)
        assert cfg.obvious_comment_threshold == 1.0

    def test_threshold_zero(self, tmp_path):
        (tmp_path / ".slopcheck.toml").write_text(
            "[rules.obvious_comment]\nthreshold = 0\n",
            encoding="utf-8",
        )
        cfg = load_config(tmp_path)
        assert cfg.obvious_comment_threshold == 0.0


class TestMalformedToml:
    def test_bad_syntax_raises_config_error(self, tmp_path):
        (tmp_path / ".slopcheck.toml").write_text(
            "[slopcheck\nbroken",
            encoding="utf-8",
        )
        with pytest.raises(ConfigError, match="Invalid TOML syntax"):
            load_config(tmp_path)


class TestUnknownRuleId:
    def test_single_unknown_id(self, tmp_path):
        (tmp_path / ".slopcheck.toml").write_text(
            '[slopcheck]\ndisabled_rules = ["not-a-rule"]\n',
            encoding="utf-8",
        )
        with pytest.raises(ConfigError, match="Unknown rule IDs"):
            load_config(tmp_path)

    def test_mixed_valid_and_invalid(self, tmp_path):
        (tmp_path / ".slopcheck.toml").write_text(
            '[slopcheck]\ndisabled_rules = ["obvious-comment", "bogus"]\n',
            encoding="utf-8",
        )
        with pytest.raises(ConfigError, match="Unknown rule IDs"):
            load_config(tmp_path)


class TestThresholdValidation:
    def test_above_range(self, tmp_path):
        (tmp_path / ".slopcheck.toml").write_text(
            "[rules.obvious_comment]\nthreshold = 1.5\n",
            encoding="utf-8",
        )
        with pytest.raises(ConfigError, match="between 0.0 and 1.0"):
            load_config(tmp_path)

    def test_negative(self, tmp_path):
        (tmp_path / ".slopcheck.toml").write_text(
            "[rules.obvious_comment]\nthreshold = -0.1\n",
            encoding="utf-8",
        )
        with pytest.raises(ConfigError, match="between 0.0 and 1.0"):
            load_config(tmp_path)

    def test_string_type(self, tmp_path):
        (tmp_path / ".slopcheck.toml").write_text(
            '[rules.obvious_comment]\nthreshold = "high"\n',
            encoding="utf-8",
        )
        with pytest.raises(ConfigError, match="must be a number"):
            load_config(tmp_path)

    def test_boolean_type(self, tmp_path):
        (tmp_path / ".slopcheck.toml").write_text(
            "[rules.obvious_comment]\nthreshold = true\n",
            encoding="utf-8",
        )
        with pytest.raises(ConfigError, match="must be a number"):
            load_config(tmp_path)


class TestMaxStatementsValidation:
    def test_zero(self, tmp_path):
        (tmp_path / ".slopcheck.toml").write_text(
            "[rules.micro_wrapper]\nmax_statements = 0\n",
            encoding="utf-8",
        )
        with pytest.raises(ConfigError, match="must be >= 1"):
            load_config(tmp_path)

    def test_negative(self, tmp_path):
        (tmp_path / ".slopcheck.toml").write_text(
            "[rules.micro_wrapper]\nmax_statements = -3\n",
            encoding="utf-8",
        )
        with pytest.raises(ConfigError, match="must be >= 1"):
            load_config(tmp_path)

    def test_boolean_type(self, tmp_path):
        (tmp_path / ".slopcheck.toml").write_text(
            "[rules.micro_wrapper]\nmax_statements = false\n",
            encoding="utf-8",
        )
        with pytest.raises(ConfigError, match="must be an integer"):
            load_config(tmp_path)

    def test_float_type(self, tmp_path):
        (tmp_path / ".slopcheck.toml").write_text(
            "[rules.micro_wrapper]\nmax_statements = 2.5\n",
            encoding="utf-8",
        )
        with pytest.raises(ConfigError, match="must be an integer"):
            load_config(tmp_path)

    def test_string_type(self, tmp_path):
        (tmp_path / ".slopcheck.toml").write_text(
            '[rules.micro_wrapper]\nmax_statements = "two"\n',
            encoding="utf-8",
        )
        with pytest.raises(ConfigError, match="must be an integer"):
            load_config(tmp_path)


class TestDisabledRulesValidation:
    def test_not_a_list(self, tmp_path):
        (tmp_path / ".slopcheck.toml").write_text(
            '[slopcheck]\ndisabled_rules = "obvious-comment"\n',
            encoding="utf-8",
        )
        with pytest.raises(ConfigError, match="must be a list of strings"):
            load_config(tmp_path)

    def test_list_with_non_string(self, tmp_path):
        (tmp_path / ".slopcheck.toml").write_text(
            "[slopcheck]\ndisabled_rules = [42]\n",
            encoding="utf-8",
        )
        with pytest.raises(ConfigError, match="must be a list of strings"):
            load_config(tmp_path)


class TestExcludeValidation:
    def test_not_a_list(self, tmp_path):
        (tmp_path / ".slopcheck.toml").write_text(
            "[slopcheck]\nexclude = 123\n",
            encoding="utf-8",
        )
        with pytest.raises(ConfigError, match="must be a list of strings"):
            load_config(tmp_path)


class TestFrozenDataclass:
    def test_config_is_immutable(self, tmp_path):
        cfg = load_config(tmp_path)
        with pytest.raises(AttributeError):
            cfg.obvious_comment_threshold = 0.9


class TestEncodingAndBom:
    def test_utf8_bom_config_loads_cleanly(self, tmp_path):
        content = (
            '[slopcheck]\ndisabled_rules = ["filler-docstring"]\n'
            "[rules.obvious_comment]\nthreshold = 0.8\n"
        ).encode("utf-8")
        (tmp_path / ".slopcheck.toml").write_bytes(b"\xef\xbb\xbf" + content)

        cfg = load_config(tmp_path)
        assert cfg.disabled_rules == frozenset({"filler-docstring"})
        assert cfg.obvious_comment_threshold == 0.8

    def test_invalid_utf8_raises_config_error(self, tmp_path):
        (tmp_path / ".slopcheck.toml").write_bytes(b"\xff\xfe[slopcheck]\n")
        with pytest.raises(ConfigError, match="Invalid UTF-8 encoding"):
            load_config(tmp_path)
