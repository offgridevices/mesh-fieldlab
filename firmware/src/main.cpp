// Standalone LoRa link-quality logger.
//
// Sits on a Meshtastic node's serial header pretending to be a phone, and
// writes what the radio hears to a card. No phone, no laptop, no network.
//
// The shape of it: run a self-test somebody can read while standing there,
// then log until the battery dies, and never stop logging for any reason a
// human is not present to fix.

#include <Arduino.h>
#include <Meshtastic.h>

#include "clock.h"
#include "config.h"
#include "log_schema.h"
#include "logfile.h"
#include "screen.h"
#include "selftest.h"

namespace {

// True while the self-test owns the callbacks. After it finishes they feed
// the card instead.
bool g_booting = true;

uint32_t g_lastStatus = 0;
uint32_t g_lastReport = 0;
uint32_t g_lastLed = 0;
uint32_t g_screenOffAt = 0;
uint32_t g_packetsSeen = 0;
uint32_t g_lastPacketAt = 0;

bool g_buttonWasDown = false;
uint32_t g_buttonChangedAt = 0;

//: Which page the button is showing. Stays where it was left, so a second
//: visit to the same node opens where you were looking.
uint8_t g_page = 0;

Screen::NodeView g_view;
SelfTest::Result g_selfTest;

//: Per-neighbour tallies, so the neighbours page can say who and how well
//: rather than only how many.
uint32_t g_peer[Screen::MAX_NEIGHBOURS] = {0};
uint32_t g_peerPkts[Screen::MAX_NEIGHBOURS] = {0};
int32_t  g_peerRssiSum[Screen::MAX_NEIGHBOURS] = {0};
uint8_t  g_peerCount = 0;

void notePeer(uint32_t node, int32_t rssi) {
  if (node == 0 || node == my_node_num) return;
  for (uint8_t i = 0; i < g_peerCount; i++) {
    if (g_peer[i] == node) {
      g_peerPkts[i]++;
      g_peerRssiSum[i] += rssi;
      return;
    }
  }
  if (g_peerCount >= Screen::MAX_NEIGHBOURS) return;
  g_peer[g_peerCount] = node;
  g_peerPkts[g_peerCount] = 1;
  g_peerRssiSum[g_peerCount] = rssi;
  g_peerCount++;
}

// --- callbacks --------------------------------------------------------------

void onPacket(const mt_packet_meta_t * meta) {
  g_packetsSeen++;
  g_lastPacketAt = millis();

  // The radio's clock is the only absolute time the logger ever sees, and it
  // arrives stapled to packets. Take it at the first opportunity — before the
  // row is written, so the file can be named the moment it becomes possible.
  Clock::adopt(meta->rx_time);

#if SERIAL_ECHO_PACKETS
  // The same row that reaches the card, in a form a person can read. A packet
  // arriving is the one thing you want to see immediately on a bench.
  uint8_t hops = (meta->hop_start >= meta->hop_limit)
                   ? (uint8_t)(meta->hop_start - meta->hop_limit) : 0;
  Serial.printf("pkt  from %lu  %ld dBm  %.2f dB  %s%s%s\n",
                (unsigned long)meta->from,
                (long)meta->rx_rssi,
                meta->rx_snr,
                hops == 0 ? "direct" : "relayed",
                meta->via_mqtt ? "  [MQTT — not over the air]" : "",
                meta->is_decoded ? "" : "  [encrypted]");
#endif

  notePeer(meta->from, meta->rx_rssi);

  if (g_booting) {
    SelfTest::notePacket(meta);
    return;
  }
  LogFile::writePacket(meta);
}

void onRadioConfig(const mt_radio_config_t * config) {
  SelfTest::noteRadioConfig(config);
}

void onNodeReport(mt_node_t * node, mt_nr_progress_t progress) {
  if (progress != MT_NR_IN_PROGRESS || node == nullptr) return;
  SelfTest::noteOwnNode(node);
  if (!g_booting) LogFile::writeNode(node);
}

// --- display ----------------------------------------------------------------

// Refresh everything the pages read. Cheap, and it keeps the screen code free
// of any reaching back into the rest of the firmware.
void refreshView() {
  uint32_t now = millis();
  g_view.batteryPct    = g_selfTest.battery_pct;
  g_view.uptimeSec     = now / 1000;
  g_view.packets       = g_packetsSeen;
  g_view.rows          = LogFile::rowsWritten();
  g_view.everHeard     = (g_lastPacketAt != 0);
  g_view.secsSinceLast = g_view.everHeard ? (now - g_lastPacketAt) / 1000 : 0;
  g_view.cardOk        = LogFile::healthy();
  g_view.freeMb        = LogFile::freeMegabytes();
  g_view.fileName      = LogFile::fileName();
  g_view.myNode        = my_node_num;

  g_view.neighbourCount = g_peerCount;
  for (uint8_t i = 0; i < g_peerCount; i++) {
    g_view.neighbour[i]     = g_peer[i];
    g_view.neighbourPkts[i] = g_peerPkts[i];
    g_view.neighbourRssi[i] = (int16_t)(g_peerRssiSum[i] / (int32_t)g_peerPkts[i]);
  }

  Clock::dateText(g_view.dateText, sizeof(g_view.dateText));
  Clock::timeText(g_view.timeText, sizeof(g_view.timeText));

  // The heard check goes green once anything has ever been heard, not only
  // during the startup listen — a node that finds its neighbours late is
  // working, and should stop showing a fault.
  g_view.ok[Screen::CHK_HEARD] = (g_peerCount > 0);
  g_view.ok[Screen::CHK_CARD]  = LogFile::healthy();
  // Likewise the clock: it can arrive after the boot gave up waiting, and a
  // node that is now correctly timed should not keep showing a fault for it.
  g_view.ok[Screen::CHK_CLOCK] = Clock::valid();
}

// Debounced, edge-triggered. A held button must not page continuously, and a
// repaint must not happen more often than a person can read.
void serviceButton(uint32_t now) {
  bool down = (digitalRead(BUTTON_PIN) == LOW);

  if (down != g_buttonWasDown) {
    if (now - g_buttonChangedAt > 40) {
      g_buttonChangedAt = now;
      g_buttonWasDown = down;
      if (down) {
        // First press wakes the screen where it was left; each further press
        // goes one page deeper.
        if (g_screenOffAt == 0) Screen::wake();
        else g_page = (uint8_t)((g_page + 1) % Screen::PAGE_COUNT);
        refreshView();
        Screen::page(g_page, g_view);
        g_screenOffAt = now + SCREEN_WAKE_MS;
      }
    }
    return;
  }

  if (g_screenOffAt != 0 && (int32_t)(now - g_screenOffAt) >= 0) {
    Screen::sleep();
    g_screenOffAt = 0;
  }
}

// Slow blink healthy, double-blink when a packet landed recently, fast and
// continuous when the card has failed.
void serviceLed(uint32_t now) {
  if (!LogFile::healthy()) {
    if (now - g_lastLed >= 100) {
      g_lastLed = now;
      digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
    }
    return;
  }

  uint32_t period = (g_lastPacketAt != 0 && now - g_lastPacketAt < 3000) ? 250 : 1500;
  if (now - g_lastLed >= period) {
    g_lastLed = now;
    digitalWrite(LED_BUILTIN, !digitalRead(LED_BUILTIN));
  }
}

}  // namespace

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  Serial.begin(115200);
  // Bounded, so a node with nothing plugged in still starts on time.
  while (!Serial && millis() < SERIAL_WAIT_MS) delay(10);

  Serial.printf("\n\n%s  logger %s  schema %d\n",
                NODE_SHORT_NAME, LOGGER_VERSION, LOG_SCHEMA_VERSION);
  Serial.println("----------------------------------------");

  // Before anything asks for a local time. Costs nothing and cannot fail.
  Clock::begin();

  // Radios off, clock down. The logger has nothing to transmit and must stay
  // awake for the serial stream, so this is all the power saving there is.
  setCpuFrequencyMhz(80);

  bool displayOk = Screen::begin();

  // The card first, because everything downstream is pointless without it.
  bool mounted = LogFile::mount();
  bool writable = mounted && LogFile::proveWritable();
  uint32_t freeMb = mounted ? LogFile::freeMegabytes() : 0;

  uint32_t bootCount = LogFile::nextBootCount();

  set_packet_meta_callback(onPacket);
  set_radio_config_callback(onRadioConfig);
  mt_serial_init(RADIO_RX_PIN, RADIO_TX_PIN, RADIO_BAUD);

  SelfTest::Result result =
      SelfTest::run(displayOk, mounted, writable, freeMb, onNodeReport);

  // Open the file after the test so BOOT is genuinely the first row. The
  // thirty seconds of listening are spent counting neighbours, not logging;
  // losing them off the front of a two-hour session costs nothing.
  if (writable && LogFile::open(NODE_SHORT_NAME, bootCount)) {
    char extra[320];
    SelfTest::toExtra(result, bootCount, extra, sizeof(extra));
    LogFile::writeBoot(extra);
    Serial.printf("logging  : %s\n", LogFile::fileName());
    if (!LogFile::isDated()) {
      Serial.println("           NO CLOCK YET — this name is provisional.");
      Serial.println("           The file is renamed with its date as soon as");
      Serial.println("           a packet arrives carrying the time.");
    }
  } else {
    Serial.println("logging  : NOT RECORDING — the card is unusable");
    Serial.println("           the node still runs, so the fault is visible");
  }
  Serial.println("----------------------------------------");

  g_selfTest = result;
  g_view.verdict = SelfTest::verdict(result);
  g_view.ok[Screen::CHK_CARD]  = result.card_writable;
  g_view.ok[Screen::CHK_RADIO] = result.radio_ok;
  g_view.ok[Screen::CHK_POS]   = result.fixed_position;
  g_view.ok[Screen::CHK_CLOCK] = result.clock_set;
  g_view.ok[Screen::CHK_HEARD] = (result.heard_count > 0);
  g_view.region = SelfTest::regionName(result.region);
  g_view.preset = SelfTest::presetName(result.preset);
  g_view.hops   = result.hop_limit;
  g_view.lat    = result.lat;
  g_view.lon    = result.lon;

  g_booting = false;
  refreshView();
  Screen::page(0, g_view);
  g_page = 0;
  g_screenOffAt = millis() + 30000;
  g_lastStatus = millis();
  g_lastReport = millis();
}

void loop() {
  uint32_t now = millis();

  mt_loop(now);

  // A file opened before the clock was known gets its date the moment one
  // arrives. No-op on every loop after that.
  if (LogFile::adoptClockName(NODE_SHORT_NAME)) {
    Serial.printf("clock    : time acquired — file is now %s\n", LogFile::fileName());
  }

  LogFile::tick(now);

  if (now - g_lastStatus >= STATUS_INTERVAL_MS) {
    g_lastStatus = now;
    LogFile::writeStatus(ESP.getFreeHeap());
#if SERIAL_ECHO
    Serial.printf("status   %lu min  %lu packets  %lu rows  card %s\n",
                  (unsigned long)(now / 60000),
                  (unsigned long)g_packetsSeen,
                  (unsigned long)LogFile::rowsWritten(),
                  LogFile::healthy() ? "ok" : "FAILED");
#endif
  }

  if (now - g_lastReport >= NODE_REPORT_MS) {
    g_lastReport = now;
    mt_request_node_report(onNodeReport);
  }

  serviceButton(now);
  serviceLed(now);
}
