"""
Unit tests for structured output parsing and validation.
"""
import pytest
from nougen_shards.structured import parse_json_content, validate_against_schema

def test_parse_json_direct():
    content = '{"key": "value"}'
    assert parse_json_content(content) == {"key": "value"}

def test_parse_json_markdown():
    content = "Here is the data:\n```json\n{\"foo\": 123}\n```\nHope this helps!"
    assert parse_json_content(content) == {"foo": 123}

def test_parse_json_braces():
    content = "Mixed text {\"bar\": true} and more text"
    assert parse_json_content(content) == {"bar": True}

def test_validate_against_schema_success():
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"}
        },
        "required": ["name"]
    }
    data = {"name": "Dave", "age": 30}
    valid, errors = validate_against_schema(data, schema)
    assert valid is True
    assert len(errors) == 0

def test_validate_against_schema_failure():
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"}
        },
        "required": ["name", "id"],
        "additionalProperties": False
    }
    data = {"name": 123, "extra": "data"}
    valid, errors = validate_against_schema(data, schema)
    assert valid is False
    assert any("Missing required field: id" in e for e in errors)
    assert any("Field 'name' expected string" in e for e in errors)
    assert any("Unexpected additional property: extra" in e for e in errors)
