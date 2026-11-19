from nougen_shards.talkinghead import ACCOUNTS, cuts, pauses

LOG = """[silencedetect] silence_start: 0
[silencedetect] silence_end: 0.402208 | silence_duration: 0.402208
[silencedetect] silence_start: 1.831375
[silencedetect] silence_end: 2.067792 | silence_duration: 0.236417
[silencedetect] silence_start: 3.954042
[silencedetect] silence_end: 4.2385 | silence_duration: 0.284458
[silencedetect] silence_start: 6.160083
[silencedetect] silence_end: 6.7 | silence_duration: 0.539917"""


def test_pauses_skip_leading_silence():
    got = pauses(LOG)
    assert len(got) == 3 and abs(got[1] - 4.096) < 0.01


def test_locked_intro_cuts_once_at_the_pause():
    assert cuts(6.7, pauses(LOG)) == [4.096]


def test_short_line_is_one_job_and_no_pause_falls_back_to_hard_cut():
    assert cuts(4.0, []) == []
    assert cuts(10.0, []) == [4.6, 9.2]


def test_accounts_are_key_names_not_values():
    assert all(not a.startswith("hf_") for a in ACCOUNTS)
