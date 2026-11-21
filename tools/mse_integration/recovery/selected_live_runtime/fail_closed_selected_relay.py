"""Close only the selected pilot relay after loss of clock qualification."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT=Path('/run/phoenix-mse-pilot-clock')
RELAY=Path('/var/lib/libvirt/images/phoenix-mse-evidence-20261121/selected-live-relay')
NAME='phoenix-mse-selected-live-relay.service'
p=json.loads((ROOT/'clock-plan.json').read_bytes())
assert hashlib.sha256(Path('/etc/machine-id').read_bytes()).hexdigest()==p['host_pin']
assert Path('/proc/sys/kernel/random/boot_id').read_text().strip()==p['host_boot']
assert Path('/run/systemd/system',NAME).resolve(strict=True)==RELAY/NAME
assert hashlib.sha256((RELAY/NAME).read_bytes()).hexdigest()==p['relay_unit_sha256']
subprocess.run(['systemctl','stop',NAME],check=True,timeout=18)
assert not subprocess.check_output(['ss','-Hltn','sport = :8446']).strip()
assert 'table inet phoenix_mse_selected_live_relay' not in subprocess.check_output(
    ['nft','list','tables'],text=True).splitlines()
print('Closed the exact selected relay after a clock qualification failure.')
