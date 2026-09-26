"""Configuration loading for nougen_verse.

Every threshold, weight, lexicon and profile the engine uses comes from a
``Config`` object. The defaults live in ``data/defaults.json`` and are merged
with, in order of increasing priority:

1. a JSON file named by the ``NOUGEN_VERSE_CONFIG`` environment variable,
2. environment variables shaped ``NOUGEN_VERSE__SECTION__KEY=value``
   (the value is parsed as JSON when it parses, otherwise kept as a string),
3. the ``overrides`` mapping passed to :func:`load_config`.

The merged result is logged at debug level so a run can always say which
values it used.
"""

from __future__ import annotations

import copy
import json
import logging
import os
from functools import lru_cache
from importlib import resources
from typing import Any, Mapping

log = logging.getLogger("nougen_verse.config")

ENV_CONFIG_FILE = "NOUGEN_VERSE_CONFIG"
ENV_PREFIX = "NOUGEN_VERSE__"
ENV_DICTIONARY = "NOUGEN_VERSE_DICTIONARY"
ENV_PERSONA_PATH = "NOUGEN_VERSE_PERSONA_PATH"
ENV_ENABLE_GENERATE = "NOUGEN_VERSE_ENABLE_GENERATE"


def _read_data_text(name: str) -> str:
    return resources.files("nougen_verse").joinpath("data", name).read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def load_data_json(name: str) -> Any:
    """Load a bundled JSON data file (cached, treat the result as read-only)."""
    return json.loads(_read_data_text(name))


def load_data_lines(name: str) -> list[str]:
    """Load a bundled text data file as stripped, non-comment lines."""
    out = []
    for line in _read_data_text(name).splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def deep_merge(base: dict, extra: Mapping) -> dict:
    """Return ``base`` updated recursively with ``extra`` (base is not mutated)."""
    result = copy.deepcopy(base)
    for key, value in extra.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _parse_env_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw


def _env_overrides(env: Mapping[str, str]) -> dict:
    overrides: dict = {}
    for name, raw in env.items():
        if not name.startswith(ENV_PREFIX):
            continue
        path = [p.lower() for p in name[len(ENV_PREFIX):].split("__") if p]
        if not path:
            continue
        node = overrides
        for part in path[:-1]:
            node = node.setdefault(part, {})
        node[path[-1]] = _parse_env_value(raw)
    return overrides


class Config:
    """Read-mostly view over the merged configuration dictionary.

    Sections are reachable as attributes (``cfg.rhyme["slant_max_distance"]``)
    or with :meth:`get` using a dotted path (``cfg.get("rhyme.slant_max_distance")``).
    """

    def __init__(self, data: dict, sources: list[str] | None = None):
        self._data = data
        self.sources = list(sources or ["defaults"])

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._data[name]
        except KeyError as exc:
            raise AttributeError(f"config has no section {name!r}") from exc

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def with_overrides(self, overrides: Mapping | None) -> "Config":
        if not overrides:
            return self
        return Config(deep_merge(self._data, overrides), self.sources + ["overrides"])

    def to_dict(self) -> dict:
        return copy.deepcopy(self._data)


def load_config(overrides: Mapping | None = None, env: Mapping[str, str] | None = None) -> Config:
    """Build a :class:`Config` from defaults, env and explicit overrides."""
    env = os.environ if env is None else env
    data = copy.deepcopy(load_data_json("defaults.json"))
    sources = ["defaults"]
    path = env.get(ENV_CONFIG_FILE)
    if path:
        try:
            with open(path, encoding="utf-8") as fh:
                data = deep_merge(data, json.load(fh))
            sources.append(f"file:{path}")
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("could not read %s=%s (%s); continuing with defaults", ENV_CONFIG_FILE, path, exc)
    env_over = _env_overrides(env)
    if env_over:
        data = deep_merge(data, env_over)
        sources.append("env")
    if overrides:
        data = deep_merge(data, overrides)
        sources.append("overrides")
    log.debug("config sources: %s", sources)
    return Config(data, sources)


_DEFAULT: Config | None = None


def get_default_config() -> Config:
    """Process-wide config built from defaults and the current environment."""
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_config()
    return _DEFAULT


def reset_default_config() -> None:
    """Forget the cached default config (used after env changes, mainly in tests)."""
    global _DEFAULT
    _DEFAULT = None


def resolve_config(config: Config | Mapping | None) -> Config:
    if config is None:
        return get_default_config()
    if isinstance(config, Config):
        return config
    return load_config(overrides=config)
