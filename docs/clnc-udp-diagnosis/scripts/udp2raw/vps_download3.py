import os, paramiko
HOST="<VPS_IP>"; PORT=22; USER="root"; PASS=os.environ.get("VPS_PASS","")
ssh=paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST,port=PORT,username=USER,password=PASS,timeout=15,look_for_keys=False,allow_agent=False)
def run(c):
    stdin,stdout,stderr=ssh.exec_command(c,timeout=120)
    return stdout.read().decode(errors="replace"), stderr.read().decode(errors="replace")

REL="20230206.0"
urls=[
 f"https://github.com/wangyu-/udp2raw/releases/download/{REL}/udp2raw_binaries.tar.gz",
 f"https://ghfast.top/https://github.com/wangyu-/udp2raw/releases/download/{REL}/udp2raw_binaries.tar.gz",
 f"https://kgithub.com/wangyu-/udp2raw/releases/download/{REL}/udp2raw_binaries.tar.gz",
]
ok=False
for u in urls:
    print("\nTRY",u)
    o,e=run(f"cd /opt/udp2raw && curl -sL --max-time 100 -o u.tar.gz '{u}' && ls -l u.tar.gz && (gzip -t u.tar.gz && echo GZIP_OK || echo GZIP_BAD)")
    print(o,e)
    if "GZIP_OK" in o:
        run("cd /opt/udp2raw && tar xzf u.tar.gz && rm -f u.tar.gz && mkdir -p bin && for f in udp2raw_*; do [ -f \"$f\" ] && cp -f \"$f\" bin/ 2>/dev/null; done; chmod +x bin/udp2raw_*; echo EXTRACTED; ls -l bin/")
        ok=True; print("=== OK via",u); break
print("\nFINAL ok=",ok)
if ok:
    o,e=run("cd /opt/udp2raw && ./bin/udp2raw_amd64 --version 2>&1 | head -2; echo '--- ARM variants ---'; ls -l bin/udp2raw_arm* bin/udp2raw_mips* 2>/dev/null")
    print(o,e)
ssh.close()
