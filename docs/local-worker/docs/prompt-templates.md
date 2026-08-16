# Bounded Prompt Templates

Small local models (like Gemma 4 E2B) perform best under bounded scopes. Avoid general questions and use these templates for predictable results.

## 1. JSON Extraction
Use when you need structured key-value maps from raw input text.

```text
Extract all unique error codes, their line numbers, and the source filename from the following log text. Return only valid JSON matching this schema:
{
  "errors": [
    {
      "code": "string",
      "line": integer,
      "file": "string"
    }
  ]
}
Do not write explanations or wrap the code in anything but a valid JSON structure.
---
Input:
[PASTE LOGS HERE]
```

## 2. Docstring Generation
Use when documenting code classes, functions, or variables.

```text
Generate a clean docstring in Google style for the following Python function. Keep it brief and focused only on the arguments and return values.
---
Code:
[PASTE CODE HERE]
```

## 3. Localization
Translate key-value maps for frontend components.

```text
Translate the values in this JSON object into German while keeping the keys exactly the same.
---
JSON:
[PASTE JSON HERE]
```
