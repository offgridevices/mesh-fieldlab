#pragma once

#include <Arduino.h>

// The 0.91" OLED, on its own two-wire bus.
//
// Everything here is best-effort. If the display is absent, broken, or at an
// address we did not guess, the node logs exactly as well without it — a
// screen must never be able to cost a session.
namespace Screen {

// Probes both addresses these modules ship with. Returns false if neither
// answers, after which every other call here is a no-op.
bool begin();

bool present();
uint8_t address();

// Four lines of up to 25 characters. Pass nullptr for a blank line.
void show(const char * l1, const char * l2 = nullptr,
          const char * l3 = nullptr, const char * l4 = nullptr);

// Power down the panel. Draws microamps until woken.
void sleep();
void wake();

}  // namespace Screen
