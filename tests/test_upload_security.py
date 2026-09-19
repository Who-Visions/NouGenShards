from tools.ai_video_transcriber.backend.pipeline import is_heif_container


def test_rejects_heif_brand_even_when_renamed():
    assert is_heif_container(b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00")
    assert is_heif_container(b"\x00\x00\x00\x18ftypmif1\x00\x00\x00\x00")


def test_allows_non_heif_iso_bmff_and_short_headers():
    assert not is_heif_container(b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00")
    assert not is_heif_container(b"ftyp")
