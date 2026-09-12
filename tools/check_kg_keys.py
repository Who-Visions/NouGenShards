import sqlite3
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nougen_shards.keymaker import _unprotect

db_path = Path.home() / ".nougen" / "shards" / "shards_secrets.db"
conn = sqlite3.connect(str(db_path))
rows = conn.execute("SELECT secret_key, secret_value FROM secrets").fetchall()
print(f"Total secrets in Keymaker vault: {len(rows)}")
for k, v in rows:
    if any(term in k.upper() for term in ("GOOGLE", "GEMINI", "KG", "SEARCH", "API_KEY")):
        try:
            val = _unprotect(v)
            masked = val[:8] + "..." + val[-4:] if len(val) > 12 else "***"
            print(f"  - {k}: {masked} (length {len(val)})")
        except Exception as e:
            print(f"  - {k}: decrypt failed ({e})")

