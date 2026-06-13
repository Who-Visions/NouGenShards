/**
 * Structured Output Helpers for NouGenShards. (TS mimic of structured.py)
 * Handles local JSON validation and repair.
 */

function _is_plain_object(val: any): val is Record<string, any> {
  return typeof val === "object" && val !== null && !Array.isArray(val);
}

/**
 * Attempts to parse JSON from a string, handling common LLM formatting issues.
 */
export function parse_json_content(content: string): Record<string, any> {
  content = content.trim();

  // 1. Direct Parse
  try {
    const parsed = JSON.parse(content);
    if (_is_plain_object(parsed)) {
      return parsed;
    }
  } catch {
    /* fallthrough */
  }

  // 2. Extract from Markdown Code Block
  const match = content.match(/```(?:json)?\s*([\s\S]*?)\s*```/);
  if (match) {
    try {
      const parsed = JSON.parse(match[1]);
      if (_is_plain_object(parsed)) {
        return parsed;
      }
    } catch {
      /* fallthrough */
    }
  }

  // 3. Extract from first { to last }
  const start = content.indexOf("{");
  const end = content.lastIndexOf("}");
  if (start !== -1 && end !== -1) {
    try {
      const parsed = JSON.parse(content.slice(start, end + 1));
      if (_is_plain_object(parsed)) {
        return parsed;
      }
    } catch {
      /* fallthrough */
    }
  }

  throw new Error("Failed to parse JSON from content.");
}

function _type_name(val: any): string {
  if (val === null) return "NoneType";
  if (Array.isArray(val)) return "list";
  switch (typeof val) {
    case "string":
      return "str";
    case "number":
      return Number.isInteger(val) ? "int" : "float";
    case "boolean":
      return "bool";
    case "object":
      return "dict";
    default:
      return typeof val;
  }
}

/**
 * Minimal schema validation fallback.
 * Checks required fields and basic types.
 */
export function validate_against_schema(
  data: Record<string, any>,
  schema: Record<string, any>,
): [boolean, string[]] {
  const errors: string[] = [];

  // Check Required Fields
  const required: string[] = schema.required ?? [];
  for (const field of required) {
    if (!(field in data)) {
      errors.push(`Missing required field: ${field}`);
    }
  }

  // Check Types (Primitive)
  const properties: Record<string, any> = schema.properties ?? {};
  for (const [field, val] of Object.entries(data)) {
    if (field in properties) {
      const expected_type = properties[field].type;
      if (expected_type === "string" && typeof val !== "string") {
        errors.push(`Field '${field}' expected string, got ${_type_name(val)}`);
      } else if (expected_type === "number" && typeof val !== "number") {
        errors.push(`Field '${field}' expected number, got ${_type_name(val)}`);
      } else if (expected_type === "integer" && !Number.isInteger(val)) {
        errors.push(`Field '${field}' expected integer, got ${_type_name(val)}`);
      } else if (expected_type === "boolean" && typeof val !== "boolean") {
        errors.push(`Field '${field}' expected boolean, got ${_type_name(val)}`);
      } else if (expected_type === "array" && !Array.isArray(val)) {
        errors.push(`Field '${field}' expected array, got ${_type_name(val)}`);
      } else if (expected_type === "object" && !_is_plain_object(val)) {
        errors.push(`Field '${field}' expected object, got ${_type_name(val)}`);
      }
    }
  }

  // Check additionalProperties: false
  if (schema.additionalProperties === false) {
    for (const field of Object.keys(data)) {
      if (!(field in properties)) {
        errors.push(`Unexpected additional property: ${field}`);
      }
    }
  }

  return [errors.length === 0, errors];
}
