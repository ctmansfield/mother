"""Seal one exact local custody ZIP without opening its archive structure."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess
from uuid import uuid4

GIB = 1024**3


def sha_stream(stream):
    digest=hashlib.sha256()
    for chunk in iter(lambda:stream.read(1024*1024),b''):
        digest.update(chunk)
    return digest.hexdigest()


def file_pin(path):
    with path.open('rb') as stream:
        return sha_stream(stream)


def seal(age, recipient, source, pending):
    with pending.open('xb') as sink:
        result=subprocess.run([str(age),'--encrypt','--recipients-file',str(recipient),'-o','-'],
                              stdin=source,stdout=sink,stderr=subprocess.PIPE,timeout=900)
        if result.returncode!=0:
            raise RuntimeError('Local sealing failed; partial ciphertext remains restricted')
        sink.flush()
        os.fsync(sink.fileno())
    assert stat.S_IMODE(pending.stat().st_mode)==0o600


def publish(pending, final):
    os.link(pending,final)
    pending.unlink()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('source_receipt',type=Path)
    parser.add_argument('custody',type=Path)
    parser.add_argument('age',type=Path)
    parser.add_argument('age_sha256')
    args=parser.parse_args()
    os.umask(0o077)
    setup=json.loads((args.custody/'custody-readback.private.json').read_bytes())
    capture=Path(setup['capture_staging'])
    recipient=Path(setup['recipient_public_path'])
    receipt_info=args.source_receipt.lstat()
    assert stat.S_ISREG(receipt_info.st_mode) and receipt_info.st_uid==os.getuid()
    assert stat.S_IMODE(receipt_info.st_mode)==0o600
    expected=json.loads(args.source_receipt.read_bytes())
    assert expected.get('opaque_local_filename',args.source.name)==args.source.name
    assert args.source.parent==capture and args.source.suffix=='.zip'
    assert capture.resolve()==capture and capture.stat().st_uid==os.getuid()
    assert stat.S_IMODE(capture.stat().st_mode)==0o700 and os.path.ismount(capture.parent)
    assert not os.path.ismount(args.custody/'identity-mount')
    info=plistlib.loads(subprocess.check_output(['/usr/bin/hdiutil','info','-plist'],timeout=15))
    image,=[r for r in info['images'] if r.get('image-path')==setup['capture_image']]
    assert image['image-encrypted'] and any(Path(x.get('mount-point',''))==capture.parent
                                           for x in image['system-entities'])
    assert file_pin(recipient)==setup['recipient_public_sha256']
    assert file_pin(args.age)==args.age_sha256
    version=subprocess.check_output([str(args.age),'--version'],timeout=5).strip()
    assert version==b'v1.3.2'
    raw_size=expected['size']
    bound=raw_size+raw_size//100+1024**2
    assert 0<raw_size<bound<=8*GIB
    assert min(shutil.disk_usage(capture).free,shutil.disk_usage(args.custody).free)>=bound+GIB
    tag='import-'+uuid4().hex
    pending=capture/(tag+'.age.part')
    sealed=capture/(tag+'.age')
    fd=os.open(args.source,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as raw:
        start=os.fstat(raw.fileno())
        assert stat.S_ISREG(start.st_mode) and start.st_nlink==1 and start.st_uid==os.getuid()
        assert stat.S_IMODE(start.st_mode)==0o600 and start.st_size==raw_size
        assert sha_stream(raw)==expected['sha256']
        raw.seek(0)
        seal(args.age,recipient,raw,pending)
        raw.seek(0)
        finish=os.fstat(raw.fileno())
        assert (start.st_size,start.st_mtime_ns,start.st_ctime_ns)==(finish.st_size,finish.st_mtime_ns,finish.st_ctime_ns)
        assert sha_stream(raw)==expected['sha256']
    n=pending.stat().st_size
    assert raw_size<n<=bound<=8*GIB
    ciphertext_sha=file_pin(pending)
    transfer=dict(import_id=tag,ciphertext_filename=sealed.name,ciphertext_sha256=ciphertext_sha,
                  ciphertext_bytes=n,recipient_sha256=setup['recipient_public_sha256'])
    # Original pins are stored inside a separately authenticated encrypted manifest.
    private_manifest={**transfer,'plaintext_bytes':raw_size,'plaintext_sha256':expected['sha256']}
    manifest_input=json.dumps(private_manifest,sort_keys=True,separators=(',',':')).encode()
    manifest_pending=capture/(tag+'.manifest.age.part')
    with manifest_pending.open('xb') as f:
        run=subprocess.run([str(args.age),'-e','-R',str(recipient),'-o','-'],input=manifest_input,
                           stdout=f,stderr=subprocess.PIPE,timeout=20)
        assert run.returncode==0
        f.flush()
        os.fsync(f.fileno())
    publish(manifest_pending,capture/(tag+'.manifest.age'))
    publish(pending,sealed)
    with (capture/(tag+'.transfer.private.json')).open('x') as f:
        json.dump(transfer,f,sort_keys=True,separators=(',',':'))
        f.flush()
        os.fsync(f.fileno())
    directory=os.open(capture,os.O_RDONLY|os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    print(json.dumps(dict(sealed_local_only=True,source_unchanged=True,raw_manifest_encrypted=True,
                          within_object_cap=True,network_transfer=False)))


if __name__=='__main__':
    main()
