"""Copy one explicitly selected received ZIP into encrypted local custody. No parsing."""
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

BLOCK_SIZE = 1024 * 1024


def fresh_folder(path):
    check=path.lstat()
    if (path.resolve()!=path or not stat.S_ISDIR(check.st_mode) or check.st_uid!=os.getuid()
            or stat.S_IMODE(check.st_mode)!=0o700):
        raise ValueError("Custody directory failed identity or mode validation")


def sha(handle):
    digest=hashlib.sha256()
    for block in iter(lambda:handle.read(BLOCK_SIZE),b''):
        digest.update(block)
    return digest.hexdigest()


def copy_zip(source, receiver, expected_image):
    downloads=Path.home()/'Downloads'
    if source.parent!=downloads or source.suffix.lower()!='.zip':
        raise ValueError("Select the exact received .zip in local Downloads")
    fresh_folder(downloads)
    fresh_folder(receiver)
    data=Path('/System/Volumes/Data')
    reader_info=plistlib.loads(subprocess.check_output(['/usr/sbin/diskutil','info','-plist',str(data)],timeout=15))
    if downloads.stat().st_dev!=data.stat().st_dev or not reader_info['FileVault']:
        raise ValueError("Downloads is outside the qualified encrypted Data volume")
    if not os.path.ismount(receiver.parent):
        raise ValueError("Expected the qualified mounted capture volume")
    images=plistlib.loads(subprocess.check_output(['/usr/bin/hdiutil','info','-plist'],timeout=15))['images']
    matching=[entry for entry in images if Path(entry.get('image-path',''))==expected_image]
    if len(matching)!=1 or not matching[0].get('image-encrypted') or not any(
        Path(item.get('mount-point',''))==receiver.parent for item in matching[0]['system-entities']
    ):
        raise ValueError("Mounted capture image does not match the encrypted custody pin")

    fd=os.open(source,os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as src:
        before=os.fstat(src.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid() or before.st_nlink!=1:
            raise ValueError("Expected a single-link local ZIP owned by the custodian")
        permissions=subprocess.check_output(['/bin/ls','-le',str(source)],text=True,timeout=10)
        if any(' allow ' in line for line in permissions.splitlines()[1:]):
            raise ValueError("Sender file has a granting ACL")
        os.fchmod(src.fileno(),0o600)
        before=os.fstat(src.fileno())
        if before.st_size<=0 or shutil.disk_usage(receiver).free < before.st_size + 1024**3:
            raise ValueError("Closed ZIP or safe capture capacity not verified")
        identifier=uuid4().hex
        pending=receiver/(identifier+'.copy-part')
        final=receiver/(identifier+'.zip')
        digest=hashlib.sha256()
        length=0
        with pending.open('xb') as sink:
            for block in iter(lambda:src.read(BLOCK_SIZE),b''):
                length+=len(block)
                if length>before.st_size: raise ValueError("Received ZIP changed while copying")
                digest.update(block)
                sink.write(block)
            sink.flush()
            os.fsync(sink.fileno())
        src.seek(0)
        after=os.fstat(src.fileno())
        stable=(before.st_size,before.st_mtime_ns,before.st_ctime_ns)==(
            after.st_size,after.st_mtime_ns,after.st_ctime_ns)
        with pending.open('rb') as dest:
            dest_sha=sha(dest)
        if not stable or length!=before.st_size or sha(src)!=digest.hexdigest() or dest_sha!=digest.hexdigest():
            raise ValueError("Closed ZIP digest, length or identity changed during custody copy")
        os.link(pending,final)
        pending.unlink()
        info=final.stat()
        assert info.st_nlink==1 and stat.S_IMODE(info.st_mode)==0o600
        return dict(local_only=True,size=length,sha256=dest_sha,opaque_local_filename=final.name,original_retained=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    parser.add_argument("receiver",type=Path)
    parser.add_argument("expected_image",type=Path)
    args=parser.parse_args()
    os.umask(0o077)
    print(json.dumps(copy_zip(args.source,args.receiver,args.expected_image)))


if __name__=='__main__':
    main()
