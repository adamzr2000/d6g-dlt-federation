#!/usr/bin/env python3
# run_experiments.py
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
from typing import Any, Dict
import requests

# --- Default endpoints (change if needed) ---
URL_CONSUMER_DOMAIN1 = "http://10.5.15.55:8090/start_demo_consumer"
URL_PROVIDER_DOMAIN2 = "http://10.5.99.6:8090/start_demo_provider"
URL_PROVIDER_DOMAIN3 = "http://10.5.99.5:8090/start_demo_provider"

HEADERS = {"Content-Type": "application/json"}

def post_json(url: str, payload: Dict[str, Any], timeout: int = 80) -> Dict[str, Any]:
    """POST JSON and return parsed JSON (or raise)."""
    resp = requests.post(url, headers=HEADERS, data=json.dumps(payload), timeout=timeout)
    # Raise for HTTP status != 200
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        # Include server's body if available for easier debugging
        raise RuntimeError("HTTP {} from {}: {}".format(resp.status_code, url, resp.text)) from e
    try:
        return resp.json()
    except ValueError:
        # Fallback: return raw text
        return {"raw": resp.text}

def run_once(run_idx: int, export_to_csv: bool) -> None:
    print("\n=== RUN {} ===".format(run_idx))

    # --- 1) Provider domain2 (detnet_transport) ---
    provider2_csv = "/exeriments/data/provider_domain_2_run_{}.csv".format(run_idx)
    provider2_payload = {
        "description_filter": "detnet_transport",
        "price_wei_per_hour": 10000,
        "location": "5TONIC @ Madrid, Spain",
        "export_to_csv": export_to_csv,
        "csv_path": provider2_csv,
    }
    print("[1/3] domain2 → start_demo_provider  payload:", json.dumps(provider2_payload))
    r1 = post_json(URL_PROVIDER_DOMAIN2, provider2_payload)
    print("[1/3] response:", json.dumps(r1, indent=2))

    # --- 2) Provider domain3 (ros_app_k8s_deployment) ---
    provider3_csv = "/exeriments/data/provider_domain_3_run_{}.csv".format(run_idx)
    provider3_payload = {
        "description_filter": "ros_app_k8s_deployment",
        "price_wei_per_hour": 10000,
        "location": "5TONIC @ Madrid, Spain",
        "export_to_csv": export_to_csv,
        "csv_path": provider3_csv,
    }
    print("[2/3] domain3 → start_demo_provider  payload:", json.dumps(provider3_payload))
    r2 = post_json(URL_PROVIDER_DOMAIN3, provider3_payload)
    print("[2/3] response:", json.dumps(r2, indent=2))

    # --- 3) Consumer domain1 (announces both services) ---
    consumer_csv = "/exeriments/data/consumer_domain_1_run_{}.csv".format(run_idx)
    consumer_payload = {
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
        # If your API expects offers_to_wait or other fields, add them here.
        # "offers_to_wait": 1,
    }
    print("[3/3] domain1 → start_demo_consumer  payload:", json.dumps(consumer_payload))
    r3 = post_json(URL_CONSUMER_DOMAIN1, consumer_payload, timeout=120)
    print("[3/3] response:", json.dumps(r3, indent=2))

def main():
    parser = argparse.ArgumentParser(description="Run multiple experimental runs for federation demo.")
    parser.add_argument("--runs", type=int, default=1, help="Number of experiment runs (default: 1)")
    parser.add_argument("--export", type=str, default="false", choices=["true", "false"],
                        help="Whether to export CSVs (true/false). Default: false")
    parser.add_argument("--sleep", type=float, default=5.0, help="Seconds to sleep between runs (default: 1.0)")

    args = parser.parse_args()

    export_to_csv = (args.export.lower() == "true")

    for i in range(1, args.runs + 1):
        try:
            run_once(i, export_to_csv)
            time.sleep(args.sleep)
        except Exception as e:
            print("!! Run {} failed: {}".format(i, e))
            # continue to next run (or break if you want to stop on first failure)
            continue

    print("\nAll requested runs finished.")

if __name__ == "__main__":
    main()
