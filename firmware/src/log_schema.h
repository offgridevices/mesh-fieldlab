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

#define LOG_SCHEMA_VERSION 3

// One line, split only to stay readable. Keep the pieces comma-correct.
#define LOG_HEADER \
  "schema_ver,uptime_ms,dev_rx_time,rx_node,tx_node,pkt_id,rx_rssi_dbm," \
  "rx_snr_db,hop_limit,hop_start,hops_used,relay_node,next_hop,via_mqtt," \
  "portnum,payload_size,channel,row_type,extra"

#define ROW_PKT     "PKT"
#define ROW_STATUS  "STATUS"
#define ROW_NODE    "NODE"
#define ROW_BOOT    "BOOT"

// Values in the `extra` column may not contain either of these, or the field
// splits somewhere the reader cannot detect.
#define EXTRA_PAIR_SEP  ';'
#define EXTRA_KV_SEP    '='
