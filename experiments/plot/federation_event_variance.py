#!/usr/bin/env python3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.patches import Rectangle
from matplotlib.lines import Line2D

# ---------- constants ----------
SUMMARY_CSV = "../data/_summary/event_times_summary.csv"
OUT_PNG = "federation_event_variance.png"
OUT_PDF = "federation_event_variance.pdf"
FONT_SCALE = 1.6
LINE_WIDTH = 1.5

# palettes
COLOR_PALETTE = ["#B3B3FF", "#FFB3B3", "#B3D9B3"]      # fills (light)
EDGE_COLOR_PALETTE = ["#0000FF", "#FF0000", "#008000"] # lines/edges (strong)

# Domain order (top -> bottom) must match DOMAIN_POS
DOMAIN_ORDER = ["provider_domain_2", "consumer_domain_1", "provider_domain_3"]

# Y positions (top -> bottom)
DOMAIN_POS = {"provider_domain_2": 2, "consumer_domain_1": 1, "provider_domain_3": 0}
DOMAIN_LABEL = {
    "consumer_domain_1": "Domain1\n(Consumer)",
    "provider_domain_2": "Domain2\n(Provider)",
    "provider_domain_3": "Domain3\n(Provider)",
}

# map palettes to domains
DOMAIN_FILL = dict(zip(DOMAIN_ORDER, COLOR_PALETTE))
DOMAIN_VLINE = dict(zip(DOMAIN_ORDER, EDGE_COLOR_PALETTE))

# Event code mapping (numbers printed under each bar)
STEP_CODE = {
    # consumer-side
    "service1_announced": 1, "service2_announced": 1,
    "service1_winner_chosen": 4, "service2_winner_chosen": 4,
    "service1_deploy_info_sent_to_provider": 5, "service2_deploy_info_sent_to_provider": 5,
    "service1_confirm_deploy_received": 8, "service2_confirm_deploy_received": 8,
    "e2e_service_running": 9,
    # provider-side
    "service1_announce_received": 2, "service2_announce_received": 2,
    "service1_bid_offer_sent": 3, "service2_bid_offer_sent": 3,
    "service1_winner_received": 6, "service2_winner_received": 6,
    "service1_confirm_deploy_sent": 7, "service2_confirm_deploy_sent": 7,
}

SKIP_STEPS = {"service2_deploy_info_sent_to_consumer", "service1_other_announce_received"}

LEGEND_LABELS = [
    "1. Service announced",
    "2. Announce received",
    "3. Bid offer sent",
    "4. Winner chosen",
    "5. Deploy info sent",
    "6. Winner received",
    "7. Service deployed",
    "8. Deploy confirmation received",
    "9. E2E service running",
]

# ---------- Load & prepare ----------
df = pd.read_csv(SUMMARY_CSV)

# keep only known domains and steps, map helper columns
df = df[df["domain"].isin(DOMAIN_POS.keys())].copy()
df = df[~df["event"].isin(SKIP_STEPS)].copy()
df["ypos"] = df["domain"].map(DOMAIN_POS)
df["domain_label"] = df["domain"].map(DOMAIN_LABEL)
df["code"] = df["event"].map(STEP_CODE)

# drop rows without a code or without a mean x position
df = df[df["code"].notna()].copy()
df = df[pd.to_numeric(df["mean_t_rel_s"], errors="coerce").notna()].copy()

# ---------- Style ----------
sns.set_theme(context="paper", style="ticks", font_scale=FONT_SCALE)
fig, ax = plt.subplots(figsize=(11.5, 4.8))

# Grid & spines
ax.set_axisbelow(True)
ax.xaxis.grid(True, which="major", linestyle="--", linewidth=LINE_WIDTH, alpha=0.5, color="grey")
ax.yaxis.grid(False)
for side in ("top", "right", "bottom", "left"):
    ax.spines[side].set_color("black")
    ax.spines[side].set_linewidth(LINE_WIDTH)

# Drawing parameters
bar_half_height = 0.3
num_offset_y = 0.12    # fixed vertical distance below the bar
rect_half_height = 0.22
rect_alpha = 0.6

