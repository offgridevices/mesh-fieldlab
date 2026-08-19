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

#include "esp_bt.h"

#include "clock.h"
#include "config.h"
#include "log_schema.h"
#include "logfile.h"
#include "recovery.h"
#include "screen.h"
#include "selftest.h"

namespace {

// True while the self-test owns the callbacks. After it finishes they feed
// the card instead.
bool g_booting = true;

uint32_t g_lastStatus = 0;
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

//: Kept past setup, because a card that arrives late still has to name its
//: file, and the boot counter is the only name available before a clock is.
uint32_t g_bootCount = 0;

//: Recoveries that happened with nowhere to write them. A position that arrives
//: while the card is out changes what every row after it means, and the event
//: fires exactly once — so it is held here until a file exists to take it.
uint8_t g_pendingRecov = 0;

//: Set once the radio has named us and the neighbour list has been cleaned of
//: our own entry. After that notePeer filters us out on its own.
bool g_selfForgotten = false;

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

// True for a packet this node originated, which the radio hands back over the
// serial link as it sends. It never travelled through the air to get here, so
// it carries no RSSI and no SNR and is not a measurement of anything.
//
// Left in, these outnumbered the real receptions on the first bench capture —
// thirty-seven rows of zeroes against forty-five genuine ones — and every one
// of them would have been averaged into the link statistics as a perfect
// reception at 0 dBm.
bool isOurOwn(const mt_packet_meta_t * meta) {
  if (my_node_num == 0 || meta->from != my_node_num) return false;
  // A rebroadcast of our own packet, heard back off a neighbour, IS a real
  // reception and worth keeping. The absence of a signal reading is what
  // separates the two.
  return meta->rx_rssi == 0;
}

void onPacket(const mt_packet_meta_t * meta) {
  // Our own transmissions prove the serial link is alive just as well as a
  // stranger's, so liveness is noted before anything is filtered out.
  Recovery::noteRadioContact(millis());

  // The clock is taken even from our own packets: they carry the radio's time
  // just as well, and refusing it would mean waiting on a stranger to speak
  // before this node could date its file.
  Clock::adopt(meta->rx_time);

  if (isOurOwn(meta)) {
#if SERIAL_ECHO_PACKETS
    Serial.printf("sent from us  id %lu  (not logged — not a reception)\n",
                  (unsigned long)meta->id);
#endif
    return;
  }

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

  notePeer(meta->from, meta->rx_rssi);

  if (g_booting) {
    SelfTest::notePacket(meta);
    return;
  }
  LogFile::writePacket(meta);
}

void onRadioConfig(const mt_radio_config_t * config) {
  Recovery::noteRadioContact(millis());
  SelfTest::noteRadioConfig(config);
}

void onNodeReport(mt_node_t * node, mt_nr_progress_t progress) {
  uint32_t now = millis();

  // Every progress value counts, including the empty one that closes a report.
  // What is being proved here is that the radio answered at all, not that it
  // had anything useful to say.
  Recovery::noteRadioContact(now);

  if (progress != MT_NR_IN_PROGRESS || node == nullptr) return;
  SelfTest::noteOwnNode(node);

  // A report the recovery tick asked for is a liveness probe. It refreshes
  // this node's own view of itself, above, and then stops: writing forty rows
  // every thirty seconds while a fault clears would cost more of the file than
  // the fault did.
  if (!g_booting && !Recovery::suppressNodeRows(now)) LogFile::writeNode(node);
}

// The BOOT row for a file that did not begin at power-on — because the card
// arrived late, or was swapped. Without one the file cannot be interpreted at
// all: nothing in it would say which preset, which region, or where the node
// was stood.
void writeResumeBoot(uint32_t now) {
  SelfTest::refreshOwn(g_selfTest);
  char extra[360];
  SelfTest::toExtra(g_selfTest, g_bootCount, extra, sizeof(extra));
  size_t used = strlen(extra);
  // Seconds of session that happened before this file existed. Marks the file
  // as a continuation rather than a power cycle, which otherwise looks
  // identical to a node that rebooted itself in the field.
  snprintf(extra + used, sizeof(extra) - used, ";resume=%lu",
           (unsigned long)(now / 1000));
  LogFile::writeBoot(extra);
}

// --- display ----------------------------------------------------------------

// Refresh everything the pages read. Cheap, and it keeps the screen code free
// of any reaching back into the rest of the firmware.
void refreshView() {
  uint32_t now = millis();
  // Battery and position come from the radio and keep changing, so re-read
  // them rather than showing what they were at boot.
  SelfTest::refreshOwn(g_selfTest);
  g_view.lat           = g_selfTest.lat;
  g_view.lon           = g_selfTest.lon;
  g_view.batteryPct    = g_selfTest.battery_pct;
  g_view.region        = SelfTest::regionName(g_selfTest.region);
  g_view.preset        = SelfTest::presetName(g_selfTest.preset);
  g_view.hops          = g_selfTest.hop_limit;
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

  // Every check is re-read from live state on each refresh, never latched at
  // boot. A node that finds its neighbours, its clock or its radio late is a
  // working node, and a fault that has cleared but still shows red is how
  // people learn to stop trusting the screen.
  g_view.ok[Screen::CHK_HEARD] = (g_peerCount > 0);
  g_view.ok[Screen::CHK_CARD]  = LogFile::healthy();
  g_view.ok[Screen::CHK_CLOCK] = Clock::valid();
  g_view.ok[Screen::CHK_RADIO] = g_selfTest.radio_ok;
  g_view.ok[Screen::CHK_POS]   = SelfTest::positionUsable(g_selfTest);
  g_view.verdict               = SelfTest::verdict(g_selfTest);
}

// A packet that arrived before the radio had told us our own node number was
// counted as a neighbour, because the "is this me?" test had nothing to
// compare against yet. Drop that entry now that we know who we are.
void forgetSelf() {
  if (g_selfForgotten || my_node_num == 0) return;
  // From here on notePeer has a real number to compare against, so no further
  // self-entry can be created and this only ever needs doing once.
  g_selfForgotten = true;
  for (uint8_t i = 0; i < g_peerCount; i++) {
    if (g_peer[i] != my_node_num) continue;
    for (uint8_t j = i; j + 1 < g_peerCount; j++) {
      g_peer[j]        = g_peer[j + 1];
      g_peerPkts[j]    = g_peerPkts[j + 1];
      g_peerRssiSum[j] = g_peerRssiSum[j + 1];
    }
    g_peerCount--;
    return;
  }
}

// Act on whatever the recovery tick just changed.
//
// Two audiences and they want different things. The console is for somebody on
// a bench watching a fault clear; the file is for whoever reads the card weeks
// later and has to explain a hole in the middle of a session. Neither can be
// reconstructed from the other, so both are written.
void serviceRecovery(uint32_t now, const Recovery::Event & ev) {
  // A brand-new file is empty apart from its header. Nothing else may be
  // written until it can say how the node was configured.
  if (ev.newFile) {
    writeResumeBoot(now);
    Serial.printf("card     : a card arrived — now logging to %s\n",
                  LogFile::fileName());
    Serial.printf("           %lu rows were formed with nowhere to put them and\n",
                  (unsigned long)LogFile::dropped());
    Serial.println("           are gone; everything from here is recorded.");
  }

  if (ev.lost != 0) {
    char names[48];
    Serial.printf("FAULT    : %s\n", Recovery::describe(ev.lost, names, sizeof(names)));
  }

  if (ev.recovered != 0) {
    char names[48];
    Recovery::describe(ev.recovered, names, sizeof(names));
    Serial.printf("recovered: %s\n", names);
  }

  // Nowhere to write it yet. Hold onto what came back rather than losing it —
  // the event happens once, and a recovery nobody recorded is a change in the
  // measurements that the file never explains.
  if (!LogFile::healthy()) {
    g_pendingRecov |= ev.recovered;
    return;
  }

  // A status row rather than a row type of its own: STATUS already carries the
  // card's health and the dropped-row count, which is most of what a recovery
  // needs to say, and a new row type would mean every existing reader had to
  // learn about it. The recov= key names what came back.
  //
  // The card's own return is skipped on a new file, because the BOOT row
  // written a moment ago already marks that instant. Anything that came back
  // while there was no card is not skipped: it has never been recorded at all.
  uint8_t toRecord = (uint8_t)((ev.newFile ? 0 : ev.recovered) | g_pendingRecov);
  if (toRecord == 0) return;

  char names[48];
  Recovery::describe(toRecord, names, sizeof(names));
  g_lastStatus = now;
  LogFile::writeStatus(ESP.getFreeHeap(), names);
  g_pendingRecov = 0;
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

  // --- radios off ----------------------------------------------------------
  // Nothing in this node uses the 2.4 GHz radio. It reaches the mesh radio
  // over a serial pair and the card over SPI; WiFi and BLE have no part in
  // any of it, and the module's own ceramic antenna is left doing nothing.
  //
  // Both are already off, because nothing here ever starts them — but "off
  // because nobody asked" is a property of today's code, not a guarantee. A
  // library added later could bring one up unnoticed, and the first symptom
  // would be a current draw that no longer matches the battery arithmetic
  // the session length rests on.
  //
  // BLE is therefore shut off here and for good. Releasing the controller's
  // memory cannot be undone for the rest of the boot, so nothing can start
  // BLE afterwards however politely it asks. Measured cost of saying so: six
  // bytes of flash.
  esp_bt_mem_release(ESP_BT_MODE_BTDM);

  // WiFi is deliberately NOT switched off in code, and that is not an
  // oversight. It has no equivalent one-way release, and the only way to ask
  // is to call into the WiFi stack — which links the whole thing in. Measured
  // on this firmware: esp_wifi_stop() plus esp_wifi_deinit() cost 133 KB of
  // flash and 16 KB of RAM, to switch off something that was never on. That
  // puts the entire radio stack inside the image in order to announce that we
  // are not using the radio, which is worse than saying nothing.
  //
  // The guarantee is made where it is free instead: check_radios.py runs after
  // every build and fails it if a WiFi or BLE entry point has found its way
  // into the image. Off because it cannot be reached, rather than off because
  // it was asked nicely at boot.

  // Clock down. The logger must stay awake for the serial stream, so with the
  // radios gone this is the last power saving left.
  setCpuFrequencyMhz(80);

  bool displayOk = Screen::begin();

  // The card first, because everything downstream is pointless without it.
  bool mounted = LogFile::mount();
  bool writable = mounted && LogFile::proveWritable();
  uint32_t freeMb = mounted ? LogFile::freeMegabytes() : 0;

  // From flash, not the card, so it is available even when the slot is empty —
  // which is exactly the case where a file may have to be named later.
  g_bootCount = LogFile::nextBootCount();

  set_packet_meta_callback(onPacket);
  set_radio_config_callback(onRadioConfig);
  mt_serial_init(RADIO_RX_PIN, RADIO_TX_PIN, RADIO_BAUD);

  SelfTest::Result result =
      SelfTest::run(displayOk, mounted, writable, freeMb, onNodeReport);

  // Open the file after the test so BOOT is genuinely the first row. The
  // thirty seconds of listening are spent counting neighbours, not logging;
  // losing them off the front of a two-hour session costs nothing.
  if (writable && LogFile::open(NODE_SHORT_NAME, g_bootCount)) {
    char extra[360];
    SelfTest::toExtra(result, g_bootCount, extra, sizeof(extra));
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
    Serial.println("           Push a working card in and it starts a file on");
    Serial.println("           its own, without a power cycle. Nothing heard");
    Serial.println("           before that point is recoverable.");
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

  // Seeded with what the test concluded, so the first tick reports only what
  // has genuinely changed since somebody was stood here watching.
  Recovery::begin(NODE_SHORT_NAME, g_bootCount, result, onNodeReport);

  g_booting = false;
  refreshView();
  Screen::page(0, g_view);
  g_page = 0;
  g_screenOffAt = millis() + 30000;
  g_lastStatus = millis();
}

void loop() {
  uint32_t now = millis();

  mt_loop(now);

  // A file opened before the clock was known gets its date the moment one
  // arrives. No-op on every loop after that.
  if (LogFile::adoptClockName(NODE_SHORT_NAME)) {
    Serial.printf("clock    : time acquired — file is now %s\n", LogFile::fileName());
  }

  // The moment the radio names us, drop ourselves from the neighbour list. Not
  // tied to a radio recovery event: on the ordinary boot the radio answers
  // during the self-test, so no recovery ever fires and the stale self-entry
  // would sit in the count for the whole session.
  forgetSelf();

  // Everything that can break and then stop being broken: the card, the radio,
  // the position, the clock, the neighbours. Owns the node-report schedule too,
  // so that asking the radio anything is one decision made in one place.
  Recovery::Event ev = Recovery::tick(now, g_selfTest, g_peerCount);
  serviceRecovery(now, ev);

  LogFile::tick(now);

  if (now - g_lastStatus >= STATUS_INTERVAL_MS) {
    g_lastStatus = now;
    LogFile::writeStatus(ESP.getFreeHeap());
#if SERIAL_ECHO
    Serial.printf("status   %lu min  %lu packets  %lu rows  %lu dropped  card %s\n",
                  (unsigned long)(now / 60000),
                  (unsigned long)g_packetsSeen,
                  (unsigned long)LogFile::rowsWritten(),
                  (unsigned long)LogFile::dropped(),
                  LogFile::healthy() ? "ok" : "FAILED");
#endif
  }

  serviceButton(now);
  serviceLed(now);
}
