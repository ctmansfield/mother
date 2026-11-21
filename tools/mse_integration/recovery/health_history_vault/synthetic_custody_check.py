"""Exercise detached-recipient archival custody with generated non-health test bytes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile

def run(*args):
    return subprocess.run(args, check=True, capture_output=True, timeout=45).stdout


def hash_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bin_dir", type=Path)
    parser.add_argument("workspace", type=Path)
    args = parser.parse_args()
    age = str((args.bin_dir / "age").resolve(strict=True))
    keygen = str((args.bin_dir / "age-keygen").resolve(strict=True))
    assert run(age, "--version").strip() == b"v1.3.2"
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix="synthetic-history-", dir=args.workspace) as name:
        root = Path(name)
        vault = root / "vault"
        capture = root / "capture"
        keys = root / "separate-custodian"
        for path in (vault, capture, keys):
            path.mkdir(mode=0o700)
        original = capture / "generated-not-health.zip"
        with zipfile.ZipFile(original, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("export.xml", b'<synthetic fixture="true"/>')
            archive.writestr("attachments/generated.txt", b"synthetic archive attachment")
        identity = keys / "rehearsal.agekey"
        wrong = keys / "unrelated.agekey"
        run(keygen, "-pq", "-o", str(identity))
        run(keygen, "-pq", "-o", str(wrong))
        assert all(p.stat().st_mode & 0o777 == 0o600 for p in (identity, wrong))
        recipient = capture / "recipient.txt"
        run(keygen, "-y", "-o", str(recipient), str(identity))
        ciphertext = vault / "generated-not-health.zip.age"
        run(age, "--encrypt", "--recipients-file", str(recipient), "-o", str(ciphertext), str(original))
        obtained = run(age, "--decrypt", "--identity", str(identity), str(ciphertext))
        assert hashlib.sha256(obtained).hexdigest() == hash_file(original)
        refusal = subprocess.run(
            [age, "--decrypt", "--identity", str(wrong), str(ciphertext)],
            capture_output=True, timeout=45,
        )
        assert refusal.returncode != 0 and not refusal.stdout
        tampered = vault / "generated-tampered.age"
        altered = bytearray(ciphertext.read_bytes())
        altered[-1] ^= 1
        with tampered.open("xb") as handle:
            handle.write(altered)
        refusal = subprocess.run(
            [age, "--decrypt", "--identity", str(identity), str(tampered)],
            capture_output=True, timeout=45,
        )
        assert refusal.returncode != 0
        assert {p.name for p in vault.iterdir()} == {ciphertext.name, tampered.name}
        print(json.dumps(dict(tool="age v1.3.2", synthetic_only=True, members=2,
            original_bytes=original.stat().st_size, ciphertext_bytes=ciphertext.stat().st_size,
            exact_round_trip=True, wrong_key_refused=True, tamper_refused=True,
            vault_contains_only_ciphertext=True)))


if __name__ == "__main__":
    main()
