"""
Structured Output Helpers for NouGenShards.
Handles local JSON validation and repair.
"""
import json
import re
from typing import Any, Tuple, List, Optional, Dict

def parse_json_content(content: str) -> Dict[str, Any]:
    """
    Attempts to parse JSON from a string, handling common LLM formatting issues.
    """
    content = content.strip()
    
    # 1. Direct Parse
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
        
    # 2. Extract from Markdown Code Block
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
            
    # 3. Extract from first { to last }
    start = content.find('{')
    end = content.rfind('}')
    if start != -1 and end != -1:
        try:
            parsed = json.loads(content[start:end+1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
            
    raise ValueError("Failed to parse JSON from content.")

def validate_against_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Minimal schema validation fallback.
    Checks required fields and basic types.
    """
    errors: List[str] = []
    
    # Check Required Fields
    required = schema.get("required", [])
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: {field}")
            
    # Check Types (Primitive)
    properties = schema.get("properties", {})
    for field, val in data.items():
        if field in properties:
            expected_type = properties[field].get("type")
            if expected_type == "string" and not isinstance(val, str):
                errors.append(f"Field '{field}' expected string, got {type(val).__name__}")
            elif expected_type == "number" and not isinstance(val, (int, float)):
                errors.append(f"Field '{field}' expected number, got {type(val).__name__}")
            elif expected_type == "integer" and not isinstance(val, int):
                errors.append(f"Field '{field}' expected integer, got {type(val).__name__}")
            elif expected_type == "boolean" and not isinstance(val, bool):
                errors.append(f"Field '{field}' expected boolean, got {type(val).__name__}")
            elif expected_type == "array" and not isinstance(val, list):
                errors.append(f"Field '{field}' expected array, got {type(val).__name__}")
            elif expected_type == "object" and not isinstance(val, dict):
                errors.append(f"Field '{field}' expected object, got {type(val).__name__}")
                
    # Check additionalProperties: false
    if schema.get("additionalProperties") is False:
        for field in data:
            if field not in properties:
                errors.append(f"Unexpected additional property: {field}")
                
    return (len(errors) == 0, errors)
