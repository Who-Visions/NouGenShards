import json
from pathlib import Path
from nougen_shards.taskflow_triage import (
    TaskFlowTriageEngine,
    UrgencyLevel,
    TriageCategory,
)


def test_classify_p0_critical():
    engine = TaskFlowTriageEngine()
    item = engine.classify_payload(
        "20260908T145733Z__phoebus__hurricane_kick_red_card.json",
        {"sender": "phoebus", "text": "RED CARD: socket failure detected on node"},
    )
    assert item.urgency == UrgencyLevel.P0_CRITICAL
    assert item.category == TriageCategory.SECURITY_ALERT
    assert item.action_required == "IMMEDIATE_INTERVENTION"


def test_classify_p2_waiting():
    engine = TaskFlowTriageEngine()
    item = engine.classify_payload(
        "pr_check_wait.json",
        {"sender": "ci_bot", "text": "Waiting on PR checks to complete in background"},
    )
    assert item.urgency == UrgencyLevel.P2_WAITING
    assert item.category == TriageCategory.WAITING_DEPENDENCY
    assert item.action_required == "SCHEDULE_IDLE_TIMER"


def test_classify_p3_telemetry():
    engine = TaskFlowTriageEngine()
    item = engine.classify_payload(
        "ping_1788997352762.json",
        {"sender": "phoebus", "type": "ping", "text": "Keepalive heartbeat"},
    )
    assert item.urgency == UrgencyLevel.P3_FYI
    assert item.category == TriageCategory.HEARTBEAT_TELEMETRY
    assert item.action_required == "DEDUP_AND_ARCHIVE"


def test_classify_p1_actionable():
    engine = TaskFlowTriageEngine()
    item = engine.classify_payload(
        "20260910T215425Z__chatgpt-app__g-whoentertains.json",
        {"sender": "chatgpt-app", "text": "Extract Arnheim visual-perception grammar into NouGen"},
    )
    assert item.urgency == UrgencyLevel.P1_ACTIONABLE
    assert item.category == TriageCategory.RELAY_WORK
    assert item.action_required == "DISPATCH_TASKFLOW_LANE"


def test_triage_directory_and_report(tmp_path: Path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()

    (inbox / "alert_red_card.json").write_text(
        json.dumps({"sender": "blade", "text": "Fatal emergency error"})
    )
    (inbox / "task_relay.json").write_text(
        json.dumps({"sender": "codex", "text": "Open relay baton #42"})
    )
    (inbox / "ping_123.json").write_text(
        json.dumps({"sender": "phoebus", "type": "ping", "text": "ping"})
    )

    engine = TaskFlowTriageEngine(inbox_dir=inbox)
    items = engine.triage_directory()
    assert len(items) == 3

    report = engine.generate_report(items)
    assert "**Total Ingested**: 3 items" in report
    assert "**P0 Critical**: 1" in report
    assert "**P1 Actionable**: 1" in report
    assert "**P3 Archived / FYI**: 1" in report
