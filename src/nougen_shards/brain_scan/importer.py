from dataclasses import dataclass
from typing import Optional
from .scanner import scan_environment
from .parsers import parse_universal
from .redaction import redact_content
from .. import core as shards

@dataclass
class ImportResult:
    files_scanned: int
    records_parsed: int
    shards_created: int
    duplicates_skipped: int
    secrets_redacted: int

def run_import(project_path: Optional[str] = None, include_unknown: bool = False, 
               source_filter: Optional[str] = None, redact: bool = True, confirm: bool = False) -> ImportResult:
    """Executes the Brain Import pipeline (Dry-Run by default)."""
    
    candidates = scan_environment(project_path, include_unknown)
    if source_filter:
        candidates = [c for c in candidates if c.tool.lower() == source_filter.lower()]
        
    result = ImportResult(
        files_scanned=len(candidates),
        records_parsed=0,
        shards_created=0,
        duplicates_skipped=0,
        secrets_redacted=0
    )
    
    if not confirm:
        # Fast estimation for dry run
        for c in candidates:
            # Estimate 1 record per file on average if small, maybe more if jsonl
            if c.path.suffix == ".jsonl":
                result.records_parsed += 10 # heuristic
            else:
                result.records_parsed += 1
        return result

    # Real Execution
    for c in candidates:
        records = parse_universal(c.path, c.tool, c.is_project_context)
        for rec in records:
            result.records_parsed += 1
            
            content = rec.content
            title_text = rec.title
            if redact:
                redacted = redact_content(content)
                redacted_title = redact_content(title_text)
                if redacted != content or redacted_title != title_text:
                    result.secrets_redacted += 1
                    content = redacted
                    title_text = redacted_title

            tags = ["brain_scan", f"tool:{rec.source_tool}", f"kind:{rec.source_kind}"]

            success = shards.capture(
                event_type="IMPORT",
                title=f"[{rec.source_tool.upper()}] {title_text}",
                content=content,
                tags=tags
            )
            
            if success:
                result.shards_created += 1
            else:
                result.duplicates_skipped += 1
                
    return result
