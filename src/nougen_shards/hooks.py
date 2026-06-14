"""
Reversed Hooks Lane for NouGenShards.
Intercepts and compacts message history into high-signal Semantic Anchors.
"""
import re
import json
from typing import List, Dict, Any

def extract_invariants(messages: List[Dict[str, Any]]) -> str:
    """
    Semantic Extraction: Pipes the message array through lightweight regex/AST 
    parsing to extract structural invariants (types, schema, explicit directives).
    """
    invariants = []
    
    # Patterns for high-signal architectural markers
    patterns = [
        r"(?:type|interface|class|def|function)\s+([a-zA-Z0-9_]+)",
        r"(?:endpoint|url|path|api)\s*[:=]\s*['\"]([^'\"]+)['\"]",
        r"(?:directive|mandate|rule)\s*[:=]\s*([^.\n]+)",
        r"database\s+schema\s*[:=]\s*([^.\n]+)"
    ]

    seen_markers = set()
    
    for msg in messages:
        content = msg.get("content", "")
        if not isinstance(content, str):
            continue
            
        for p in patterns:
            matches = re.findall(p, content, re.IGNORECASE)
            for m in matches:
                if m not in seen_markers:
                    invariants.append(m)
                    seen_markers.add(m)
                    
    # Limit to top invariants to keep under token budget
    summary = ", ".join(invariants[:20])
    return f"Structural Invariants: {summary}" if invariants else "No new invariants detected."

def inject_semantic_anchors(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Cache Alignment: Replaces raw chronological history with a compressed 
    'Semantic Anchor' block containing strict graph delta pointers.
    """
    if len(messages) <= 3:
        return messages # Don't compact short sessions
        
    # 1. Preserve System Prompt (The Anchor)
    system_msgs = [m for m in messages if m.get("role") == "system"]
    
    # 2. Extract Invariants from the entire buffer
    anchors_text = extract_invariants(messages)
    
    # 3. Create the compact anchor message
    # This replaces the middle 'tail' of the conversation
    compact_anchor = {
        "role": "user",
        "content": f"[REVERSED_HOOK] Semantic Anchor (History Virtualized): {anchors_text}"
    }
    
    # 4. Keep the most recent user request (The Execution Shard)
    recent_msgs = [m for m in messages if m.get("role") != "system"][-2:]
    
    return system_msgs + [compact_anchor] + recent_msgs

def pre_tool_use_hook(message_payload: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Main entry point for Play 2: Pointer Compaction.
    Intercepts the history buffer before serialization.
    """
    return inject_semantic_anchors(message_payload)
