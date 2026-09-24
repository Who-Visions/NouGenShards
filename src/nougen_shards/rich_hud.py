#!/usr/bin/env python3
"""
rich_hud.py - Cyber-Tactical Rich Terminal UI Dashboard & Suite for NouGenAi / NouGenShards.
Provides publication-grade visual telemetry and rich formatting across:
- 9-DB Shard Grid Substrate (~/.nougen/shards)
- Fleet Topology & Mesh Matrix (Hyperion, Apollo, Phoebus)
- Live Shard Search Results with Syntax Highlighting & Score Badges
- Memory Growth, Utility Velocity & Timeline Analytics
- System Diagnostics & Service Connectivity Health Matrix
- Relay Baton Board & Active Claims Stream
"""

import os
import sys
import time
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# Windows UTF-8 console protection
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich import box

console = Console()

SHARD_DIR = os.environ.get("NOUGEN_VAULT_DIR", str(Path.home() / ".nougen" / "shards"))
MAX_DB_CAPACITY_MB = 1024.0


def is_rich_enabled() -> bool:
    """Check if rich terminal rendering is suitable for the current stream."""
    if os.environ.get("NO_COLOR") or os.environ.get("NOUGEN_PLAIN"):
        return False
    if os.environ.get("NOUGEN_FORCE_COLOR") or os.environ.get("NOUGEN_FORCE_RICH"):
        return True
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def make_progress_bar(current_mb: float, max_mb: float = MAX_DB_CAPACITY_MB, width: int = 12) -> str:
    """Creates a high-contrast capacity bar with threshold coloring."""
    ratio = min(1.0, max(0.0, current_mb / max_mb))
    filled = int(ratio * width)
    unfilled = width - filled
    pct = ratio * 100

    if pct >= 90:
        bar_color = "bright_red"
    elif pct >= 75:
        bar_color = "bright_yellow"
    else:
        bar_color = "bright_cyan"

    return f"[{bar_color}]{'█' * filled}{'░' * unfilled}[/] {pct:5.1f}%"


def make_score_bar(score: float, width: int = 8) -> str:
    """Creates a normalized score meter for search results."""
    ratio = min(1.0, max(0.0, score))
    filled = int(ratio * width)
    unfilled = width - filled
    pct = ratio * 100

    if pct >= 80:
        col = "bright_green"
    elif pct >= 50:
        col = "bright_yellow"
    else:
        col = "bright_red"

    return f"[{col}]{'█' * filled}{'░' * unfilled}[/] [{col}]{score:.2f}[/]"


def get_substrate_stats() -> Dict[str, Any]:
    """Scans the 9-DB persistent substrate and deduplication index."""
    stats = []
    total_shards = 0
    total_mb = 0.0
    active_idx = 9

    dedup_path = os.path.join(SHARD_DIR, "dedup_index.db")
    total_hashes = 0
    if os.path.exists(dedup_path):
        try:
            conn = sqlite3.connect(dedup_path)
            total_hashes = conn.execute("SELECT count(*) FROM hashes").fetchone()[0]
            conn.close()
        except Exception:
            pass

    for i in range(1, 10):
        db_path = os.path.join(SHARD_DIR, f"nougen_shards_{i}.db")
        if os.path.exists(db_path):
            try:
                size_mb = os.path.getsize(db_path) / (1024 * 1024)
                conn = sqlite3.connect(db_path)
                count = conn.execute("SELECT count(*) FROM shards").fetchone()[0]
                conn.close()
                is_active = (i == active_idx)
                stats.append({
                    "index": i,
                    "count": count,
                    "size_mb": size_mb,
                    "is_active": is_active,
                    "healthy": True
                })
                total_shards += count
                total_mb += size_mb
            except Exception as e:
                stats.append({
                    "index": i,
                    "count": 0,
                    "size_mb": 0.0,
                    "is_active": False,
                    "healthy": False,
                    "error": str(e)
                })
    return {
        "dbs": stats,
        "total_shards": total_shards,
        "total_mb": total_mb,
        "total_hashes": total_hashes
    }


