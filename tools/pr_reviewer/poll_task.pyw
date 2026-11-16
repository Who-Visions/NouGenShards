"""Scheduled-task entry for the aiwithdav3 reviewer poll: runs bun with no window, logs failures to run.log."""
import os, pathlib, shutil, subprocess, datetime
here = pathlib.Path(__file__).resolve().parent
log = pathlib.Path.home() / ".nougen" / "research" / "reviews" / "aiwithdav3" / "run.log"
log.parent.mkdir(parents=True, exist_ok=True)  # fresh machine: the except path must be able to log
bun = shutil.which("bun") or str(pathlib.Path.home() / ".bun" / "bin" / ("bun.exe" if os.name == "nt" else "bun"))
try:
    r = subprocess.run([bun, str(here / "review.ts"), "poll", "--owner", "Who-Visions", "--since-hours", "72", "--max", "4"],
                       cwd=here, stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace",
                       timeout=3300, creationflags=0x08000000 if os.name == "nt" else 0)
    if r.returncode:
        log.open("a", encoding="utf-8").write(f"[task {datetime.datetime.now():%m/%d %I:%M %p}] poll exit {r.returncode}: {(r.stderr or '')[-400:]}\n")
except Exception as e:
    log.open("a", encoding="utf-8").write(f"[task {datetime.datetime.now():%m/%d %I:%M %p}] launcher error: {e}\n")
