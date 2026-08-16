#include "selftest.h"

#include "config.h"
#include "screen.h"

namespace SelfTest {
namespace {

// Seconds since the epoch at 2020-01-01. Anything below this is an unset or
// nonsense clock rather than a real reading.
const uint32_t EPOCH_FLOOR = 1577836800UL;

const uint8_t MAX_NEIGHBOURS = 8;

mt_radio_config_t g_config;
bool     g_haveConfig = false;
bool     g_clockSet   = false;
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

// Pumps the protocol without blocking the caller's sense of time.
void serviceUntil(uint32_t deadline) {
  while ((int32_t)(millis() - deadline) < 0) {
    mt_loop(millis());
    delay(5);
  }
}

}  // namespace

void noteRadioConfig(const mt_radio_config_t * config) {
  g_config = *config;
  g_haveConfig = true;
}

void notePacket(const mt_packet_meta_t * meta) {
  rememberHeard(meta->from);
  if (meta->rx_time >= EPOCH_FLOOR) g_clockSet = true;
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

  // --- the radio ------------------------------------------------------------
  // my_node_num stays zero until the radio has answered, so it doubles as the
  // proof that wiring, baud rate and PROTO mode are all correct at once.
  uint32_t deadline = millis() + RADIO_WAIT_MS;
  while ((int32_t)(millis() - deadline) < 0 && my_node_num == 0) {
    mt_loop(millis());
    delay(10);
  }
  r.radio_ok = (my_node_num != 0);

  if (!r.radio_ok) {
    Screen::show(NODE_SHORT_NAME " starting", line, "RADIO: NO ANSWER",
                 "check wiring + PROTO");
    // No point listening for neighbours through a link that is not there.
    return r;
  }

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

  // --- who can we hear ------------------------------------------------------
  // The report also carries our own entry, which is where the position and
  // battery come from — the radio owns the battery, not the logger.
  if (nodeReportCb != nullptr) mt_request_node_report(nodeReportCb);
  serviceUntil(millis() + BOOT_LISTEN_MS);

  r.heard_count = g_heardCount;
  r.clock_set   = g_clockSet;
  r.battery_pct = g_battery;
  r.lat         = g_lat;
  r.lon         = g_lon;
  r.alt         = g_alt;
  return r;
}

void toExtra(const Result & r, uint32_t bootCount, char * out, size_t n) {
  snprintf(out, n,
           "fw=" LOGGER_VERSION ";ant=" ANTENNA_MODEL
           ";boot=%lu;preset=%s;region=%s;hops=%u"
           ";lat=%.6f;lon=%.6f;alt=%ld"
           ";st_card=%d;st_write=%d;st_radio=%d;st_pos=%d;st_clock=%d;st_heard=%u"
           ";disp=%d;batt=%u",
           (unsigned long)bootCount,
           presetName(r.preset), regionName(r.region), (unsigned)r.hop_limit,
           r.lat, r.lon, (long)r.alt,
           r.card_mounted ? 1 : 0,
           r.card_writable ? 1 : 0,
           r.radio_ok ? 1 : 0,
           r.fixed_position ? 1 : 0,
           r.clock_set ? 1 : 0,
           (unsigned)r.heard_count,
           r.display_ok ? 1 : 0,
           (unsigned)r.battery_pct);
}

void toScreen(const Result & r, char l1[26], char l2[26], char l3[26], char l4[26]) {
  snprintf(l1, 26, "%s %u%%%s CARD %s",
           NODE_SHORT_NAME,
           (unsigned)r.battery_pct,
           r.battery_pct ? "" : "?",
           r.card_writable ? "OK" : "BAD");

  if (r.radio_ok) {
    snprintf(l2, 26, "RADIO OK %s %s",
             presetName(r.preset), regionName(r.region));
  } else {
    snprintf(l2, 26, "RADIO: NO ANSWER");
  }

  snprintf(l3, 26, "POS %s  CLOCK %s  h%u",
           r.fixed_position ? "OK" : "--",
           r.clock_set ? "OK" : "--",
           (unsigned)r.hop_limit);

  if (r.heard_count > 0) {
    snprintf(l4, 26, "HEARD %u  READY", (unsigned)r.heard_count);
  } else {
    snprintf(l4, 26, "HEARD NONE  READY");
  }
}

}  // namespace SelfTest
