---
name: nougenmix
description: Use when building, auditing or mixing a trap or hip-hop beat in FL Studio through the NouGenMix MCP (fl_* tools): laying drums on the hot spots, writing hats with rolls, pitching and placing an 808, finding space for percussion, leveling and panning the mixer, reading a sample's tempo and key, arranging sections, or drafting titles/hooks on the local Ollama lane. Also use when the operator says "nougenmorph" a music tutorial: absorb the mechanics into theory/ with provenance labels and tests, never the wording. Covers the Gibson 3D imaging model shared with nougen-verse.
---

# NouGenMix

FL Studio control over MCP plus the craft rules absorbed from producers and David Gibson. Every
rule in `src/fl_studio_mcp/theory/` carries a provenance label: `tutorial`/`gibson` (stated in a
source), `ours` (verified on a live project), `assumption` (inference). Say which one you are
leaning on when you make a call.

## Before touching FL

1. One FL instance only. Focus the running one by PID; `open_application` launches a new one.
2. `fl_connection_status` must show the loopMIDI port. If not, stop and say so.
3. The piano roll edits only the channel its window is bound to. Select the channel, then F7
   until the title shows it. `channels.selectOne` alone does not retarget.
4. The keystroke trigger needs FL in front. If a queued change does not land, run
   ComposeWithLLM from the piano roll wrench menu.
5. Dave's project is a sacrificial test bed; write freely, never ask to write. He saves.

## Order of work for a beat

1. **Reference budget** (`sampling.reference_budget`): tempo, key, element count, arrangement of
   the reference. Do not exceed its element count.
2. **Key and 808 pitch**: measure the loop (chroma -> `key_from_pitch_classes`), measure the 808
   sample's fundamental, `fl_pitch_808(target, sample_hz)`. Re-measure after any sample swap.
3. **Drums on the hot spots**: `fl_apply_trap_drums` (steps 0, 6, 10; backbeat or half-time), then
   `fl_audit_trap_pattern`. Kick and snare never share a step.
4. **Hats**: two-step base, then rolls (6B triplets or 32nds, velocity ramps) and silence.
   `fl_hat_line_notes` -> `fl_send_notes`. Every note on the grid; check with `trap.is_mechanical`.
5. **808 line**: roots on the kick, follow the chord roots, vary the second half
   (`fl_transpose_bars` +7 or an octave), end with `fl_tail_guard`.
6. **Percussion**: `fl_suggest_percussion_slots`; open hat at bar start or just before the snare;
   counter snare in the free space; pan alternately (`fl_pan_balance`).
7. **Mix** (Gibson): route each channel to its own insert. Snare ~ -3 dB, melody ~ -6, hats below
   the snare, 808 loudest if there is no kick. `fl_set_track_db`, then `fl_audit_trap_mix`.
   Build a `mix_space.MixScene` when checking masking: kick/808/bass centred, hi-hat half-left.
8. **Arrangement** is by hand (the API cannot place clips): `fl_trap_arrangement` gives the plan.

## Local lane

`fl_draft_local` runs gemma4:e2b-qat for titles, tags, hook ideas, plain-English reads of an
audit. Never for notes, ticks or dB. If Ollama is down it says so; do not fall back to a paid route.

## nougenmorph a tutorial

Read the structure, keep the mechanics, drop the wording. Land: a `theory/*.py` module with
labeled rules and pure functions, tests including a live-state fixture if one exists, a
`docs/*-valerion.md`, one shard, a relay leg. Fleet-vote judgement calls when the fleet is up.

## Gibson geometry (shared with nougen-verse)

Pan = X, volume = Z (front/back), frequency = Y. Transparent spheres; bass is big; fattening is a
line; reverb is a cube; the space is finite (crowd control). `verse_space` ports it: a double
entendre is one transparent object with two coordinates; callbacks are reverb; setup/payoff is delay.

## Piano-roll automation, hard-won (2026-09-21)

- After EVERY FL restart, run ComposeWithLLM once from the piano roll wrench menu. Until then
  Ctrl+Alt+Y is a no-op, `fl_trigger_script` still says "success", and every state read is stale.
  Check: `piano_roll_state.json` mtime must be newer than the trigger; if not, the trigger is dead.
- `fl_open_piano_roll` (selectOneChannel + showWindow) focuses the roll; it does not rebind it.
  Rebind = human double-click on the channel, or F7 with the roll closed. Verify blind by reading
  the state's note count and pitch set against what that channel should hold.
- FL's client area can capture black while the window is "foreground". Clicks and keys still land.
- FL's API has no polyphony / mono / cut / release setter (verified in the stubs). A long-tail 808
  needs the producer to click Poly 1 / Mono. Say so; do not promise a handler.
- Pitched sample: key = 72 + target_midi - sample_midi. Re-measure the sample after any swap.
- `transport.getTempo` exists now; read BPM before any tail or roll arithmetic.

## Theory modules added 2026-09-21 (all with provenance labels and tests)

- `sampling.py` chops: even grid, deterministic rearrange, lazy offset, chop checklists; R&B
  extensions (`extend_chord`), cross-layer semitone clash (`voice_clash`), `sparse_808_from_kick`.
- `bass.py`: `root_from_voicing` (inversions), `bassline` (simple/passing/approach/octave),
  `slide` (length = glide time), `clash_checklist`, `two_808_rules`, `drone_ok`, `GENRE_BASS`.
- `chains.py`: `split_band_808` (mono sub, saturated 200-5k band, mono-compatible widener) and
  `low_band_duck_808` (peak controller -> EQ band gain, inverted) as data + validators.
- `low_end.py`: `masking_priority` (who owns which critical band), `phase_offset_scan` on stems,
  `pitch_dive` (the 808's punch), `CLIPPING` notes.
- `translation.py`: three-band presence matrix; every key role must register in low, mid, high.

Order for a low-end problem: sound choice > HP the melodies > polarity flip > band-limited duck >
split-band saturation > clipper glue. Never a whole-channel sidechain first.

NouGenProbe (realtime audio) can only be a native FL plugin: SDK at Outpost/NouGenMix-sdk
(fpsdk_20210311b, C++/Delphi). Effect plugins read audio in Eff_Render on the mixer thread;
no allocs, no I/O there; hand descriptors to a ring buffer and publish from Idle_Public.

## NouGenProbe, live (verified 2026-09-21)

- Install: `Plugins\Fruity\Effects\<Name>\<Name>_x64.dll` + `Plugin.nfo` (`ps_vendorname=`).
  The standalone Plugin Manager will NOT register a native-SDK effect. Register with Browser >
  PLUGINS tab > right-click "Plugin database" > "Refresh plugin list (fast scan)"; then the
  `.fst` lands in `Presets\Plugin database\Installed\Effects\Fruity\`. The slot menu's "New"
  submenu stays stale; use "More plugins..." and search.
- Feed: `~/.nougenmix/probe/<tag>.jsonl`, one row per block. It writes zeros while stopped, so
  `utils.probe.latest` windows back to the last audible block and reports `stale_blocks`.
- `mix_probe_read` for numbers, `mix_diagnose_live` for a bounded `mix.diagnostic` verdict.
  Probe bands are 250 Hz / 4 kHz one-pole, not the stem analyzer's 200/3000; no fundamental.
- Known bug: `beat` is 0.0 (FHD_GetMixingTime in Idle_Public unanswered). Leg 20260921T163334Z.
