from nougen_shards.remotion_engine import CompositionSpec, RemotionTimelineCalculator


def test_composition_spec():
    spec = CompositionSpec(id="PromoVideo", fps=60, duration_in_frames=600)
    assert spec.duration_in_seconds == 10.0
    cli_args = spec.to_remotion_cli_args("src/index.ts", "out/promo.mp4")
    assert cli_args[:5] == ["npx", "remotion", "render", "src/index.ts", "PromoVideo"]
    assert cli_args[5] == "out/promo.mp4"


def test_timeline_calculator():
    calc = RemotionTimelineCalculator()
    assert calc.seconds_to_frame(2.5, fps=30) == 75
    assert calc.frame_to_seconds(90, fps=30) == 3.0

    spring_p0 = calc.calculate_spring_steps(0, fps=30)
    spring_p30 = calc.calculate_spring_steps(30, fps=30)
    assert spring_p0 == 0.0
    assert spring_p30 > 0.8


def test_transcript_alignment():
    words = [
        {"word": "Autonomous", "start": 0.0, "end": 0.5},
        {"word": "Fleet", "start": 0.6, "end": 1.1},
    ]
    aligned = RemotionTimelineCalculator.align_transcript_words(words, fps=30)
    assert len(aligned) == 2
    assert aligned[0]["start_frame"] == 0
    assert aligned[0]["end_frame"] == 15
    assert aligned[1]["start_frame"] == 18
    assert aligned[1]["end_frame"] == 33
