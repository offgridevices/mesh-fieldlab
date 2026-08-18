#include "logfile.h"

#include <FS.h>
#include <Preferences.h>
#include <SD.h>
#include <SPI.h>

#include "clock.h"
#include "config.h"
#include "log_schema.h"

namespace LogFile {
namespace {

File     g_file;
char     g_name[64] = {0};
bool     g_mounted = false;
bool     g_healthy = false;
bool     g_dated = false;      // is g_name the date-stamped form?
uint32_t g_rows = 0;
uint32_t g_dropped = 0;
uint32_t g_sinceFlush = 0;
uint32_t g_lastFlush = 0;
uint32_t g_lastRetry = 0;
uint8_t  g_failedTries = 0;

// One row is well under this. Sized with room to spare rather than tuned:
// a truncated row is a corrupted measurement, and RAM is not the constraint.
char g_line[512];

// Marks the card unusable and closes the handle, so the retry path starts
// from a clean state rather than a half-open file.
void fail() {
  g_healthy = false;
  if (g_file) g_file.close();
}

void append(const char * line) {
  // A row formed while the card is down is counted, not silently forgotten.
  // The count is the only honest measure of how much a session lost, and it is
  // written into every status row from the moment the card comes back.
  if (!g_healthy || !g_file) {
    g_dropped++;
    return;
  }

  size_t wanted = strlen(line);
  if (g_file.write((const uint8_t *)line, wanted) != wanted) {
    fail();
    g_dropped++;
    return;
  }
  g_rows++;
  g_sinceFlush++;
}

// The date-stamped name, in local time, never colliding with one already on
// the card.
//
// Two boots inside the same minute is rare, and a brownout loop is the way it
// happens — which is exactly the case where the earlier file is the one that
// explains what went wrong. Overwriting it would destroy the evidence.
void datedName(char * out, size_t n, const char * shortName) {
  char when[16];
  Clock::stamp(when, sizeof(when));
  snprintf(out, n, "/LOG_%s_%s.csv", shortName, when);
  for (int i = 2; i <= 9 && SD.exists(out); i++) {
    snprintf(out, n, "/LOG_%s_%s-%d.csv", shortName, when, i);
  }
}

// The name used when the clock is still unset. The boot counter is the only
// thing that distinguishes one session from the next, and it is enough: it
// survives power cuts, so nothing is ever overwritten.
void bootName(char * out, size_t n, const char * shortName, uint32_t bootCount) {
  snprintf(out, n, "/LOG_%s_%lu.csv", shortName, (unsigned long)bootCount);
}

// Every row starts with the same three fields, and every non-packet row
// zeroes the packet columns. Building that once keeps the callers honest.
int prefix(char * out, size_t n, uint32_t devTime) {
  return snprintf(out, n, "%d,%lu,%lu,%lu,",
                  LOG_SCHEMA_VERSION,
                  (unsigned long)millis(),
                  (unsigned long)devTime,
                  (unsigned long)my_node_num);
}

}  // namespace

bool mount() {
  if (g_mounted) return true;
  if (!SD.begin(SD_CS_PIN)) return false;
  g_mounted = true;
  return true;
}

bool proveWritable() {
  const char * path = "/.writetest";
  const char * mark = "logger-writetest\n";

  File f = SD.open(path, FILE_WRITE);
  if (!f) return false;
  size_t wrote = f.write((const uint8_t *)mark, strlen(mark));
  f.flush();
  f.close();
  if (wrote != strlen(mark)) { SD.remove(path); return false; }

  f = SD.open(path, FILE_READ);
  if (!f) return false;
  char back[32] = {0};
  size_t read = f.readBytes(back, sizeof(back) - 1);
  f.close();
  SD.remove(path);

  return read == strlen(mark) && strcmp(back, mark) == 0;
}

uint32_t freeMegabytes() {
  if (!g_mounted) return 0;
  uint64_t total = SD.totalBytes();
  uint64_t used = SD.usedBytes();
  if (used > total) return 0;
  return (uint32_t)((total - used) / (1024ULL * 1024ULL));
}

uint32_t nextBootCount() {
  Preferences prefs;
  if (!prefs.begin("logger", false)) return 0;
  uint32_t n = prefs.getUInt("boot", 0) + 1;
  prefs.putUInt("boot", n);
  prefs.end();
  return n;
}

bool open(const char * shortName, uint32_t bootCount) {
  // If the radio has already told us the time — the usual case, because the
  // self-test spends thirty seconds listening before this is called — the file
  // is born with its date on it. If not, it opens under the boot counter and
  // gets renamed later. Logging never waits for a clock.
  // Recovery can reach here mid-session with a stale handle from the card that
  // went away. Let go of it before taking another.
  if (g_file) g_file.close();

  g_dated = Clock::valid();
  if (g_dated) datedName(g_name, sizeof(g_name), shortName);
  else         bootName(g_name, sizeof(g_name), shortName, bootCount);

  g_file = SD.open(g_name, FILE_WRITE);
  if (!g_file) return false;

  g_healthy = true;
  g_file.print(LOG_HEADER);
  g_file.print('\n');
  g_file.flush();
  g_lastFlush = millis();

  // A new file counts its own rows. The dropped-row count is deliberately left
  // cumulative — it measures what the session lost, which spans files — but
  // rows= is read against the file it appears in, and a count carried over from
  // a card no longer in the slot cannot be reconciled with anything.
  g_rows = 0;
  g_sinceFlush = 0;
  return true;
}

bool isDated() { return g_dated; }

bool adoptClockName(const char * shortName) {
  if (g_dated || !Clock::valid()) return false;
  if (!g_healthy || !g_file) return false;

  char target[sizeof(g_name)];
  datedName(target, sizeof(target), shortName);

  // Close before renaming: a rename under an open handle is the kind of thing
  // that works on one FAT implementation and quietly corrupts on another.
  g_file.flush();
  g_file.close();

  if (!SD.rename(g_name, target)) {
    // The name is cosmetic and the data is not. Reopen what we had and carry
    // on under the boot-counter name rather than dropping the session.
    g_file = SD.open(g_name, FILE_APPEND);
    if (!g_file) fail();
    return false;
  }

  strncpy(g_name, target, sizeof(g_name) - 1);
  g_name[sizeof(g_name) - 1] = '\0';

  g_file = SD.open(g_name, FILE_APPEND);
  if (!g_file) { fail(); return false; }

  g_dated = true;
  g_lastFlush = millis();
  return true;
}

void writeBoot(const char * extra) {
  // Once the clock is set every row carries absolute time, not just packet
  // rows. That is what lets two nodes' files be lined up against each other
  // across a quiet stretch when nothing was received.
  int n = prefix(g_line, sizeof(g_line), Clock::nowEpoch());
  snprintf(g_line + n, sizeof(g_line) - n, "0,0,0,0.00,0,0,0,0,0,0,0,0,0," ROW_BOOT ",%s\n", extra);
  append(g_line);
}

void writePacket(const mt_packet_meta_t * meta) {
  // hop_start below hop_limit would be nonsense on the wire, but a corrupt
  // frame can produce it. Clamping here keeps hops_used consistent with its
  // own inputs rather than writing a row the checker will reject.
  uint8_t hops = (meta->hop_start >= meta->hop_limit)
                   ? (uint8_t)(meta->hop_start - meta->hop_limit)
                   : 0;

  int n = prefix(g_line, sizeof(g_line), meta->rx_time);
  snprintf(g_line + n, sizeof(g_line) - n,
           "%lu,%lu,%ld,%.2f,%u,%u,%u,%u,%u,%u,%lu,%u,%u," ROW_PKT ",\n",
           (unsigned long)meta->from,
           (unsigned long)meta->id,
           (long)meta->rx_rssi,
           meta->rx_snr,
           (unsigned)meta->hop_limit,
           (unsigned)meta->hop_start,
           (unsigned)hops,
           (unsigned)meta->relay_node,
           (unsigned)meta->next_hop,
           (unsigned)(meta->via_mqtt ? 1 : 0),
           (unsigned long)meta->portnum,
           (unsigned)meta->payload_size,
           (unsigned)meta->channel);
  append(g_line);
}

void writeStatus(uint32_t freeHeap, const char * note) {
  // Once the clock is set every row carries absolute time, not just packet
  // rows. That is what lets two nodes' files be lined up against each other
  // across a quiet stretch when nothing was received.
  int n = prefix(g_line, sizeof(g_line), Clock::nowEpoch());
  n += snprintf(g_line + n, sizeof(g_line) - n,
                "0,0,0,0.00,0,0,0,0,0,0,0,0,0," ROW_STATUS
                ",rows=%lu;heap=%lu;sd_ok=%d;drops=%lu",
                (unsigned long)g_rows,
                (unsigned long)freeHeap,
                g_healthy ? 1 : 0,
                (unsigned long)g_dropped);
  // Named here rather than inferred from a gap in the timestamps, because a
  // gap says only that something stopped. Which block came back, and when, is
  // the difference between a file somebody can explain and one they distrust.
  if (note != nullptr && note[0] != '\0') {
    n += snprintf(g_line + n, sizeof(g_line) - n, ";recov=%s", note);
  }
  snprintf(g_line + n, sizeof(g_line) - n, "\n");
  append(g_line);
}

void writeNode(const mt_node_t * node) {
  // The name is the only free text that reaches the file. A comma or a
  // separator inside it would split the row apart somewhere no reader could
  // detect, so it is rewritten rather than trusted.
  char name[MAX_SHORT_NAME_LEN + 1];
  if (node->has_user) {
    strncpy(name, node->short_name, sizeof(name) - 1);
    name[sizeof(name) - 1] = '\0';
  } else {
    name[0] = '\0';
  }
  for (char * p = name; *p; p++) {
    if (*p == ',' || *p == EXTRA_PAIR_SEP || *p == EXTRA_KV_SEP || *p < 32 || *p > 126) {
      *p = '_';
    }
  }
  if (name[0] == '\0') { name[0] = '_'; name[1] = '\0'; }

  // Once the clock is set every row carries absolute time, not just packet
  // rows. That is what lets two nodes' files be lined up against each other
  // across a quiet stretch when nothing was received.
  int n = prefix(g_line, sizeof(g_line), Clock::nowEpoch());
  snprintf(g_line + n, sizeof(g_line) - n,
           "%lu,0,0,0.00,0,0,0,0,0,0,0,0,0," ROW_NODE
           ",name=%s;lat=%.6f;lon=%.6f;batt=%u;last_heard=%lu\n",
           (unsigned long)node->node_num,
           name,
           node->latitude,
           node->longitude,
           (unsigned)node->battery_level,
           (unsigned long)node->last_heard_from);
  append(g_line);
}

void tick(uint32_t now) {
  if (!g_healthy) return;
  if (g_sinceFlush >= FLUSH_EVERY_ROWS ||
      (g_sinceFlush > 0 && now - g_lastFlush >= FLUSH_INTERVAL_MS)) {
    g_file.flush();
    g_sinceFlush = 0;
    g_lastFlush = now;
  }
}

Recovery recover(const char * shortName, uint32_t bootCount) {
  if (g_healthy) return Recovery::NONE;

  // Try soon after a failure, then less often. Re-initialising the bus against
  // an empty slot is not free, and a node that spends a whole field day
  // retrying every five seconds is spending that time not listening. The first
  // few attempts are the ones that matter — a card reseated by hand, or a write
  // that failed once — and after those the fault needs a person anyway.
  uint32_t wait = SD_RETRY_MS << (g_failedTries > 3 ? 3 : g_failedTries);
  if (wait > RECOVERY_INTERVAL_MS) wait = RECOVERY_INTERVAL_MS;
  uint32_t now = millis();
  if (g_lastRetry != 0 && now - g_lastRetry < wait) return Recovery::NONE;
  g_lastRetry = now;

  auto giveUpForNow = [&]() {
    if (g_failedTries < 255) g_failedTries++;
    return Recovery::NONE;
  };

  // From scratch every time. A card that was pulled and pushed back in is a
  // different volume as far as the driver is concerned, and reusing the old
  // mount state is how you get a handle that accepts writes into nowhere.
  SD.end();
  g_mounted = false;
  if (!mount()) return giveUpForNow();

  // Mounting is not the same as working. The boot test proves the card takes
  // data before trusting it and so does this: a card that mounts and silently
  // discards writes would otherwise read as a full recovery and lose the rest
  // of the session as convincingly as no card at all.
  if (!proveWritable()) return giveUpForNow();

  g_failedTries = 0;

  // Our own file is still there — the ordinary case of a write that failed, or
  // a card reseated without being swapped. Carry on where the session left off.
  if (g_name[0] != '\0' && SD.exists(g_name)) {
    g_file = SD.open(g_name, FILE_APPEND);
    if (!g_file) return giveUpForNow();
    g_healthy = true;
    g_lastFlush = now;
    return Recovery::RESUMED;
  }

  // Either nothing was ever opened, because the node started with an empty
  // slot, or this is a different card. Both need a file of their own, and both
  // need a BOOT row before anything in it can be interpreted — which is the
  // caller's job, and why the two outcomes are distinguished.
  if (!open(shortName, bootCount)) return giveUpForNow();
  return Recovery::RESTARTED;
}

bool healthy() { return g_healthy; }
bool mounted() { return g_mounted; }
uint32_t rowsWritten() { return g_rows; }
uint32_t dropped() { return g_dropped; }
const char * fileName() { return g_name; }

}  // namespace LogFile