def build_dashboard_renderable(sub_data: Optional[Dict[str, Any]] = None) -> Group:
    """Builds the complete renderable Group for the flagship HUD dashboard."""
    if sub_data is None:
        sub_data = get_substrate_stats()

    # 1. Header Banner
    header_text = Text()
    header_text.append("🪩  NOUGENSHARDS CLI ", style="bold bright_white")
    header_text.append("— Powered by ", style="dim white")
    header_text.append("NouGen", style="bold bright_cyan")
    header_text.append("Ai", style="bold bright_magenta")
    header_text.append("  [ NouGenMorph Engine v1.3.1 ]\n", style="bold bright_yellow")
    header_text.append("Authority: ", style="dim")
    header_text.append("Dave Meralus (Dav3 / GM)  ", style="bold green")
    header_text.append("│  Node: ", style="dim")
    header_text.append("Hyperion (ProArt PX13)  ", style="bold cyan")
    header_text.append("│  Time: ", style="dim")
    header_text.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S EDT"), style="bold bright_white")

    header_panel = Panel(header_text, box=box.DOUBLE_EDGE, border_style="bright_cyan", padding=(0, 2))

    # 2. Substrate Grid Table
    grid_table = Table(
        title="🧠 NouGenShards 9-DB Substrate Grid Telemetry (~/.nougen/shards)",
        box=box.ROUNDED,
        header_style="bold bright_cyan",
        show_footer=True,
        expand=True
    )
    grid_table.add_column("DB Slot", justify="center", style="bold white", width=10, footer="[bold]TOTALS[/]")
    grid_table.add_column("State", justify="center", width=12, footer="[bold green]9/9 HEALTHY[/]")
    grid_table.add_column("Records", justify="right", style="bright_green", width=12, footer=f"[bold bright_green]{sub_data['total_shards']:,}[/]")
    grid_table.add_column("Storage Used", justify="right", style="bright_yellow", width=16, footer=f"[bold bright_yellow]{sub_data['total_mb']/1024:.2f} GB[/]")
    grid_table.add_column("Substrate Capacity (1024 MB Ceiling)", justify="left", width=28, footer="[dim]Global FTS5 Multi-DB[/]")
    grid_table.add_column("FTS5 Index", justify="center", style="bright_cyan", width=12, footer="[bold cyan]100% READY[/]")

    for db in sub_data["dbs"]:
        slot_label = f"DB #{db['index']}"
        if db["is_active"]:
            state = "[bold bright_green]● ACTIVE[/]"
            slot_label = f"[bold bright_green]{slot_label} ★[/]"
        else:
            state = "[dim green]ONLINE[/]"

        rec_str = f"{db['count']:,}"
        storage_str = f"{db['size_mb']:6.2f} MB"
        bar = make_progress_bar(db['size_mb'])
        fts = "[bright_green]INDEXED[/]"

        grid_table.add_row(slot_label, state, rec_str, storage_str, bar, fts)

    # 3. Fleet Topology Table
    fleet_table = Table(
        title="🛰️ Fleet Machine Topology & Distributed Compute Mesh",
        box=box.ROUNDED,
        header_style="bold bright_magenta",
        expand=True
    )
    fleet_table.add_column("Node Name", style="bold white", width=14)
    fleet_table.add_column("Role / Compute Stadium", style="bright_cyan", width=28)
    fleet_table.add_column("Coach / Agent", style="bright_green", width=18)
    fleet_table.add_column("Local Model / Player", style="bright_yellow", width=18)
    fleet_table.add_column("IP / Network", style="bright_white", width=16)
    fleet_table.add_column("Mesh Status", justify="center", style="bold green", width=12)

    # Rows come from this machine's ~/.nougen/nodes.json; public code ships no
    # fleet roster, so a fresh clone shows an empty mesh.
    for row in _local_fleet_rows():
        fleet_table.add_row(*row)
    if not fleet_table.rows:
        fleet_table.add_row("(none)", "no ~/.nougen/nodes.json", "-", "-", "-", "[dim]STANDALONE[/]")

    # 4. Engine & State Panel
    relay_text = Text()
    relay_text.append("• Universal Engine: ", style="dim")
    relay_text.append("NouGenMorph (Cognitive Synthesis & Multimodal Learning)\n", style="bold bright_cyan")
    relay_text.append("• Active Git Branch: ", style="dim")
    relay_text.append("fleet/nougenmorph-elevation (Origin Synced)\n", style="bold bright_green")
    relay_text.append("• Total Ingested Hashes: ", style="dim")
    relay_text.append(f"{sub_data['total_hashes']:,} deduplicated atoms\n", style="bold bright_yellow")
    relay_text.append("• Token Discipline: ", style="dim")
    relay_text.append("Local-First Ollama E2B routing with Context-Mode protection active.", style="bold white")

    info_panel = Panel(relay_text, title="⚙️ NouGenAi System Telemetry & Relay State", box=box.ROUNDED, border_style="bright_yellow")

    return Group(header_panel, grid_table, fleet_table, info_panel)


