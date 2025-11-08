#!/usr/bin/env python3
import warnings
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator

SUMMARY_CSV = "../data/_summary/federation_durations.csv"
OUT_PNG = "federation_total_latency_per_domain.png"
OUT_PDF = "federation_total_latency_per_domain.pdf"
FONT_SCALE = 1.6
LINE_WIDTH = 1.8

LABELS = {
    "consumer_domain_1": f"Domain1\n(Consumer)",
    "provider_domain_2": f"Domain2\n(Provider)",
    "provider_domain_3": f"Domain3\n(Provider)",
}

ORDER = ["consumer_domain_1", "provider_domain_2", "provider_domain_3"]

# Federation procedure using blockchain, Deployment procedure (off-chain)
COLOR_PALETTE = ["#B3B3FF", "#FFB3B3", "#B3D9B3"] 
EDGE_COLOR_PALETTE = ["#0000FF", "#FF0000", "#008000"]



# --- Load & prepare ---
df = pd.read_csv(SUMMARY_CSV)
df = df[df["domain"].isin(ORDER)].copy()
df["domain"] = pd.Categorical(df["domain"], categories=ORDER, ordered=True)
df["domain_label"] = df["domain"].map(LABELS)

has_offchain = {"mean_offchain_duration_s", "std_offchain_duration_s"}.issubset(df.columns)
if has_offchain:
    too_big = df["mean_offchain_duration_s"] > df["mean_duration_s"]
    if too_big.any():
        rows = ", ".join(df.loc[too_big, "domain"].astype(str).tolist())
        warnings.warn(f"Off-chain mean > total mean for: {rows}. Clamping to total.")
    df["deployment_proc_mean"] = df["mean_offchain_duration_s"].clip(lower=0, upper=df["mean_duration_s"])
    df["federation_bc_mean"] = (df["mean_duration_s"] - df["deployment_proc_mean"]).clip(lower=0)
else:
    df["deployment_proc_mean"] = 0.0
    df["federation_bc_mean"] = df["mean_duration_s"]

# Keep requested order (Domain1 → Domain2 → Domain3)
d = df.sort_values("domain")

# --- Style ---
sns.set_theme(context="paper", style="ticks", font_scale=FONT_SCALE)

fig, ax = plt.subplots(figsize=(10, 5.2))

# Stacked bars

bars_bc = ax.barh(
    y=d["domain_label"],
    width=d["federation_bc_mean"],
    label="Federation procedure (blockchain)",
    edgecolor=EDGE_COLOR_PALETTE[0],
    linewidth=LINE_WIDTH,
    color=COLOR_PALETTE[0],
    zorder=2,
)

bars_dep = ax.barh(
    y=d["domain_label"],
    width=d["deployment_proc_mean"],
    left=d["federation_bc_mean"],
    label="Deployment procedure (off-chain)",
    edgecolor=EDGE_COLOR_PALETTE[1],
    linewidth=LINE_WIDTH,
    color=COLOR_PALETTE[1],
    zorder=1
)


# Std-dev error bars at total end — dark color
if "std_duration_s" in d.columns:
    for (_, row), bar in zip(d.iterrows(), bars_dep):  # bars_dep ends at total width
        y = bar.get_y() + bar.get_height() / 2
        x_total = float(row["federation_bc_mean"] + row["deployment_proc_mean"])
        err = row.get("std_duration_s")
        if pd.notna(err):
            ax.errorbar(x=x_total, y=y, xerr=err, fmt="none", capsize=6, linewidth=LINE_WIDTH*1.5,
                        ecolor="black", color="black")

# Axes labels/title
ax.set_title("Federation summarized times")
ax.set_xlabel("Time (s)")
# ax.set_ylabel("Domain")

# --- Better grid (clean + behind bars) ---
ax.set_axisbelow(True)  # grid behind bars
ax.xaxis.grid(True, which="major", linestyle="--", linewidth=LINE_WIDTH, alpha=0.5, color="grey")
ax.yaxis.grid(False)

# --- Spines: dark + slightly thicker ---
for side in ("top", "right", "bottom", "left"):
    ax.spines[side].set_color("black")
    ax.spines[side].set_linewidth(LINE_WIDTH)

# Legend inside, top-right
leg = ax.legend(loc="upper right", frameon=True)
frame = leg.get_frame()
frame.set_edgecolor("black")
frame.set_linewidth(LINE_WIDTH)

# Margins & export
ax.margins(x=0.06)
plt.tight_layout()
plt.savefig(OUT_PNG, dpi=300)
plt.savefig(OUT_PDF)
plt.show()
plt.close()

print(f"✅ Saved: {OUT_PNG}, {OUT_PDF}")
