# NouGenTime

Canonical source for shared NouGen wall-clock formatting lives in
`NouGenShards/src/nougen_time`. The byte-identical copy in NouGenRelay is a
generated mirror so either repository remains independently installable.

After changing this package in NouGenShards, run:

```powershell
python tools/sync_nougen_time.py
python tools/sync_nougen_time.py --check
```

The API treats Unix time and naive legacy ISO timestamps as UTC, renders human
time in `America/New_York`, and uses six fractional digits for canonical ISO
timestamps. Use `now()` for wall-clock timestamps and `monotonic_ns()` only for
elapsed durations. Present invalid timestamps raise `InvalidTimestampError`;
missing timestamps return `None` from `parse()` and `?` from formatters.
