#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--confirm" ]]; then
    echo "This launches the N=4096 paper-scale sweep with up to 10^7 frames per noise point."
    echo "It may require several days. Re-run as: ./run_full.sh --confirm"
    exit 2
fi

cd "$(dirname "$0")/software/core"
make compile_staircase_long
./test_staircase_long.exe 2.0 12345 50 10000000 0.055
