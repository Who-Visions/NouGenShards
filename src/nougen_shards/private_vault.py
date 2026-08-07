"""
Encryption-at-rest for personal-sensitivity shards and files.

The Keymaker (`keymaker.py`) protects *secrets* — API keys, service accounts — with
Windows DPAPI. It was never meant for bulk content: DPAPI blobs are user-bound, not
seekable, and wrapping every shard body in a separate DPAPI call is slow and leaves
the key material entirely at the mercy of one Windows profile.

This module is the content lane. It uses envelope encryption:

    data key   : 32 random bytes, generated once per vault
    at rest    : the data key is DPAPI-wrapped via keymaker (or held in
                 NOUGEN_PRIVATE_KEY for CI / non-Windows lanes)
    payload    : AES-256-GCM, fresh 96-bit nonce per value
    wire format: ngenc1:<base64(nonce || ciphertext || tag)>

AAD binds the format version into the tag, so a ciphertext minted under one wire
format cannot be replayed into a future one.

RECOVERY: DPAPI is bound to the current Windows user. A profile rebuild would make
every encrypted record unrecoverable, which is unacceptable for tax and financial
documents. Generating a key therefore ALWAYS writes a one-time plaintext recovery
key next to the vault; move it offline. No key is ever created without a recovery
path — if the recovery file cannot be written, key generation fails closed.

Usage:
    python -m nougen_shards.private_vault status
    python -m nougen_shards.private_vault encrypt-file <path> [--keep]
    python -m nougen_shards.private_vault decrypt-file <path.ngenc>
"""
from __future__ import annotations

import base64
import os
import secrets
from typing import Optional

# Wire-format marker. Bump the suffix if the envelope ever changes; the AAD below
# binds it so old ciphertext cannot be silently reinterpreted under a new format.
ENC_PREFIX = "ngenc1:"
_AAD = b"nougen-private-vault-v1"

_NONCE_BYTES = 12   # 96-bit nonce: the GCM-recommended size
_KEY_BYTES = 32     # AES-256

# Environment overrides (Rule 0.2: env -> config -> probe, constants are fallbacks).
ENV_KEY = "NOUGEN_PRIVATE_KEY"          # base64 data key, for CI / non-Windows lanes
ENV_KEY_FILE = "NOUGEN_PRIVATE_KEY_FILE"
# os.pathsep-separated directories swept for an already-minted key before
# a new one is generated. Set it to pin key custody explicitly.
ENV_KEY_SEARCH_PATH = "NOUGEN_KEY_SEARCH_PATH"
# Operator workspace root; its `vault` subdirectory joins the key sweep when set.
ENV_WORKSPACE_ROOT = "WATCHTOWER_ROOT"
ENV_VAULT = "NOUGEN_VAULT_DIR"

KEY_FILENAME = "private_key.bin"
RECOVERY_FILENAME = "RECOVERY_KEY.txt"

# Sensitivity levels. 'normal' is the existing plaintext corpus and stays plaintext;
# anything at or above _ENCRYPTED_AT gets its body encrypted before it touches disk.
SENSITIVITY_NORMAL = "normal"
SENSITIVITY_PRIVATE = "private"
SENSITIVITY_SECRET = "secret"
_ENCRYPTED_AT = {SENSITIVITY_PRIVATE, SENSITIVITY_SECRET}

_key_cache: Optional[bytes] = None


class PrivateVaultError(RuntimeError):
    """Raised when the data key cannot be resolved, created, or recovered."""


def should_encrypt(sensitivity: Optional[str]) -> bool:
    """True when a shard at this sensitivity must have its body encrypted at rest."""
    return (sensitivity or SENSITIVITY_NORMAL).strip().lower() in _ENCRYPTED_AT


def normalize_sensitivity(sensitivity: Optional[str]) -> str:
    value = (sensitivity or SENSITIVITY_NORMAL).strip().lower()
    if value not in (SENSITIVITY_NORMAL, SENSITIVITY_PRIVATE, SENSITIVITY_SECRET):
        raise ValueError(
            f"unknown sensitivity {sensitivity!r}; "
            f"expected one of normal/private/secret"
        )
    return value


# --- vault + key resolution -------------------------------------------------

def resolve_vault_dir() -> str:
    """Vault directory, discovered rather than assumed (Rule 0.2)."""
    env = os.environ.get(ENV_VAULT)
    if env:
        return env
    try:
        from .core import _resolve_vault_dir  # type: ignore
        return _resolve_vault_dir()
    except Exception:
        return os.path.join(os.path.expanduser("~"), ".nougen", "shards")


def key_path() -> str:
    override = os.environ.get(ENV_KEY_FILE)
    if override:
        return override
    return os.path.join(resolve_vault_dir(), KEY_FILENAME)


