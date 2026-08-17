#pragma once

// ---------------------------------------------------------------------------
// Per-node settings.
//
// This is the only block that differs between the four units. Change
// NODE_SHORT_NAME, flash, label the box, move on. Everything else is
// identical by design: four units that differ only in a string are four
// units that behave the same way in a field.
// ---------------------------------------------------------------------------

#define NODE_SHORT_NAME   "N1"                // Also the log filename stem
#define ANTENNA_MODEL     "rak-stock-3dbi"    // Recorded in every file
#define LOGGER_VERSION    "0.2.0"

// --- timezone --------------------------------------------------------------
// A POSIX timezone rule, not a fixed offset. The two dates on the end are the
// daylight-saving changeovers, so the offset is correct year-round without the
// firmware knowing anything about today's date.
//
// This affects log FILENAMES only, which are in local time because a person
// reading a card wants to recognise the afternoon they collected it. Every
// timestamp inside the rows stays UTC. Change this if the nodes are ever run
// in another zone; the analysis does not depend on it either way.
//
//   US Eastern    EST5EDT,M3.2.0,M11.1.0
//   US Central    CST6CDT,M3.2.0,M11.1.0
//   US Mountain   MST7MDT,M3.2.0,M11.1.0
//   US Pacific    PST8PDT,M3.2.0,M11.1.0
//   UTC           UTC0
#define TZ_POSIX          "EST5EDT,M3.2.0,M11.1.0"

// --- wiring ----------------------------------------------------------------
// See docs/packet-logger-design.md §5.2. Changing these means changing that
// table too.

#define RADIO_RX_PIN      D7      // to the radio's TX
#define RADIO_TX_PIN      D6      // to the radio's RX
#define RADIO_BAUD        38400

#define SD_CS_PIN         D3      // SCK/MISO/MOSI are the board defaults

#define BUTTON_PIN        D0      // to ground; uses the internal pull-up

// --- timings ---------------------------------------------------------------

#define FLUSH_INTERVAL_MS   5000UL    // A field day that dies with data in RAM
#define FLUSH_EVERY_ROWS    10        // is a wasted field day. Flush often.

#define STATUS_INTERVAL_MS  60000UL
#define NODE_REPORT_MS      300000UL

#define RADIO_WAIT_MS       15000UL   // Self-test: wait for the radio to answer
#define BOOT_LISTEN_MS      30000UL   // Self-test: listen for neighbours
#define SCREEN_WAKE_MS      10000UL   // How long a button press lights the screen

#define SD_RETRY_MS         5000UL    // Remount attempts after a card failure

// --- console ---------------------------------------------------------------
// Everything the screen shows is also written to USB serial, so a node can be
// brought up on a bench before the display exists and diagnosed later without
// one. In the field nothing is plugged in and the writes go nowhere.

#define SERIAL_ECHO          1        // boot banner, self-test, status
#define SERIAL_ECHO_PACKETS  1        // one line per received packet
#define SERIAL_WAIT_MS       2000UL   // bounded wait for the host to attach

// --- sanity ----------------------------------------------------------------
// A whole boot is roughly RADIO_WAIT_MS + BOOT_LISTEN_MS of standing there.
// Much beyond a minute and people stop watching it, which defeats the point.
#if (RADIO_WAIT_MS + BOOT_LISTEN_MS) > 90000UL
#error "Boot self-test is too long to stand and watch. Shorten the waits."
#endif
