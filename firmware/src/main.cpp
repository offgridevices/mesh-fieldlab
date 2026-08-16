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

// --- callbacks --------------------------------------------------------------

void onPacket(const mt_packet_meta_t * meta) {
  g_packetsSeen++;
  g_lastPacketAt = millis();

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

void showRunningSummary() {
  uint32_t up = millis() / 1000;
  char l1[26], l2[26], l3[26], l4[26];

  snprintf(l1, sizeof(l1), "%s  %luh%02lum", NODE_SHORT_NAME,
           (unsigned long)(up / 3600), (unsigned long)((up / 60) % 60));
  snprintf(l2, sizeof(l2), "ROWS %lu  CARD %s",
           (unsigned long)LogFile::rowsWritten(),
           LogFile::healthy() ? "OK" : "FAIL");
  snprintf(l3, sizeof(l3), "HEARD %lu packets", (unsigned long)g_packetsSeen);

  if (g_lastPacketAt == 0) {
    snprintf(l4, sizeof(l4), "LAST: none yet");
  } else {
    snprintf(l4, sizeof(l4), "LAST %lus ago",
             (unsigned long)((millis() - g_lastPacketAt) / 1000));
  }

  Screen::show(l1, l2, l3, l4);
  g_screenOffAt = millis() + SCREEN_WAKE_MS;
}

// Debounced, edge-triggered. A held button must not repaint continuously —
// that would put the display on the bus far more than intended.
void serviceButton(uint32_t now) {
  bool down = (digitalRead(BUTTON_PIN) == LOW);

  if (down != g_buttonWasDown) {
    if (now - g_buttonChangedAt > 40) {
      g_buttonChangedAt = now;
      g_buttonWasDown = down;
      if (down) showRunningSummary();
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
    char extra[256];
    SelfTest::toExtra(result, bootCount, extra, sizeof(extra));
    LogFile::writeBoot(extra);
    Serial.printf("logging  : %s\n", LogFile::fileName());
  } else {
    Serial.println("logging  : NOT RECORDING — the card is unusable");
    Serial.println("           the node still runs, so the fault is visible");
  }
  Serial.println("----------------------------------------");

  char l1[26], l2[26], l3[26], l4[26];
  SelfTest::toScreen(result, l1, l2, l3, l4);
  Screen::show(l1, l2, l3, l4);
  g_screenOffAt = millis() + 30000;

  g_booting = false;
  g_lastStatus = millis();
  g_lastReport = millis();
}

void loop() {
  uint32_t now = millis();

  mt_loop(now);
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
