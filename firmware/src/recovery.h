#pragma once

#include <Arduino.h>
#include <Meshtastic.h>

#include "selftest.h"

// The part that keeps a node useful after something goes wrong and then stops
// going wrong.
//
// The boot self-test answers five questions once, while somebody is stood
// there watching. Every one of those answers can change afterwards, and until
// now none of them could change back:
//
//   card    a node switched on with an empty slot could never start recording,
//           however many cards were pushed in afterwards
//   radio   a radio that reset mid-session went on reading OK forever, while
//           the node quietly logged nothing
//   pos     a coordinate set from a phone an hour in was picked up eventually,
//           but nothing said so and nothing recorded when
//   clock   already recovered on its own; watched here so it is reported
//   heard   already recovered on its own; watched here so it is reported
//
// The rule this module exists to enforce: nothing the boot test can do may be
// a one-time-only ability. The alternative is a person opening a sealed box in
// a field and power-cycling it, which loses every row recorded so far — so a
// node that cannot recover in place is a node that cannot be trusted to be
// left alone, which was the entire point of building it.
namespace Recovery {

// The five blocks, as bits, so a tick can report several at once.
enum Block : uint8_t {
  B_CARD  = 1 << 0,
  B_RADIO = 1 << 1,
  B_POS   = 1 << 2,
  B_CLOCK = 1 << 3,
  B_HEARD = 1 << 4,
};

// What changed on one tick. Both masks are zero on the overwhelming majority
// of ticks, which is what a working node looks like.
struct Event {
  uint8_t recovered = 0;   // blocks that came back
  uint8_t lost      = 0;   // blocks that went away
  //: A fresh file was opened because the card arrived late or was swapped. It
  //: holds a header and nothing else, so the caller must write it a BOOT row
  //: before anything else reaches it.
  bool    newFile   = false;
};

// Call once, after the boot self-test, with what that test concluded. Seeding
// the state from the boot result is what stops the first tick from announcing
// every already-working block as a fresh recovery.
void begin(const char * shortName, uint32_t bootCount,
           const SelfTest::Result & boot,
           void (*nodeReportCb)(mt_node_t *, mt_nr_progress_t));

// Any word at all from the radio — a packet, a config block, a node report.
// This is the only evidence that the serial link is still alive, so every
// callback must report in.
void noteRadioContact(uint32_t now);

// True while the node report currently arriving was asked for by this module
// rather than by the ordinary schedule.
//
// Those replies are a liveness probe, not data. With forty-odd nodes known to
// a radio, writing one row per node every thirty seconds would bury the packet
// rows the session exists to collect, so probe replies update the node's own
// state and are otherwise thrown away.
bool suppressNodeRows(uint32_t now);

// Call every loop. Owns the node-report schedule and every retry.
//
// `heardCount` is the one thing this module cannot see for itself: how many
// neighbours the caller has counted so far. Everything else it reads from the
// card, the clock and the radio.
//
// The self-test result is updated in place, and deliberately so. It is not a
// record of what was true at boot — it is what the screen's verdict and any
// later BOOT row are built from, and both have to describe the node as it is
// now, not as it was when somebody switched it on.
Event tick(uint32_t now, SelfTest::Result & r, uint8_t heardCount);

// Render a mask as "card+radio+pos", for the console and for the recov= key on
// a status row. Safe with an empty mask, which yields an empty string.
const char * describe(uint8_t mask, char * out, size_t n);

}  // namespace Recovery
