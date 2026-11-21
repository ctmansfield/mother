"""Verify the exact selected-pilot source package before guest staging."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile


def digest(body):
    return hashlib.sha256(body).hexdigest()


def verified_members(package, manifest_file, commit, package_sha256, manifest_sha256):
    manifest_bytes = manifest_file.read_bytes()
    if digest(manifest_bytes) != manifest_sha256 or digest(package.read_bytes()) != package_sha256:
        raise ValueError("Selected package or detached manifest does not match reviewed pins")
    manifest = json.loads(manifest_bytes)
    if manifest["commit"] != commit or manifest["package_sha256"] != package_sha256:
        raise ValueError("Detached manifest does not name the reviewed package and commit")
    expected = {entry["path"]: entry for entry in manifest["files"]}
    if len(expected) != len(manifest["files"]):
        raise ValueError("Detached manifest repeats a source member")
    actual = {}
    with tarfile.open(package, "r:") as bundle:
        for item in bundle:
            name = PurePosixPath(item.name)
            if (
                not item.isfile()
                or name.is_absolute()
                or ".." in name.parts
                or str(name) != item.name
                or item.name in actual
                or item.name not in expected
                or item.size != expected[item.name]["size"]
            ):
                raise ValueError("Unexpected selected package member")
            handle = bundle.extractfile(item)
            if handle is None:
                raise ValueError("Missing selected package member")
            with handle:
                body = handle.read()
            if digest(body) != expected[item.name]["sha256"]:
                raise ValueError("Selected package member does not match detached manifest")
            actual[item.name] = body
    if actual.keys() != expected.keys():
        raise ValueError("Selected package is incomplete")
    return manifest, actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("commit")
    parser.add_argument("package_sha256")
    parser.add_argument("manifest_sha256")
    args = parser.parse_args()
    manifest, entries = verified_members(
        args.package, args.manifest, args.commit, args.package_sha256, args.manifest_sha256
    )
    for path, body in entries.items():
        if path.endswith(".py"):
            compile(body, path, "exec")
    print(json.dumps(dict(commit=manifest["commit"], tree=manifest["tree"], members=len(entries))))


if __name__ == "__main__":
    main()
