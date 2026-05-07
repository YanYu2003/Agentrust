#!/usr/bin/env python3
"""Wait until an HTTP URL returns 200 (simple readiness probe for run_demo)."""
from __future__ import annotations

import sys
import time
import urllib.request


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: wait_health.py <url> [timeout_seconds]", file=sys.stderr)
        sys.exit(2)
    url = sys.argv[1]
    timeout_s = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.getcode() == 200:
                    print(f"OK {url}")
                    sys.exit(0)
        except OSError:
            pass
        time.sleep(1)
    print(f"TIMEOUT waiting for {url}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
