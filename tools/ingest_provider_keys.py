#!/usr/bin/env python
"""ingest_provider_keys.py — batch-ingest fleet provider keys into the keymaker vault.

Reads a CSV/TSV YOU export from your key spreadsheet and DPAPI-encrypts every key
into the Memory Vault via keymaker. Secret values flow from your file -> your vault;
they are never printed (only key-name + SHA-256 fingerprint + status are shown).

CSV/TSV columns (header row, case-insensitive; extra columns ignored):
    provider, account, key_name, key            [, model]
- provider: OpenRouter | HuggingFace | Ollama | arlai | ...
- account:  email / label (used to disambiguate multi-account keys)
- key_name: optional friendly name; if blank a name is derived
- key:      the secret value (rows with a blank/again-seen key are skipped)

Vault naming: <PROVIDER>_KEY_<ACCOUNT_NORMALISED>  (mirrors existing OLLAMA_KEY_* rows).
A per-provider default <PROVIDER>_API_KEY is set to the FIRST key seen for that provider.

Usage:
    set NOUGEN_VAULT_DIR=path\\to\\your\\vault   (optional)
    python tools/ingest_provider_keys.py path\\to\\keys.csv
"""
import csv
import hashlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

try:
    from nougen_shards import keymaker
except ImportError:
    sys.path.insert(0, str(REPO_ROOT))
    from src.nougen_shards import keymaker  # type: ignore


def _norm(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in (s or "").strip().upper()).strip("_")


def _sniff(path: Path):
    sample = path.read_text(encoding="utf-8-sig", errors="replace")[:4096]
    delim = "\t" if sample.count("\t") >= sample.count(",") else ","
    return delim


def main(argv) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    path = Path(argv[1])
    if not path.exists():
        print(f"file not found: {path}")
        return 2

    delim = _sniff(path)
    seen_fp = set()
    provider_default = {}
    ingested = 0
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as fh:
        reader = csv.DictReader(fh, delimiter=delim)
        cols = {c.lower().strip(): c for c in (reader.fieldnames or [])}
        kcol = cols.get("key") or cols.get("keys") or cols.get("value")
        pcol = cols.get("provider")
        acol = cols.get("account")
        ncol = cols.get("key_name") or cols.get("name")
        if not kcol:
            print(f"no 'key' column found; headers were: {reader.fieldnames}")
            return 2
        for row in reader:
            key = (row.get(kcol) or "").strip()
            if not key or not any(key.startswith(p) for p in ("sk-", "hf_", "sk-or-")) and len(key) < 16:
                continue
            fp = hashlib.sha256(key.encode()).hexdigest()[:12]
            if fp in seen_fp:
                continue
            seen_fp.add(fp)
            provider = (row.get(pcol) if pcol else "") or "PROVIDER"
            account = (row.get(acol) if acol else "") or ""
            name = (row.get(ncol) if ncol else "") or ""
            vault_name = f"{_norm(provider)}_KEY_{_norm(account) or _norm(name) or fp}"
            try:
                keymaker.ingest_secret(vault_name, key)
            except Exception as exc:  # pragma: no cover - environment dependent
                print(f"SKIP {vault_name}: {type(exc).__name__}: {str(exc)[:60]}")
                continue
            prov_key = _norm(provider)
            if prov_key not in provider_default:
                provider_default[prov_key] = key
            ingested += 1
            print(f"{vault_name:46s} {fp}  DPAPI-encrypted")

    for prov, key in provider_default.items():
        default_name = f"{prov}_API_KEY"
        try:
            keymaker.ingest_secret(default_name, key)
            print(f"{default_name:46s} {'default set':22s}")
        except Exception as exc:  # pragma: no cover
            print(f"SKIP {default_name}: {type(exc).__name__}")

    print(f"\n{ingested} keys ingested (values never printed). Ledger: see keymaker CSV (metadata only).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
