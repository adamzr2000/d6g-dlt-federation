#!/usr/bin/env python3
import os
import glob
import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Tuple

BASE_DIR = "."
PRECISION = 6   # was 3
SUMMARY_DIR = os.path.join(BASE_DIR, "_summary")
os.makedirs(SUMMARY_DIR, exist_ok=True)

# Events to summarize (order matters for plotting)
EVENTS_BY_DOMAIN: Dict[str, List[str]] = {
    "consumer_domain_1": [
        "service1_announced",
        "service1_bid_offer_received",
        "service1_winner_chosen",
        "service1_deploy_info_sent_to_provider",
        "service1_confirm_deploy_received",
        "service2_announced",
        "service2_bid_offer_received",
        "service2_winner_chosen",
        "service2_deploy_info_sent_to_provider",
        "service2_confirm_deploy_received",
        "e2e_service_running",
    ],
    "provider_domain_2": [
        "service1_announce_received",
        "service1_bid_offer_sent",
        "service1_winner_received",
        "service1_deploy_start",
        "service1_deploy_finished",
        "service1_confirm_deploy_sent",
    ],
    "provider_domain_3": [
        "service1_announce_received",  # alias supported below
        "service2_announce_received",
        "service2_bid_offer_sent",
        "service2_winner_received",
        "service2_deploy_start",
        "service2_deploy_finished",
        "service2_deploy_info_sent_to_consumer",
        "service2_confirm_deploy_sent",
    ],
}

# Optional aliases to make legacy labels count toward the requested ones
EVENT_ALIASES: Dict[Tuple[str, str], List[str]] = {
    # For provider_domain_3 some files use "service1_other_announce_received"
    ("provider_domain_3", "service1_announce_received"): [
        "service1_announce_received",
        "service1_other_announce_received",
    ],
}

def load_event_time(csv_path: str, wanted_step: str, domain: str) -> Optional[float]:
    """Return t_rel for the wanted step (supports aliasing)."""
    df = pd.read_csv(csv_path)
    candidates = EVENT_ALIASES.get((domain, wanted_step), [wanted_step])
    for name in candidates:
        matches = df.loc[df["step"] == name, "t_rel"]
        if not matches.empty:
            try:
                return float(matches.iloc[0])
            except (TypeError, ValueError):
                pass
    return None

def collect_domain_event_stats(domain: str, events: List[str]) -> List[Dict[str, object]]:
    pattern = os.path.join(BASE_DIR, f"{domain}_run_*.csv")
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"⚠️ No files found for domain '{domain}' with pattern {pattern}")

    times_by_event: Dict[str, List[float]] = {e: [] for e in events}

    for f in files:
        for e in events:
            t = load_event_time(f, e, domain)
            if t is not None:
                times_by_event[e].append(t)
            else:
                print(f"⚠️ Missing event '{e}' in {os.path.basename(f)}")

    rows: List[Dict[str, object]] = []
    for e in events:
        arr = times_by_event[e]
        if arr:
            mean = float(np.mean(arr))
            std = float(np.std(arr))
            runs = len(arr)
            rows.append({
                "domain": domain,
                "event": e,
                "runs": runs,
                "mean_t_rel_s": round(mean, PRECISION),
                "std_t_rel_s": round(std, PRECISION),
            })
        else:
            rows.append({
                "domain": domain,
                "event": e,
                "runs": 0,
                "mean_t_rel_s": np.nan,
                "std_t_rel_s": np.nan,
            })
    return rows

def main() -> None:
    all_rows: List[Dict[str, object]] = []
    for domain, events in EVENTS_BY_DOMAIN.items():
        all_rows.extend(collect_domain_event_stats(domain, events))

    out_csv = os.path.join(SUMMARY_DIR, "event_times_summary.csv")
    pd.DataFrame(all_rows).to_csv(out_csv, index=False)
    print(f"\n✅ Event-time summary saved to {out_csv}\n")

    # Optional per-domain CSVs
    for domain in EVENTS_BY_DOMAIN:
        df = pd.DataFrame([r for r in all_rows if r["domain"] == domain])
        df.to_csv(os.path.join(SUMMARY_DIR, f"event_times_{domain}.csv"), index=False)

if __name__ == "__main__":
    main()
