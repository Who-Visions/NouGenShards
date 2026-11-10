# NOU / UDCT reference implementation

Python 3.11+, no external dependencies. Run:

```bash
python -m unittest discover -s . -p 'test_*.py' -v
python udct.py > performance.json
```

## Contract

- `Performance`: immutable identity, semantic cues, timed phonemes, speech-energy envelope.
- `evaluate(performance, seconds)`: deterministic, stateless, normalized rig channels.
- `frames(performance, fps)`: time-sampled channel output.
- `blender_adapter.apply_frame(mesh, channels, frame)`: sample shape-key mapping; requires Blender and a rig with matching keys.

## Production integration

1. Replace illustrative phonemes with aligned phoneme timestamps from a speech aligner.
2. Add continuous viseme coarticulation across neighboring phonemes and consonant closures.
3. Add proper gaze target IK, eyelid-to-eye coupling, per-eye saccades and vergence.
4. Map head/body/shoulders/arms to actual armature bones, not just shape keys.
5. Add collision-aware gesture clips, contact constraints, hair physics and camera-aware silhouettes.
6. Validate character-specific bone axes, units, deformation and rig constraints.
7. Drive the same timeline through audio, camera, render and subtitles; use fixed fps and asset hashes.
8. Log seed, input hash, rig version, engine version, and output checksums.

This is a runnable control-system prototype, **not** a finished production rig or speech-synthesis engine.
