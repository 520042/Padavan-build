import os, sys, paramiko

HOST = "<VPS_IP>"
PORT = 22
USER = "root"
PASS = os.environ.get("VPS_PASS", "")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST, port=PORT, username=USER, password=PASS, timeout=15, look_for_keys=False, allow_agent=False)

cmds = [
    "echo '== uname -a =='; uname -a",
    "echo '== uname -m =='; uname -m",
    "echo '== ss -tlnp =='; (ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null)",
    "echo '== iptables -L INPUT -n -v =='; iptables -L INPUT -n -v 2>/dev/null | head -40",
    "echo '== tools =='; which wget curl tar udp2raw 2>/dev/null; ls -l /usr/local/bin/udp2raw 2>/dev/null",
    "echo '== os =='; (cat /etc/os-release 2>/dev/null | head -3)",
    "echo '== pubip =='; (curl -s --max-time 8 ip.sb 2>/dev/null || curl -s --max-time 8 icanhazip.com 2>/dev/null || echo 'no-pubip')",
]
for c in cmds:
    print("### CMD:", c.splitlines()[0])
    stdin, stdout, stderr = ssh.exec_command(c, timeout=30)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    print(out)
    if err.strip():
        print("!! ERR:", err)
    print()

ssh.close()
