#include "logfile.h"

#include <FS.h>
#include <Preferences.h>
#include <SD.h>
#include <SPI.h>

#include "config.h"
#include "log_schema.h"

namespace LogFile {
namespace {

File     g_file;
char     g_name[32] = {0};
bool     g_mounted = false;
bool     g_healthy = false;
uint32_t g_rows = 0;
uint32_t g_sinceFlush = 0;
uint32_t g_lastFlush = 0;
uint32_t g_lastRetry = 0;

// One row is well under this. Sized with room to spare rather than tuned:
// a truncated row is a corrupted measurement, and RAM is not the constraint.
char g_line[320];

// Marks the card unusable and closes the handle, so the retry path starts
// from a clean state rather than a half-open file.
void fail() {
  g_healthy = false;
  if (g_file) g_file.close();
}

void append(const char * line) {
  if (!g_healthy || !g_file) return;

  size_t wanted = strlen(line);
  if (g_file.write((const uint8_t *)line, wanted) != wanted) {
    fail();
    return;
  }
  g_rows++;
  g_sinceFlush++;
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
  snprintf(g_name, sizeof(g_name), "/LOG_%s_%lu.csv", shortName, (unsigned long)bootCount);

  g_file = SD.open(g_name, FILE_WRITE);
  if (!g_file) return false;

  g_healthy = true;
  g_file.print(LOG_HEADER);
  g_file.print('\n');
  g_file.flush();
  g_lastFlush = millis();
  return true;
}

void writeBoot(const char * extra) {
  int n = prefix(g_line, sizeof(g_line), 0);
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

void writeStatus(uint32_t freeHeap) {
  int n = prefix(g_line, sizeof(g_line), 0);
  snprintf(g_line + n, sizeof(g_line) - n,
           "0,0,0,0.00,0,0,0,0,0,0,0,0,0," ROW_STATUS ",rows=%lu;heap=%lu;sd_ok=%d\n",
           (unsigned long)g_rows,
           (unsigned long)freeHeap,
           g_healthy ? 1 : 0);
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

  int n = prefix(g_line, sizeof(g_line), 0);
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
  if (g_healthy) {
    if (g_sinceFlush >= FLUSH_EVERY_ROWS ||
        (g_sinceFlush > 0 && now - g_lastFlush >= FLUSH_INTERVAL_MS)) {
      g_file.flush();
      g_sinceFlush = 0;
      g_lastFlush = now;
    }
    return;
  }

  // Unhealthy: keep trying, on a timer, forever. Never give up and never
  // stop the caller from running.
  if (now - g_lastRetry < SD_RETRY_MS) return;
  g_lastRetry = now;

  SD.end();
  g_mounted = false;
  if (!mount()) return;

  g_file = SD.open(g_name, FILE_APPEND);
  if (!g_file) return;
  g_healthy = true;
  g_lastFlush = now;
}

bool healthy() { return g_healthy; }
uint32_t rowsWritten() { return g_rows; }
const char * fileName() { return g_name; }

}  // namespace LogFile
