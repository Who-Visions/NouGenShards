"""Socket delivery counts only on the receiver's ack, not on bytes sent (WG-1031)."""
import json

from nougen_shards import nougenmsg


def test_ack_with_inbox_file_is_delivery():
    raw = (json.dumps({"status": "delivered", "inbox_files": ["/x/a.json"]}) + "\n").encode()
    assert nougenmsg._confirm_socket_ack(raw) is True


def test_bytes_accepted_without_ack_is_not_delivery():
    assert nougenmsg._confirm_socket_ack(b"") is False


def test_non_json_reply_is_not_delivery():
    assert nougenmsg._confirm_socket_ack(b"ok") is False


def test_delivered_without_inbox_file_is_not_delivery():
    raw = json.dumps({"status": "delivered", "inbox_files": []}).encode()
    assert nougenmsg._confirm_socket_ack(raw) is False


def test_other_status_is_not_delivery():
    raw = json.dumps({"status": "error", "inbox_files": ["/x"]}).encode()
    assert nougenmsg._confirm_socket_ack(raw) is False
