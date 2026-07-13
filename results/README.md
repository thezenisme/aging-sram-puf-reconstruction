# Frozen Reference Output

`main_rate12_long.csv` is the compact output retained from the paper-scale
rate-1/2, N=4096 Monte Carlo sweep. It is provided so that readers can inspect
and plot the reported trend without repeating the multi-day simulation.

Generate a figure from the frozen CSV with:

```bash
python results/plot_precomputed.py
```

The CSV records aggregate FER and iteration statistics, not per-frame traces.
Values printed as `0.000000` are output-resolution entries from runs governed
by the stopping rule described in the manuscript; they are not analytic proof
of zero failure probability.
