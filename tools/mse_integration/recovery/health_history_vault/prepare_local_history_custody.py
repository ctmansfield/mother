"""Provision two independently encrypted local custody mounts without handling Health data."""
import argparse
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import plistlib
import secrets
import subprocess

SECURITY = "/System/Library/Frameworks/Security.framework/Security"
ACCOUNT = b"health-history-custodian"


def run(*args, secret=None):
    return subprocess.run(args, input=secret, check=True, capture_output=True, timeout=90).stdout


def put_password(service, secret):
    security = c.CDLL(SECURITY)
    add = security.SecKeychainAddGenericPassword
    add.argtypes = [c.c_void_p, c.c_uint32, c.c_char_p, c.c_uint32, c.c_char_p,
                    c.c_uint32, c.c_void_p, c.c_void_p]
    add.restype = c.c_int32
    body = c.create_string_buffer(secret)
    status = add(None, len(service), service, len(ACCOUNT), ACCOUNT, len(secret), body, None)
    if status != 0:
        raise RuntimeError(f"Dedicated Keychain item creation failed with OSStatus {status}")


def get_password(service):
    security = c.CDLL(SECURITY)
    find = security.SecKeychainFindGenericPassword
    find.argtypes = [c.c_void_p, c.c_uint32, c.c_char_p, c.c_uint32, c.c_char_p,
                     c.POINTER(c.c_uint32), c.POINTER(c.c_void_p), c.c_void_p]
    find.restype = c.c_int32
    free = security.SecKeychainItemFreeContent
    free.argtypes = [c.c_void_p, c.c_void_p]
    free.restype = c.c_int32
    size = c.c_uint32()
    value = c.c_void_p()
    result = find(None, len(service), service, len(ACCOUNT), ACCOUNT, c.byref(size), c.byref(value), None)
    if result != 0:
        raise RuntimeError(f"Dedicated Keychain item read failed with OSStatus {result}")
    try:
        return c.string_at(value, size.value)
    finally:
        free(None, value)


def attach(image, mount, password):
    assert mount.is_dir() and not mount.is_symlink() and not any(mount.iterdir())
    run('/usr/bin/hdiutil','attach',str(image),'-stdinpass','-nobrowse','-owners','on',
        '-mountpoint',str(mount),secret=password+b'\0')
    assert os.path.ismount(mount)


def detach(mount):
    run('/usr/bin/hdiutil','detach',str(mount))
    assert not os.path.ismount(mount)


def prepare_image(root, label, size):
    service=('org.phoenix.mse.health-history.local-r1.'+label).encode()
    image=root/(label+'.sparsebundle')
    mount=root/(label+'-mount')
    assert not image.exists() and not mount.exists()
    secret=secrets.token_urlsafe(36).encode()
    put_password(service,secret)
    assert get_password(service)==secret
    run('/usr/bin/hdiutil','create','-size',size,'-fs','APFS','-type','SPARSEBUNDLE',
        '-volname','MSE History '+label.title(),'-encryption','AES-256','-stdinpass',str(image),secret=secret+b'\0')
    encryption=plistlib.loads(run('/usr/bin/hdiutil','isencrypted','-plist',str(image)))
    assert encryption['encrypted']
    image.chmod(0o700)
    mount.mkdir(mode=0o700)
    attach(image,mount,get_password(service))
    return image,mount,service


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path)
    parser.add_argument('age_keygen',type=Path)
    args=parser.parse_args()
    root=args.root.resolve()
    assert root.parent.is_dir() and not root.exists()
    os.umask(0o077)
    root.mkdir(mode=0o700)
    capture_image,capture,capture_item=prepare_image(root,'capture','12g')
    folder=capture/'staging'
    folder.mkdir(mode=0o700)
    assert folder.stat().st_uid==os.getuid() and folder.stat().st_mode&0o777==0o700
    key_image,key_mount,key_item=prepare_image(root,'identity','256m')
    try:
        protected=key_mount/'protected'
        protected.mkdir(mode=0o700)
        identity=protected/'health-history-recipient.agekey'
        public=root/'health-history-recipient.public.txt'
        run(str(args.age_keygen.resolve()),'-pq','-o',str(identity))
        run(str(args.age_keygen.resolve()),'-y','-o',str(public),str(identity))
        assert identity.stat().st_uid==os.getuid() and identity.stat().st_mode&0o777==0o600
        assert public.read_bytes().startswith(b'age1pq1')
        key_readback=run(str(args.age_keygen.resolve()),'-y',str(identity))
        assert key_readback==public.read_bytes()
    finally:
        detach(key_mount)
    receipt=dict(capture_image=str(capture_image),capture_staging=str(folder),
                 capture_encrypted=True,capture_mounted=True,capture_limit_gib=12,
                 key_image=str(key_image),key_encrypted=True,key_mount_detached=True,
                 recipient_public_path=str(public),recipient_public_sha256=hashlib.sha256(public.read_bytes()).hexdigest(),
                 keychain_service_labels=[capture_item.decode(),key_item.decode()],real_health_data_present=False)
    with (root/'custody-readback.private.json').open('x') as f:
        json.dump(receipt,f,indent=2)
    print(json.dumps({key:receipt[key] for key in (
        'capture_encrypted','capture_mounted','capture_limit_gib','key_encrypted','key_mount_detached',
        'recipient_public_sha256','real_health_data_present')}))


if __name__=='__main__':
    main()
