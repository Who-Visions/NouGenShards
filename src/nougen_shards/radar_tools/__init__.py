"""Vendored copy of the nougen-radar tools (Who-Visions/nougen-radar @ 8a022e5).

The upstream repo is private, so tenant nodes installing public NouGenShards
could not fetch it and every radar/arXiv tool reported `degraded`.
`arxiv_radar.find_radar_root()` uses this directory only when no real
nougen-radar checkout is found, so operator nodes keep using their own clone.

The files are loaded by path (spec_from_file_location), not imported as
submodules. Refresh them by copying from the upstream `tools/` directory.
"""
