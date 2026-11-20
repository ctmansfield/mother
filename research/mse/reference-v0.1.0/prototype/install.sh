#!/usr/bin/env bash
# Invoke with bash, do not source. The final command's status is returned naturally.
mse_script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python3 -B "$mse_script_dir/tools/lifecycle.py" install "$@"
