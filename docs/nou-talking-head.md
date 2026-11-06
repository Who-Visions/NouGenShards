# NOU talking head (locked 2026-11-06)

Dave locked this on 2026-11-06 at 10:50 AM EST ("Love it. lock it"). The reference take is
`NOU/lipsync/nou_intro_v5_omniavatar.mp4` in Drive. Shard 28080 records the lock.

## The method

One still and one voice line go in. One audio-driven model makes the whole performance: head,
eyes, brows and lips all move from the audio together.

| Piece | Locked value |
| --- | --- |
| Model | OmniAvatar, through the HF Space `alexnasa/OmniAvatar` (free ZeroGPU) |
| Still | `~/.nougen/nou_assets/stills/expressions_2026-11-05/nou_neutral.png` |
| Voice | Kokoro `af_sky`, speed 1.05 |
| Steps | 4 (8 needs more GPU than one free job allows) |
| Output | 400x720 at 24 fps, upscaled with lanczos to 720x1296 |

```bash
./.venv/bin/python -m nougen_shards.talkinghead still.png line.wav out.mp4
```

## Long lines

A free job renders about 5 s of audio. The tool finds the pauses with ffmpeg `silencedetect`.
It cuts at the latest pause that keeps each chunk at 4.6 s or less, and cuts hard if there is no
pause. Each chunk starts from the last frame of the chunk before it, so the result plays as one
take. The last chunk gets 0.6 s of silence and a prompt that ends on a small smile.

## Quota

Each job uses about 170 s of an account's daily ZeroGPU quota. When one account runs out, the
tool moves on to the next Hugging Face account in the Keymaker. Code and docs list key names only.

## Rejected, do not return to

- **Wav2Lip over a still (v2).** Only the mouth moves, so it looks like a mouth mask on a photo.
- **Wan 2.2 animation, then Wav2Lip on top (v3, v4).** The pieces show at the seams. Extra
  chained clips, zooms and grain made it worse ("over engineered").
- **LongCat-Video-Avatar 1.5 Space.** Each job asks for 480 s of GPU, over the free per-job limit.
- **Running locally on blade.** Its RTX 2080 Max-Q has 8 GB, too small for the 14B avatar models.

Research behind the choice (2026-11-06, Exa): the Tight Studio open avatar model review (Aug 2026),
the Live Avatar paper (arXiv 2512.04677), and the InfiniteTalk and OmniAvatar project pages.