# ---------- Draw variance rectangles and vertical bars ----------
for _, row in df.iterrows():
    x = float(row["mean_t_rel_s"])
    s = float(row["std_t_rel_s"]) if pd.notna(row["std_t_rel_s"]) else 0.0
    y = float(row["ypos"])
    dom = row["domain"]

    color_fill = DOMAIN_FILL.get(dom, "#e0e0e0")
    line_color = DOMAIN_VLINE.get(dom, "black")

    if s > 0:
        rect = Rectangle(
            (x - s, y - rect_half_height),
            width=2*s, height=2*rect_half_height,
            facecolor=color_fill, edgecolor="none", alpha=rect_alpha,
        )
        ax.add_patch(rect)

    ax.vlines(
        x=x, ymin=y - bar_half_height, ymax=y + bar_half_height,
        colors=line_color, linewidth=LINE_WIDTH
    )

# ---------- Pixel-aware horizontal de-overlap for numbers ----------
MIN_SEP_PX = 20  # tweak to taste

# Make sure we have a renderer and accurate axis size
fig.canvas.draw()
x0, x1 = ax.get_xlim()
ax_width_px = ax.get_window_extent().width
data_per_px = (x1 - x0) / ax_width_px if ax_width_px > 0 else 0.0
delta_data = MIN_SEP_PX * data_per_px

# Compute jittered x positions per domain
label_positions = {}
for dom, g in df.groupby("domain"):
    g = g.sort_values("mean_t_rel_s")
    xs = g["mean_t_rel_s"].astype(float).tolist()
    xs_j = xs[:]
    for i in range(1, len(xs_j)):
        if xs_j[i] - xs_j[i-1] < delta_data:
            xs_j[i] = xs_j[i-1] + delta_data
    # Clamp to current x-limits
    for i in range(len(xs_j)):
        xs_j[i] = max(min(xs_j[i], x1), x0)
    label_positions.update({idx: xj for idx, xj in zip(g.index, xs_j)})

# Now draw numbers with jittered x
for idx, row in df.iterrows():
    x_num = label_positions[idx]
    y = float(row["ypos"])
    ax.text(
        x_num, y - bar_half_height - num_offset_y, f"{int(row['code'])}",
        ha="center", va="center", fontsize=12, color="black"
    )

# ---------- axes labels ----------
ax.set_yticks([
    DOMAIN_POS["provider_domain_2"],
    DOMAIN_POS["consumer_domain_1"],
    DOMAIN_POS["provider_domain_3"],
])
ax.set_yticklabels([
    DOMAIN_LABEL["provider_domain_2"],
    DOMAIN_LABEL["consumer_domain_1"],
    DOMAIN_LABEL["provider_domain_3"],
])

ax.set_xlabel("Time (s)")
ax.set_title("Federation event variances")

# ---------- legends ----------
# Domain legend (uses line colors)
# domain_handles = [Line2D([0], [0], color=DOMAIN_VLINE.get(d, "black"), linewidth=3) for d in DOMAIN_ORDER]
# domain_labels = [DOMAIN_LABEL[d] for d in DOMAIN_ORDER]
# leg_domain = ax.legend(
#     domain_handles, domain_labels,
#     title="Domains",
#     loc="upper left", bbox_to_anchor=(1.02, 1.0),
#     frameon=True, borderaxespad=0.0
# )
# frame_d = leg_domain.get_frame()
# frame_d.set_edgecolor("black")
# frame_d.set_linewidth(LINE_WIDTH)
# ax.add_artist(leg_domain)  # ensure we can add a second legend

# Step legend (text-only, as before)
legend_handles = [Line2D([], [], linestyle="none", marker=None, color="none")
                  for _ in LEGEND_LABELS]
leg_steps = ax.legend(
    legend_handles, LEGEND_LABELS,
    loc="center left", bbox_to_anchor=(1.02, 0.5),
    frameon=True, handlelength=0, handletextpad=0.4,
)
frame_s = leg_steps.get_frame()
frame_s.set_edgecolor("black")
frame_s.set_linewidth(LINE_WIDTH)

# ---------- finalize & save ----------
ax.margins(y=0.15)
plt.tight_layout()
plt.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
plt.savefig(OUT_PDF, bbox_inches="tight")
plt.show()
plt.close()

print(f"✅ Saved: {OUT_PNG}, {OUT_PDF}")
