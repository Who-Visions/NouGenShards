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
    # NOTE (limitation): counts every record that core.capture reported as
    # "not newly created". core.capture returns False for a real dedup hit
    # AND for the IntegrityError repair path (hash already indexed elsewhere),
    # with no in-band signal to tell them apart — both mean the content is
    # already stored, so labelling them "duplicates" is accurate. A False
    # return is NOT distinguishable from a duplicate here without changing
    # core.capture's bool contract across the codebase; genuine write failures
    # raise instead of returning False, so they are not silently folded in.
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
                # False == "already stored" (dedup hit or stale-index repair).
                # See ImportResult.duplicates_skipped for why these cannot be
                # separated from a write failure without a broad core refactor.
                result.duplicates_skipped += 1
                
    return result
