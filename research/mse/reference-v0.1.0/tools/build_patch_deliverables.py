#!/usr/bin/env python3
"""Build and verify standalone, add-only patches; never access upstream trees."""
from pathlib import Path
import difflib
import hashlib
import json
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def build(name, files):
    sections = []
    originals = {}
    for source, target in sorted(files, key=lambda item: item[1]):
        data = source.read_bytes()
        content = data.decode('utf-8')
        if content and not content.endswith('\n'):
            raise ValueError(f'Text file lacks final newline: {source}')
        mode = '100755' if source.stat().st_mode & 0o111 else '100644'
        blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        sections.append(f'diff --git a/{target} b/{target}\nnew file mode {mode}\nindex 0000000..{blob}\n')
        sections.extend(difflib.unified_diff([], content.splitlines(keepends=True),
                        fromfile='/dev/null', tofile=f'b/{target}', n=3))
        originals[target] = digest(data)
    patch = ROOT / 'patches' / name
    patch.parent.mkdir(parents=True, exist_ok=True)
    patch.write_text(''.join(sections), encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='mse-patch-review-') as temp:
        check = subprocess.run(['git', '-C', temp, 'apply', '--check', str(patch)],
                               capture_output=True, text=True)
        if check.returncode:
            raise RuntimeError(check.stderr)
        apply = subprocess.run(['git', '-C', temp, 'apply', str(patch)],
                               capture_output=True, text=True)
        if apply.returncode:
            raise RuntimeError(apply.stderr)
        restored = {str(p.relative_to(temp)): digest(p.read_bytes())
                    for p in Path(temp).rglob('*') if p.is_file()}
        if restored != originals:
            raise RuntimeError(f'Patch reconstruction differs: {name}')
    return {'patch': name, 'sha256': digest(patch.read_bytes()),
            'added_files': len(originals), 'git_apply_check': 'passed',
            'exact_reconstruction': True,
            'scope': 'empty temporary review directory only'}


def main():
    manifest = json.loads((ROOT / 'prototype/RELEASE_MANIFEST.json').read_text())
    p1 = [(ROOT / 'prototype' / rel, 'mse-reference/' + rel)
          for rel in [*manifest['files'], 'RELEASE_MANIFEST.json']]
    p2 = [(p, 'mse-design/contracts/' + str(p.relative_to(ROOT / 'design/contracts')))
          for p in (ROOT / 'design/contracts').rglob('*')
          if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
    p3 = [(ROOT / 'design/001_mse_proposed.sql', 'mse-design/001_mse_proposed.sql')]
    results = [build('P001-offline-reference.patch', p1),
               build('P002-research-contracts.patch', p2),
               build('P003-proposed-state-schema.patch', p3)]
    result = {'patches': results, 'upstream_repository_changed': False,
              'biological_validation': False}
    (ROOT / 'verification/PATCH_VERIFICATION.json').write_text(
        json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
