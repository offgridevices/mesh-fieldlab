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
void writeStatus(uint32_t freeHeap);
void writeNode(const mt_node_t * node);

// Call every loop. Owns the flush policy and the remount retry.
void tick(uint32_t now);

bool healthy();
uint32_t rowsWritten();
const char * fileName();

}  // namespace LogFile
