"""Load the bundled JSON Schemas and validate outputs against them.

Validation needs the optional ``jsonschema`` package (extra ``validate``).
The engine itself never requires it.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from typing import Any

SCHEMA_FILES = {
    "verse_request": "verse_request.schema.json",
    "verse_blueprint": "verse_blueprint.schema.json",
    "verse_analysis": "verse_analysis.schema.json",
    "score_report": "score_report.schema.json",
    "repair_plan": "repair_plan.schema.json",
    "compiled_prompt": "compiled_prompt.schema.json",
}


class SchemaValidationUnavailable(RuntimeError):
    """Raised when jsonschema is not installed."""


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict:
    if name not in SCHEMA_FILES:
        raise KeyError(f"unknown schema {name!r}; known: {sorted(SCHEMA_FILES)}")
    text = resources.files("nougen_verse").joinpath("schemas", SCHEMA_FILES[name]).read_text(encoding="utf-8")
    return json.loads(text)


def validate(instance: Any, name: str) -> list[str]:
    """Return a sorted list of validation error messages (empty when valid)."""
    try:
        import jsonschema  # type: ignore
    except ImportError as exc:
        raise SchemaValidationUnavailable("schema validation needs the optional jsonschema package (pip install 'nougen-verse[validate]')") from exc
    if hasattr(instance, "to_dict"):
        instance = instance.to_dict()
    instance = json.loads(json.dumps(instance))
    validator = jsonschema.Draft202012Validator(load_schema(name))
    errors = []
    for err in validator.iter_errors(instance):
        path = "/".join(str(p) for p in err.absolute_path) or "(root)"
        errors.append(f"{path}: {err.message}")
    return sorted(errors)
