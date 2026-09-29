from unittest.mock import patch

import pytest

from nougen_shards.media_failure import MediaIngestFailure
from nougen_shards.transcriber import NouGenTranscriber


def test_failed_url_has_ordered_safe_attempts(tmp_path):
    class BrokenYDL:
        def __init__(self, options):
            pass

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
    assert "private" not in str(failure)
