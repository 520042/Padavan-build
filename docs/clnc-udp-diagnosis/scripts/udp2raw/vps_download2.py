import os, paramiko
HOST="<VPS_IP>"; PORT=22; USER="root"; PASS=os.environ.get("VPS_PASS","")
ssh=paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST,port=PORT,username=USER,password=PASS,timeout=15,look_for_keys=False,allow_agent=False)
def run(c):
    stdin,stdout,stderr=ssh.exec_command(c,timeout=90)
    return stdout.read().decode(errors="replace"), stderr.read().decode(errors="replace")

# inspect the bad file
o,e=run("cd /opt/udp2raw && cat udp2raw_binaries.tar.gz; echo '---'; rm -f udp2raw_binaries.tar.gz")
print("bad file content:", repr(o))

REL="v20230206.0"
urls=[
 f"https://github.com/wangyu-/udp2raw/releases/download/{REL}/udp2raw_binaries.tar.gz",
 f"https://ghproxy.com/https://github.com/wangyu-/udp2raw/releases/download/{REL}/udp2raw_binaries.tar.gz",
 f"https://ghfast.top/https://github.com/wangyu-/udp2raw/releases/download/{REL}/udp2raw_binaries.tar.gz",
 f"https://mirror.ghproxy.com/https://github.com/wangyu-/udp2raw/releases/download/{REL}/udp2raw_binaries.tar.gz",
 f"https://kgithub.com/wangyu-/udp2raw/releases/download/{REL}/udp2raw_binaries.tar.gz",
]
ok=False
for u in urls:
    print("\nTRY",u)
    o,e=run(f"cd /opt/udp2raw && curl -sL --max-time 90 -o u.tar.gz '{u}' && ls -l u.tar.gz && (gzip -t u.tar.gz && echo GZIP_OK || echo GZIP_BAD)")
    print(o,e)
    if "GZIP_OK" in o:
        run("cd /opt/udp2raw && tar xzf u.tar.gz && rm -f u.tar.gz && for f in udp2raw_*; do [ -f \"$f\" ] && cp -f \"$f\" bin/ 2>/dev/null; done; chmod +x bin/udp2raw_*; ls -l bin/")
        ok=True; print("=== DOWNLOAD OK via",u); break
print("\nFINAL ok=",ok)
if ok:
    o,e=run("cd /opt/udp2raw && ./bin/udp2raw_amd64 --version 2>&1 | head -2")
    print("amd64 version:",o,e)
ssh.close()
