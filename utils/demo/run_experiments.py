#!/usr/bin/env python3
# run_experiments.py  (threaded)
#
# Usage examples:
#   python3 run_experiments.py --runs 3 --export true
#   python3 run_experiments.py --runs 1 --export false
#
# Notes:
# - Requires: requests (pip install requests)
# - Python 3.6+ compatible

import argparse
import json
import time
import threading
from typing import Any, Dict
import requests

# --- Default endpoints (change if needed) ---
URL_CONSUMER_DOMAIN1 = "http://10.5.15.55:8090/start_demo_consumer"
URL_PROVIDER_DOMAIN2 = "http://10.5.99.6:8090/start_demo_provider"
URL_PROVIDER_DOMAIN3 = "http://10.5.99.5:8090/start_demo_provider"

HEADERS = {"Content-Type": "application/json"}

print_lock = threading.Lock()  # keep logs tidy across threads

def post_json(url: str, payload: Dict[str, Any], timeout: int = 80) -> Dict[str, Any]:
    """POST JSON and return parsed JSON (or raise)."""
    resp = requests.post(url, headers=HEADERS, data=json.dumps(payload), timeout=timeout)
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        raise RuntimeError("HTTP {} from {}: {}".format(resp.status_code, url, resp.text)) from e
    try:
        return resp.json()
    except ValueError:
        return {"raw": resp.text}

def worker(name: str, url: str, payload: Dict[str, Any], timeout: int, out: Dict[str, Any]) -> None:
    """Thread target: perform request, capture result or error."""
    with print_lock:
        print("[{}] → POST {}  payload: {}".format(name, url, json.dumps(payload)))
    try:
        res = post_json(url, payload, timeout=timeout)
        out[name] = {"ok": True, "response": res}
        with print_lock:
            print("[{}] ✓ response: {}".format(name, json.dumps(res, indent=2)))
    except Exception as e:
        out[name] = {"ok": False, "error": str(e)}
        with print_lock:
            print("[{}] ✗ error: {}".format(name, e))

def run_once(run_idx: int, export_to_csv: bool) -> None:
    print("\n=== RUN {} (concurrent) ===".format(run_idx))

    # Build per-run payloads (same as your baseline, just threaded)
    provider2_csv = "/exeriments/data/provider_domain_2_run_{}.csv".format(run_idx)
    provider3_csv = "/exeriments/data/provider_domain_3_run_{}.csv".format(run_idx)
    consumer_csv  = "/exeriments/data/consumer_domain_1_run_{}.csv".format(run_idx)

    payload_provider2 = {
        "description_filter": "detnet_transport",
        "price_wei_per_hour": 10000,
        "location": "5TONIC @ Madrid, Spain",
        "export_to_csv": export_to_csv,
        "csv_path": provider2_csv,
    }

    payload_provider3 = {
        "description_filter": "ros_app_k8s_deployment",
        "price_wei_per_hour": 10000,
        "location": "5TONIC @ Madrid, Spain",
        "export_to_csv": export_to_csv,
        "csv_path": provider3_csv,
    }

    payload_consumer = {
        "service1_description": "detnet_transport",
        "service1_max_latency_ms": 50,
        "service1_max_jitter_ms": 20,
        "service1_min_bandwidth_Mbps": 1,
        "service1_deployment_manifest_cid": "service1_cid",

        "service2_description": "ros_app_k8s_deployment",
        "service2_availability": 9999,
        "service2_compute_cpu_mcores": 2000,
        "service2_compute_ram_MB": 4000,
        "service2_deployment_manifest_cid": "service2_cid",

        "expected_hours": 2,
        "export_to_csv": export_to_csv,
        "csv_path": consumer_csv,
        # "offers_to_wait": 1,  # add if your API expects it
    }

    # Fire all three in parallel
    results: Dict[str, Any] = {}
    threads = [
        threading.Thread(target=worker, args=("domain2/provider", URL_PROVIDER_DOMAIN2, payload_provider2, 80, results)),
        threading.Thread(target=worker, args=("domain3/provider", URL_PROVIDER_DOMAIN3, payload_provider3, 80, results)),
        threading.Thread(target=worker, args=("domain1/consumer", URL_CONSUMER_DOMAIN1, payload_consumer, 120, results)),
    ]

    start_ts = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.time() - start_ts

    # Summary
    print("\n=== RUN {} Summary (elapsed: {:.2f}s) ===".format(run_idx, elapsed))
    for name in ("domain2/provider", "domain3/provider", "domain1/consumer"):
        r = results.get(name, {"ok": False, "error": "no result"})
        if r.get("ok"):
            print("- {}: OK".format(name))
        else:
            print("- {}: ERROR → {}".format(name, r.get("error")))

def main():
    parser = argparse.ArgumentParser(description="Run multiple experimental runs for federation demo (concurrent per run).")
    parser.add_argument("--runs", type=int, default=1, help="Number of experiment runs (default: 1)")
    parser.add_argument("--export", type=str, default="false", choices=["true", "false"],
                        help="Whether to export CSVs (true/false). Default: false")
    parser.add_argument("--sleep", type=float, default=5.0, help="Seconds to sleep between runs (default: 5.0)")

    args = parser.parse_args()
    export_to_csv = (args.export.lower() == "true")

    for i in range(1, args.runs + 1):
        try:
            run_once(i, export_to_csv)
            if i < args.runs:
                time.sleep(args.sleep)
        except Exception as e:
            print("!! Run {} failed: {}".format(i, e))
            # continue to next run
            continue

    print("\nAll requested runs finished.")

if __name__ == "__main__":
    main()
