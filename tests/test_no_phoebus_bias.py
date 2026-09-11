from pathlib import Path


def test_no_silent_phoebus_fallback():
    bad_patterns = [
        'or peers["phoebus"]',
        "or peers['phoebus']",
        'default_vault = "phoebus"',
        "default_vault = 'phoebus'",
    ]

    roots = [Path("nougen_shards"), Path("src")]
    texts = []

    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            texts.append((path, path.read_text(errors="ignore")))

    failures = []
    for path, text in texts:
        for pattern in bad_patterns:
            if pattern in text:
                failures.append(f"{path}: {pattern}")

    assert not failures, "Silent Phoebus bias found:\n" + "\n".join(failures)
