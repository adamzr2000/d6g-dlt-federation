#!/usr/bin/env python3
import os
import pandas as pd
import numpy as np

BASE_DIR = "."
SUMMARY_DIR = os.path.join(BASE_DIR, "_summary")
os.makedirs(SUMMARY_DIR, exist_ok=True)

# Main federation window per domain
STEP_RANGES = {
    "consumer_domain_1": ("service1_announced", "e2e_service_running"), # "e2e_service_running"
    "provider_domain_2": ("service1_announce_received", "service1_confirm_deploy_sent"),
    "provider_domain_3": ("service2_announce_received", "service2_confirm_deploy_sent"),
}

# Off-chain window per domain (as requested)
OFFCHAIN_STEP_RANGES = {
    "consumer_domain_1": ("establish_connection_with_provider_start", "e2e_service_running"), # "e2e_service_running"
    "provider_domain_2": ("service1_deploy_start", "service1_deploy_finished"),
    "provider_domain_3": ("service2_deploy_start", "service2_deploy_finished"),
}

def get_duration(csv_path, start_step, end_step):
    df = pd.read_csv(csv_path)
    try:
        t_start = float(df.loc[df["step"] == start_step, "t_rel"].values[0])
        t_end   = float(df.loc[df["step"] == end_step, "t_rel"].values[0])
        return t_end - t_start
    except IndexError:
        print(f"⚠️ Missing steps ({start_step}→{end_step}) in {csv_path}")
        return np.nan

summary_rows = []

for domain, (start_step, end_step) in STEP_RANGES.items():
    pattern = f"{domain}_run_"
    durations = []
    offchain_durations = []

    off_start, off_end = OFFCHAIN_STEP_RANGES[domain]

    for fname in os.listdir(BASE_DIR):
        if fname.startswith(pattern) and fname.endswith(".csv"):
            path = os.path.join(BASE_DIR, fname)
            d = get_duration(path, start_step, end_step)
            if not np.isnan(d):
                durations.append(d)

            d_off = get_duration(path, off_start, off_end)
            if not np.isnan(d_off):
                offchain_durations.append(d_off)

    # Aggregate (mean/std across runs found for each metric)
    row = {
        "domain": domain,
        "runs": len(durations),  # runs counted for the main window
        "mean_duration_s": round(float(np.mean(durations)), 3) if durations else np.nan,
        "std_duration_s": round(float(np.std(durations)), 3) if durations else np.nan,
        "mean_offchain_duration_s": round(float(np.mean(offchain_durations)), 3) if offchain_durations else np.nan,
        "std_offchain_duration_s": round(float(np.std(offchain_durations)), 3) if offchain_durations else np.nan,
    }
    summary_rows.append(row)

summary_df = pd.DataFrame(summary_rows)
out_path = os.path.join(SUMMARY_DIR, "federation_durations.csv")
summary_df.to_csv(out_path, index=False)

print(f"\n✅ Summary saved to {out_path}\n")
print(summary_df)
