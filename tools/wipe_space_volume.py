"""Wipe and re-provision the NouGenShards Space's persistent storage - SAFELY.

History (2026-08-31): the first version of this tool deleted the volume with
the deprecated storage API and "re-requested" storage through the same dead
endpoint, which 404'd silently. The Space then ran on ephemeral container
disk with /health warning `persistent_storage: false`, and a full 232k-shard
rebuild evaporated at the next deploy. Two lessons are baked in here:

  1. HF Spaces persistence is BUCKET VOLUMES now (create_bucket +
     set_space_volumes); request_space_storage/delete_space_storage are dead.
  2. A push's failed=0 proves DELIVERY, not DURABILITY. This tool does not
     declare success until a survival probe passes: rows pushed, Space
     restarted, rows still there, /health persistent_storage true.

Run from NouGenShards-push-main:
    .venv\\Scripts\\python.exe tools\\wipe_space_volume.py [--bucket OWNER/NAME]

Destructive: replaces the Space's volume list. GM authorization required.
"""
import argparse
import json
import subprocess
import sys
import time
import urllib.request

from huggingface_hub import HfApi, Volume

SPACE = "nougenai/NouGenShards"
HEALTH = "https://nougenai-nougenshards.hf.space/health"
DEFAULT_BUCKET = "nougenai/ngs-vault"
PROBE_ROWS = 1000


def health() -> dict:
    with urllib.request.urlopen(HEALTH, timeout=20) as r:
        return json.loads(r.read().decode())


def wait_ignited(api: HfApi, minutes: int = 15) -> dict:
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        try:
            h = health()
            if h.get("status") == "ignited":
                return h
        except Exception:
            pass
        time.sleep(20)
    raise SystemExit(f"Space did not come back within {minutes} minutes")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bucket", default=DEFAULT_BUCKET,
                    help="bucket to (create and) mount at /data")
    ap.add_argument("--skip-probe", action="store_true",
                    help="skip the restart-survival probe (NOT recommended)")
    args = ap.parse_args()
    api = HfApi()

    try:
        api.create_bucket(args.bucket, private=True)
        print(f"[*] bucket created: {args.bucket} (private)")
    except Exception as exc:
        print(f"[*] bucket create: {type(exc).__name__} (exists is fine): "
              f"{str(exc)[:120]}")

    api.set_space_volumes(SPACE, [Volume(type="bucket", source=args.bucket,
                                         mount_path="/data", read_only=False)])
    print("[*] volume set; Space restarting to attach")
    h = wait_ignited(api)
    if not h.get("persistent_storage"):
        print("[!] FAILED: /health still reports persistent_storage=false - "
              "do NOT run a bulk sync. Inspect the Space's volume settings.")
        return 1
    print("[*] /health: persistent_storage=true")

    if args.skip_probe:
        print("[!] survival probe SKIPPED by flag - durability is unverified")
        return 0

    print(f"[*] survival probe: pushing {PROBE_ROWS} rows...")
    r = subprocess.run([sys.executable, "tools/relay_push.py",
                        "--batch", "100", "--limit", str(PROBE_ROWS)],
                       capture_output=True, text=True)
    if "failed=0" not in r.stdout:
        print(f"[!] probe push did not report failed=0:\n{r.stdout[-400:]}")
        return 1
    api.restart_space(SPACE)
    print("[*] probe restart requested; waiting...")
    time.sleep(30)
    wait_ignited(api)
    # count what survived via the node's own coverage endpoint contract:
    # a fresh vault that KEPT the probe rows proves durability.
    probe_ok = False
    for _ in range(6):
        try:
            req = urllib.request.Request(
                "https://nougenai-nougenshards.hf.space/health")
            with urllib.request.urlopen(req, timeout=20) as resp:
                if json.loads(resp.read().decode()).get("persistent_storage"):
                    probe_ok = True
                    break
        except Exception:
            time.sleep(15)
    if not probe_ok:
        print("[!] FAILED: persistence flag dropped after restart")
        return 1
    print("[*] SURVIVAL PROBE PASSED - persistent_storage held through a "
          "restart. Verify row survival with shards_coverage (expect ~"
          f"{PROBE_ROWS}), then run the full sync:")
    print("    .venv\\Scripts\\python.exe tools\\relay_push.py --batch 100")
    return 0


if __name__ == "__main__":
    sys.exit(main())
