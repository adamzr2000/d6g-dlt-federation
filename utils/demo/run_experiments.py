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
from typing import Any, Dict, Tuple
import requests
from pathlib import Path

# --- Default endpoints (change if needed) ---
URL_CONSUMER_DOMAIN1 = "http://10.5.15.55:8090/start_demo_consumer"
URL_PROVIDER_DOMAIN2 = "http://10.5.99.6:8090/start_demo_provider"
URL_PROVIDER_DOMAIN3 = "http://10.5.99.5:8090/start_demo_provider"

# --- NEW: cleanup endpoints ---
K8S_ORCH_D3    = "http://10.5.99.12:6665"      # domain3 edge: k8s orchestrator
VXLAN_D3       = "http://10.5.99.12:6666"      # domain3 edge: vxlan service
VXLAN_D1_EDGE  = "http://10.5.1.21:6666"       # domain1 edge: vxlan service
VXLAN_D1_ROBOT = "http://10.3.202.66:6666"     # domain1 robot: vxlan service
D3_EDGE_VTEP   = "10.11.7.6"                    # domain3 edge VTEP IP to remove as peer

HEADERS = {"Content-Type": "application/json"}

print_lock = threading.Lock()  # keep logs tidy across threads

def load_service_cids() -> Tuple[str, str]:
    here = Path(__file__).resolve().parent
    cid_path = here / "ipfs-deploy-info" / "deployed_cids.json"
    if not cid_path.exists():
        raise FileNotFoundError(f"CID file not found: {cid_path}")

    with cid_path.open("r", encoding="utf-8") as f:
        mapping = json.load(f)

    s1 = mapping.get("domain1-deploy-info-service1.json")
    s2 = mapping.get("domain1-deploy-info-service2.yml")

    missing = []
    if not s1:
        missing.append("domain1-deploy-info-service1.json")
    if not s2:
        missing.append("domain1-deploy-info-service2.yml")

    if missing:
        raise KeyError(
            "Missing CID(s) for: {} in {}".format(", ".join(missing), cid_path)
        )

    with print_lock:
        print(f"[cids] Using service1 CID: {s1}")
        print(f"[cids] Using service2 CID: {s2}")

    return s1, s2


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

    # Load CIDs for service1 and service2
    service1_cid, service2_cid = load_service_cids()

    # Build per-run payloads (same as your baseline, just threaded)
    provider2_csv = "/experiments/data/provider_domain_2_run_{}.csv".format(run_idx)
    provider3_csv = "/experiments/data/provider_domain_3_run_{}.csv".format(run_idx)
    consumer_csv  = "/experiments/data/consumer_domain_1_run_{}.csv".format(run_idx)

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
        "service1_availability": 9999,
        "service1_max_latency_ms": 50,
        "service1_max_jitter_ms": 10,
        "service1_min_bandwidth_Mbps": 20,
        "service1_deployment_manifest_cid": service1_cid,
        "service2_description": "ros_app_k8s_deployment",
        "service2_compute_cpu_mcores": 2000,
        "service2_compute_ram_MB": 4000,
        "service2_deployment_manifest_cid": service2_cid,
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

def _ok(msg: str) -> None:
    with print_lock:
        print("[cleanup] ✓ " + msg)

def _err(msg: str, e: Exception) -> None:
    with print_lock:
        print("[cleanup] ✗ {}: {}".format(msg, e))

def _post_no_body(url: str, timeout: int = 30) -> Dict[str, Any]:
    r = requests.post(url, timeout=timeout)
    r.raise_for_status()
    if r.headers.get("content-type", "").startswith("application/json"):
        return r.json()
    return {"raw": r.text}

def _delete_json(url: str, payload: Dict[str, Any] = None, timeout: int = 30) -> Dict[str, Any]:
    r = requests.delete(url, json=(payload or {}), timeout=timeout)
    r.raise_for_status()
    if r.headers.get("content-type", "").startswith("application/json"):
        return r.json()
    return {"raw": r.text}

def cleanup_after_run() -> None:
    """Best-effort cleanup after each run (matches your cURL sequence)."""
    # 1) Domain3 edge: delete all k8s deployments (wait) and remove vxlan200
    try:
        _post_no_body("{}/deployments/delete_all?wait=true".format(K8S_ORCH_D3))
        _ok("domain3: k8s deployments deleted")
    except Exception as e:
        _err("domain3: k8s delete_all failed", e)

    try:
        _delete_json("{}/vxlan/vxlan200".format(VXLAN_D3))
        _ok("domain3: vxlan200 removed")
    except Exception as e:
        _err("domain3: vxlan200 delete failed", e)

    # 2) Remove domain3 edge as peer from domain1 edge + robot
    # peers_payload = {"peers": [D3_EDGE_VTEP]}
    # try:
    #     _delete_json("{}/vxlan/vxlan200/peers".format(VXLAN_D1_EDGE), payload=peers_payload)
    #     _ok("domain1 edge: removed peer {}".format(D3_EDGE_VTEP))
    # except Exception as e:
    #     _err("domain1 edge: remove peer failed", e)

    # try:
    #     _delete_json("{}/vxlan/vxlan200/peers".format(VXLAN_D1_ROBOT), payload=peers_payload)
    #     _ok("domain1 robot: removed peer {}".format(D3_EDGE_VTEP))
    # except Exception as e:
    #     _err("domain1 robot: remove peer failed", e)

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
        except Exception as e:
            print("!! Run {} failed: {}".format(i, e))
        finally:
            time.sleep(10)
            cleanup_after_run()

        if i < args.runs:
            time.sleep(args.sleep)

    print("\nAll requested runs finished.")

if __name__ == "__main__":
    main()
