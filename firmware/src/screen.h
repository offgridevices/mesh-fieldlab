#pragma once

#include <Arduino.h>

// The 0.91" OLED, on its own two-wire bus.
//
// Everything here is best-effort. If the display is absent, broken, or at an
// address we did not guess, the node logs exactly as well without it — a
// screen must never be able to cost a session.
namespace Screen {

//: The checks shown as state blocks, in a fixed order that never changes.
//: Position is what makes them readable without reading.
enum Check : uint8_t { CHK_CARD, CHK_RADIO, CHK_POS, CHK_CLOCK, CHK_HEARD, CHK_COUNT };

constexpr uint8_t MAX_NEIGHBOURS = 8;

//: Everything any page might want to show. Filled in by main; the screen
//: never reaches back for anything.
struct NodeView {
  bool     ok[CHK_COUNT] = {false, false, false, false, false};
  const char * verdict   = "STARTING";
  uint8_t  batteryPct    = 0;

  uint32_t uptimeSec     = 0;
  uint32_t packets       = 0;
  uint32_t rows          = 0;
  uint32_t secsSinceLast = 0;
  bool     everHeard     = false;
  bool     cardOk        = false;

  const char * region    = "?";
  const char * preset    = "?";
  uint8_t  hops          = 0;
  uint32_t myNode        = 0;

  double   lat           = 0.0;
  double   lon           = 0.0;

  uint32_t freeMb        = 0;
  const char * fileName  = "";

  //: Local date and time as text. The screen computes nothing — main fills
  //: these from Clock, so what the clock page shows can never disagree with
  //: the date on the filename.
  char dateText[16]      = "no date";
  char timeText[16]      = "--:--";

  uint32_t neighbour[MAX_NEIGHBOURS]      = {0};
  uint32_t neighbourPkts[MAX_NEIGHBOURS]  = {0};
  int16_t  neighbourRssi[MAX_NEIGHBOURS]  = {0};
  uint8_t  neighbourCount = 0;
};

//: How many pages the button cycles through.
//:
//: Page 0 is the summary. Pages 1..5 are the five state blocks in the order
//: they appear in that summary row — C, R, P, K, H — each opening on the same
//: block it came from, so the menu is the home screen read one at a time
//: rather than a separate thing to learn. Page 6 is everything else.
constexpr uint8_t PAGE_COUNT = 7;

// Probes both addresses these modules ship with. Returns false if neither
// answers, after which every other call here is a no-op.
bool begin();

bool present();
uint8_t address();

// Four lines of small text. Used while the self-test is still running, where
// what matters is which step is in progress rather than the verdict.
void show(const char * l1, const char * l2 = nullptr,
          const char * l3 = nullptr, const char * l4 = nullptr);

// Draw one page of the menu. Page 0 is the summary — one word large enough to
// read at arm's length, a row of state blocks, and the battery as a shape.
// Later pages answer progressively more specific questions.
void page(uint8_t index, const NodeView & v);

// Power down the panel. Draws microamps until woken.
void sleep();
void wake();

}  // namespace Screen
