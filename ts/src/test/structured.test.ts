/** Port of tests/test_structured_outputs.py — JSON parsing + schema validation. */
import { test } from "node:test";
import assert from "node:assert/strict";
import { parse_json_content, validate_against_schema } from "../nougen_shards/structured.js";

test("parse_json_direct", () => {
  assert.deepEqual(parse_json_content('{"key": "value"}'), { key: "value" });
});

test("parse_json_markdown", () => {
  const content = 'Here is the data:\n```json\n{"foo": 123}\n```\nHope this helps!';
  assert.deepEqual(parse_json_content(content), { foo: 123 });
});

test("parse_json_braces", () => {
  const content = 'Mixed text {"bar": true} and more text';
  assert.deepEqual(parse_json_content(content), { bar: true });
});

test("validate_against_schema_success", () => {
  const schema = {
    type: "object",
    properties: { name: { type: "string" }, age: { type: "integer" } },
    required: ["name"],
  };
  const [valid, errors] = validate_against_schema({ name: "Dave", age: 30 }, schema);
  assert.equal(valid, true);
  assert.equal(errors.length, 0);
});

test("validate_against_schema_failure", () => {
  const schema = {
    type: "object",
    properties: { name: { type: "string" }, age: { type: "integer" } },
    required: ["name", "id"],
    additionalProperties: false,
  };
  const [valid, errors] = validate_against_schema({ name: 123, extra: "data" }, schema);
  assert.equal(valid, false);
  assert.ok(errors.some((e) => e.includes("Missing required field: id")));
  assert.ok(errors.some((e) => e.includes("Field 'name' expected string")));
  assert.ok(errors.some((e) => e.includes("Unexpected additional property: extra")));
});
