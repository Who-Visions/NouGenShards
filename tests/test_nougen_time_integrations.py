from nougen_time import format_display_time, format_log_time


def test_handoff_status_uses_shared_eastern_utc_formatter():
    from nougen_shards.handoff import _user_time

    stamp = "2026-11-01T06:30:00.000000Z"
    assert _user_time(stamp) == format_display_time(stamp)
    assert "1:30 AM EST" in _user_time(stamp)
    assert "2026-11-01T06:30:00.000000Z" in _user_time(stamp)


def test_shard_recall_uses_shared_clock_and_format():
    from nougen_shards.core import format_shard_when

    stamp = "2026-03-08T07:00:00.000000Z"
    result = format_shard_when(stamp)
    assert result.startswith(format_log_time(stamp))
    assert "3:00:00 AM EDT" in result
