"""The analysis makes three decisions that would each silently ruin a result.

These tests exist mostly to pin those three: relayed packets are excluded,
flood copies are removed before counting, and every figure is a median.
"""

from __future__ import annotations

import pytest

from conftest import RX_NODE, TX_NODE, make_file, row
from fieldlab import schema as S
from fieldlab.analyze import (
    NodeInfo,
    Session,
    asymmetry,
    haversine_m,
    link_stats,
    load_directory,
    load_file,
)


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return path


def boot(node=RX_NODE, **extra) -> str:
    pairs = {
        "fw": "0.1.0", "preset": "LONG_FAST", "boot": "1",
        "lat": "39.8283", "lon": "-98.5795", "alt": "0", "ant": "stock",
        "region": "US", "hops": "3",
    }
    pairs.update({k: str(v) for k, v in extra.items()})
    return row(S.ROW_BOOT, rx_node=node, extra=S.format_extra(pairs))


def pkt(pkt_id, rssi=-80, snr=5.0, hops=0, tx=TX_NODE, rx=RX_NODE, uptime=1000) -> str:
    return row(
        S.ROW_PKT, rx_node=rx, tx_node=tx, pkt_id=pkt_id,
        rx_rssi_dbm=rssi, rx_snr_db=snr,
        hop_start=3, hop_limit=3 - hops, hops_used=hops,
        uptime_ms=uptime, dev_rx_time=1786000000 + uptime // 1000,
    )


# ---------------------------------------------------------------------------
# The three decisions
# ---------------------------------------------------------------------------


def test_relayed_packets_do_not_contribute_to_a_link(tmp_path):
    # A relayed packet measures the last hop, not this pair of nodes.
    text = make_file(boot(), pkt(1, hops=0), pkt(2, hops=1), pkt(3, hops=2))
    session = Session()
    load_file(write(tmp_path, "LOG_N1_1.csv", text), session)

    stats = link_stats(session)
    assert len(stats) == 1
    assert stats[0].packets == 1
    assert stats[0].relayed_packets == 2


def test_flood_copies_are_removed_before_anything_is_counted(tmp_path):
    text = make_file(boot(), pkt(7, rssi=-70), pkt(7, rssi=-70), pkt(7, rssi=-70))
    session = Session()
    load_file(write(tmp_path, "LOG_N1_1.csv", text), session)

    assert session.duplicates_dropped == 2
    assert link_stats(session)[0].packets == 1


def test_a_single_outlier_does_not_drag_the_result(tmp_path):
    # Nine readings near -80 and one multipath null at -120. A mean would
    # report about -84; the median is where the link actually lives.
    rows = [pkt(i, rssi=-80) for i in range(1, 10)] + [pkt(99, rssi=-120)]
    session = Session()
    load_file(write(tmp_path, "LOG_N1_1.csv", make_file(boot(), *rows)), session)

    stats = link_stats(session)[0]
    assert stats.rssi_median == -80
    # The null is not hidden either — it drags the low tail well below the
    # median, which is what the tail is there to show.
    assert stats.rssi_p10 < -100
    assert stats.rssi_p90 == -80


def test_below_ten_samples_the_tails_are_the_extremes(tmp_path):
    # Interpolated percentiles are meaningless over a handful of readings, so
    # the range is reported honestly instead of dressed up.
    rows = [pkt(1, rssi=-70), pkt(2, rssi=-80), pkt(3, rssi=-95)]
    session = Session()
    load_file(write(tmp_path, "LOG_N1_1.csv", make_file(boot(), *rows)), session)

    stats = link_stats(session)[0]
    assert (stats.rssi_p10, stats.rssi_median, stats.rssi_p90) == (-95, -80, -70)


# ---------------------------------------------------------------------------
# Reading a session
# ---------------------------------------------------------------------------


def test_a_file_the_checker_rejects_is_not_analysed(tmp_path):
    bad = make_file(boot(), pkt(1, tx=RX_NODE))  # a node hearing itself
    session = Session()
    load_file(write(tmp_path, "LOG_N1_1.csv", bad), session)

    assert session.files == []
    assert len(session.skipped) == 1
    assert "SELF_RECEPTION" in session.skipped[0][1]


def test_force_analyses_it_anyway(tmp_path):
    bad = make_file(boot(), pkt(1, tx=RX_NODE))
    session = Session()
    load_file(write(tmp_path, "LOG_N1_1.csv", bad), session, force=True)
    assert len(session.files) == 1


