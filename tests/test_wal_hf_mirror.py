import json
import threading

from nougen_shards.wal_hf_mirror import DEFAULT_REPO, HFDatasetMirror


class FakeScheduler:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.lock = threading.Lock()


def test_mirror_targets_private_wal_dataset(tmp_path):
    m = HFDatasetMirror(str(tmp_path), scheduler_cls=FakeScheduler)
    assert m.scheduler.kwargs["repo_id"] == DEFAULT_REPO == "nougenai/NouGenShards-wal"
    assert m.scheduler.kwargs["repo_type"] == "dataset"
    assert m.scheduler.kwargs["private"] is True


def test_append_writes_one_jsonl_line_per_record(tmp_path):
    m = HFDatasetMirror(str(tmp_path), scheduler_cls=FakeScheduler)
    m.append({"content_sha256": "a", "title": "t1"})
    m.append({"content_sha256": "b", "title": "t2"})
    lines = (tmp_path / "wal.jsonl").read_text().splitlines()
    assert [json.loads(x)["content_sha256"] for x in lines] == ["a", "b"]
