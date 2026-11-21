import glob, hashlib, json, os, pathlib, shutil, subprocess, sys

p = pathlib.Path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*a):
    return subprocess.check_output(a, text=True).strip()


assert set(os.listdir("/sys/class/net")) == {"lo"}
old_hostname = p("/etc/hostname").read_text().strip()
assert old_hostname == sys.argv[1]
assert not p("/var/lib/tailscale/tailscaled.state").exists()
assert not any(
    p(name).stat().st_size
    for name in glob.glob("/root/.ssh/authorized_keys*")
    + glob.glob("/home/*/.ssh/authorized_keys*")
)
assert not p("/var/lib/phoenix-foreground-inbox").exists()
assert not p("/var/lib/phoenix-foreground-control-20261116").exists()
assert not p("/etc/phoenix-foreground-inbox").exists()
for unit in ("ssh.service", "ssh.socket"):
    assert subprocess.run(["systemctl", "is-active", "--quiet", unit]).returncode != 0
old_machine = sha(p("/etc/machine-id"))
old_ssh = {sha(p(x)) for x in glob.glob("/etc/ssh/ssh_host_*_key.pub")}
name = sys.argv[2]
p("/etc/hostname").write_text(name + "\n")
hosts = p("/etc/hosts")
hosts.write_text(hosts.read_text().replace(old_hostname, name))
machine = p("/etc/machine-id")
new = os.urandom(16).hex() + "\n"
machine.write_text(new)
dbus = p("/var/lib/dbus/machine-id")
if dbus.exists() and not dbus.is_symlink():
    dbus.write_text(new)
for path in glob.glob("/etc/ssh/ssh_host_*_key") + glob.glob(
    "/etc/ssh/ssh_host_*_key.pub"
):
    p(path).unlink()
assert shutil.which("ssh-keygen")
run("ssh-keygen", "-A")
fingerprint = sha(p("/etc/ssh/ssh_host_ed25519_key.pub"))
assert fingerprint not in old_ssh and sha(machine) != old_machine
print(
    json.dumps(
        dict(
            hostname=name,
            previous_machine_sha256=old_machine,
            machine_sha256=sha(machine),
            ssh_public_sha256=fingerprint,
            no_interfaces=True,
            ssh_inactive=True,
        )
    )
)
