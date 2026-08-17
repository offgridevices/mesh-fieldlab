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
#define LOGGER_VERSION    "0.8.0"

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

// Self-test: how long to wait for the radio to answer, and how often to ask.
//
// Both boards come up off the same supply at the same instant, so the logger
// is ready long before the radio has finished booting Meshtastic. Anything
// asked in that window is dropped without a reply and the library never asks
// twice, so the ask is repeated here until one lands.
//
// The wait only runs to the end when there is genuinely no radio; with one
// attached it exits the moment the radio names itself, normally in seconds.
#define RADIO_WAIT_MS       45000UL
#define RADIO_ASK_EVERY_MS   3000UL

#define BOOT_LISTEN_MS      30000UL   // Self-test: listen for neighbours
#define SCREEN_WAKE_MS      10000UL   // How long a button press lights the screen

// How long the boot waits for the time before logging without it.
//
// Nothing is logged until the clock is set, because a file that starts before
// the time is known cannot be lined up against the other three nodes. The wait
// ends the instant a packet arrives carrying the time — normally seconds after
// a phone connects — so this number is only the give-up bound, not the cost.
//
// It is bounded on purpose. An undated file still holds every RSSI and SNR
// reading, and every link statistic within itself; losing a whole session to a
// phone that would not pair is a far worse outcome than losing the timestamps.
//
//   0        log immediately, whatever the clock says (the old behaviour)
//   large    effectively refuse to log at all without a clock
#define CLOCK_WAIT_MS       600000UL  // ten minutes

// --- recovery ---------------------------------------------------------------
// Nothing the boot test can do may be a one-time-only ability. A card put in
// after the node was switched on, a radio that reset, a position set from a
// phone an hour into a session — all of these have to be picked up while the
// node keeps running, because the alternative is a person power-cycling a
// sealed box in a field and losing everything recorded so far.

#define SD_RETRY_MS         5000UL    // First remount attempt after a failure
#define RECOVERY_INTERVAL_MS 30000UL  // ...backing off to this, and staying there

// How long the radio may say nothing at all before it is treated as gone.
//
// Must comfortably exceed NODE_REPORT_MS, because on a silent mesh the periodic
// node report is the only thing that proves the radio is still there. One whole
// missed report plus most of another: a single dropped reply cannot condemn a
// working radio, and a genuinely dead one is still caught inside ten minutes.
#define RADIO_SILENT_MS     480000UL

// A node report asked for by the recovery tick rather than by the ordinary
// schedule is a liveness probe, not data. This is how long its replies are
// recognised as such and kept out of the file — at 40-odd known nodes, logging
// every probe would bury the packet rows.
#define PROBE_WINDOW_MS     10000UL

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
//
// CLOCK_WAIT_MS is deliberately not counted here: it is conditional, it ends
// as soon as the phone hands over the time, and the screen tells you what it
// is waiting for the whole time it waits.
#if (RADIO_WAIT_MS + BOOT_LISTEN_MS) > 90000UL
#error "Boot self-test is too long to stand and watch. Shorten the waits."
#endif

// A silence window shorter than the gap between node reports would condemn a
// perfectly good radio on a quiet mesh, every time, forever.
#if RADIO_SILENT_MS <= NODE_REPORT_MS
#error "RADIO_SILENT_MS must exceed NODE_REPORT_MS or a healthy radio reads as dead."
#endif
