"""`nougen setup`: redeem an invite and write the node's kit. Runs under unittest or pytest."""
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from nougen_shards import cli, tenant_onboard


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


GOOD = {"tenant_id": "pat-shards", "node_url": "https://pat-shards-ab12.example.test",
        "token": "tok-demo", "tunnel_token": "tun-demo"}


class RedeemInviteTests(unittest.TestCase):
    def test_success_returns_setup_values(self):
        seen = {}

        def opener(req):
            seen["body"] = json.loads(req.data.decode())
            return _Resp(json.dumps(GOOD).encode())

        out = tenant_onboard.redeem_invite(" abc ", "https://join.example.test/onboard/redeem", opener)
        self.assertEqual(seen["body"], {"code": "abc"})
        self.assertEqual(out["token"], "tok-demo")
        self.assertEqual(out["tenant_id"], "pat-shards")

    def test_missing_join_url_is_a_clear_error(self):
        with self.assertRaisesRegex(tenant_onboard.OnboardError, "NOUGEN_JOIN_URL"):
            tenant_onboard.redeem_invite("abc", "")

    def test_server_error_message_is_shown(self):
        def opener(req):
            raise urllib.error.HTTPError(req.full_url, 400, "bad", {}, _Resp(b'{"error":"already used"}'))

        with self.assertRaisesRegex(tenant_onboard.OnboardError, "already used"):
            tenant_onboard.redeem_invite("abc", "https://j.test", opener)

    def test_incomplete_reply_is_rejected(self):
        def opener(req):
            return _Resp(b'{"tenant_id":"x"}')

        with self.assertRaises(tenant_onboard.OnboardError):
            tenant_onboard.redeem_invite("abc", "https://j.test", opener)


class SetupCommandTests(unittest.TestCase):
    def test_setup_writes_kit_under_home_and_runs_it(self):
        with tempfile.TemporaryDirectory() as home:
            args = type("A", (), {"code": "abc"})()
            with mock.patch.dict(os.environ, {"NOUGEN_JOIN_URL": "https://j.test"}), \
                 mock.patch.object(cli, "cmd_init") as init, \
                 mock.patch.object(tenant_onboard, "redeem_invite", return_value={
                     "tenant_id": "pat-shards", "node_url": GOOD["node_url"], "token": "tok-demo",
                     "tunnel_token": "tun-demo", "port": 4444}), \
                 mock.patch.object(Path, "home", return_value=Path(home)), \
                 mock.patch("subprocess.call", return_value=0) as call:
                rc = cli.cmd_setup(args)
            self.assertEqual(rc, 0)
            init.assert_called_once()
            script = Path(home) / ".nougen" / "tenant-kits" / "pat-shards" / ("join.ps1" if os.name == "nt" else "join.sh")
            self.assertTrue(script.is_file(), "kit must persist under ~/.nougen, not a temp folder")
            self.assertIn("tok-demo", script.read_text())
            self.assertEqual(call.call_args.args[0][-1], str(script))

    def test_setup_reports_redeem_errors_without_traceback(self):
        args = type("A", (), {"code": "bad"})()
        with mock.patch.object(cli, "cmd_init"), \
             mock.patch.object(tenant_onboard, "redeem_invite",
                               side_effect=tenant_onboard.OnboardError("that invite code didn't work")):
            self.assertEqual(cli.cmd_setup(args), 1)


if __name__ == "__main__":
    unittest.main()
