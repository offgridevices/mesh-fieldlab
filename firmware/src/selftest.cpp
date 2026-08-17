#include "selftest.h"

#include <stdarg.h>

#include "clock.h"
#include "config.h"
#include "screen.h"

namespace SelfTest {
namespace {

const uint8_t MAX_NEIGHBOURS = 8;

mt_radio_config_t g_config;
bool     g_haveConfig = false;
uint8_t  g_battery    = 0;
double   g_lat        = 0.0;
double   g_lon        = 0.0;
int32_t  g_alt        = 0;

uint32_t g_heard[MAX_NEIGHBOURS];
uint8_t  g_heardCount = 0;

void rememberHeard(uint32_t node) {
  if (node == 0 || node == my_node_num) return;
  for (uint8_t i = 0; i < g_heardCount; i++) {
    if (g_heard[i] == node) return;
  }
  if (g_heardCount < MAX_NEIGHBOURS) g_heard[g_heardCount++] = node;
}

// The console mirrors the screen. Both are best-effort and neither is
// required: a node with no display and no USB still logs correctly.
void say(const char * fmt, ...) {
#if SERIAL_ECHO
  char line[128];
  va_list args;
  va_start(args, fmt);
  vsnprintf(line, sizeof(line), fmt, args);
  va_end(args);
  Serial.println(line);
#else
  (void)fmt;
#endif
}

// Pumps the protocol without blocking the caller's sense of time.
void serviceUntil(uint32_t deadline) {
  while ((int32_t)(millis() - deadline) < 0) {
    mt_loop(millis());
    delay(5);
  }
}

// Wait for the radio to hand over a time, and say so while waiting.
//
// The screen names the action, not the fault. Somebody standing over the node
// needs to know to reach for their phone; that a flag is false is no use to
// them. The countdown is there so the wait never feels like a hang.
//
// Returns as soon as the clock is set, which is normally seconds after a phone
// connects to any node on the mesh.
bool awaitClock(uint32_t timeoutMs) {
  uint32_t deadline = millis() + timeoutMs;
  uint32_t lastPaint = 0;
  uint32_t heldSince = 0;

  while (!Clock::valid() && (int32_t)(millis() - deadline) < 0) {
    mt_loop(millis());
    uint32_t now = millis();

    // Holding the button skips the wait. On a bench there is no mesh to hand
    // over a time, and sitting through the full timeout to test anything else
    // wastes ten minutes. Held rather than pressed, so that a knock in a bag
    // cannot quietly cost a session its timestamps.
    if (digitalRead(BUTTON_PIN) == LOW) {
      if (heldSince == 0) {
        heldSince = now;
      } else if (now - heldSince >= 2000) {
        say("clock    : wait skipped by button");
        return false;
      }
    } else {
      heldSince = 0;
    }

    if (now - lastPaint >= 500) {
      lastPaint = now;
      // Blinking here matters: a still screen and a dark LED for ten minutes
      // looks exactly like a node that has crashed.
      digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));

      uint32_t left = (uint32_t)(deadline - now) / 1000;
      char line[26];
      snprintf(line, sizeof(line), "logs anyway in %lu:%02lu",
               (unsigned long)(left / 60), (unsigned long)(left % 60));
      Screen::show(NODE_SHORT_NAME " waiting for time",
                   "CONNECT YOUR PHONE",
                   "hold button to skip",
                   line);
    }
    delay(5);
  }
  return Clock::valid();
}

}  // namespace

void noteRadioConfig(const mt_radio_config_t * config) {
  g_config = *config;
  g_haveConfig = true;
}

void notePacket(const mt_packet_meta_t * meta) {
  rememberHeard(meta->from);
  // Whether the clock is set is not tracked here — Clock owns that, and owns
  // it for the whole firmware, so the screen, the filename and the BOOT row
  // can never disagree about it.
  Clock::adopt(meta->rx_time);
}

void noteOwnNode(const mt_node_t * node) {
  if (node == nullptr || !node->is_mine) return;
  g_battery = node->battery_level;
  g_lat = node->latitude;
  g_lon = node->longitude;
  // The library narrows the protocol's 32-bit altitude to a single signed
  // byte, so anything beyond ±127 m is already lost by the time it reaches
  // here. Recorded as-is; see the open items in the design document.
  g_alt = node->altitude;
}

