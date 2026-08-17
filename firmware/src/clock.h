#pragma once

#include <Arduino.h>

// Absolute time, and the one honest fact about it: the logger has no clock of
// its own.
//
// The XIAO has no battery-backed RTC, so every cold boot starts at the epoch
// knowing nothing. The only automatic source of real time is the radio, which
// stamps received packets with `rx_time` — and the radio only knows the time
// if something told it (a GPS, a phone, the CLI, or another node on the mesh
// that already knew). See §8 of the design document.
//
// The consequence, which the rest of the firmware is built around: a file may
// have to be opened before the time is known. Nothing waits for the clock.
// When time does arrive the file is renamed, and until then the name says so.
namespace Clock {

// Seconds since the epoch at 2020-01-01. Anything below this is an unset or
// nonsense clock rather than a real reading. Shared with the self-test, which
// applies the same floor to the same field.
const uint32_t EPOCH_FLOOR = 1577836800UL;

// Installs the timezone rule from config.h. Call once, before anything asks
// for a local time.
void begin();

// Take a candidate epoch, usually a packet's rx_time.
//
// Returns true only on the transition from no-clock to clock, which is the
// moment the caller needs to act on — it is when the open file stops being
// nameable only by boot count. Later calls return false: the system clock
// free-runs from the crystal once set, which is steadier than re-stamping it
// from every packet that arrives.
bool adopt(uint32_t epoch);

// True once a real time has been adopted.
bool valid();

// UTC seconds, or 0 if the clock was never set. This is what goes in the
// rows: machines get UTC, so no analysis ever has to reason about which side
// of a daylight-saving change a file landed on.
uint32_t nowEpoch();

// `YYYYMMDD_HHMM` in local time, for the filename. People get local time,
// because a person standing over a box of cards wants to recognise the
// afternoon they collected them.
//
// Writes "00000000_0000" if the clock is unset, which no caller should be
// using anyway — check valid() first.
void stamp(char * out, size_t n);

// Local date and time as readable text, for the screen: "2026-08-17" and
// "14:32 EDT". Both write a clearly-empty form when the clock is unset, so a
// glance at the screen can never show a plausible-looking wrong time.
void dateText(char * out, size_t n);
void timeText(char * out, size_t n);

// Offset from UTC in seconds, and the abbreviation in force at this instant
// ("EST", "EDT"). Both are written into the BOOT row so a local-time filename
// can always be mapped back to UTC without guessing.
long utcOffsetSeconds();
const char * zoneName();

}  // namespace Clock
