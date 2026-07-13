#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/software/core"
export OMP_NUM_THREADS=1
make compile_staircase_short
./test_staircase_short.exe 2.0 12345 5 1000 0.005

echo "Quick verification complete. This run is not the paper-scale Monte Carlo experiment."
