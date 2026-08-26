#pragma once

// ---------------------------------------------------------------------------
// The CSV contract.
//
// This must stay identical to tools/src/fieldlab/schema.py, which is the
// authority. A test in the Python suite reads this file and fails if the two
// drift apart, so a column added on one side cannot quietly go missing on the
// other.
//
// Changing anything here means bumping the version in both places and saying
// so in docs/packet-logger-design.md.
// ---------------------------------------------------------------------------

#define LOG_SCHEMA_VERSION 4

// One line, split only to stay readable. Keep the pieces comma-correct.
#define LOG_HEADER \
  "schema_ver,uptime_ms,dev_rx_time,rx_node,tx_node,to_node,pkt_id," \
  "rx_rssi_dbm,rx_snr_db,hop_limit,hop_start,hops_used,relay_node,next_hop," \
  "via_mqtt,portnum,decoded,payload_size,channel,row_type,extra"

// Packet columns, zeroed, for a row that is not a packet. The count has to
// track LOG_HEADER exactly: a row short by one column is rejected outright,
// and a row where the zeroes are merely in the wrong place is worse, because
// it parses. NO_PKT_COLS starts at tx_node; NO_PKT_AFTER_TX starts one later,
// for NODE rows, which carry their subject node in tx_node.
#define NO_PKT_AFTER_TX  "0,0,0,0.00,0,0,0,0,0,0,0,0,0,0,"
#define NO_PKT_COLS      "0," NO_PKT_AFTER_TX

#define ROW_PKT     "PKT"
#define ROW_STATUS  "STATUS"
#define ROW_NODE    "NODE"
#define ROW_BOOT    "BOOT"

// A reading the radio did not supply. Empty rather than a sentinel: every
// numeric sentinel is a value some radio could legitimately report, and a NaN
// put through printf reaches the card as "nan", which the checker rejects as
// a malformed number rather than reading as absent.
#define EXTRA_ABSENT    ""

// Values in the `extra` column may not contain either of these, or the field
// splits somewhere the reader cannot detect.
#define EXTRA_PAIR_SEP  ';'
#define EXTRA_KV_SEP    '='
