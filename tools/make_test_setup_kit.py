"""Build a sandboxed copy of the tenant 'Set up NouGen.cmd' for local testing.

Redirects the install folder to <root>\\NG, skips the HKCU Run registration and the
browser open, so the full download + start + health path can be exercised on any
machine without touching its real NouGen install. Usage:
    python tools/make_test_setup_kit.py <root> [port]
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
from nougen_shards import tenant_onboard as t  # noqa: E402

root = pathlib.Path(sys.argv[1])
port = int(sys.argv[2]) if len(sys.argv) > 2 else 4555
kit = t.write_kit("testtenant", "TOK", "TUN", port, root, node_url=f"http://127.0.0.1:{port}/health")
p = kit / "Set up NouGen.cmd"
s = p.read_text(encoding="utf-8")
s = s.replace("Join-Path $env:LOCALAPPDATA 'NouGen'", "'" + str(root / "NG") + "'")
s = s.replace("Set-ItemProperty", "# Set-ItemProperty")
s = s.replace("Start-Process 'http", "Write-Host 'would open http")
p.write_text(s, encoding="utf-8", newline="\r\n")
print(p)
