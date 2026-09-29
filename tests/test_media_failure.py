from unittest.mock import patch

import pytest

from nougen_shards.media_failure import MediaIngestFailure, classify_download_error, public_source
from nougen_shards.transcriber import NouGenTranscriber


def test_failed_url_has_ordered_safe_attempts(tmp_path):
    class BrokenYDL:
        def __init__(self, options):
            assert options["ignoreconfig"] is True

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, source, download):
            raise RuntimeError("login required cookie secret-token=private")

    with patch("nougen_shards.transcriber.yt_dlp.YoutubeDL", BrokenYDL):
        with pytest.raises(MediaIngestFailure) as caught:
            NouGenTranscriber(output_dir=str(tmp_path)).extract_or_download_audio(
                "https://www.instagram.com/reel/DblWuNUKu4C/?token=private"
            )
    failure = caught.value.to_dict()
    assert failure["code"] == "AUTH_REQUIRED"
    assert failure["source"] == "https://www.instagram.com/reel/DblWuNUKu4C/"
    assert [attempt["adapter"] for attempt in failure["attempts"]] == [
        "yt-dlp-public", "yt-dlp-authorized", "gallery-dl", "browser-authorized"
    ]
    assert [attempt["status"] for attempt in failure["attempts"]] == [
        "failed", "skipped", "skipped", "skipped"
    ]
    assert "private" not in str(failure)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("login required", "AUTH_REQUIRED"),
        ("HTTP Error 429: rate limit", "RATE_LIMITED"),
        ("Instagram challenge_required: captcha", "BOT_CHALLENGE"),
        ("HTTP Error 404: media not found", "MEDIA_NOT_FOUND"),
        ("ffmpeg: Invalid data found when processing input", "CORRUPT_MEDIA"),
        ("Unsupported URL", "UNSUPPORTED"),
        ("Connection reset by peer", "NETWORK"),
        ("Postprocessing: ffmpeg failed", "FFMPEG_FAILURE"),
        ("Invalid data found when processing input", "CORRUPT_MEDIA"),
        ("Unexpected extractor assertion", "DOWNLOADER_BUG"),
    ],
)
def test_download_error_classification_is_stable(message, expected):
    assert classify_download_error(RuntimeError(message)) == expected


def test_public_source_removes_userinfo_query_and_fragment():
    assert public_source(
        "https://private:password@www.instagram.com:8443/reel/abc/?token=secret#fragment"
    ) == "https://www.instagram.com:8443/reel/abc/"


def test_missing_local_media_returns_safe_structured_failure(tmp_path):
    missing = tmp_path / "private-name.mp4"
    with pytest.raises(MediaIngestFailure) as caught:
        NouGenTranscriber(output_dir=str(tmp_path / "out")).extract_or_download_audio(str(missing))
    payload = caught.value.to_dict()
    assert payload["code"] == "MEDIA_NOT_FOUND"
    assert payload["source"] == "local-media"
    assert str(missing) not in str(payload)


def test_successful_transcript_and_shard_drop_source_credentials_and_query(tmp_path):
    url = "https://user:pass@instagram.com/reel/abc/?token=secret#frag"
    captured = {}
    tube = NouGenTranscriber(output_dir=str(tmp_path), whisper_model="tiny")
    tube.extract_or_download_audio = lambda source: (
        "audio.m4a", "Reel", {"source": public_source(source), "platform": "Instagram"}
    )
    tube.engine.transcribe_file = lambda path, language=None: {
        "text": "spoken words", "language": "en", "duration": 1.0,
        "segments": [{"start": 0, "end": 1, "text": "spoken words"}],
    }

    def capture(**kwargs):
        captured.update(kwargs)
        return {"durable": True}

    with patch("nougen_shards.transcriber.shards.capture", side_effect=capture):
        result = tube.process_and_shard(url, auto_shard=True)

    expected_source = "https://instagram.com/reel/abc/"
    assert result["source"] == expected_source
    assert captured["source_uri"] == expected_source
    transcript = (tmp_path / "Reel.md").read_text()
    assert expected_source in transcript
    for private_value in ("user", "pass", "secret", "token=", "#frag"):
        assert private_value not in transcript
