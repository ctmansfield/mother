import hashlib, json, os, sqlite3, ssl, stat, subprocess, tarfile
from pathlib import Path, PurePosixPath

stage = Path("/var/lib/phoenix-mse-archive-stage")
root = Path("/opt/phoenix-mse-archive")
target = root / "source"
archive = stage / "mse-private-archive-source-r2.tar"
manifest = stage / "mse-private-archive-manifest-r2.json"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


assert (
    sha(archive) == "2c08025275b348a566b90f5ff24ad2542e07f530a1332fb326f030c55ee79ead"
)
assert (
    sha(manifest) == "56769ea35b117bfcb7407b6fc3a9f4b8c286e286a5dfc1a4e2f6208683d13103"
)
assert not target.exists() and not target.is_symlink()
assert root.resolve() == root and root.stat().st_uid == 0
pins = json.loads(manifest.read_bytes())
assert pins["commit"] == "86e362f04aac4431ecd637a2c5e0c1aee1f03ad5"
assert pins["tree"] == "aa63eeca751a39588e2947ba04e560f798b24ba9"
members = {x["path"]: x for x in pins["files"]}
assert len(members) == 24
requested = {}
with tarfile.open(archive) as tar:
    for item in tar:
        path = PurePosixPath(item.name)
        assert not path.is_absolute() and ".." not in path.parts
        if item.isdir():
            continue
        assert item.isreg() and item.name in members and item.name not in requested
        exact = members[item.name]
        assert item.size == exact["size"]
        data = tar.extractfile(item).read()
        assert hashlib.sha256(data).hexdigest() == exact["sha256"]
        requested[item.name] = data
assert requested.keys() == members.keys()
target.mkdir(mode=0o755)
target.chmod(0o755)
for name, data in requested.items():
    out = target / name
    out.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    for d in out.parents:
        if d == target:
            break
        d.chmod(0o755)
    with out.open("xb") as f:
        f.write(data)
    out.chmod(0o644)
    assert sha(out) == members[name]["sha256"]
v = root / "venv/bin/python"
subprocess.run(
    [
        "runuser",
        "-u",
        "mse-archive",
        "--",
        str(v),
        "-B",
        "-m",
        "integrations.mse_archive_service.server",
        "--help",
    ],
    cwd=target,
    check=True,
    capture_output=True,
)
assert not subprocess.check_output(["ss", "-Hltn"], text=True).strip()
print(
    json.dumps(
        dict(
            commit=pins["commit"],
            tree=pins["tree"],
            members=len(requested),
            imports="passed",
            sqlite=sqlite3.sqlite_version,
            openssl=ssl.OPENSSL_VERSION,
            listener=False,
        )
    )
)
