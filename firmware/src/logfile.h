#pragma once

#include <Arduino.h>
#include <Meshtastic.h>

// The card. Everything that reaches disk goes through here.
//
// The governing rule is that a card fault must never stop the node. If writes
// start failing the logger keeps counting, keeps signalling, and keeps trying
// to remount — a node that logs a gap is far more useful than one that halts.
namespace LogFile {

// Mount the card. Safe to call repeatedly; that is how remounting works.
bool mount();

// Prove the card actually accepts data, not merely that it mounted. Writes a
// scratch file, flushes it, reads it back, removes it. A card that mounts but
// silently discards writes looks healthy for hours, which is the worst way to
// lose a field day.
bool proveWritable();

uint32_t freeMegabytes();

// Read and increment the persistent boot counter. Survives power cuts, which
// is what makes one-file-per-boot work.
uint32_t nextBootCount();

// Open the session file and write the header.
//
// Named /LOG_<shortName>_<YYYYMMDD>_<HHMM>.csv in local time when the clock is
// set, which it normally is by this point — the self-test has already spent
// thirty seconds listening, and any packet it heard carries the time.
//
// When the clock is not set the file opens as /LOG_<shortName>_<bootCount>.csv
// instead and adoptClockName() renames it later. Logging never waits for a
// clock; a file with an awkward name beats a field day with no file.
bool open(const char * shortName, uint32_t bootCount);

// True once the open file carries a date rather than a boot counter.
bool isDated();

// Rename a boot-counter file to its date-stamped name, now that the time is
// known. Returns true only on the rename that actually happened, so the
// caller can report it once.
//
// Safe to call every loop: it is a no-op if the file is already dated or the
// clock is still unset.
bool adoptClockName(const char * shortName);

void writeBoot(const char * extra);
void writePacket(const mt_packet_meta_t * meta);

// `note` becomes the row's recov= key, naming whatever just came back. Null
// for the ordinary once-a-minute row.
void writeStatus(uint32_t freeHeap, const char * note = nullptr);
void writeNode(const mt_node_t * node);

// Call every loop. Owns the flush policy only; recovery is attempted through
// recover() so that its timing is one decision made in one place.
void tick(uint32_t now);

// What an attempt to bring the card back actually achieved.
enum class Recovery : uint8_t {
  NONE,      // still no usable card
  RESUMED,   // the session's own file was there and is open again
  RESTARTED  // a usable card with no file of ours on it; a new one is open
};

// Try to make the card usable again. Safe and cheap to call on a timer, and
// designed to be called forever: a node whose card is missing must still be
// able to start recording the moment somebody pushes one in.
//
// The case that motivates the whole function is a node switched on with an
// empty slot. Nothing was ever opened, so there is no file to reopen — the old
// retry path could only ever reattach to a name that already existed, which
// meant a card inserted after boot was mounted, proven, and then ignored for
// the rest of the session.
//
// RESTARTED tells the caller the returned file is empty apart from its header
// and still needs a BOOT row, because a file that cannot say how the node was
// configured is not analysable.
Recovery recover(const char * shortName, uint32_t bootCount);

bool healthy();

// A card is present and mounted. Not the same as healthy(): a card that
// mounts and then refuses a test write is mounted and useless, and telling
// those apart is the difference between "push it in properly" and "bring a
// different card".
bool mounted();

uint32_t rowsWritten();

// Rows that were formed but had nowhere to go, because the card was down when
// they were written. Counted rather than buffered: the number is what tells a
// reader how big the hole in a session really is.
uint32_t dropped();

const char * fileName();

}  // namespace LogFile