def recovery_path() -> str:
    return os.path.join(os.path.dirname(key_path()), RECOVERY_FILENAME)


def _candidate_key_paths() -> list:
    """Every directory a previously-minted key could be sitting in.

    A deployment can legitimately have more than one "vault" directory — an
    operator-configured memory vault and the package's own shard cluster. If
    `NOUGEN_VAULT_DIR` differs between sessions, a naive resolver would find no
    key, mint a SECOND one, and orphan every shard encrypted under the first.
    Silent key divergence is data loss, so we sweep before ever generating.

    Locations are resolved from configuration, never from a hardcoded workspace
    name: set `NOUGEN_KEY_SEARCH_PATH` to pin custody explicitly.
    """
    seen, out = set(), []
    candidates = [os.path.dirname(key_path())]

    override = os.environ.get(ENV_KEY_SEARCH_PATH)
    if override:
        # Explicit search path wins outright: it is what makes the sweep testable
        # and what lets an operator pin custody to known directories.
        candidates.extend(p for p in override.split(os.pathsep) if p)
    else:
        candidates.append(resolve_vault_dir())
        root = os.environ.get(ENV_WORKSPACE_ROOT)
        if root:
            candidates.append(os.path.join(root, "vault"))
        candidates.append(os.path.join(os.path.expanduser("~"), ".nougen", "shards"))

    for directory in candidates:
        if not directory:
            continue
        path = os.path.join(directory, KEY_FILENAME)
        if path not in seen:
            seen.add(path)
            out.append(path)
    return out


def _write_recovery_key(raw: bytes) -> str:
    """Write the offline recovery copy. Fails closed — no recovery file, no key."""
    path = recovery_path()
    b64 = base64.b64encode(raw).decode("ascii")
    body = (
        "NouGen private vault — RECOVERY KEY\n"
        "===================================\n\n"
        "This is the ONLY way to decrypt your private shards and .ngenc files if the\n"
        "Windows profile that created them is lost or rebuilt.\n\n"
        "MOVE THIS FILE OFF THIS MACHINE. Password manager, printed copy, or an\n"
        "encrypted drive. Then delete it from disk.\n\n"
        f"{ENV_KEY}={b64}\n\n"
        "To recover: set that environment variable and the vault decrypts normally.\n"
    )
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
    except OSError as exc:
        raise PrivateVaultError(
            f"refusing to generate a data key: recovery file {path} is unwritable ({exc}). "
            "Encrypting without a recovery path risks permanent data loss."
        ) from exc
    try:
        from .keymaker import _harden_path  # type: ignore
        _harden_path(path)
    except Exception:
        pass
    return path


def _generate_key() -> bytes:
    raw = secrets.token_bytes(_KEY_BYTES)
    # Recovery copy first: if this fails we must not leave an unrecoverable key behind.
    written = _write_recovery_key(raw)

    path = key_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = base64.b64encode(raw).decode("ascii")
    try:
        from .keymaker import _protect  # type: ignore
        stored = _protect(payload)
    except Exception as exc:
        os.unlink(written)
        raise PrivateVaultError(
            f"cannot protect the data key at rest ({exc}). "
            f"Set {ENV_KEY} explicitly to run without DPAPI or an OS keyring."
        ) from exc

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(stored)
    try:
        from .keymaker import _harden_path  # type: ignore
        _harden_path(path)
    except Exception:
        pass
    return raw


def load_key(create: bool = True) -> bytes:
    """Resolve the vault data key: env -> key file -> generate."""
    global _key_cache
    if _key_cache is not None:
        return _key_cache

    env = os.environ.get(ENV_KEY)
    if env:
        try:
            raw = base64.b64decode(env)
        except Exception as exc:
            raise PrivateVaultError(f"{ENV_KEY} is not valid base64") from exc
        if len(raw) != _KEY_BYTES:
            raise PrivateVaultError(
                f"{ENV_KEY} must decode to {_KEY_BYTES} bytes, got {len(raw)}"
            )
        _key_cache = raw
        return raw

    for path in _candidate_key_paths():
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as fh:
            stored = fh.read().strip()
        try:
            from .keymaker import _unprotect  # type: ignore
            payload = _unprotect(stored)
        except Exception as exc:
            raise PrivateVaultError(
                f"cannot unwrap the data key at {path} ({exc}). If this machine's Windows "
                f"profile changed, restore from {RECOVERY_FILENAME} by setting {ENV_KEY}."
            ) from exc
        raw = base64.b64decode(payload)
        _key_cache = raw
        return raw

    if not create:
        raise PrivateVaultError(
            f"no data key found in any of: {', '.join(_candidate_key_paths())}")
    raw = _generate_key()
    _key_cache = raw
    return raw


