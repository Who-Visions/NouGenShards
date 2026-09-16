"""Assemble the full Learn With Mrs. B book: cover + Unit 1 (build_pilot) + Units 2-8 (unitN.py).

Writes every page SVG, book.html (US Letter, one page per sheet) and, when Chrome is
found, learn-with-mrs-b-book.pdf. Missing unit modules are reported, not fatal.
Chrome path: env CHROME_PATH, else the standard install locations.
"""
import importlib
import os
import shutil
import subprocess
from pathlib import Path

import build_pilot as bp

OUT = Path(__file__).parent


def chrome():
    for c in (os.environ.get("CHROME_PATH"), r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", shutil.which("chrome")):
        if c and Path(c).exists():
            return c
    return None


def main():
    pages, missing = list(bp.PAGES), []
    for n in range(2, 9):
        try:
            mod = importlib.import_module(f"unit{n}")
            pages += list(mod.PAGES)
        except Exception as exc:  # a unit still in progress must not block the others
            missing.append(f"unit{n}: {type(exc).__name__}: {exc}")
    svgs = []
    for name, fn in pages:
        s = fn()
        (OUT / f"{name}.svg").write_text(s, encoding="utf-8")
        svgs.append(s)
    html = ("<!doctype html><html><head><meta charset='utf-8'><title>Learn With Mrs. B</title>"
            "<style>@page{size:8.5in 11in;margin:0}html,body{margin:0}"
            ".pg{width:8.5in;height:11in;page-break-after:always;overflow:hidden}"
            ".pg svg{width:100%;height:100%}</style></head><body>"
            + "".join(f"<div class='pg'>{s}</div>" for s in svgs) + "</body></html>")
    book = OUT / "book.html"
    book.write_text(html, encoding="utf-8")
    pdf = OUT / "learn-with-mrs-b-book.pdf"
    exe = chrome()
    if exe:
        import tempfile
        # a throwaway profile: headless Chrome can stall on this machine when it shares the default profile
        with tempfile.TemporaryDirectory(prefix="mrsb_chrome_") as prof:
            subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                            f"--user-data-dir={prof}", f"--print-to-pdf={pdf}", book.resolve().as_uri()],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
    print(f"pages: {len(svgs)} (cover + {len(svgs) - 1} interior)")
    print("pdf:", pdf if pdf.exists() else "not written (no Chrome found)")
    for m in missing:
        print("missing", m)


if __name__ == "__main__":
    main()
