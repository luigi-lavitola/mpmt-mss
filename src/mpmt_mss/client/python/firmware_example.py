"""
Flashes firmware onto every defined channel, one at a time, using the
febmgr.flashFirmware RPC (see FEBManager.flashFirmware in feb_manager.py).

Each call takes roughly 30-90s (stm32flash itself, plus the settle time
needed to isolate the target channel on the shared UART) - long enough that
the default MSSClient timeout (10s) would time out mid-flash, so the client
here is built with a much longer one. A failed channel doesn't stop the
run: it's logged and the loop moves on to the next one, with a summary at
the end.

Usage:
    python firmware_example.py /path/to/firmware.hex
    python firmware_example.py /path/to/firmware.hex --channels 3,7,12
"""

import argparse
import sys

from mssclient import MSSClient, JsonRpcError, JsonRpcTransportError

FLASH_TIMEOUT_SEC = 180.0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", help="path to the .hex firmware file, on the mss host")
    parser.add_argument("--url", default="http://zynq:8000/rpc", help="mss RPC endpoint")
    parser.add_argument(
        "--channels",
        help="comma-separated channel numbers to flash (default: every defined channel)",
    )
    args = parser.parse_args()

    client = MSSClient(args.url, timeout=FLASH_TIMEOUT_SEC)

    if args.channels:
        channels = [int(c) for c in args.channels.split(",")]
    else:
        channels = sorted(client.febmgr.getDefinedChannels())

    print(f"Flashing {len(channels)} channel(s): {channels}")

    results = {}
    for channel in channels:
        print(f"--- channel {channel}: flashing '{args.firmware}' ---")
        try:
            results[channel] = client.febmgr.flashFirmware(channel, args.firmware)
        except JsonRpcError as exc:
            results[channel] = f"RPC error [{exc.code}] {exc.message}"
        except JsonRpcTransportError as exc:
            results[channel] = f"Transport error: {exc}"
        print(results[channel])

    print("\n--- summary ---")
    failed = 0
    for channel, result in results.items():
        ok = result.startswith("OK")
        failed += not ok
        print(f"channel {channel}: {'OK' if ok else 'FAILED'}")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