def reset_key_cache() -> None:
    """Drop the in-process key cache. Used by tests and after key rotation."""
    global _key_cache
    _key_cache = None


# --- primitives -------------------------------------------------------------

def _aesgcm(key: bytes):
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise PrivateVaultError(
            "the 'cryptography' package is required for private shards"
        ) from exc
    return AESGCM(key)


def is_encrypted(value) -> bool:
    return isinstance(value, str) and value.startswith(ENC_PREFIX)


def encrypt_text(plaintext: str, key: Optional[bytes] = None) -> str:
    """Encrypt a string to the ngenc1 wire format. Idempotent on encrypted input."""
    if plaintext is None:
        return plaintext
    if is_encrypted(plaintext):
        return plaintext
    raw = key if key is not None else load_key()
    nonce = secrets.token_bytes(_NONCE_BYTES)
    blob = _aesgcm(raw).encrypt(nonce, plaintext.encode("utf-8"), _AAD)
    return ENC_PREFIX + base64.b64encode(nonce + blob).decode("ascii")


def decrypt_text(stored: str, key: Optional[bytes] = None) -> str:
    """Decrypt ngenc1 text. Passes plaintext through so mixed corpora just work."""
    if not is_encrypted(stored):
        return stored
    raw = key if key is not None else load_key(create=False)
    payload = base64.b64decode(stored[len(ENC_PREFIX):])
    nonce, blob = payload[:_NONCE_BYTES], payload[_NONCE_BYTES:]
    return _aesgcm(raw).decrypt(nonce, blob, _AAD).decode("utf-8")


# --- file lane --------------------------------------------------------------

FILE_SUFFIX = ".ngenc"
_FILE_MAGIC = b"NGENC1\x00"


def encrypt_file(path: str, keep_original: bool = False) -> str:
    """
    Encrypt a file to <path>.ngenc.

    The plaintext original is removed only after the ciphertext has been decrypted
    back in memory and byte-compared against the source. These are irreplaceable
    records; a failed verification keeps the original and raises.
    """
    with open(path, "rb") as fh:
        data = fh.read()

    raw = load_key()
    nonce = secrets.token_bytes(_NONCE_BYTES)
    blob = _aesgcm(raw).encrypt(nonce, data, _AAD)
    out = path + FILE_SUFFIX
    with open(out, "wb") as fh:
        fh.write(_FILE_MAGIC + nonce + blob)

    # Verify before destroying anything.
    if decrypt_file_bytes(out) != data:
        os.unlink(out)
        raise PrivateVaultError(
            f"round-trip verification failed for {path}; original left untouched"
        )

    if not keep_original:
        os.unlink(path)
    return out


def decrypt_file_bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        payload = fh.read()
    if not payload.startswith(_FILE_MAGIC):
        raise PrivateVaultError(f"{path} is not a NouGen encrypted file")
    body = payload[len(_FILE_MAGIC):]
    nonce, blob = body[:_NONCE_BYTES], body[_NONCE_BYTES:]
    return _aesgcm(load_key(create=False)).decrypt(nonce, blob, _AAD)


def decrypt_file(path: str, dest: Optional[str] = None) -> str:
    data = decrypt_file_bytes(path)
    if dest is None:
        dest = path[: -len(FILE_SUFFIX)] if path.endswith(FILE_SUFFIX) else path + ".dec"
    with open(dest, "wb") as fh:
        fh.write(data)
    return dest


# --- CLI --------------------------------------------------------------------

def _main(argv=None):
    import argparse
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="NouGen private vault (encryption at rest).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="report key location and whether it resolves")
    p_enc = sub.add_parser("encrypt-file")
    p_enc.add_argument("path")
    p_enc.add_argument("--keep", action="store_true", help="retain the plaintext original")
    p_dec = sub.add_parser("decrypt-file")
    p_dec.add_argument("path")
    p_dec.add_argument("--dest")
    args = ap.parse_args(argv)

    if args.cmd == "status":
        print(f"vault      : {resolve_vault_dir()}")
        print(f"key file   : {key_path()}")
        print(f"env key set: {'yes' if os.environ.get(ENV_KEY) else 'no'}")
        try:
            load_key(create=False)
            print("key        : resolves OK")
        except PrivateVaultError as exc:
            print(f"key        : NOT AVAILABLE ({exc})")
            return 1
        rec = recovery_path()
        if os.path.exists(rec):
            print(f"recovery   : {rec}  <-- MOVE THIS OFFLINE")
        return 0

    if args.cmd == "encrypt-file":
        out = encrypt_file(args.path, keep_original=args.keep)
        print(f"encrypted -> {out}")
        return 0

    if args.cmd == "decrypt-file":
        out = decrypt_file(args.path, dest=args.dest)
        print(f"decrypted -> {out}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(_main())
