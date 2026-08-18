#include "recovery.h"

#include "clock.h"
#include "config.h"
#include "logfile.h"

namespace Recovery {
namespace {

const char * g_shortName = "";
uint32_t     g_bootCount = 0;
void (*g_nodeReportCb)(mt_node_t *, mt_nr_progress_t) = nullptr;

//: Which blocks were working as of the last tick. The diff against this is
//: what turns a level ("the card is fine") into an event ("the card came
//: back"), and an event is the only thing worth printing or recording.
uint8_t g_was = 0;

//: millis() of the last word from the radio. Zero means it has never spoken,
//: which is a different state from having gone quiet and matters at boot: a
//: node whose radio never answered must not be told its radio just died.
uint32_t g_lastContact = 0;

//: The ordinary once-every-five-minutes node report, kept exactly as it was.
//: Recovery probes are counted separately so they cannot displace it.
uint32_t g_lastOrdinary = 0;
uint32_t g_lastProbe = 0;
uint32_t g_probeUntil = 0;

bool radioAlive(uint32_t now) {
  // Never answered at all is not the same as fallen silent, and neither is a
  // reason to guess. my_node_num is set only by a reply, so it is the proof
  // that the link worked at least once.
  if (my_node_num == 0 || g_lastContact == 0) return false;
  return (now - g_lastContact) < RADIO_SILENT_MS;
}

void ask(uint32_t now, bool probe) {
  if (g_nodeReportCb == nullptr) return;
  // An ordinary report closes any probe window still open, so a probe fired
  // seconds earlier cannot swallow the one report of the five minutes that was
  // meant to reach the card.
  g_probeUntil = probe ? now + PROBE_WINDOW_MS : 0;
  mt_request_node_report(g_nodeReportCb);
}

uint8_t currentMask(const SelfTest::Result & r, uint32_t now, bool heardAny) {
  uint8_t mask = 0;
  if (LogFile::healthy())          mask |= B_CARD;
  if (radioAlive(now))             mask |= B_RADIO;
  if (SelfTest::positionUsable(r)) mask |= B_POS;
  if (Clock::valid())              mask |= B_CLOCK;
  if (heardAny)                    mask |= B_HEARD;
  return mask;
}

}  // namespace

void begin(const char * shortName, uint32_t bootCount,
           const SelfTest::Result & boot,
           void (*nodeReportCb)(mt_node_t *, mt_nr_progress_t)) {
  g_shortName    = shortName;
  g_bootCount    = bootCount;
  g_nodeReportCb = nodeReportCb;

  uint32_t now = millis();
  g_lastOrdinary = now;

  // Seeded from what the boot test found, so the first tick compares like with
  // like. Starting from zero would report every healthy block as a recovery in
  // the first thirty seconds and put a meaningless recov= row in every file.
  g_was = 0;
  if (LogFile::healthy())             g_was |= B_CARD;
  if (boot.radio_ok)                  g_was |= B_RADIO;
  if (SelfTest::positionUsable(boot)) g_was |= B_POS;
  if (boot.clock_set)                 g_was |= B_CLOCK;
  if (boot.heard_count > 0)           g_was |= B_HEARD;

  // Start the silence clock at the end of the boot test, not from whenever the
  // radio last happened to speak. The test can spend ten minutes waiting for a
  // clock in complete silence — longer than RADIO_SILENT_MS — so a radio that
  // answered perfectly well would otherwise be condemned by the very first
  // tick. Zero stays the sentinel for a radio that never answered: my_node_num
  // is set only by a reply, so it is the proof the link worked.
  if (my_node_num != 0) g_lastContact = (now == 0) ? 1 : now;
}

void noteRadioContact(uint32_t now) {
  // Never zero, because zero is the sentinel for "never heard from". One
  // millisecond of error at boot is not worth a second variable.
  g_lastContact = (now == 0) ? 1 : now;
}

bool suppressNodeRows(uint32_t now) {
  return g_probeUntil != 0 && (int32_t)(now - g_probeUntil) < 0;
}

Event tick(uint32_t now, SelfTest::Result & r, uint8_t heardCount) {
  Event e;

  // --- the card -------------------------------------------------------------
  // First, because it owns its own back-off timer and because everything below
  // wants to know the answer it produces rather than the one from last tick.
  LogFile::Recovery card = LogFile::recover(g_shortName, g_bootCount);
  e.newFile = (card == LogFile::Recovery::RESTARTED);

  // --- the radio ------------------------------------------------------------
  // Settings are re-read on the way back up; that is SelfTest's business, and
  // it is told the verdict rather than working it out, because deciding a
  // radio has gone quiet means watching a clock and not the protocol.
  SelfTest::reviewRadio(r, radioAlive(now));

  // --- the settings ---------------------------------------------------------
  // Position, battery and the LoRa config all arrive from the radio and all
  // keep changing. Somebody standing at a node with a phone is exactly how a
  // position gets set an hour into a session, and this is what notices.
  SelfTest::refreshOwn(r);

  // --- and the rest of the boot test's snapshot -----------------------------
  // These three are read straight back out of the Result by two things that
  // must not be allowed to lie: the single word on the screen, and any BOOT
  // row written into a file opened later. Left at their boot values, a node
  // whose card arrived twenty minutes late would open a fresh file and write
  // into it that the card would not mount — which the checker rejects, so the
  // recovered session would be thrown away by the very tool meant to read it.
  r.card_mounted  = LogFile::mounted();
  r.card_writable = LogFile::healthy();
  r.clock_set     = Clock::valid();
  r.heard_count   = heardCount;

  // --- asking the radio anything at all -------------------------------------
  // The ordinary schedule is untouched: one node report every five minutes,
  // written to the card as before. Everything else is an extra, unlogged ask
  // made only while something is wrong, because that is the only time a faster
  // answer is worth the serial traffic.
  if (now - g_lastOrdinary >= NODE_REPORT_MS) {
    g_lastOrdinary = now;
    g_lastProbe = now;
    ask(now, false);
  } else {
    // What a probe can achieve depends on what is wrong. A card fault is not in
    // this list at all: the card recovers on its own timer, and no amount of
    // asking the radio moves it — the old code probed anyway, every thirty
    // seconds, for as long as the slot stayed empty.
    uint32_t askEvery = 0;
    if (!r.radio_ok) {
      // A silent radio is asked hard and often. It costs nothing, nothing is
      // arriving anyway, and the sooner it answers the sooner the node records.
      askEvery = RADIO_ASK_EVERY_MS;
    } else if (now - g_lastContact >= RADIO_SILENT_MS / 2) {
      // Quiet, but not yet condemned. A single dropped reply must not be left
      // to sit until the next scheduled report before anyone checks again.
      askEvery = RECOVERY_INTERVAL_MS;
    } else if (!SelfTest::positionUsable(r)) {
      askEvery = POS_PROBE_MS;
    }
    if (askEvery != 0 && now - g_lastProbe >= askEvery) {
      g_lastProbe = now;
      ask(now, true);
    }
  }

  // --- what changed ---------------------------------------------------------
  uint8_t mask = currentMask(r, now, heardCount > 0);
  e.recovered = (uint8_t)(mask & ~g_was);
  e.lost      = (uint8_t)(g_was & ~mask);
  g_was = mask;
  return e;
}

const char * describe(uint8_t mask, char * out, size_t n) {
  static const struct { uint8_t bit; const char * name; } NAMES[] = {
    {B_CARD, "card"}, {B_RADIO, "radio"}, {B_POS, "pos"},
    {B_CLOCK, "clock"}, {B_HEARD, "heard"},
  };
  size_t used = 0;
  if (n == 0) return out;
  out[0] = '\0';
  for (const auto & entry : NAMES) {
    if (!(mask & entry.bit)) continue;
    // Joined with '+' rather than a comma or a semicolon: this string goes
    // into the extra column, where either of those would split the field
    // somewhere no reader could detect.
    int wrote = snprintf(out + used, n - used, "%s%s", used ? "+" : "", entry.name);
    if (wrote <= 0 || (size_t)wrote >= n - used) break;
    used += (size_t)wrote;
  }
  return out;
}

}  // namespace Recovery
