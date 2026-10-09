"""Render the shared chat-widget IR contract into Python and TypeScript artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "contracts" / "chat-widgets.v1.json"
PYTHON_OUTPUT = ROOT / "src" / "nougen_shards" / "chat_widget_ir.py"
TYPESCRIPT_OUTPUT = ROOT / "ui" / "src" / "chatWidgetIR.ts"


def _ref_name(ref: str) -> str:
    if not ref.startswith("#/definitions/"):
        raise ValueError(f"Unsupported schema reference: {ref}")
    return ref.rsplit("/", 1)[-1]


def _ts_type(schema: dict, definitions: dict, depth: int = 0) -> str:
    if depth > 16:
        raise ValueError("Schema nesting exceeds compiler limit")
    if "$ref" in schema:
        return _ref_name(schema["$ref"])
    if "const" in schema:
        return json.dumps(schema["const"])
    if "enum" in schema:
        return " | ".join(json.dumps(item) for item in schema["enum"])
    if "oneOf" in schema or "anyOf" in schema:
        return " | ".join(f"({_ts_type(item, definitions, depth + 1)})" for item in schema.get("oneOf", schema.get("anyOf", [])))
    kind = schema.get("type")
    if kind == "array":
        item = _ts_type(schema.get("items", {}), definitions, depth + 1)
        return f"Array<{item}>"
    if kind == "object":
        props = schema.get("properties", {})
        required = set(schema.get("required", []))
        fields = [f"  {name}{'' if name in required else '?'}: {_ts_type(value, definitions, depth + 1)};" for name, value in props.items()]
        return "{\n" + "\n".join(fields) + "\n}"
    return {"string": "string", "number": "number", "integer": "number", "boolean": "boolean"}.get(kind, "unknown")


def render(spec: dict) -> dict[Path, str]:
    if spec.get("contract") != "nougen.chat-widget-ir" or not isinstance(spec.get("version"), int):
        raise ValueError("Invalid chat widget IR contract identity")
    variants = spec.get("variants", [])
    kinds = [variant["kind"] for variant in variants]
    if len(kinds) != len(set(kinds)) or not kinds:
        raise ValueError("Widget kinds must be unique and non-empty")
    parameters = spec.get("toolParameters")
    if not isinstance(parameters, dict) or parameters.get("type") != "object":
        raise ValueError("Tool parameters must be an object schema")
    if any("$ref" in json.dumps(parameters) for _ in [0]):
        raise ValueError("Tool parameters must be self-contained for model providers")

    python_data = json.dumps({"version": spec["version"], "kinds": kinds, "limits": spec.get("limits", {}), "parameters": parameters}, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    python = '''"""GENERATED from contracts/chat-widgets.v1.json; do not edit."""
import json

_IR = json.loads(''' + repr(python_data) + ''')
CHAT_WIDGET_IR_VERSION = _IR["version"]
CHAT_WIDGET_KINDS = tuple(_IR["kinds"])
CHAT_WIDGET_LIMITS = _IR["limits"]
PRESENT_WIDGET_PARAMETERS = _IR["parameters"]
'''

    definitions = spec.get("definitions", {})
    type_lines = [f"export const CHAT_WIDGET_IR_VERSION = {spec['version']} as const;", f"export const CHAT_WIDGET_KINDS = {json.dumps(kinds)} as const;", f"export const CHAT_WIDGET_LIMITS = {json.dumps(spec.get('limits', {}), sort_keys=True)} as const;", ""]
    for name, schema in definitions.items():
        type_lines.append(f"export type {name} = {_ts_type(schema, definitions)};")
    type_lines.append("")
    variant_types = []
    for variant in variants:
        props = {"contractVersion": {"const": spec["version"]}, "kind": {"const": variant["kind"]}, "title": {"type": "string", "maxLength": spec["limits"]["titleLength"]}, **variant["fields"]}
        required = ["contractVersion", "kind", "title", *variant["fields"].keys()]
        variant_types.append(_ts_type({"type": "object", "properties": props, "required": required}, definitions))
    type_lines.append("export type Widget = " + "\n  | ".join(variant_types) + ";")
    type_lines.append("")
    type_lines.append("export const CHAT_WIDGET_VARIANTS = " + json.dumps(variants, ensure_ascii=False, separators=(",", ":")) + " as const;")
    typescript = "// GENERATED from contracts/chat-widgets.v1.json; do not edit.\n" + "\n".join(type_lines)
    return {PYTHON_OUTPUT: python, TYPESCRIPT_OUTPUT: typescript}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail when generated files are stale")
    args = parser.parse_args()
    spec = json.loads(SOURCE.read_text(encoding="utf-8"))
    outputs = render(spec)
    stale = []
    for path, content in outputs.items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                stale.append(path.relative_to(ROOT).as_posix())
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    if stale:
        print("stale generated chat widget IR: " + ", ".join(stale))
        return 1
    print(("verified" if args.check else "generated") + f" {len(outputs)} chat widget IR artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