const char * presetName(uint8_t preset) {
  switch (preset) {
    case 0:  return "LONGF";   // LONG_FAST
    case 1:  return "LONGS";   // LONG_SLOW
    case 2:  return "VLONGS";  // VERY_LONG_SLOW (deprecated upstream)
    case 3:  return "MEDS";    // MEDIUM_SLOW
    case 4:  return "MEDF";    // MEDIUM_FAST
    case 5:  return "SHORTS";  // SHORT_SLOW
    case 6:  return "SHORTF";  // SHORT_FAST
    case 7:  return "LONGMOD"; // LONG_MODERATE
    case 8:  return "SHORTT";  // SHORT_TURBO
    default: return "?";
  }
}

const char * regionName(uint8_t region) {
  switch (region) {
    case 0:  return "UNSET";
    case 1:  return "US";
    case 2:  return "EU433";
    case 3:  return "EU868";
    case 4:  return "CN";
    case 5:  return "JP";
    case 6:  return "ANZ";
    case 7:  return "KR";
    case 8:  return "TW";
    case 9:  return "RU";
    case 10: return "IN";
    case 11: return "NZ865";
    case 12: return "TH";
    case 13: return "LORA24";
    case 14: return "UA433";
    case 15: return "UA868";
    default: return "?";
  }
}