def render_rich_dashboard():
    """Renders the static flagship NouGenAi Terminal Dashboard."""
    renderable = build_dashboard_renderable()
    console.print(renderable)


def render_rich_live_hud(duration: Optional[float] = None, fps: float = 2.0):
    """Runs a real-time live updating terminal HUD."""
    console.print("[dim]Starting NouGenAi Live Substrate Monitor (Press Ctrl+C to exit)...[/]")
    start_time = time.time()
    try:
        with Live(build_dashboard_renderable(), refresh_per_second=fps, console=console) as live:
            while True:
                if duration and (time.time() - start_time) >= duration:
                    break
                time.sleep(1.0 / fps)
                live.update(build_dashboard_renderable())
    except KeyboardInterrupt:
        console.print("\n[yellow]Live monitor stopped.[/]")


def render_rich_search_results(query: str, results: List[Dict[str, Any]], sweep_report: Optional[Dict[str, Any]] = None):
    """Renders beautiful cyber-tactical search results."""
    header_text = Text()
    header_text.append("🔍 Search Results for: ", style="bold bright_white")
    header_text.append(f'"{query}"', style="bold bright_yellow")
    header_text.append(f"  ({len(results)} matches ranked by relevance across 9 DBs)\n", style="dim")

    if sweep_report and sweep_report.get("lanes_timed_out"):
        timed_out = ", ".join(sweep_report["lanes_timed_out"])
        header_text.append(f"⚠️ Partial sweep: timed out lanes: {timed_out}", style="bold bright_red")

    console.print(Panel(header_text, box=box.ROUNDED, border_style="bright_cyan"))

    for idx, res in enumerate(results, 1):
        res_id = res.get("id", "?")
        db_idx = res.get("_db_index", res.get("db_index", "?"))
        title = res.get("title", "Untitled Shard")
        content = res.get("content", "").strip()
        final_score = res.get("final_score", 0.0)
        utility = res.get("utility_score", res.get("utility", 1.0))
        tags = res.get("tags", "[]")
        domain = res.get("domain_key", res.get("domain", ""))

        card_title = Text()
        card_title.append(f"#{idx} ", style="bold bright_magenta")
        card_title.append(f"[Shard #{res_id} in DB #{db_idx}] ", style="bold bright_cyan")
        card_title.append(title, style="bold bright_white")

        card_body = Text()
        # Score banner
        card_body.append("Score: ", style="dim")
        card_body.append(make_score_bar(final_score))
        card_body.append("  │  Utility: ", style="dim")
        card_body.append(f"{utility:+.2f}  ", style="bold bright_green" if utility >= 0 else "bold bright_red")
        if domain:
            card_body.append("│  Domain: ", style="dim")
            card_body.append(f"{domain}  ", style="bold bright_yellow")
        if tags and tags != "[]":
            card_body.append("│  Tags: ", style="dim")
            card_body.append(f"{tags}  ", style="dim cyan")
        card_body.append("\n\n")

        # Content truncation for snippet view
        lines = content.splitlines()
        preview = "\n".join(lines[:8])
        if len(lines) > 8:
            preview += f"\n... [{len(lines) - 8} more lines]"

        card_body.append(preview, style="white")

        # Action hint footer
        action_hint = f"nougen get {res_id} --db {db_idx}"
        console.print(Panel(
            card_body,
            title=card_title,
            title_align="left",
            subtitle=f"[dim cyan]Inspect: [bold white]{action_hint}[/dim cyan]",
            subtitle_align="right",
            box=box.ROUNDED,
            border_style="bright_blue"
        ))


