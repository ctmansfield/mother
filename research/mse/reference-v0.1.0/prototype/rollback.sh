#!/usr/bin/env bash
# Rollback retires an unchanged isolated installation by renaming it; nothing is deleted.
mse_script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python3 -B "$mse_script_dir/tools/lifecycle.py" retire "$@"
