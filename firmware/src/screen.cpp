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

// Five blocks in a fixed order. A passing check is solid, so all-good is an
// even rhythm of marks and any failure is a hole in it — visible before the
// letters are read. A failure also carries a slash, so it cannot be mistaken
// for a smudge.
void checks(const bool ok[CHK_COUNT], uint8_t y) {
  static const char * LABEL[CHK_COUNT] = {"C", "R", "P", "K", "H"};
  small();
  for (uint8_t i = 0; i < CHK_COUNT; i++) {
    uint8_t x = i * 20;
    if (ok[i]) {
      g_oled.drawBox(x, y, 14, 11);
      g_oled.setDrawColor(0);
      g_oled.drawStr(x + 5, y + 9, LABEL[i]);
      g_oled.setDrawColor(1);
    } else {
      g_oled.drawFrame(x, y, 14, 11);
      g_oled.drawStr(x + 5, y + 9, LABEL[i]);
      g_oled.drawLine(x + 1, y + 9, x + 12, y + 1);
    }
  }
}

void header(const char * left, const char * right) {
  small();
  g_oled.drawStr(0, 7, left);
  if (right) rightStr(W, 7, right);
  g_oled.drawHLine(0, 10, W);
}

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

// 1 · Is it still recording?
void pageActivity(const NodeView & v) {
  char up[12], last[12], line[26];
  uint32_t h = v.uptimeSec / 3600, m = (v.uptimeSec / 60) % 60;
  snprintf(up, sizeof(up), "%luh%02lum", (unsigned long)h, (unsigned long)m);

  header("ACTIVITY", up);

  // The packet count is the headline: it is the one number that proves the
  // node is doing its job right now.
  large();
  snprintf(line, sizeof(line), "%lu", (unsigned long)v.packets);
  g_oled.drawStr(0, 28, line);
  uint8_t w = g_oled.getStrWidth(line);
  small();
  g_oled.drawStr(w + 5, 28, "heard");

  if (v.everHeard) {
    ago(last, sizeof(last), v.secsSinceLast);
    snprintf(line, sizeof(line), "last %s ago", last);
  } else {
    snprintf(line, sizeof(line), "none yet");
  }
  rightStr(W, 20, v.cardOk ? "card ok" : "CARD BAD");
  rightStr(W, 30, line);
}

// 2 · Who can it hear, and how well?
void pageNeighbours(const NodeView & v) {
  char count[10];
  snprintf(count, sizeof(count), "%u", (unsigned)v.neighbourCount);
  header("HEARD", count);

  small();
  if (v.neighbourCount == 0) {
    g_oled.drawStr(0, 22, "nothing yet");
    g_oled.drawStr(0, 31, "check the others are on");
    return;
  }

  char line[26];
  // Two per row, four visible. More than four neighbours is not this build.
  for (uint8_t i = 0; i < v.neighbourCount && i < 4; i++) {
    uint8_t col = i % 2, row = i / 2;
    snprintf(line, sizeof(line), "%lu %ddB",
             (unsigned long)(v.neighbour[i] % 10000),
             (int)v.neighbourRssi[i]);
    g_oled.drawStr(col * 64, 21 + row * 9, line);
  }
}

// 3 · Is it set up the same as the other three?
void pageRadio(const NodeView & v) {
  char node[14];
  snprintf(node, sizeof(node), "%lu", (unsigned long)(v.myNode % 100000));
  header("RADIO", v.ok[CHK_RADIO] ? node : "NO ANSWER");

  small();
  char line[26];
  snprintf(line, sizeof(line), "%s  %s  hop %u", v.region, v.preset, (unsigned)v.hops);
  g_oled.drawStr(0, 21, line);
  snprintf(line, sizeof(line), "pos %s   clock %s",
           v.ok[CHK_POS] ? "set" : "NO", v.ok[CHK_CLOCK] ? "set" : "NO");
  g_oled.drawStr(0, 31, line);
}

// 4 · Will it last the session?
void pageStorage(const NodeView & v) {
  char mb[14];
  snprintf(mb, sizeof(mb), "%lu MB", (unsigned long)v.freeMb);
  header("CARD", v.cardOk ? mb : "FAILED");

  small();
  g_oled.drawStr(0, 21, v.fileName[0] ? v.fileName : "not recording");

  char line[26];
  snprintf(line, sizeof(line), "%lu rows written", (unsigned long)v.rows);
  g_oled.drawStr(0, 31, line);
  battery(105, 20, v.batteryPct);
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
  switch (index % PAGE_COUNT) {
    case 0: pageSummary(v);    break;
    case 1: pageActivity(v);   break;
    case 2: pageNeighbours(v); break;
    case 3: pageRadio(v);      break;
    default: pageStorage(v);   break;
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
