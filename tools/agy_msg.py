#!/usr/bin/env python3
"""AgyMsg CLI and server shim."""
import sys
import os

# Add src and repo root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if len(sys.argv) > 1 and sys.argv[1] == "listen":
    from tools.agy_pipe_server import run_server
    run_server()
else:
    from tools.nougenmsg import main
    main()