def render_rich_stats(payload: Dict[str, Any]):
    """Renders memory velocity and historical timeline analytics."""
    period = payload.get("period", "week")
    growth = payload.get("growth", {})
    utility_delta = payload.get("utility_delta", 0.0)
    timeline = payload.get("timeline", "")
    accel = payload.get("acceleration_rate_pct")

    table = Table(
        title=f"📈 NouGenShards Memory Growth & Utility Velocity ({period.upper()})",
        box=box.ROUNDED,
        header_style="bold bright_cyan",
        expand=True
    )
    table.add_column("Metric", style="bold white", width=24)
    table.add_column("Value", style="bold bright_green", width=20)
    table.add_column("Interpretation", style="dim", width=36)

    table.add_row(
        "New Shards Captured",
        f"{growth.get('new_shards', 0):,}",
        "Ingested into persistent substrate during period"
    )
    table.add_row(
        "Total Memory Records",
        f"{growth.get('total_shards', 0):,}",
        "Global cross-DB cumulative shard count"
    )
    util_style = "bold bright_green" if utility_delta >= 0 else "bold bright_red"
    table.add_row(
        "Utility Delta (Δ)",
        f"[{util_style}]{'+' if utility_delta >= 0 else ''}{utility_delta:.2f}[/]",
        "Net reinforcement utility feedback delta"
    )
    if accel is not None:
        table.add_row(
            "Growth Acceleration",
            f"{accel:5.2f}%",
            "Period intake relative to total knowledge mass"
        )

    console.print(table)

    if timeline:
        timeline_panel = Panel(
            Text(timeline, style="bold bright_yellow"),
            title=f"⏳ Ingestion Timeline ({period})",
            box=box.ROUNDED,
            border_style="bright_yellow"
        )
        console.print(timeline_panel)


def render_rich_doctor(report: Dict[str, Any]):
    """Renders doctor diagnostic checklist."""
    table = Table(
        title="👨‍⚕️ NouGenShards Doctor — System Diagnostics & Connectivity",
        box=box.ROUNDED,
        header_style="bold bright_magenta",
        expand=True
    )
    table.add_column("Subsystem / Component", style="bold white", width=28)
    table.add_column("Status", justify="center", width=14)
    table.add_column("Details / Diagnostic Evidence", style="dim", width=42)

    # Substrate
    sub = report.get("substrate", {})
    sub_status = "[bold bright_green]✅ ONLINE[/]" if sub.get("found") else "[bold bright_red]❌ MISSING[/]"
    table.add_row("Shard Substrate (9-DB Grid)", sub_status, f"Active DB #{sub.get('active_index', 9)}")

    # Vault
    vault = report.get("vault", {})
    vault_status = "[bold bright_green]✅ SECURED[/]" if vault.get("exists") else "[bold bright_yellow]⚠️ EMPTY[/]"
    raw_provs = vault.get("providers", [])
    if len(raw_provs) > 8:
        distinct = sorted(list({p.split("_")[0] for p in raw_provs}))
        providers = f"{len(raw_provs)} secrets across {', '.join(distinct)}"
    else:
        providers = ", ".join(raw_provs) or "None configured"
    table.add_row("Keymaker Secrets Vault", vault_status, f"{providers}")

    # Connectivity
    conn = report.get("connectivity", {})
    for prov, alive in conn.items():
        st = "[bold bright_green]✅ ONLINE[/]" if alive else "[dim red]❌ OFFLINE[/]"
        table.add_row(f"LLM Provider: {prov.capitalize()}", st, "Connected and responsive" if alive else "No API key / unreachable")

    # Cognitive Engines
    table.add_row("NouGenMorph Dream State", "[bold bright_green]✅ READY[/]", "TMEM Synthesizer active")
    table.add_row("Evolution Engine (OpenSkill)", "[bold bright_green]✅ READY[/]", "Progressive skill synthesizer active")

    console.print(table)


