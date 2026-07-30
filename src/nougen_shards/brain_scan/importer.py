from dataclasses import dataclass
from typing import Callable, Optional
from .scanner import scan_environment
from .parsers import iter_records
from .redaction import redact_content
from .registry import SQLITE_EXTS
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
               source_filter: Optional[str] = None, redact: bool = True, confirm: bool = False,
               progress: Optional[Callable[[str, int, int], None]] = None) -> ImportResult:
    """Executes the Brain Import pipeline (Dry-Run by default).

    `progress(source_path, records_seen, shards_created)` is invoked
    periodically during a confirmed run so callers can report on a long
    ingest; a database can contribute six figures of records on its own.
    """

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
            # Databases are counted for real: the per-file heuristics below are
            # off by orders of magnitude for a table-backed source, which made
            # the estimate useless for deciding whether to import.
            if c.path.suffix.lower() in SQLITE_EXTS:
                from .sqlite_sources import estimate_records  # pylint: disable=import-outside-toplevel
                result.records_parsed += estimate_records(c.path)
            elif c.path.suffix == ".jsonl":
                result.records_parsed += 10 # heuristic
            else:
                result.records_parsed += 1
        return result

    # Real Execution
    for c in candidates:
        for rec in iter_records(c.path, c.tool, c.is_project_context):
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

            # density_score is passed explicitly so capture() does not fall into
            # its per-item LLM scoring path. Left to default, every record costs
            # an Ollama probe plus an OpenRouter probe; with no provider
            # reachable that is ~85s of connection timeout per shard, which puts
            # a large import beyond any usable runtime.
            success = shards.capture(
                event_type="IMPORT",
                title=f"[{rec.source_tool.upper()}] {title_text}",
                content=content,
                tags=tags,
                density_score=shards.compression_density(content)
            )
            
            if success:
                result.shards_created += 1
            else:
                # False == "already stored" (dedup hit or stale-index repair).
                # See ImportResult.duplicates_skipped for why these cannot be
                # separated from a write failure without a broad core refactor.
                result.duplicates_skipped += 1

            if progress and result.records_parsed % 500 == 0:
                progress(str(c.path), result.records_parsed, result.shards_created)

        if progress:
            progress(str(c.path), result.records_parsed, result.shards_created)

    return result
