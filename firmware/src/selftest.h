#pragma once

#include <Arduino.h>
#include <Meshtastic.h>

// The thirty seconds that decide whether a field day was worth driving to.
//
// Every check here answers a question that is cheap now and expensive later.
// None of them stop the node: a failure is shown, written into the log, and
// then logging starts anyway. A node recording with a bad clock is worth far
// more than a node refusing to start, because the analysis can be told about
// a known-bad field but cannot invent data nobody captured.
namespace SelfTest {

struct Result {
  bool     display_ok     = false;
  bool     card_mounted   = false;
  bool     card_writable  = false;
  uint32_t free_mb        = 0;

  bool     radio_ok       = false;   // it answered at all
  bool     have_config    = false;   // and told us how it is set up
  uint8_t  region         = 0;
  uint8_t  preset         = 0;
  uint8_t  hop_limit      = 0;
  bool     fixed_position = false;
  bool     tx_enabled     = false;

  bool     clock_set      = false;
  bool     clock_waited   = false;   // did the boot have to stop and wait?
  uint32_t clock_wait_ms  = 0;       // and for how long, whether or not it came
  uint8_t  battery_pct    = 0;
  uint8_t  heard_count    = 0;       // distinct neighbours during the listen

  // The radio's own position, as it reports it. Zero here with
  // fixed_position set means somebody skipped writing the coordinate.
  double   lat            = 0.0;
  double   lon            = 0.0;
  int32_t  alt            = 0;
};

// Fed by the callbacks in main while the test is running.
void noteRadioConfig(const mt_radio_config_t * config);
void notePacket(const mt_packet_meta_t * meta);
void noteOwnNode(const mt_node_t * node);

// Drives mt_loop() and the display through the whole sequence. Blocks for up
// to RADIO_WAIT_MS + BOOT_LISTEN_MS, which is the point — somebody is stood
// there watching it.
//
// nodeReportCb is the caller's node-report handler; the test asks for a report
// once the radio answers, and the caller both records it and feeds our own
// entry back through noteOwnNode.
Result run(bool displayOk, bool cardMounted, bool cardWritable, uint32_t freeMb,
           void (*nodeReportCb)(mt_node_t *, mt_nr_progress_t));

// Re-reads the values the radio keeps reporting — battery and position — into
// the result. Cheap, and meant to be called on every screen refresh: a battery
// gauge frozen at its boot reading is worse than none, because it looks live.
void refreshOwn(Result & r);

// Whether the rows this node writes can honestly be tied to a place.
//
// Requires both the fixed-position setting AND a coordinate behind it. Turning
// the setting on without entering a position is easy to do from a phone and
// leaves the node looking configured while it is not.
bool positionUsable(const Result & r);

// Records whether the radio is currently answering, and re-reads its settings
// whenever it starts. `alive` is the caller's judgement — Recovery owns it,
// because deciding a radio has gone quiet means watching the clock, not the
// protocol. Returns true only when the answer changed, so the caller can say
// so once rather than every loop.
//
// This has to move in both directions. A radio can outlast the boot test's
// patience — it is a whole Meshtastic device starting up, on the same supply,
// at the same moment — so a node that answers late must stop being shown as
// broken. And a radio can stop: a reset, a brownout, a connector shaken loose
// in a bag. Latching the first answer as final leaves that node displaying
// RADIO OK and recording nothing at all, for hours, with nobody there to see.
bool reviewRadio(Result & r, bool alive);

// Renders the outcome as `extra` for the BOOT row, so the file records what
// the screen said. Nobody remembers by the time the card is read.
void toExtra(const Result & r, uint32_t bootCount, char * out, size_t n);

// The single word shown large at the end of the test.
//
// Where more than one check failed this names the one that matters most,
// because a person reading a screen in a field wants the next action, not a
// complete account. The block row underneath carries the full picture.
const char * verdict(const Result & r);

const char * presetName(uint8_t preset);
const char * regionName(uint8_t region);

}  // namespace SelfTest
