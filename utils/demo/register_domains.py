#!/usr/bin/env python3
import sys
import json
import urllib.request
import urllib.error

DOMAINS = [
    ("domain1", "10.5.15.55:8090"),
    ("domain2", "10.5.99.6:8090"),
    ("domain3", "10.5.99.5:8090"),
]

TIMEOUT = 10  # seconds

def post_and_print(name: str, endpoint: str) -> bool:
    url = f"http://{endpoint}/register_domain/{name}"
    req = urllib.request.Request(url, data=b"", method="POST")
    print(f"\n=== POST {url} ===")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read()
            # Try JSON pretty-print first
            try:
                parsed = json.loads(body.decode("utf-8"))
                print(json.dumps(parsed, indent=2, sort_keys=True))
            except json.JSONDecodeError:
                # Fallback: print raw body if not JSON
                print(body.decode("utf-8", errors="replace"))
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        print(f"HTTPError {e.code}: {e.reason}")
        try:
            err_body = e.read().decode("utf-8", errors="replace")
            print(err_body)
        except Exception:
            pass
        return False
    except urllib.error.URLError as e:
        print(f"URLError: {e.reason}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    failures = 0
    for name, endpoint in DOMAINS:
        ok = post_and_print(name, endpoint)
        if not ok:
            failures += 1
    if failures:
        print(f"\nCompleted with {failures} failure(s).")
        sys.exit(1)
    print("\nAll requests succeeded.")

if __name__ == "__main__":
    main()
