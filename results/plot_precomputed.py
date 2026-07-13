from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


root = Path(__file__).resolve().parent
data = np.genfromtxt(root / "main_rate12_long.csv", delimiter=",", names=True)

fig, ax = plt.subplots(figsize=(5.2, 3.5))
for column, label, marker in (
    ("Baseline_FER", "Continuous LLR", "o"),
    ("Staircase_FER", "Proposed", "s"),
):
    values = np.maximum(data[column], 1e-7)
    ax.semilogy(100 * data["Actual_BER"], values, marker=marker,
                markersize=3, linewidth=1.2, label=label)

ax.set_xlabel("Actual raw BER (%)")
ax.set_ylabel("Frame error rate")
ax.grid(True, which="both", linewidth=0.4, alpha=0.5)
ax.legend(frameon=False)
fig.tight_layout()
fig.savefig(root / "main_rate12_long.pdf", bbox_inches="tight")
fig.savefig(root / "main_rate12_long.png", dpi=200, bbox_inches="tight")