def test_a_whole_directory_loads_as_one_session(tmp_path):
    write(tmp_path, "LOG_N1_1.csv", make_file(boot(RX_NODE), pkt(1)))
    write(tmp_path, "LOG_N2_1.csv",
          make_file(boot(TX_NODE), pkt(2, tx=RX_NODE, rx=TX_NODE)))

    session = load_directory(tmp_path)
    assert len(session.files) == 2
    assert set(session.nodes) == {RX_NODE, TX_NODE}
    assert len(link_stats(session)) == 2  # both directions


def test_locally_originated_rows_are_not_receptions(tmp_path):
    # rssi of exactly zero means the node originated it, not heard it.
    text = make_file(boot(), pkt(1, rssi=0), pkt(2, rssi=-80))
    session = Session()
    load_file(write(tmp_path, "LOG_N1_1.csv", text), session, force=True)
    assert len(session.receptions) == 1


def test_the_boot_row_supplies_the_node_description(tmp_path):
    text = make_file(boot(name="N1", lat="39.8", lon="-98.5", alt="42"), pkt(1))
    session = Session()
    load_file(write(tmp_path, "LOG_N1_1.csv", text), session)

    node = session.nodes[RX_NODE]
    assert node.name == "N1"
    assert node.alt == 42
    assert node.preset == "LONG_FAST"
    assert node.has_position


# ---------------------------------------------------------------------------
# Things that invalidate a comparison
# ---------------------------------------------------------------------------


def test_nodes_configured_differently_are_flagged(tmp_path):
    write(tmp_path, "LOG_N1_1.csv", make_file(boot(RX_NODE, preset="LONG_FAST"), pkt(1)))
    write(tmp_path, "LOG_N2_1.csv",
          make_file(boot(TX_NODE, preset="MEDIUM_FAST"),
                    pkt(2, tx=RX_NODE, rx=TX_NODE)))

    problems = load_directory(tmp_path).config_mismatches()
    assert any("preset" in p for p in problems)


def test_matching_configuration_says_nothing(tmp_path):
    write(tmp_path, "LOG_N1_1.csv", make_file(boot(RX_NODE), pkt(1)))
    write(tmp_path, "LOG_N2_1.csv", make_file(boot(TX_NODE), pkt(2, tx=RX_NODE, rx=TX_NODE)))
    assert load_directory(tmp_path).config_mismatches() == []


def test_a_node_without_a_coordinate_yields_no_distance(tmp_path):
    write(tmp_path, "LOG_N1_1.csv", make_file(boot(RX_NODE), pkt(1)))
    write(tmp_path, "LOG_N2_1.csv",
          make_file(boot(TX_NODE, lat="0", lon="0"),
                    pkt(2, tx=RX_NODE, rx=TX_NODE)), )

    session = load_directory(tmp_path, force=True)
    assert any(s.distance_m is None for s in link_stats(session))


# ---------------------------------------------------------------------------
# Geometry and asymmetry
# ---------------------------------------------------------------------------


def test_distance_between_two_known_points():
    a = NodeInfo(node=1, lat=39.8283, lon=-98.5795)
    b = NodeInfo(node=2, lat=39.8373, lon=-98.5795)  # 0.009 deg north
    metres = haversine_m(a, b)
    assert 995 < metres < 1010


def test_distance_is_none_without_both_positions():
    a = NodeInfo(node=1, lat=39.8, lon=-98.5)
    b = NodeInfo(node=2)
    assert haversine_m(a, b) is None


def test_the_two_directions_of_a_pair_are_compared(tmp_path):
    write(tmp_path, "LOG_N1_1.csv",
          make_file(boot(RX_NODE), *[pkt(i, rssi=-70) for i in range(1, 6)]))
    write(tmp_path, "LOG_N2_1.csv",
          make_file(boot(TX_NODE),
                    *[pkt(i, rssi=-84, tx=RX_NODE, rx=TX_NODE) for i in range(10, 15)]))

    pairs = asymmetry(link_stats(load_directory(tmp_path)))
    assert len(pairs) == 1
    _, _, difference, worse = pairs[0]
    assert difference == pytest.approx(14.0)
    assert worse == -84


def test_a_one_way_link_has_nothing_to_compare(tmp_path):
    write(tmp_path, "LOG_N1_1.csv", make_file(boot(RX_NODE), pkt(1)))
    assert asymmetry(link_stats(load_directory(tmp_path))) == []


def test_an_empty_directory_is_an_empty_session(tmp_path):
    session = load_directory(tmp_path)
    assert session.files == []
    assert link_stats(session) == []
