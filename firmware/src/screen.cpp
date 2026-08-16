#include "screen.h"

#include <U8g2lib.h>
#include <Wire.h>

namespace Screen {
namespace {

// These modules ship at one of two addresses and the silkscreen rarely says
// which. Guessing wrong looks exactly like a dead screen, so try both.
const uint8_t CANDIDATES[] = {0x3C, 0x3D};

U8G2_SSD1306_128X32_UNIVISION_F_HW_I2C g_oled(U8G2_R0, U8X8_PIN_NONE);

bool    g_present = false;
uint8_t g_address = 0;
bool    g_asleep  = false;

bool answersAt(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

}  // namespace

bool begin() {
  Wire.begin();

  for (uint8_t addr : CANDIDATES) {
    if (!answersAt(addr)) continue;
    g_address = addr;
    g_oled.setI2CAddress(addr << 1);  // U8g2 wants the 8-bit form
    if (!g_oled.begin()) return false;
    g_oled.setFont(u8g2_font_5x8_tf);  // 25 characters across, four rows down
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
  for (int i = 0; i < 4; i++) {
    if (lines[i] != nullptr) g_oled.drawStr(0, 7 + i * 8, lines[i]);
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
