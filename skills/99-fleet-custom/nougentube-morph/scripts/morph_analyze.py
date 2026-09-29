import argparse
import json
import re
import sys
from typing import Dict, Any, List

def parse_args():
    parser = argparse.ArgumentParser(description="NougenMorph: Analyze NougenTube digests for skills and patterns.")
    parser.add_argument("--transcript", required=True, help="Path to transcript file")
    parser.add_argument("--info", required=True, help="Path to info.json file")
    return parser.parse_args()

def load_info(path: str) -> Dict[str, Any]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading info file {path}: {e}", file=sys.stderr)
        return {}

def load_transcript(path: str) -> str:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error loading transcript file {path}: {e}", file=sys.stderr)
        return ""

def extract_chapters_from_description(description: str) -> List[Dict[str, str]]:
    chapters = []
    if not description:
        return chapters
    
    # Match standard YouTube chapter format: 00:00 Chapter Title or 0:00 Chapter Title
    pattern = re.compile(r'(?:^|\n)\s*(\d{1,2}:\d{2}(?::\d{2})?)\s+-\s*(.+?)(?=\n|$)', re.IGNORECASE)
    # Also support without hyphen
    pattern2 = re.compile(r'(?:^|\n)\s*(\d{1,2}:\d{2}(?::\d{2})?)\s+(?!-)(.+?)(?=\n|$)', re.IGNORECASE)
    
    for m in pattern.finditer(description):
        chapters.append({"time": m.group(1), "title": m.group(2).strip()})
        
    if not chapters:
        for m in pattern2.finditer(description):
            chapters.append({"time": m.group(1), "title": m.group(2).strip()})
            
    return chapters

def mock_analysis(info: Dict[str, Any], transcript: str) -> Dict[str, Any]:
    # In a real tool, this would call an LLM to parse the transcript.
    # Here we scaffold the output structure that the agent will fill.
    return {
        "title": info.get("title", "Unknown Title"),
        "channel": info.get("uploader", info.get("channel", "Unknown Channel")),
        "duration": info.get("duration_string", info.get("duration", "Unknown")),
        "chapters": extract_chapters_from_description(info.get("description", "")),
        "stack_patterns": [
            {"name": "Example Stack", "packages": ["pkg1", "pkg2"], "description": "Example description"}
        ],
        "workflow_patterns": [
            {"name": "Example Workflow", "steps": ["step 1", "step 2"], "description": "Example description"}
        ],
        "creative_techniques": [
            {"name": "Example Technique", "description": "Example description", "code_hint": "// code"}
        ],
        "skill_candidates": [
            {"name": "example-skill", "category": "00-example", "description": "Example", "priority": "medium"}
        ]
    }

def print_summary(analysis: Dict[str, Any]):
    print("="*50)
    print(f"🎬 NougenMorph Analysis: {analysis['title']}")
    print(f"📺 Channel: {analysis['channel']} | ⏱️ Duration: {analysis['duration']}")
    print("="*50)
    
    chapters = analysis['chapters']
    if chapters:
        print("\n📑 Chapters:")
        for ch in chapters:
            print(f"  [{ch['time']}] {ch['title']}")
            
    print("\n🛠️  Stack Patterns:")
    for sp in analysis['stack_patterns']:
        print(f"  - {sp['name']}: {', '.join(sp['packages'])}")
        
    print("\n🔄 Workflow Patterns:")
    for wp in analysis['workflow_patterns']:
        print(f"  - {wp['name']}: {' → '.join(wp['steps'])}")
        
    print("\n💡 Skill Candidates:")
    for sc in analysis['skill_candidates']:
        print(f"  - [{sc['category']}] {sc['name']} ({sc['priority']})")
    
    print("\n" + "="*50)

def main():
    args = parse_args()
    info = load_info(args.info)
    transcript = load_transcript(args.transcript)
    
    analysis = mock_analysis(info, transcript)
    
    print_summary(analysis)

if __name__ == "__main__":
    main()
