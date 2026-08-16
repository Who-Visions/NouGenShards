#!/usr/bin/env python3
import sys
import json
import urllib.request

SYSTEM_PROMPT = """
You are a task-routing classifier for an agentic coding environment. 
Classify the given task into one of four routing categories:
1. LOCAL_FAST: Simple text formatting, boilerplate, comments, docstrings, raw log output generation, git commands, shell commands.
2. LOCAL_STRUCTURED: JSON extraction, data classification, list cleanup, translation, function/tool mapping.
3. LOCAL_SCOPED_CODE: Single-file edits, focused explanations, regex generation, simple test case writing, micro-refactors.
4. CLOUD_COMPLEX: Multi-file reasoning, application migrations, system architectures, deep debugging across modules, security audits, or any task explicitly requiring web searches or remote context.

Your response MUST be valid JSON with the format:
{
  "category": "LOCAL_FAST | LOCAL_STRUCTURED | LOCAL_SCOPED_CODE | CLOUD_COMPLEX",
  "confidence": "HIGH | MEDIUM | LOW",
  "reason": "Brief explanation of why it fits this category."
}
"""

def route_task(task_description, model="gemma4:e2b"):
    url = "http://localhost:11434/api/chat"
    
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Task: {task_description}"}
        ],
        "options": {
            "temperature": 0.0
        },
        "stream": False
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode('utf-8'))
            content = res.get("message", {}).get("content", "").strip()
            # Clean up potential markdown formatting block
            if content.startswith("```"):
                lines = content.splitlines()
                if lines[0].startswith("```json") or lines[0] == "```":
                    content = "\n".join(lines[1:-1])
            return json.loads(content)
    except Exception as e:
        return {
            "error": f"Failed to connect or parse routing: {e}",
            "category": "CLOUD_COMPLEX",
            "confidence": "LOW",
            "reason": "Fallback due to local Ollama error."
        }

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: model_router.py '<task_description>'")
        sys.exit(1)
        
    task = sys.argv[1]
    result = route_task(task)
    print(json.dumps(result, indent=2))
