#!/usr/bin/env python3
"""
Web UI hard-enforcement loop.

The native desktop GUI cannot render on a headless box, so the Web UI is the
ONLY usable interface. If Nighty — or the user via the interface — disables the
Web UI, this guard re-asserts it within a few seconds:

  • nighty.config  -> web = true
  • web_config.json -> the credentials/host/port from .env

It also keeps data/profile.json ASCII-encoded so Nighty (which reads it with the
cp1252 default under Wine) can always read it back; otherwise emoji in a profile
make the panel's "save profile" fail with HTTP 500.

For Rich Presence it is type-aware: only RPC presets crash the backend under
Box64 (image-asset fetch), so it disables auto-start / stops in memory ONLY for
RPC-type active profiles. Custom-status rotators are safe and left under the
user's control, so "Run last active profile on startup" works for them.

Started in the background by run.sh (and supervised by systemd). It writes only
when something actually changed, so it never fights Nighty's own writes.
"""
import os
import time

import enforce_config as ec  # same directory


def main():
    if os.environ.get("ENFORCE_WEBUI", "1") != "1":
        print("[guard] ENFORCE_WEBUI disabled — guard not running.")
        return
    interval = float(os.environ.get("ENFORCE_INTERVAL", "5"))
    # The in-memory RP crash-guard (stop_unsafe_running_profile) polls Nighty's live
    # profile state through the stub, which DISPATCHES ONTO NIGHTY'S MAIN THREAD.
    # On an emulated backend (Box64) doing that every few seconds steals CPU from
    # the bot's asyncio loop and shows up as gateway "heartbeat blocked" warnings —
    # which make the bot miss Discord's 3s interaction ACK window ("the application
    # did not respond"). The cheap, local on-disk guard (enforce_safe_presence)
    # already forces run_at_startup=False for RPC presets EVERY cycle, so they never
    # auto-start; the in-memory stop is only a backstop for a preset a user toggles
    # on by hand and does not need per-cycle granularity. So we keep the local
    # enforcement fast (interval) but poll the stub far less often (rp_interval),
    # cutting main-thread contention ~6x with no loss of auto-start protection.
    rp_interval = float(os.environ.get("RP_GUARD_INTERVAL", "30"))
    rotate_interval = float(os.environ.get("ROTATE_INTERVAL", "900"))
    print(f"[guard] Web UI hard-enforcement active (every {interval}s; "
          f"RP in-memory guard every {rp_interval}s; "
          f"log rotation every {rotate_interval}s)")
    last_rp = 0.0
    last_rotate = time.time()
    while True:
        try:
            appdata = ec.find_appdata()
            if appdata:
                ec.enforce_web(appdata)
                ec.enforce_safe_presence(appdata)     # heal encoding; disable only RPC auto-start
                ec.sync_nighty_log(appdata)           # ensure diagnostics/nighty.log is mirrored
            # Stop an RPC preset already running in memory (no-op for safe profiles).
            # Throttled: this is the only stub call in the loop, so it is the part
            # that contends with the bot's event loop under emulation.
            now = time.time()
            if now - last_rp >= rp_interval:
                ec.stop_unsafe_running_profile()
                last_rp = now
            if appdata and now - last_rotate >= rotate_interval:
                ec.rotate_and_clean_logs(appdata)
                last_rotate = now
        except Exception as e:
            print("[guard] error:", repr(e))
        time.sleep(interval)


if __name__ == "__main__":
    main()
