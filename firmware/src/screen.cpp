#include "screen.h"

#include <U8g2lib.h>
#include <Wire.h>

#include "config.h"

namespace Screen {
namespace {

// These modules ship at one of two addresses and the silkscreen rarely says
// which. Guessing wrong looks exactly like a dead screen, so try both.
const uint8_t CANDIDATES[] = {0x3C, 0x3D};

U8G2_SSD1306_128X32_UNIVISION_F_HW_I2C g_oled(U8G2_R0, U8X8_PIN_NONE);

bool    g_present = false;
uint8_t g_address = 0;
bool    g_asleep  = false;

const uint8_t W = 128, H = 32;

bool answersAt(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

void small() { g_oled.setFont(u8g2_font_5x8_tf); }
void large() { g_oled.setFont(u8g2_font_9x15B_tf); }

void rightStr(uint8_t x_right, uint8_t baseline, const char * s) {
  g_oled.drawStr(x_right - g_oled.getStrWidth(s), baseline, s);
}

// A shape rather than a number, because a shape is read without being read.
void battery(uint8_t x, uint8_t y, uint8_t pct) {
  g_oled.drawFrame(x, y, 19, 11);
  g_oled.drawBox(x + 19, y + 3, 2, 5);
  if (pct > 100) pct = 100;
  uint8_t fill = (uint8_t)((15u * pct) / 100u);
  if (pct > 0 && fill == 0) fill = 1;          // never show empty when it is not
  if (fill) g_oled.drawBox(x + 2, y + 2, fill, 7);
  if (pct == 0) {                               // unknown, not flat
    g_oled.drawStr(x + 6, y + 9, "?");
  }
}

//: The letters, in the order they appear in the summary row and in the order
//: the button walks through the pages. Indexed by Check.
const char * LABEL[CHK_COUNT] = {"C", "R", "P", "K", "H"};

// One state block. Solid means passing; a hollow block also carries a slash,
// so a failure cannot be mistaken for a smudge.
//
// Every block on the device comes through here — the summary row and the
// detail pages alike — so the mark at the top of a detail page is literally
// the same drawing as the one you pressed to get there.
void block(uint8_t x, uint8_t y, const char * label, bool ok) {
  small();
  if (ok) {
    g_oled.drawBox(x, y, 14, 11);
    g_oled.setDrawColor(0);
    g_oled.drawStr(x + 5, y + 9, label);
    g_oled.setDrawColor(1);
  } else {
    g_oled.drawFrame(x, y, 14, 11);
    g_oled.drawStr(x + 5, y + 9, label);
    g_oled.drawLine(x + 1, y + 9, x + 12, y + 1);
  }
}

// Five blocks in a fixed order. A passing check is solid, so all-good is an
// even rhythm of marks and any failure is a hole in it — visible before the
// letters are read.
void checks(const bool ok[CHK_COUNT], uint8_t y) {
  for (uint8_t i = 0; i < CHK_COUNT; i++) block(i * 20, y, LABEL[i], ok[i]);
}

//: Where a detail page's title starts, clear of the block to its left.
const uint8_t TITLE_X = 18;

// A detail page's header, read left to right in the order the question is
// asked: which check this is, what it is called, and how it is doing.
//
//   [C] CARD                1871 MB
//   -------------------------------
//
// The block leads because it is the thing that was wrong on the summary row —
// you pressed through to this page to find out about that mark, so it is what
// the page opens with. `right` is the page's headline fact.
void detailHeader(const char * title, Check which, const bool ok[CHK_COUNT],
                  const char * right) {
  block(0, 0, LABEL[which], ok[which]);
  small();
  g_oled.drawStr(TITLE_X, 9, title);
  if (right) rightStr(W, 9, right);
  g_oled.drawHLine(0, 12, W);
}

// The two body lines every detail page has room for. Naming them stops each
// page inventing its own baselines and drifting a pixel out from the others.
const uint8_t LINE1 = 22, LINE2 = 31;

void ago(char * out, size_t n, uint32_t secs) {
  if (secs < 90) snprintf(out, n, "%lus", (unsigned long)secs);
  else if (secs < 5400) snprintf(out, n, "%lum", (unsigned long)(secs / 60));
  else snprintf(out, n, "%luh", (unsigned long)(secs / 3600));
}

// --- the pages -------------------------------------------------------------

// 0 · Walk away, or not?
void pageSummary(const NodeView & v) {
  large();
  g_oled.drawStr(0, 13, NODE_SHORT_NAME);
  rightStr(W, 13, v.verdict);
  checks(v.ok, 20);
  battery(105, 20, v.batteryPct);
}

// 1 · C — is it recording, and will the card last the session?
void pageCard(const NodeView & v) {
  char mb[14];
  snprintf(mb, sizeof(mb), "%lu MB", (unsigned long)v.freeMb);
  detailHeader("CARD", CHK_CARD, v.ok, v.cardOk ? mb : "FAILED");

  small();
  g_oled.drawStr(0, LINE1, v.fileName[0] ? v.fileName : "not recording");

  // Rows climbing is the proof it is still working, not merely still on.
  char line[26];
  snprintf(line, sizeof(line), "%lu rows written", (unsigned long)v.rows);
  g_oled.drawStr(0, LINE2, line);
}

// 2 · R — is it set up the same as the other three?
void pageRadio(const NodeView & v) {
  char node[14];
  snprintf(node, sizeof(node), "%lu", (unsigned long)(v.myNode % 100000));
  detailHeader("RADIO", CHK_RADIO, v.ok, v.ok[CHK_RADIO] ? node : "NO ANSWER");

  small();
  char line[26];
  snprintf(line, sizeof(line), "%s  %s", v.region, v.preset);
  g_oled.drawStr(0, LINE1, line);
  snprintf(line, sizeof(line), "hop limit %u", (unsigned)v.hops);
  g_oled.drawStr(0, LINE2, line);
}

// 3 · P — can these rows be tied to a place?
void pagePosition(const NodeView & v) {
  detailHeader("POSITION", CHK_POS, v.ok, v.ok[CHK_POS] ? "fixed" : "NOT SET");

  small();
  if (!v.ok[CHK_POS]) {
    g_oled.drawStr(0, LINE1, "no fixed position set");
    g_oled.drawStr(0, LINE2, "rows have no place");
    return;
  }

  char line[26];
  snprintf(line, sizeof(line), "lat %.5f", v.lat);
  g_oled.drawStr(0, LINE1, line);
  snprintf(line, sizeof(line), "lon %.5f", v.lon);
  g_oled.drawStr(0, LINE2, line);
}

// 4 · K — can this file be lined up against the other three?
void pageClock(const NodeView & v) {
  detailHeader("CLOCK", CHK_CLOCK, v.ok, v.ok[CHK_CLOCK] ? nullptr : "NOT SET");

  small();
  if (!v.ok[CHK_CLOCK]) {
    g_oled.drawStr(0, LINE1, "connect your phone to");
    g_oled.drawStr(0, LINE2, "any node on the mesh");
    return;
  }
  g_oled.drawStr(0, LINE1, v.dateText);
  g_oled.drawStr(0, LINE2, v.timeText);
}

// 5 · H — who can it hear, and how well?
void pageHeard(const NodeView & v) {
  char count[10];
  snprintf(count, sizeof(count), "%u", (unsigned)v.neighbourCount);
  detailHeader("HEARD", CHK_HEARD, v.ok, count);

  small();
  if (v.neighbourCount == 0) {
    g_oled.drawStr(0, LINE1, "nothing yet");
    g_oled.drawStr(0, LINE2, "check the others are on");
    return;
  }

  char line[26];
  // Two per row, four visible. More than four neighbours is not this build.
  for (uint8_t i = 0; i < v.neighbourCount && i < 4; i++) {
    uint8_t col = i % 2, row = i / 2;
    snprintf(line, sizeof(line), "%lu %ddB",
             (unsigned long)(v.neighbour[i] % 10000),
             (int)v.neighbourRssi[i]);
    g_oled.drawStr(col * 64, LINE1 + row * 9, line);
  }
}

// 6 · Everything with no block of its own: power, and how busy it has been.
void pagePower(const NodeView & v) {
  // Drawn to detailHeader's geometry by hand: this is the one page with no
  // block of its own, so the battery shape stands in the icon's place and the
  // run of pages keeps its rhythm.
  char pct[8];
  snprintf(pct, sizeof(pct), "%u%%", (unsigned)v.batteryPct);
  battery(0, 0, v.batteryPct);
  small();
  g_oled.drawStr(25, 9, "POWER");
  rightStr(W, 9, pct);
  g_oled.drawHLine(0, 12, W);

  char line[26], last[12];
  uint32_t h = v.uptimeSec / 3600, m = (v.uptimeSec / 60) % 60;
  snprintf(line, sizeof(line), "up %luh%02lum",
           (unsigned long)h, (unsigned long)m);
  g_oled.drawStr(0, LINE1, line);

  if (v.everHeard) {
    ago(last, sizeof(last), v.secsSinceLast);
    snprintf(line, sizeof(line), "%lu heard  last %s",
             (unsigned long)v.packets, last);
  } else {
    snprintf(line, sizeof(line), "%lu heard  none yet",
             (unsigned long)v.packets);
  }
  g_oled.drawStr(0, LINE2, line);
}

}  // namespace

bool begin() {
  Wire.begin();
  for (uint8_t addr : CANDIDATES) {
    if (!answersAt(addr)) continue;
    g_address = addr;
    g_oled.setI2CAddress(addr << 1);  // U8g2 wants the 8-bit form
    if (!g_oled.begin()) return false;
    g_oled.setFont(u8g2_font_5x8_tf);
    g_present = true;
    return true;
  }
  return false;
}

bool present() { return g_present; }
uint8_t address() { return g_address; }

void show(const char * l1, const char * l2, const char * l3, const char * l4) {
  if (!g_present) return;
  if (g_asleep) wake();

  const char * lines[4] = {l1, l2, l3, l4};
  g_oled.clearBuffer();
  small();
  for (int i = 0; i < 4; i++) {
    if (lines[i] != nullptr) g_oled.drawStr(0, 7 + i * 8, lines[i]);
  }
  g_oled.sendBuffer();
}

void page(uint8_t index, const NodeView & v) {
  if (!g_present) return;
  if (g_asleep) wake();

  g_oled.clearBuffer();
  // The order is the summary row read one block at a time, then everything
  // that has no block, then back to the summary.
  switch (index % PAGE_COUNT) {
    case 0: pageSummary(v);  break;
    case 1: pageCard(v);     break;   // C
    case 2: pageRadio(v);    break;   // R
    case 3: pagePosition(v); break;   // P
    case 4: pageClock(v);    break;   // K
    case 5: pageHeard(v);    break;   // H
    default: pagePower(v);   break;
  }
  g_oled.sendBuffer();
}

void sleep() {
  if (!g_present || g_asleep) return;
  g_oled.setPowerSave(1);
  g_asleep = true;
}

void wake() {
  if (!g_present || !g_asleep) return;
  g_oled.setPowerSave(0);
  g_asleep = false;
}

}  // namespace Screen
