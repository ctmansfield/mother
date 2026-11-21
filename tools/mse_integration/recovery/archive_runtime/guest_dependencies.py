from pathlib import Path, PurePosixPath
import hashlib, json, os, shutil, sqlite3, ssl, stat, subprocess, sys, zipfile

PINS = json.loads(Path(sys.argv[1]).read_text())
GUEST_IP = sys.argv[2]
root = Path("/opt/phoenix-mse-archive")
stage = Path("/var/lib/phoenix-mse-archive-stage")
assert not root.exists()
assert (
    subprocess.run(["getent", "passwd", "mse-archive"], capture_output=True).returncode
    == 2
)
addresses = json.loads(
    subprocess.check_output(["ip", "-j", "-4", "addr", "show"], text=True)
)
assert any(
    item.get("local") == GUEST_IP and item.get("prefixlen") == 30
    for a in addresses
    for item in a.get("addr_info", [])
)
routes = json.loads(subprocess.check_output(["ip", "-j", "-4", "route"], text=True))
assert not any(route.get("dst", "default") == "default" for route in routes)
assert not subprocess.check_output(["ss", "-Hltn"], text=True).strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


for name, expected in PINS.items():
    path = stage / name
    info = path.lstat()
    assert (
        stat.S_ISREG(info.st_mode)
        and info.st_uid == 0
        and info.st_nlink == 1
        and digest(path) == expected
    )
root.mkdir(mode=0o755)
subprocess.run(
    ["/usr/bin/python3", "-m", "venv", "--without-pip", str(root / "venv")],
    check=True,
    capture_output=True,
)
site = root / "venv/lib/python3.12/site-packages"
for name in sorted(PINS):
    with zipfile.ZipFile(stage / name) as z:
        assert z.testzip() is None
        for entry in z.infolist():
            path = PurePosixPath(entry.filename)
            mode = entry.external_attr >> 16
            assert path.parts and not path.is_absolute() and ".." not in path.parts
            assert not any(
                p.endswith(".data") for p in path.parts
            ) and not stat.S_ISLNK(mode)
            if not entry.is_dir():
                target = site.joinpath(*path.parts)
                target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
                with target.open("xb") as f:
                    f.write(z.read(entry))
                target.chmod(0o644)
subprocess.run(
    [
        "useradd",
        "--system",
        "--user-group",
        "--no-create-home",
        "--shell",
        "/usr/sbin/nologin",
        "mse-archive",
    ],
    check=True,
    capture_output=True,
)
v = root / "venv/bin/python"
verified = subprocess.check_output(
    [
        str(v),
        "-I",
        "-B",
        "-c",
        "import importlib.metadata as m, json, rpds, jsonschema, sqlite3, ssl;print(json.dumps({n:m.version(n) for n in ('jsonschema','attrs','jsonschema-specifications','referencing','rpds-py','typing-extensions')}))",
    ],
    text=True,
)
print(
    json.dumps(
        dict(
            versions=json.loads(verified),
            wheel_sha256=PINS,
            sqlite=sqlite3.sqlite_version,
            openssl=ssl.OPENSSL_VERSION,
            guest_link=True,
            has_default_route=False,
            listeners=0,
        )
    )
)
