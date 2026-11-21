"""Inspect the two local custody paths without listing received files."""
from pathlib import Path
import json
import os
import plistlib
import re
import stat
import subprocess

here=Path(__file__).resolve().parent
root=here/'local-custody'
record=json.loads((root/'custody-readback.private.json').read_bytes())
downloads=Path.home()/'Downloads'
capture=Path(record['capture_staging'])
data=Path('/System/Volumes/Data')
def run(*args): return subprocess.check_output(args,timeout=20)

def verify_folder(p):
    s=p.lstat()
    assert stat.S_ISDIR(s.st_mode) and not p.is_symlink() and p.resolve()==p
    assert s.st_uid==os.getuid() and stat.S_IMODE(s.st_mode)==0o700
    acl=run('/bin/ls','-lde',str(p)).decode().splitlines()[1:]
    assert all(re.fullmatch(r'\s*\d+: group:everyone deny delete\s*',line) for line in acl if line.strip())
    return dict(owned=True,mode='0700',no_allow_acl=True)

download_info=verify_folder(downloads)
capture_info=verify_folder(capture)
assert downloads.stat().st_dev==data.stat().st_dev
info=plistlib.loads(run('/usr/sbin/diskutil','info','-plist',str(data)))
assert info['FilesystemType']=='apfs' and info['FileVault'] and info['EncryptionThisVolumeProper']
assert os.path.ismount(capture.parent) and not os.path.ismount(root/'identity-mount')
images=plistlib.loads(run('/usr/bin/hdiutil','info','-plist'))['images']
check,=[entry for entry in images if entry.get('image-path')==record['capture_image']]
assert check['image-encrypted']
shares=run('/usr/sbin/sharing','-l').decode()
for line in shares.splitlines():
    if 'path:' not in line: continue
    share=Path(line.split('path:',1)[1].strip()).expanduser()
    assert share not in (downloads,*downloads.parents) and share not in (capture,*capture.parents)
assert not any(capture.iterdir())
result=dict(downloads=download_info,downloads_filevault_apfs=True,capture=capture_info,
            mounted_capture_aes256_image=True,identity_detached=True,no_configured_matching_share=True,
            capture_staging_empty=True,real_transfer_performed=False)
os.umask(0o077)
with (root/'airdrop_local_path_preflight.private.json').open('x') as f:
    json.dump(result,f,indent=2)
print(json.dumps(result))
