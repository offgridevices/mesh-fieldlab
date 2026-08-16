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

// Open /LOG_<shortName>_<bootCount>.csv and write the header.
bool open(const char * shortName, uint32_t bootCount);

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
