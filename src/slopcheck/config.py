"""Configuration loader for .slopcheck.toml files."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

VALID_RULE_IDS = frozenset(
    {"obvious-comment", "swallowed-exception", "micro-wrapper", "filler-docstring"}
)


class ConfigError(Exception):
    """Raised when .slopcheck.toml is malformed or contains invalid values."""


@dataclass(frozen=True)
class SlopcheckConfig:
    disabled_rules: frozenset[str] = frozenset()
    exclude: tuple[str, ...] = ()
    obvious_comment_threshold: float = 0.70
    micro_wrapper_max_statements: int = 2


def _require_list_of_strings(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"'{field_name}' must be a list of strings")
    return value


def load_config(repo_root: str | Path) -> SlopcheckConfig:
    config_path = Path(repo_root) / ".slopcheck.toml"

    if not config_path.exists():
        return SlopcheckConfig()

    try:
        raw_bytes = config_path.read_bytes().removeprefix(b"\xef\xbb\xbf")
        raw = tomllib.loads(raw_bytes.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ConfigError(f"Invalid UTF-8 encoding in config file: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML syntax: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Could not read config file: {exc}") from exc

    kwargs: dict[str, object] = {}

    slopcheck_section = raw.get("slopcheck", {})
    if not isinstance(slopcheck_section, dict):
        raise ConfigError("'[slopcheck]' must be a table")

    if "disabled_rules" in slopcheck_section:
        ids = _require_list_of_strings(slopcheck_section["disabled_rules"], "disabled_rules")
        invalid = set(ids) - VALID_RULE_IDS
        if invalid:
            raise ConfigError(f"Unknown rule IDs: {sorted(invalid)}")
        kwargs["disabled_rules"] = frozenset(ids)

    if "exclude" in slopcheck_section:
        patterns = _require_list_of_strings(slopcheck_section["exclude"], "exclude")
        kwargs["exclude"] = tuple(patterns)

    rules_section = raw.get("rules", {})
    if not isinstance(rules_section, dict):
        raise ConfigError("'[rules]' must be a table")

    oc = rules_section.get("obvious_comment", {})
    if not isinstance(oc, dict):
        raise ConfigError("'[rules.obvious_comment]' must be a table")
    if "threshold" in oc:
        val = oc["threshold"]
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise ConfigError("'threshold' must be a number (not bool)")
        val = float(val)
        if not (0.0 <= val <= 1.0):
            raise ConfigError(f"'threshold' must be between 0.0 and 1.0, got {val}")
        kwargs["obvious_comment_threshold"] = val

    mw = rules_section.get("micro_wrapper", {})
    if not isinstance(mw, dict):
        raise ConfigError("'[rules.micro_wrapper]' must be a table")
    if "max_statements" in mw:
        val = mw["max_statements"]
        if isinstance(val, bool) or not isinstance(val, int):
            raise ConfigError("'max_statements' must be an integer (not bool)")
        if val < 1:
            raise ConfigError(f"'max_statements' must be >= 1, got {val}")
        kwargs["micro_wrapper_max_statements"] = val

    return SlopcheckConfig(**kwargs)
