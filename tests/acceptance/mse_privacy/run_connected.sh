#!/bin/sh
# Run from an exact combined checkout using local Python with jsonschema.
set -eu
root=$(git rev-parse --show-toplevel)
cd "$root"
python=${PYTHON:-python3}
scratch=$(mktemp -d "$root/.privacy-test.XXXXXX")
trap 'rmdir "$scratch"' EXIT
export TMPDIR="$scratch"
export PYTHONPATH="$root:$root/research/mse/reference-v0.1.0/prototype"
"$python" -B -m unittest discover -s tests/acceptance/mse_privacy -v
"$python" -I -B tools/mse_integration/recovery/privacy_stores.py --object-store "$root" --connected
