"""Seal one exact local custody ZIP without opening its archive structure."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import stat
import subprocess
from threading import Timer
from uuid import uuid4

GIB = 1024**3
CHUNK_BYTES = 1024**2


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def file_pin(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def open_private(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    stream = os.fdopen(fd, 'rb')
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600,
                'Expected an owned, single-link private regular file')
    except BaseException:
        stream.close()
        raise
    return stream


def seal(age, recipient, source, output, expected_bytes, expected_sha, timeout):
    digest = hashlib.sha256()
    count = 0
    with output.open('xb') as sink, subprocess.Popen(
        [str(age), '--encrypt', '--recipient', recipient, '-o', '-'],
        stdin=subprocess.PIPE, stdout=sink, stderr=subprocess.DEVNULL,
    ) as process:
        deadline = Timer(timeout, process.kill)
        deadline.start()
        try:
            with process.stdin as pipe:
                while chunk := source.read(CHUNK_BYTES):
                    count += len(chunk)
                    require(count <= expected_bytes, 'Sealing input exceeded its receipt')
                    require(pipe.write(chunk) == len(chunk), 'Incomplete write to age')
                    digest.update(chunk)
            require(process.wait() == 0, 'Local age sealing failed')
            require((count, digest.hexdigest()) == (expected_bytes, expected_sha),
                    'Exact bytes supplied to age differed from the receipt')
            sink.flush()
            os.fsync(sink.fileno())
        except BaseException:
            process.kill()
            raise
        finally:
            deadline.cancel()
            deadline.join()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def complete_import(capture, source, age, recipient, recipient_sha, raw_size, raw_sha, bound):
    tag = 'import-' + uuid4().hex
    staging = capture / ('.quarantine-' + tag)
    completed = capture / tag
    staging.mkdir(mode=0o700)
    sync_directory(capture)
    sealed = staging / (tag + '.age')
    with open_private(source) as raw:
        before = os.fstat(raw.fileno())
        require(before.st_dev == capture.stat().st_dev and before.st_size == raw_size,
                'Source mount or length differed from the receipt')
        seal(age, recipient, raw, sealed, raw_size, raw_sha, timeout=900)
        after = os.fstat(raw.fileno())
        require((before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                'Source changed while sealing')
        current = source.lstat()
        require((current.st_dev, current.st_ino) == (after.st_dev, after.st_ino),
                'Staged source was replaced while sealing')
    ciphertext_bytes = sealed.stat().st_size
    require(raw_size < ciphertext_bytes <= bound <= 8 * GIB, 'Ciphertext exceeded its bounds')
    transfer = dict(import_id=tag, ciphertext_filename=sealed.name, ciphertext_sha256=file_pin(sealed),
                    ciphertext_bytes=ciphertext_bytes, recipient_sha256=recipient_sha)
    manifest = {**transfer, 'plaintext_bytes': raw_size, 'plaintext_sha256': raw_sha}
    manifest_bytes = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
    seal(age, recipient, io.BytesIO(manifest_bytes), staging / (tag + '.manifest.age'),
         len(manifest_bytes), hashlib.sha256(manifest_bytes).hexdigest(), timeout=20)

    # Consumers recognize the descriptor only inside a non-hidden completed import directory.
    marker = staging / (tag + '.transfer.private.json')
    with marker.open('x') as descriptor:
        json.dump(transfer, descriptor, sort_keys=True, separators=(',', ':'))
        descriptor.flush()
        os.fsync(descriptor.fileno())
    sync_directory(staging)
    require(not completed.exists(), 'Import destination already exists')
    staging.rename(completed)
    try:
        sync_directory(capture)
    except BaseException:
        completed.rename(staging)
        sync_directory(capture)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('source_receipt', type=Path)
    parser.add_argument('custody', type=Path)
    parser.add_argument('age', type=Path)
    parser.add_argument('age_sha256')
    args = parser.parse_args()
    os.umask(0o077)

    with open_private(args.custody / 'custody-readback.private.json') as config:
        setup = json.load(config)
    capture = Path(setup['capture_staging'])
    with open_private(args.source_receipt) as receipt:
        require(os.fstat(receipt.fileno()).st_dev == capture.stat().st_dev,
                'Source receipt must reside on the capture mount')
        expected = json.load(receipt)
    require(expected['status'] == 'local_custody_verified'
            and re.fullmatch(r'[a-f0-9]{32}\.zip', expected['opaque_copy'])
            and expected['opaque_copy'] == args.source.name and args.source.parent == capture,
            'Receipt must name the exact source in capture staging')
    raw_size = expected['bytes']
    raw_sha = expected['sha256']
    require(type(raw_size) is int and isinstance(raw_sha, str)
            and re.fullmatch(r'[0-9a-f]{64}', raw_sha), 'Invalid source receipt pins')
    require(capture.resolve() == capture and capture.stat().st_uid == os.getuid()
            and stat.S_IMODE(capture.stat().st_mode) == 0o700 and os.path.ismount(capture.parent),
            'Capture staging is not a private directory on its own mount')
    require(not os.path.ismount(args.custody / 'identity-mount'), 'Private identity must be detached')
    info = plistlib.loads(subprocess.check_output(['/usr/bin/hdiutil', 'info', '-plist'], timeout=15))
    image, = [row for row in info['images'] if row.get('image-path') == setup['capture_image']]
    require(image['image-encrypted'] and any(Path(row.get('mount-point', '')) == capture.parent
            for row in image['system-entities']), 'Expected encrypted capture image is not mounted')

    recipient_bytes = Path(setup['recipient_public_path']).read_bytes()
    recipient_sha = hashlib.sha256(recipient_bytes).hexdigest()
    require(recipient_sha == setup['recipient_public_sha256'], 'Approved recipient pin differed')
    recipient, = [line for line in recipient_bytes.decode('ascii').splitlines()
                  if line and not line.startswith('#')]
    require(re.fullmatch(r'age1pq1[0-9a-z]+', recipient), 'Expected a single hybrid age recipient')
    require(file_pin(args.age) == args.age_sha256, 'age executable pin differed')
    version = subprocess.check_output([str(args.age), '--version'], timeout=5).strip()
    require(version == b'v1.3.2', 'age version differed')
    bound = raw_size + raw_size // 100 + CHUNK_BYTES
    require(0 < raw_size < bound <= 8 * GIB, 'Source exceeds the receiver allocation')
    require(min(shutil.disk_usage(capture).free, shutil.disk_usage(args.custody).free) >= bound + GIB,
            'Insufficient capture or backing storage')
    complete_import(capture, args.source, args.age, recipient, recipient_sha, raw_size, raw_sha, bound)
    print(json.dumps(dict(sealed_local_only=True, source_unchanged=True, raw_manifest_encrypted=True,
                          within_object_cap=True, network_transfer=False)))


if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Sealing stopped. Inspect private custody locally; incomplete imports are quarantined.')
