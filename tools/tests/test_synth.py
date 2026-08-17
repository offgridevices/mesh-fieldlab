"""The generator and the tools that read it must agree, or neither is trusted.

The point of modelling one shared mesh rather than four independent nodes is
that cross-file behaviour becomes testable: the same transmission appears in
several files under one packet id, which is what deduplication, delivery share
and asymmetry all depend on.
"""

from __future__ import annotations

import re
import time

import pytest

from fieldlab import schema as S
from fieldlab.analyze import Session, asymmetry, link_stats, load_file
from fieldlab.synth import MeshConfig, synth_session
from fieldlab.validate import validate_text


def test_every_generated_file_passes_the_checker():
    for name, text in synth_session(MeshConfig()).items():
        result = validate_text(text, name)
        assert result.errors == [], (name, [str(i) for i in result.errors])
        assert result.warnings == [], (name, [str(i) for i in result.warnings])


def test_one_file_per_node():
    files = synth_session(MeshConfig(node_count=4))
    assert len(files) == 4
    stamp = time.strftime("%Y%m%d_%H%M", time.gmtime(MeshConfig().start_epoch))
    assert set(files) == {f"LOG_N{i}_{stamp}.csv" for i in range(1, 5)}


def test_a_node_with_no_clock_falls_back_to_the_boot_counter():
    # A logger that never learns the time cannot date its file. The name is
    # the only place that fact survives to whoever reads the card.
    files = synth_session(MeshConfig(node_count=4, set_clock=False, boot_count=9))
    assert set(files) == {f"LOG_N{i}_9.csv" for i in range(1, 5)}
    for name in files:
        assert re.match(S.FILENAME_PATTERN, name), name


def test_the_dated_name_is_not_misread_as_a_boot_counter():
    # LOG_N1_20260806_0706.csv could be parsed as short name "N1_20260806"
    # and boot count 0706 if the pattern allowed underscores in the name.
    # That would be a silent misparse, not an error, so it is pinned here.
    m = re.match(S.FILENAME_PATTERN, "LOG_N1_20260806_0706.csv")
    assert m is not None
    assert m.group("shortname") == "N1"
    assert m.group("date") == "20260806"
    assert m.group("time") == "0706"
    assert m.group("boot") is None


def test_the_same_transmission_appears_in_several_files():
    # The property that makes a session a session rather than four monologues.
    files = synth_session(MeshConfig(duration_s=600))
    seen_by: dict[str, set[str]] = {}
    for name, text in files.items():
        for line in text.splitlines()[1:]:
            parts = line.split(",")
            if parts[S.COLUMN_INDEX["row_type"]] != S.ROW_PKT:
                continue
            seen_by.setdefault(parts[S.COLUMN_INDEX["pkt_id"]], set()).add(name)

    shared = [ids for ids in seen_by.values() if len(ids) > 1]
    assert shared, "no packet reached more than one node"


def test_a_generated_session_analyses_into_links(tmp_path):
    files = synth_session(MeshConfig(duration_s=3600))
    session = Session()
    for name, text in files.items():
        path = tmp_path / name
        path.write_text(text)
        load_file(path, session)

    assert session.skipped == []
    assert len(session.nodes) == 4
    assert session.duplicates_dropped > 0, "no flood copies to remove"

    links = link_stats(session)
    assert len(links) == 12, "four nodes should give twelve directed links"
    assert all(s.distance_m is not None for s in links)
    assert all(-130 < s.rssi_median < -20 for s in links)


def test_distance_and_signal_strength_move_together(tmp_path):
    session = Session()
    for name, text in synth_session(MeshConfig(duration_s=3600)).items():
        path = tmp_path / name
        path.write_text(text)
        load_file(path, session)

    links = sorted(link_stats(session), key=lambda s: s.distance_m)
    nearest, farthest = links[0], links[-1]
    assert nearest.rssi_median > farthest.rssi_median, (
        "the closest pair should read stronger than the most distant one"
    )


def test_the_two_directions_of_a_pair_differ(tmp_path):
    # Real links are asymmetric. A generator that produced symmetric ones would
    # let a broken analysis look correct.
    session = Session()
    for name, text in synth_session(MeshConfig(duration_s=3600)).items():
        path = tmp_path / name
        path.write_text(text)
        load_file(path, session)

    pairs = asymmetry(link_stats(session))
    assert pairs
    assert max(diff for _, _, diff, _ in pairs) > 1.0


def test_delivery_share_is_a_fraction(tmp_path):
    session = Session()
    for name, text in synth_session(MeshConfig(duration_s=1800)).items():
        path = tmp_path / name
        path.write_text(text)
        load_file(path, session)

    for s in link_stats(session):
        assert s.heard_fraction is not None
        assert 0.0 < s.heard_fraction <= 1.0


def test_the_same_seed_gives_the_same_session():
    assert synth_session(MeshConfig(seed=3)) == synth_session(MeshConfig(seed=3))
    assert synth_session(MeshConfig(seed=3)) != synth_session(MeshConfig(seed=4))


def test_an_unset_clock_can_be_simulated():
    files = synth_session(MeshConfig(set_clock=False, duration_s=600))
    name, text = next(iter(files.items()))
    result = validate_text(text, name)
    assert result.ok
    assert not result.summary.clock_was_set
    assert "NO_ABSOLUTE_TIME" in {i.code for i in result.warnings}


@pytest.mark.parametrize("bad", [
    MeshConfig(node_count=1),
    MeshConfig(interval_s=0),
    MeshConfig(duration_s=10, interval_s=60),
])
def test_nonsense_settings_are_refused(bad):
    with pytest.raises(ValueError):
        synth_session(bad)
