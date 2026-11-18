| N | K | Z | Edges | LUTs | Logic | LUTRAM | FFs | BRAM tiles | DSPs | LUT/N | Logic/N |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1024 | 512 | 64 | 3456 | 632 | 424 | 208 | 151 | 1.5 | 0 | 0.617 | 0.414 |
| 2048 | 1024 | 64 | 7488 | 950 | 534 | 416 | 156 | 2.0 | 0 | 0.464 | 0.261 |
| 4096 | 2048 | 128 | 15744 | 1440 | 608 | 832 | 160 | 3.5 | 0 | 0.352 | 0.148 |

All configurations use the same parameterized RTL, 5-bit arithmetic, memory policy, FPGA part and OOC synthesis mode.
No clock constraint is applied, matching the existing production resource-comparison boundary.
Matrices are the existing paper configurations; this is not a fixed-protograph Z-only experiment.
These results are synthesis resources, not post-route resources or achieved operating frequency.
