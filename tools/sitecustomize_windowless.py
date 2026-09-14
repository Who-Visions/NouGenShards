"""Fleet-wide: no console windows from background Python.

When this interpreter runs without a console (pythonw.exe, a hidden
scheduled task, a service), every child it spawns with subprocess would
otherwise allocate a fresh console — one flashing window per ``git`` call.
Dave saw it from three different tasks on 2026-09-14 ("everything git
spawns on my screen"). Patching each script is whack-a-mole; patching the
interpreter once is deterministic and covers scripts not written yet.

Interactive python.exe is untouched: the patch only arms when
``GetConsoleWindow()`` is NULL. Set ``NOUGEN_ALLOW_CONSOLE=1`` to disable.
Same guard lives in every fleet interpreter's site-packages.
"""
import os
import sys


def _arm() -> None:
    if os.name != "nt" or os.environ.get("NOUGEN_ALLOW_CONSOLE") == "1":
        return
    try:
        import ctypes
        if ctypes.windll.kernel32.GetConsoleWindow():
            return  # a real console is attached; nothing to hide
    except Exception:
        return
    import subprocess
    if getattr(subprocess, "_nougen_windowless", False):
        return
    flag = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    orig_run, orig_popen = subprocess.run, subprocess.Popen

    def run(*a, **kw):
        kw.setdefault("creationflags", flag)
        if "input" not in kw:
            kw.setdefault("stdin", subprocess.DEVNULL)
        return orig_run(*a, **kw)

    class Popen(orig_popen):
        def __init__(self, *a, **kw):
            kw.setdefault("creationflags", flag)
            kw.setdefault("stdin", subprocess.DEVNULL)
            super().__init__(*a, **kw)

    subprocess.run, subprocess.Popen = run, Popen
    subprocess._nougen_windowless = True


_arm()
