#!/bin/sh
set -eu
layout_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
exec "${LAYOUT_PYTHON:-python3}" "$layout_dir/run.py" "$@"
