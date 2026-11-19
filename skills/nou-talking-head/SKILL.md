---
name: nou-talking-head
description: Use when NOU (the NouGen News anchor) or any fleet character needs to speak on camera — an intro, a news line, a talking-head clip, "make her talk", "lip-sync this", "make it more natural". Runs the method the operator locked on 2026-11-06: one audio-driven OmniAvatar pass from a still and a voice line, chunked at pauses across Hugging Face accounts. Stops the rejected paths (Wav2Lip over a still, animate-then-lip-sync, stacked post effects).
---

# NOU talking head

Locked 2026-11-06 (shard 28080, `docs/nou-talking-head.md`). The reference take is
`NOU/lipsync/nou_intro_v5_omniavatar.mp4` in Drive.

## Run it

```bash
cd "NouGen/nougenshards"
./.venv/bin/python -m nougen_shards.talkinghead \
  ~/.nougen/nou_assets/stills/expressions_2026-11-05/nou_neutral.png line.wav out.mp4
```

It prints the output path, its length, where it cut the audio, and which account rendered each
chunk. Run it with the sandbox off: it needs the network and the Keychain.

## Rules

1. **One pass, audio-driven.** The model moves the face from the voice. Never animate first and
   lip-sync on top, and never lip-sync over a still.
2. **Don't add effects.** No zoom, grain, crossfades or extra clips unless the operator asks. When they say
   "more natural", change one thing and say which.
3. **Keys by name.** Accounts come from the Keymaker by key name (`ACCOUNTS` in the tool). Never
   print a token value. Listing keys means selecting the `secret_key` column only.
4. **Quota.** About 170 s of GPU per 5 s chunk. If every account is out, say when the quota
   resets. HF Pro costs money, so offer it and let the operator decide.
5. **Look before you send.** Check a contact sheet of frames, and say whether you watched it with sound.
