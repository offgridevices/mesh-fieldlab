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
#define LOGGER_VERSION    "0.1.0"

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

// --- sanity ----------------------------------------------------------------
// A whole boot is roughly RADIO_WAIT_MS + BOOT_LISTEN_MS of standing there.
// Much beyond a minute and people stop watching it, which defeats the point.
#if (RADIO_WAIT_MS + BOOT_LISTEN_MS) > 90000UL
#error "Boot self-test is too long to stand and watch. Shorten the waits."
#endif
