# Resilience reference pack

This directory preserves the session's war game, executable reference implementation,
tests and internal Hugging Face Space dispatch scripts. These are reference artifacts,
not a deployed runtime or production certification. See WAR_GAME.md for integration
requirements and the 46 planned operational scenarios.

Run the reference tests from this directory:

```powershell
python -m unittest -q test_resilience_core
```

The dispatch scripts resolve credentials through Keymaker in process memory and write
results beside themselves. Running them sends the specified task or local reference
code to the named WhoVisions Space. They require an installed nougen_shards package;
install it from the repository with `python -m pip install -e .` before execution.
No credentials are included. The saved status is an observation from dispatch time,
not a live monitor. Generated model output must be reviewed before use.

Ollama Cloud / nemotron-3-ultra drafted the publication summary; the supervising agent
checked its claims and performed validation and Git publication. Ollama did not have
direct shell or Git write access.
