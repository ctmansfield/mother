"""Cold-reopen the prepared encrypted custody images with generated synthetic data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile
from prepare_local_history_custody import attach, detach, get_password, run


def fails(*args):
    attempt=subprocess.run(args,capture_output=True,timeout=30)
    return attempt.returncode != 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('bin_dir',type=Path)
    args=parser.parse_args()
    root=args.root.resolve(strict=True)
    details=json.loads((root/'custody-readback.private.json').read_bytes())
    capture=root/'capture-mount'
    identity_mount=root/'identity-mount'
    identity=identity_mount/'protected'/'health-history-recipient.agekey'
    assert os.path.ismount(capture) and not os.path.ismount(identity_mount)
    assert not identity.exists()
    recipient=Path(details['recipient_public_path'])
    assert hashlib.sha256(recipient.read_bytes()).hexdigest()==details['recipient_public_sha256']
    os.umask(0o077)
    check=capture/'synthetic-proof'
    check.mkdir(mode=0o700)
    original=check/'generated-not-health.zip'
    with zipfile.ZipFile(original,'x') as archive:
        archive.writestr('export.xml',b'<synthetic fixture="true"/>')
        archive.writestr('attachments/generated.txt',b'generated attachment')
    exact=hashlib.sha256(original.read_bytes()).hexdigest()
    cipher=check/'generated-not-health.zip.age'
    age=str((args.bin_dir/'age').resolve())
    keygen=str((args.bin_dir/'age-keygen').resolve())
    run(age,'--encrypt','--recipients-file',str(recipient),'-o',str(cipher),str(original))
    ciphertext_digest=hashlib.sha256(cipher.read_bytes()).hexdigest()
    detach(capture)
    assert not original.exists() and not cipher.exists()
    attach(Path(details['capture_image']),capture,get_password(details['keychain_service_labels'][0].encode()))
    assert hashlib.sha256(cipher.read_bytes()).hexdigest()==ciphertext_digest
    attach(Path(details['key_image']),identity_mount,get_password(details['keychain_service_labels'][1].encode()))
    try:
        assert identity.stat().st_mode&0o777==0o600
        assert run(keygen,'-y',str(identity))==recipient.read_bytes()
        assert hashlib.sha256(run(age,'--decrypt','--identity',str(identity),str(cipher))).hexdigest()==exact
        with tempfile.TemporaryDirectory(prefix='synthetic-wrong-key-',dir=root) as temp:
            wrong=Path(temp)/'wrong.agekey'
            run(keygen,'-pq','-o',str(wrong))
            assert fails(age,'--decrypt','--identity',str(wrong),str(cipher))
        altered=bytearray(cipher.read_bytes())
        altered[-1]^=1
        tampered=check/'generated-tampered.age'
        with tampered.open('xb') as f:f.write(altered)
        assert fails(age,'--decrypt','--identity',str(identity),str(tampered))
    finally:
        detach(identity_mount)
    assert not identity.exists() and not any(Path(details['capture_staging']).iterdir())
    print(json.dumps(dict(capture_and_identity_cold_reopened=True,exact_original_verified=True,
        wrong_key_refused=True,tamper_refused=True,capture_available_bytes=shutil.disk_usage(capture).free,
        capture_mode='0700',private_identity_detached=True,real_health_data_present=False)))


if __name__=='__main__':
    main()
