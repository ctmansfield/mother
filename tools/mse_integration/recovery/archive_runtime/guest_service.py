from pathlib import Path
import base64, hashlib, json, os, pwd, re, subprocess, sys

CONFIG = json.loads(Path(sys.argv[1]).read_text())
HOST, IFACE = sys.argv[2:4]
GUEST_IP = CONFIG["expected_guest_ipv4"]
assert re.fullmatch("[a-z0-9][a-z0-9.-]+", HOST)
root = Path("/opt/phoenix-mse-archive")
source = root / "source"
parent = Path("/var/lib/phoenix-mse-archive")
state = parent / "state"
conf = Path("/etc/phoenix-mse-archive")
unit = Path("/etc/systemd/system/phoenix-mse-archive.service")


def run(*a, **opts):
    return subprocess.check_output(a, stderr=subprocess.STDOUT, **opts)


assert all(not x.exists() and not x.is_symlink() for x in (parent, conf, unit))
assert not run("ss", "-Hltn").strip()
assert (GUEST_IP + "/30").encode() in run("ip", "-4", "addr", "show", "dev", IFACE)
assert not any(
    a.get("dst", "default") == "default"
    for a in json.loads(run("ip", "-j", "-4", "route"))
)
user = pwd.getpwnam("mse-archive")
assert user.pw_uid > 0 and user.pw_shell.endswith("/nologin")
os.umask(0o077)
parent.mkdir(mode=0o700)
os.chown(parent, user.pw_uid, user.pw_gid)
state.mkdir(mode=0o700)
os.chown(state, user.pw_uid, user.pw_gid)
conf.mkdir(mode=0o711)
conf.chmod(0o711)
control = conf / "ca-control"
control.mkdir(mode=0o700)
ca = control / "ca.pem"
ca_key = control / "ca.key"
cert = conf / "guest.pem"
key = conf / "guest.key"
csr = control / "guest.csr"
ext = control / "guest.ext"
run(
    "openssl",
    "req",
    "-x509",
    "-newkey",
    "rsa:3072",
    "-nodes",
    "-days",
    "3",
    "-subj",
    "/CN=PHOENIX MSE Archive Synthetic 20261121",
    "-addext",
    "basicConstraints=critical,CA:TRUE,pathlen:0",
    "-addext",
    "keyUsage=critical,keyCertSign,cRLSign",
    "-keyout",
    str(ca_key),
    "-out",
    str(ca),
)
run(
    "openssl",
    "req",
    "-newkey",
    "rsa:2048",
    "-nodes",
    "-subj",
    "/CN=" + HOST,
    "-keyout",
    str(key),
    "-out",
    str(csr),
)
ext.write_text(
    "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectAltName=DNS:"
    + HOST
    + "\n"
)
run(
    "openssl",
    "x509",
    "-req",
    "-in",
    str(csr),
    "-CA",
    str(ca),
    "-CAkey",
    str(ca_key),
    "-CAcreateserial",
    "-days",
    "2",
    "-extfile",
    str(ext),
    "-out",
    str(cert),
)
run("openssl", "verify", "-CAfile", str(ca), "-verify_hostname", HOST, str(cert))
config = conf / "synthetic.json"
config.write_text(json.dumps(CONFIG))
for path in (config, cert, key):
    os.chown(path, user.pw_uid, user.pw_gid)
    path.chmod(0o600)
v = root / "venv/bin/python"
run(
    "runuser",
    "-u",
    "mse-archive",
    "--",
    str(v),
    "-B",
    "-m",
    "integrations.mse_archive_service.server",
    "init",
    "--config",
    str(config),
    "--root",
    str(state),
    cwd=source,
)
unit.write_text(
    f"""[Unit]
Description=Protected MSE synthetic archive HTTPS
After=network-online.target
Wants=network-online.target

[Service]
Type=exec
User=mse-archive
Group=mse-archive
WorkingDirectory={source}
UMask=0077
ExecStart={v} -B -m integrations.mse_archive_service.server serve --config {config} --root {state} --bind {GUEST_IP} --port 8445 --cert {cert} --key {key}
KillSignal=SIGINT
TimeoutStopSec=15s
Restart=no
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths={state}

[Install]
WantedBy=multi-user.target
"""
)
unit.chmod(0o644)
run("systemd-analyze", "verify", str(unit))
run("systemctl", "daemon-reload")
run("systemctl", "start", unit.name)
der = run("openssl", "x509", "-in", str(ca), "-outform", "DER")
print(
    json.dumps(
        dict(
            ca_der=base64.b64encode(der).decode(),
            ca_sha256=hashlib.sha256(der).hexdigest(),
            source_initialized=True,
            unit_sha256=hashlib.sha256(unit.read_bytes()).hexdigest(),
            state_members=sorted(x.name for x in state.iterdir()),
        )
    )
)
