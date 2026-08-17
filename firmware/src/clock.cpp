#include "clock.h"

#include <sys/time.h>
#include <time.h>

#include "config.h"

namespace Clock {
namespace {

bool g_valid = false;

// localtime_r into a caller-supplied tm, for right now. Only meaningful once
// the clock has been set.
bool localNow(struct tm * out) {
  if (!g_valid) return false;
  time_t t = time(nullptr);
  return localtime_r(&t, out) != nullptr;
}

}  // namespace

void begin() {
  // POSIX timezone rule, which carries the daylight-saving changeover dates
  // with it. Doing it this way means the firmware never has to know today's
  // date to work out today's offset — the C library does it, correctly, for
  // any date, including the ones years from now.
  setenv("TZ", TZ_POSIX, 1);
  tzset();
}

bool adopt(uint32_t epoch) {
  if (epoch < EPOCH_FLOOR) return false;
  if (g_valid) return false;

  struct timeval tv;
  tv.tv_sec = (time_t)epoch;
  tv.tv_usec = 0;
  if (settimeofday(&tv, nullptr) != 0) return false;

  g_valid = true;
  return true;
}

bool valid() { return g_valid; }

uint32_t nowEpoch() {
  if (!g_valid) return 0;
  return (uint32_t)time(nullptr);
}

void stamp(char * out, size_t n) {
  struct tm tm;
  if (!localNow(&tm)) {
    snprintf(out, n, "00000000_0000");
    return;
  }
  strftime(out, n, "%Y%m%d_%H%M", &tm);
}

long utcOffsetSeconds() {
  if (!g_valid) return 0;

  // The obvious way to do this is tm_gmtoff, which the ESP's C library does
  // not have — it is a BSD extension, not standard C. So take the same
  // instant apart twice, once local and once UTC, and subtract.
  time_t t = time(nullptr);
  struct tm lt, gt;
  if (localtime_r(&t, &lt) == nullptr) return 0;
  if (gmtime_r(&t, &gt) == nullptr) return 0;

  long off = (lt.tm_hour - gt.tm_hour) * 3600L
           + (lt.tm_min  - gt.tm_min)  * 60L
           + (lt.tm_sec  - gt.tm_sec);

  // The two can land on different days, and at new year on different years,
  // which makes the raw day-of-year difference nonsense. A real offset is
  // never more than a day, so anything larger is the wrap.
  int days = lt.tm_yday - gt.tm_yday;
  if (days > 1)       days = -1;
  else if (days < -1) days = 1;
  return off + days * 86400L;
}

const char * zoneName() {
  if (!g_valid) return "?";

  // tzname is the standard C way in; tm_zone is not available here.
  time_t t = time(nullptr);
  struct tm lt;
  if (localtime_r(&t, &lt) == nullptr) return "?";
  const char * name = tzname[lt.tm_isdst > 0 ? 1 : 0];
  return (name != nullptr && name[0] != '\0') ? name : "?";
}

}  // namespace Clock
