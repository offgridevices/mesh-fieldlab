"""Fail the build if a 2.4 GHz radio entry point is linked into the image.

This node never transmits on 2.4 GHz. It reaches the mesh radio over a serial
pair and the card over SPI; WiFi and BLE take no part in any of it.

Keeping them off at runtime is the obvious approach and the wrong one. There is
no one-way "off" for WiFi, and the only way to ask for one is to call into the
WiFi stack, which links the whole stack in — measured at 133 KB of flash and
16 KB of RAM on this firmware, spent switching off something that was never on.

So the guarantee is made here instead, where it costs nothing at all: after
every build, look at what actually ended up in the image. You cannot start a
radio whose start function is not present. If one appears, some newly added
library brought it in, and the build stops rather than the battery going flat
in a field two hours early.

BLE is handled differently, in main.cpp: esp_bt_mem_release() is called at boot
and is irreversible for the rest of the boot. That call is allowed for below —
it is the off switch, not a use of the radio.
"""

import subprocess
import sys

Import("env")  # noqa: F821  (injected by PlatformIO)


# Any defined code symbol starting with one of these means a radio stack got
# linked in. Absolute (ROM address) and undefined symbols are ignored: the
# ESP32-C6 mask ROM carries WiFi routines and its symbol file names them in
# every image ever built for the chip, whether or not anything calls them.
FORBIDDEN_PREFIXES = (
    "esp_wifi_",
    "esp_ble_",
    "ble_hs_",
    "nimble_",
    "esp_bt_controller_",
)

# The off switch itself, and the helper it inlines. Present on purpose.
ALLOWED = {
    "esp_bt_mem_release",
    "esp_bt_mem_release_area",
    "esp_bt_controller_mem_release",
}

# Defined code symbols. Deliberately excludes "A" (absolute/ROM) and "U"
# (undefined), neither of which is code that exists in this image.
CODE_TYPES = set("TtWw")


def _nm_path(environment):
    """Derive the toolchain's nm from its gcc, which PlatformIO always sets."""
    cc = environment.subst("$CC")
    head, sep, tail = cc.rpartition("gcc")
    return head + "nm" + tail if sep else "nm"


def check_radios(source, target, env):
    elf = str(target[0])
    nm = _nm_path(env)

    try:
        out = subprocess.check_output([nm, elf], universal_newlines=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        # A check that cannot run must not quietly pass.
        sys.stderr.write("\ncheck_radios: could not read symbols from %s (%s)\n" % (elf, exc))
        env.Exit(1)
        return

    found = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        sym_type, name = parts[-2], parts[-1]
        if sym_type not in CODE_TYPES:
            continue
        if name in ALLOWED:
            continue
        if name.startswith(FORBIDDEN_PREFIXES):
            found.append(name)

    if found:
        sys.stderr.write(
            "\n"
            "=========================================================================\n"
            "RADIO CHECK FAILED\n"
            "\n"
            "A WiFi or BLE entry point is linked into this firmware. This node is\n"
            "supposed to have no 2.4 GHz radio in it at all: it talks to the mesh\n"
            "radio over serial and to the card over SPI, and its power budget and\n"
            "session length both assume the 2.4 GHz side is absent, not merely idle.\n"
            "\n"
            "Something added recently pulled a radio stack in. Symbols found:\n"
        )
        for name in sorted(set(found))[:20]:
            sys.stderr.write("    %s\n" % name)
        extra = len(set(found)) - 20
        if extra > 0:
            sys.stderr.write("    ...and %d more\n" % extra)
        sys.stderr.write(
            "\n"
            "Find what pulled it in and remove it. If a radio is genuinely needed\n"
            "one day, change this check deliberately — do not silence it to get a\n"
            "green build, because the next person will read a passing build as\n"
            "proof the radio is off.\n"
            "=========================================================================\n\n"
        )
        env.Exit(1)
        return

    print("check_radios: no WiFi or BLE entry points in the image")


env.AddPostAction(  # noqa: F821
    "$BUILD_DIR/${PROGNAME}.elf",
    env.VerboseAction(check_radios, "Checking for WiFi/BLE entry points"),  # noqa: F821
)