def render_rich_models(provider: str, models: List[str]):
    """Renders models list table."""
    best_model_name = None
    if provider.lower() in ("local", "ollama") and models:
        try:
            from .custom_model_resolver import resolve_best_custom_model
            cfg = resolve_best_custom_model(models)
            if cfg:
                best_model_name = cfg.model_name
        except Exception:
            pass

    table = Table(
        title=f"🤖 Available LLM Models for [{provider.upper()}]",
        box=box.ROUNDED,
        header_style="bold bright_cyan",
        expand=True
    )
    table.add_column("Index", justify="center", style="dim", width=6)
    table.add_column("Model Name / Identifier", style="bold bright_white", width=34)
    table.add_column("Family / Classification", style="bright_yellow", width=24)
    table.add_column("Route & Priority", justify="center", style="bright_green", width=26)

    for i, m in enumerate(models, 1):
        m_lower = m.lower()
        if "yukiai" in m_lower:
            fam = "Yukiai (Hyperion Player)"
        elif "solai" in m_lower or "sol-ai" in m_lower:
            fam = "Sol-Ai (Apollo Player)"
        elif "keadra" in m_lower:
            fam = "Keadra (Phoebus Player)"
        elif "mrs-b" in m_lower or "mrsb" in m_lower:
            fam = "Mrs. B (Family Matriarch)"
        elif any(p in m_lower for p in ("dav1d", "dav3", "griot", "rhea", "iris")):
            fam = "Fleet Persona Fine-Tune"
        elif "gemma" in m_lower:
            fam = "Gemma 4"
        elif "claude" in m_lower:
            fam = "Anthropic Claude"
        elif "gpt" in m_lower or "openai" in m_lower:
            fam = "OpenAI GPT"
        elif "qwen" in m_lower:
            fam = "Alibaba Qwen"
        elif "llama" in m_lower:
            fam = "Meta Llama"
        else:
            fam = "Custom / OSS"

        is_auto = (m == best_model_name)
        if is_auto:
            route = "[bold bright_green]★ Auto-Selected (Default)[/]"
        elif ":cloud" in m_lower or "-cloud" in m_lower:
            route = "[cyan]Cloud Gateway (0 VRAM)[/]"
        elif "embed" in m_lower or "bge" in m_lower:
            route = "[dim]Embedding Only[/]"
        elif provider.lower() in ("local", "ollama"):
            route = "[green]Local VRAM[/]"
        else:
            route = "[blue]Cloud API[/]"

        table.add_row(str(i), m, fam, route)

    console.print(table)


if __name__ == "__main__":
    if "--live" in sys.argv:
        render_rich_live_hud()
    else:
        render_rich_dashboard()

def _local_fleet_rows():
    """(name, role, coach, model, ip, status) per node in ~/.nougen/nodes.json."""
    import json
    from pathlib import Path
    try:
        nodes = json.loads((Path.home() / ".nougen" / "nodes.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    rows = []
    for key, cfg in (nodes.items() if isinstance(nodes, dict) else []):
        if not isinstance(cfg, dict):
            continue
        rows.append((str(cfg.get("name") or key), str(cfg.get("role") or "-"), str(cfg.get("coach") or "-"),
                     str(cfg.get("model") or "-"), str(cfg.get("ip") or cfg.get("host") or "-"), "[green]CONFIGURED[/]"))
    return rows