Result run(bool displayOk, bool cardMounted, bool cardWritable, uint32_t freeMb,
           void (*nodeReportCb)(mt_node_t *, mt_nr_progress_t)) {
  Result r;
  r.display_ok    = displayOk;
  r.card_mounted  = cardMounted;
  r.card_writable = cardWritable;
  r.free_mb       = freeMb;

  char line[26];

  // --- the card, which we already know about --------------------------------
  snprintf(line, sizeof(line), "CARD %s %luMB",
           cardWritable ? "OK" : (cardMounted ? "RO!" : "FAIL"),
           (unsigned long)freeMb);
  Screen::show(NODE_SHORT_NAME " starting", line, "radio...", nullptr);

  say("display  : %s", displayOk ? "found" : "ABSENT (carrying on)");
  say("card     : %s", cardMounted ? "mounted" : "NOT MOUNTED");
  say("card test: %s", cardWritable ? "wrote and read back a row"
                                    : "FAILED — will not record");
  if (cardMounted) say("free     : %lu MB", (unsigned long)freeMb);
  say("radio    : waiting up to %lu s for an answer...",
      (unsigned long)(RADIO_WAIT_MS / 1000));

  // --- the radio ------------------------------------------------------------
  // my_node_num stays zero until the radio has answered, so it doubles as the
  // proof that wiring, baud rate and PROTO mode are all correct at once.
  //
  // It is only ever set by the reply to a request, though, and the library
  // never sends one by itself. Ask first, then wait — waiting without having
  // asked can only ever time out.
  //
  // Ask repeatedly, because the two boards share one supply and therefore boot
  // together: the first ask usually lands on a radio that has not finished
  // starting and is discarded in silence. The library has no retry of its own.
  uint32_t deadline = millis() + RADIO_WAIT_MS;
  uint32_t lastAsk = 0;
  while (my_node_num == 0 && (int32_t)(millis() - deadline) < 0) {
    uint32_t now = millis();
    if (lastAsk == 0 || now - lastAsk >= RADIO_ASK_EVERY_MS) {
      lastAsk = now;
      if (nodeReportCb != nullptr) mt_request_node_report(nodeReportCb);
    }
    mt_loop(now);
    delay(10);
  }
  r.radio_ok = (my_node_num != 0);

  if (!r.radio_ok) {
    Screen::show(NODE_SHORT_NAME " starting", line, "RADIO: NO ANSWER",
                 "check wiring + PROTO");
    say("radio    : NO ANSWER");
    say("           check TX/RX are crossed, the baud rate matches,");
    say("           and the Serial module is enabled in PROTO mode");
    // No point listening for neighbours through a link that is not there.
    return r;
  }
  say("radio    : answered — node %lu", (unsigned long)my_node_num);

  // Config arrives across the same exchange; give it a moment to land.
  serviceUntil(millis() + 2000);
  if (g_haveConfig) {
    r.have_config    = g_config.has_lora;
    r.region         = g_config.region;
    r.preset         = g_config.modem_preset;
    r.hop_limit      = g_config.hop_limit;
    r.tx_enabled     = g_config.tx_enabled;
    r.fixed_position = g_config.has_position && g_config.fixed_position;
  }

  snprintf(line, sizeof(line), "RADIO OK %s %s",
           presetName(r.preset), regionName(r.region));
  Screen::show(NODE_SHORT_NAME " starting", line, "listening 30s...", nullptr);

  if (r.have_config) {
    say("settings : region %s, preset %s, hop limit %u, tx %s",
        regionName(r.region), presetName(r.preset),
        (unsigned)r.hop_limit, r.tx_enabled ? "on" : "OFF");
    say("position : %s", r.fixed_position ? "fixed position is set"
                                          : "NOT SET — rows cannot be tied to a place");
  } else {
    say("settings : radio answered but sent no config");
  }
  say("listening: %lu s for neighbours...", (unsigned long)(BOOT_LISTEN_MS / 1000));

  // --- who can we hear ------------------------------------------------------
  // The report was already asked for above, and it is what woke the radio up;
  // it also carries our own entry, which is where the position and battery
  // come from — the radio owns the battery, not the logger. So there is
  // nothing to ask for here, only time to spend listening.
  serviceUntil(millis() + BOOT_LISTEN_MS);

  // --- the clock ------------------------------------------------------------
  // Nothing is logged until the time is known. A file that starts before the
  // clock is set cannot be lined up against the other three nodes, and the
  // rows written in that window would be the only ones in the session with no
  // absolute time on them.
  //
  // The wait is bounded rather than absolute, because the alternative failure
  // is worse: an undated file still holds every RSSI and SNR reading and every
  // link statistic within itself, and coming home with nothing at all because
  // a phone would not pair is not a trade worth making.
  if (!Clock::valid() && CLOCK_WAIT_MS > 0) {
    say("clock    : NOT SET — waiting up to %lu min before logging.",
        (unsigned long)(CLOCK_WAIT_MS / 60000));
    say("           CONNECT YOUR PHONE to any node on the mesh now.");
    say("           The radio takes the time from the phone and passes it on.");

    r.clock_waited = true;
    uint32_t began = millis();
    awaitClock(CLOCK_WAIT_MS);
    r.clock_wait_ms = millis() - began;

    if (Clock::valid()) {
      say("clock    : arrived after %lu s", (unsigned long)(r.clock_wait_ms / 1000));
    } else {
      say("clock    : GAVE UP after %lu s — logging anyway, undated.",
          (unsigned long)(r.clock_wait_ms / 1000));
    }
  }

  r.heard_count = g_heardCount;
  r.clock_set   = Clock::valid();
  r.battery_pct = g_battery;
  r.lat         = g_lat;
  r.lon         = g_lon;
  r.alt         = g_alt;

  say("heard    : %u neighbour%s", (unsigned)r.heard_count,
      r.heard_count == 1 ? "" : "s");
  for (uint8_t i = 0; i < g_heardCount; i++) {
    say("           node %lu", (unsigned long)g_heard[i]);
  }
  if (r.clock_set) {
    char when[16];
    Clock::stamp(when, sizeof(when));
    say("clock    : set — %s local (%s, UTC%+ld)",
        when, Clock::zoneName(), Clock::utcOffsetSeconds() / 3600);
  } else {
    say("clock    : NOT SET — rows are relative to boot only, and the file");
    say("           cannot be dated. Nothing on this mesh knows the time:");
    say("           give one node a GPS, or set it with the Meshtastic CLI.");
  }
  say("battery  : %u%%", (unsigned)r.battery_pct);
  return r;
}

