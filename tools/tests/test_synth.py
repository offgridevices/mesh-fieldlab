"""The generator and the checker must agree, or neither is trustworthy."""

from __future__ import annotations

from fieldlab import schema as S
from fieldlab.synth import SynthConfig, filename_for, synth_log
from fieldlab.validate import validate_text


def test_generated_files_pass_the_checker():
    config = SynthConfig()
    result = validate_text(synth_log(config), filename_for(config))
    assert result.errors == [], [str(i) for i in result.errors]
    assert result.warnings == [], [str(i) for i in result.warnings]


def test_a_generated_session_contains_what_a_real_one_would():
    config = SynthConfig(duration_s=1800, interval_s=20)
    result = validate_text(synth_log(config), filename_for(config))
    s = result.summary
    assert s.by_row_type[S.ROW_BOOT] == 1
    assert s.by_row_type[S.ROW_STATUS] >= 25
    assert len(s.direct_links) == len(config.peers)
    assert s.relayed_links
    assert s.duplicate_rows > 0
    assert s.clock_was_set


def test_the_same_seed_gives_the_same_file():
    assert synth_log(SynthConfig(seed=3)) == synth_log(SynthConfig(seed=3))
    assert synth_log(SynthConfig(seed=3)) != synth_log(SynthConfig(seed=4))


def test_an_unset_clock_can_be_simulated():
    config = SynthConfig(set_clock=False, duration_s=600)
    result = validate_text(synth_log(config), filename_for(config))
    assert result.ok
    assert not result.summary.clock_was_set
    assert "NO_ABSOLUTE_TIME" in {i.code for i in result.warnings}
