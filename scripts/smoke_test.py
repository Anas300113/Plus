"""Run non-authenticated go-live smoke checks against a deployed stack."""
from __future__ import annotations

import argparse
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def check(url: str, expected: int = 200) -> None:
    try:
        with urlopen(Request(url, headers={"User-Agent": "plus11-smoke-test/1"}), timeout=10) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
            if response.status != expected:
                raise RuntimeError(f"{url} returned HTTP {response.status}")
            if not body:
                raise RuntimeError(f"{url} returned an empty body")
            print(f"PASS {url} ({response.status})")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"{url} is unavailable: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--web", required=True, help="Public frontend origin, e.g. https://plus.example.com")
    parser.add_argument("--api", required=True, help="Backend origin, e.g. http://127.0.0.1:8001")
    args = parser.parse_args()
    try:
        check(args.web.rstrip("/") + "/")
        check(args.web.rstrip("/") + "/health")
        check(args.api.rstrip("/") + "/api/health")
        check(args.api.rstrip("/") + "/api/ready")
    except RuntimeError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1
    print("All unauthenticated go-live smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