void refreshOwn(Result & r) {
  // The radio keeps reporting these for as long as it is running. Reading them
  // once at boot and never again gives a battery gauge that cannot move and a
  // position that cannot arrive — both of which matter most hours into a
  // session, which is exactly when a boot-time snapshot is most out of date.
  r.battery_pct = g_battery;
  r.lat         = g_lat;
  r.lon         = g_lon;
  r.alt         = g_alt;

  // The settings too. They arrive as a series of blocks rather than in one
  // message, so the position block routinely lands after the moment the boot
  // test looked — and a value read before it arrived is not a reading, it is
  // the zero it was initialised to. Re-read rather than sample once.
  //
  // They can also change underneath us: somebody standing at the node with a
  // phone is exactly how a position gets set, and the screen has to show that
  // landing or it cannot be used to confirm the node is ready.
  if (!g_haveConfig) return;
  r.have_config    = g_config.has_lora;
  r.region         = g_config.region;
  r.preset         = g_config.modem_preset;
  r.hop_limit      = g_config.hop_limit;
  r.tx_enabled     = g_config.tx_enabled;
  r.fixed_position = g_config.has_position && g_config.fixed_position;
}

bool positionUsable(const Result & r) {
  // The setting on its own is not enough. Switching "fixed position" on
  // without giving the radio a coordinate leaves the flag set with nothing
  // behind it, which is how this node was found: configured, convincing, and
  // recording rows that could never be tied to a place.
  //
  // A node that admits it has no position is recoverable — somebody walks back
  // and sets it. A node that claims one it does not have is not, and the claim
  // is only discovered when the session is being analysed.
  if (!r.fixed_position) return false;
  // Zero is treated as absent. The point in the Atlantic it really names is
  // not somewhere these nodes will ever be, and every unset coordinate on
  // earth reads as exactly this.
  return r.lat != 0.0 || r.lon != 0.0;
}

bool reviewRadio(Result & r, bool alive) {
  if (r.radio_ok == alive) return false;

  r.radio_ok = alive;

  // On the way back up, take its settings again rather than trusting what was
  // read before it went quiet. A radio that restarted may have come back
  // configured differently — that is exactly what happens when somebody
  // reflashes or reconfigures it — and a fault that has cleared but still
  // reads as a fault teaches people to ignore the screen.
  if (alive && g_haveConfig) {
    r.have_config    = g_config.has_lora;
    r.region         = g_config.region;
    r.preset         = g_config.modem_preset;
    r.hop_limit      = g_config.hop_limit;
    r.tx_enabled     = g_config.tx_enabled;
    r.fixed_position = g_config.has_position && g_config.fixed_position;
  }
  return true;
}

void toExtra(const Result & r, uint32_t bootCount, char * out, size_t n) {
  snprintf(out, n,
           "fw=" LOGGER_VERSION ";ant=" ANTENNA_MODEL
           ";boot=%lu;preset=%s;region=%s;hops=%u"
           ";lat=%.6f;lon=%.6f;alt=%ld"
           ";st_card=%d;st_write=%d;st_radio=%d;st_pos=%d;st_clock=%d;st_heard=%u"
           ";disp=%d;batt=%u;tz=%s;utcoff=%ld;clkwait=%lu",
           (unsigned long)bootCount,
           presetName(r.preset), regionName(r.region), (unsigned)r.hop_limit,
           r.lat, r.lon, (long)r.alt,
           r.card_mounted ? 1 : 0,
           r.card_writable ? 1 : 0,
           r.radio_ok ? 1 : 0,
           positionUsable(r) ? 1 : 0,
           r.clock_set ? 1 : 0,
           (unsigned)r.heard_count,
           r.display_ok ? 1 : 0,
           (unsigned)r.battery_pct,
           // The filename is local time; these two are what let any reader
           // turn it back into UTC without knowing where the node was or what
           // the daylight-saving rules were that week.
           Clock::zoneName(),
           Clock::utcOffsetSeconds(),
           // Seconds spent held at boot waiting for the time. Zero is the
           // normal case; a large number means the phone was slow, and the
           // give-up value means the file that follows is undated.
           (unsigned long)(r.clock_wait_ms / 1000));
}

const char * verdict(const Result & r) {
  // Ordered by what stops the session soonest. A card that cannot be written
  // means nothing is recorded at all; a silent radio means nothing arrives to
  // record; the rest degrade the result rather than ending it.
  if (!r.card_writable)   return "NO CARD";
  if (!r.radio_ok)        return "NO RADIO";
  if (!positionUsable(r)) return "NO POS";
  if (!r.clock_set)      return "NO CLOCK";
  if (r.heard_count == 0) return "ALONE";
  return "READY";
}

}  // namespace SelfTest
