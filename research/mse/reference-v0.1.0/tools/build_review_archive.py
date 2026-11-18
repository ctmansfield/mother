#!/usr/bin/env python3
"""Build a deterministic review archive and verify a fresh extracted copy."""
from pathlib import Path, PurePosixPath
import gzip
import hashlib
import io
import json
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / 'mother-coach-mse-0.1.0.tgz'
PDF = ROOT.parent / 'MSE_Architecture_v0.1.0.pdf'
CHECKSUMS = ROOT.parent / 'mother-coach-mse-0.1.0.sha256'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def included():
    result = []
    for p in ROOT.rglob('*'):
        relative = p.relative_to(ROOT)
        if relative.parts[0] == 'tmp' or '__pycache__' in relative.parts or p.suffix == '.pyc':
            continue
        if p.is_symlink():
            raise RuntimeError(f'Symlink is not a release artifact: {relative}')
        if p.is_file():
            result.append(p)
    return sorted(result)


def build():
    paths = [p for p in included() if p.name != 'MANIFEST.sha256']
    (ROOT / 'MANIFEST.sha256').write_text(''.join(
        f'{digest(p.read_bytes())}  {p.relative_to(ROOT).as_posix()}\n' for p in paths))
    paths = included()
    with OUT.open('wb') as output:
        with gzip.GzipFile(fileobj=output, mode='wb', filename='', mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w', format=tarfile.PAX_FORMAT) as archive:
                top = tarfile.TarInfo(ROOT.name)
                top.type = tarfile.DIRTYPE
                top.mode = 0o700
                archive.addfile(top)
                for p in paths:
                    data = p.read_bytes()
                    info = tarfile.TarInfo(ROOT.name + '/' + p.relative_to(ROOT).as_posix())
                    info.size = len(data)
                    info.mode = 0o755 if p.stat().st_mode & 0o111 else 0o644
                    archive.addfile(info, io.BytesIO(data))
    return paths


def verify():
    with tempfile.TemporaryDirectory(prefix='mse-final-package-') as temp:
        with tarfile.open(OUT, 'r:gz') as archive:
            members = archive.getmembers()
            for member in members:
                path = PurePosixPath(member.name)
                if path.is_absolute() or '..' in path.parts or path.parts[0] != ROOT.name:
                    raise RuntimeError(f'Unsafe archive path: {member.name}')
                if not (member.isfile() or member.isdir()):
                    raise RuntimeError(f'Unexpected member type: {member.name}')
            archive.extractall(temp, filter='data')
        extracted = Path(temp) / ROOT.name
        checked = 0
        for line in (extracted / 'MANIFEST.sha256').read_text().splitlines():
            expected, relative = line.split('  ', 1)
            if digest((extracted / relative).read_bytes()) != expected:
                raise RuntimeError(f'Extracted content differs: {relative}')
            checked += 1
        manifest = json.loads((extracted / 'prototype/RELEASE_MANIFEST.json').read_text())
        for relative, expected in manifest['files'].items():
            if digest((extracted / 'prototype' / relative).read_bytes()) != expected:
                raise RuntimeError(f'Extracted prototype differs: {relative}')
        actual = {str(p.relative_to(extracted)) for p in extracted.rglob('*') if p.is_file()}
        expected = {str(p.relative_to(ROOT)) for p in included()}
        if actual != expected:
            raise RuntimeError('Archive file inventory differs from staged bundle')
    return {'safe_paths': True, 'regular_files_only': True,
            'bundle_files': len(actual), 'manifest_entries_verified': checked,
            'prototype_payload_files_verified': len(manifest['files']),
            'prototype_manifest_sha256': digest((ROOT / 'prototype/RELEASE_MANIFEST.json').read_bytes()),
            'temporary_extraction_exact': True}


def main():
    record_path = ROOT / 'verification/PACKAGE_VERIFICATION.json'
    record_path.write_text('{}\n')
    build()
    record = verify()
    record['scope'] = 'delivery integrity only; no production or biological validation'
    record_path.write_text(json.dumps(record, indent=2) + '\n')
    build()
    repeated = verify()
    for key, value in repeated.items():
        if record[key] != value:
            raise RuntimeError(f'Final verification changed: {key}')
    checksums = [(digest(p.read_bytes()), p.name) for p in (OUT, PDF)]
    CHECKSUMS.write_text(''.join(f'{sha}  {name}\n' for sha, name in checksums))
    print(json.dumps({'archive': str(OUT), 'bytes': OUT.stat().st_size,
                      'checksums': dict((name, sha) for sha, name in checksums),
                      'verification': record}, indent=2))


if __name__ == '__main__':
    main()
