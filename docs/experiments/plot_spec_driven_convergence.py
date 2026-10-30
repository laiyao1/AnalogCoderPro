"""Regenerate the README figure from saved experiment means.

Run from the repository root:
    python docs/experiments/plot_spec_driven_convergence.py
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import ScalarFormatter


def main():
    root = Path(__file__).resolve().parents[2]
    data = json.loads(
        (root / "docs/experiments/spec_driven_convergence.json").read_text()
    )
    conditions = data["conditions"]
    colors = {"spec-driven": "#187f9a", "no-spec": "#d27835"}
    styles = {"spec-driven": "-", "no-spec": "--"}
    x = list(range(1, data["trials_per_seed"] + 1))
    plt.rcParams.update(
        {"font.size": 11, "axes.spines.top": False, "axes.spines.right": False}
    )
    fig, ax = plt.subplots(figsize=(8.8, 5.6))
    for label, condition in conditions.items():
        means = condition["mean_best_so_far"]
        ax.plot(
            x,
            means,
            color=colors[label],
            linestyle=styles[label],
            linewidth=2.2,
            label=label,
        )
        ax.scatter([x[-1]], [means[-1]], color=colors[label], s=32, zorder=4)
    window = data["plot_window"]
    ax.set(
        xlim=(window["first_trial"], 1090),
        ylim=(window["fom_min"], window["fom_max"]),
        xlabel="Trials per seed",
        ylabel="Mean best-so-far FoM (MHz·pF/mW)",
        title="Mean convergence: zoomed late-stage view",
    )
    ax.yaxis.set_major_formatter(ScalarFormatter(useOffset=False))
    ax.set_xticks([250, 400, 600, 800, 1000])
    ax.legend(frameon=False, loc="upper left")
    ax.grid(alpha=0.18)
    for label, offset in (("spec-driven", 9), ("no-spec", -14)):
        mean = conditions[label]["final_mean"]
        ax.annotate(
            f"{mean:.3f}",
            (1000, mean),
            xytext=(8, offset),
            textcoords="offset points",
            color=colors[label],
            fontsize=10,
            fontweight="bold",
        )
    gap = conditions["spec-driven"]["final_mean"] - conditions["no-spec"]["final_mean"]
    effect = data["statistics"]["mean_paired_relative_percent"]
    ax.text(
        0.035,
        0.10,
        f"Final mean gap: {gap:.3f} FoM\nPaired relative mean: {effect:+.4f}%",
        transform=ax.transAxes,
        fontsize=10,
        color="#40515f",
    )
    inset = ax.inset_axes([0.56, 0.12, 0.36, 0.30])
    for label, condition in conditions.items():
        inset.plot(
            x,
            condition["mean_best_so_far"],
            color=colors[label],
            linestyle=styles[label],
            linewidth=1.1,
        )
    inset.set(
        xlim=(0, 1000),
        ylim=(0, 2000),
        xticks=[0, 1000],
        yticks=[0, 1000, 2000],
        title="Full run: original scale",
    )
    inset.title.set_fontsize(8)
    inset.tick_params(labelsize=7)
    inset.grid(alpha=0.12)
    fig.suptitle(
        "GPT-5-mini · spec-driven vs no-spec · 10 sizing seeds",
        fontsize=13,
        fontweight="bold",
    )
    fig.text(
        0.5,
        0.055,
        "Main axes zoomed: trials 250–1000, FoM 1869.5–1877.0; inset shows the full scale.",
        ha="center",
        fontsize=9,
        color="#59636b",
    )
    fig.text(
        0.5,
        0.02,
        "Task 59 vs 63 · seeds 42–51 · 1000 trials per seed · 100 pF · one fixed LLM topology per condition",
        ha="center",
        fontsize=8.5,
        color="#59636b",
    )
    fig.tight_layout(rect=(0, 0.10, 1, 0.94))
    destination = root / "docs/figures/spec_driven_convergence.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(destination, dpi=220)
    plt.close(fig)
    print(f"Saved {destination.relative_to(root)}")


if __name__ == "__main__":
    main()
