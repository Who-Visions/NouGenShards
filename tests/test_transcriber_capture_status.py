from nougen_shards import transcriber as transcriber_module
from nougen_shards.core import CaptureResult
from nougen_shards.transcriber import NouGenTranscriber


def _run(monkeypatch, tmp_path, result):
    tube = NouGenTranscriber(output_dir=str(tmp_path))
    monkeypatch.setattr(
        tube, "extract_or_download_audio",
        lambda source: ("/tmp/audio.wav", "A test video", {"platform": "youtube"}),
    )
    monkeypatch.setattr(tube.engine, "transcribe_file", lambda *a, **k: {
        "text": "A useful transcript.",
        "language": "en",
        "segments": [{"start": 0, "end": 2, "text": "A useful transcript."}],
        "duration": 2,
    })
    monkeypatch.setattr(transcriber_module.shards, "capture", lambda **kwargs: result)
    return tube.process_and_shard("https://example.test/video", auto_shard=True)


def test_duplicate_capture_is_stored_but_not_newly_captured(monkeypatch, tmp_path):
    result = _run(monkeypatch, tmp_path, CaptureResult(
        captured=False,
        reason="duplicate",
        durable=True,
        existing_shard_id=321,
        existing_db_index=3,
    ))

    assert result["captured"] is False
    assert result["stored"] is True
    assert result["sharded"] == "existing"


def test_capture_error_is_not_reported_as_existing(monkeypatch, tmp_path):
    result = _run(monkeypatch, tmp_path, CaptureResult(
        captured=False,
        reason="error",
        error="write failed",
    ))

    assert result["captured"] is False
    assert result["stored"] is False
    assert result["sharded"] == "failed"


def test_successful_capture_reports_stored(monkeypatch, tmp_path):
    result = _run(monkeypatch, tmp_path, CaptureResult(
        captured=True,
        reason="written",
        durable=True,
        shard_id=322,
        db_index=4,
    ))

    assert result["captured"] is True
    assert result["stored"] is True
    assert result["sharded"] == "captured"
