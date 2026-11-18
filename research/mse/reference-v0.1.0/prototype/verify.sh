#!/usr/bin/env bash
# No strict-mode flags or terminal-exit commands.
mse_script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python3 -B "$mse_script_dir/tools/lifecycle.py" verify
