import os, paramiko
R3G="192.168.2.1"; USER="admin"; PASS="admin"
LOCAL_MD5="ae36ea037d9c7a08b4c165dc840a7f8f"
ssh=paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(R3G,port=22,username=USER,password=PASS,timeout=15,look_for_keys=False,allow_agent=False)
def run(c, t=60):
    i,o,e=ssh.exec_command(c,timeout=t); return o.read().decode(errors="replace"), e.read().decode(errors="replace")

o,e=run("uname -m; echo '---'; mkdir -p /etc/storage/udp2raw; echo mkdir_ok")
print("=== uname/mkdir ===\n", o, ("ERR:"+e if e.strip() else ""))

# try wget (LAN, no proxy); capture exit code + stderr
o,e=run("wget --no-proxy -q -O /etc/storage/udp2raw/udp2raw http://192.168.2.165:18080/udp2raw_mips24kc_le; echo WGET=$?", t=30)
print("=== wget ===\n", o, ("ERR:"+e if e.strip() else ""))

# if --no-proxy unsupported, retry plain
if "WGET=0" not in o:
    o,e=run("wget -q -O /etc/storage/udp2raw/udp2raw http://192.168.2.165:18080/udp2raw_mips24kc_le; echo WGET=$?", t=30)
    print("=== wget(retry) ===\n", o, ("ERR:"+e if e.strip() else ""))

o,e=run("chmod +x /etc/storage/udp2raw/udp2raw; md5sum /etc/storage/udp2raw/udp2raw; ls -l /etc/storage/udp2raw/udp2raw")
print("=== chmod/md5 ===\n", o, ("ERR:"+e if e.strip() else ""))
remote_md5 = ""
for line in o.splitlines():
    p=line.split()
    if p and len(p[0])==32 and all(c in "0123456789abcdef" for c in p[0]):
        remote_md5=p[0]; break
print("MD5 match:", remote_md5==LOCAL_MD5, "(remote=%s local=%s)" % (remote_md5, LOCAL_MD5))

# smoke test: does the mipsel binary actually execute?
o,e=run("/etc/storage/udp2raw/udp2raw -h 2>&1 | head -8; echo SMOKExit=${PIPESTATUS[0]}", t=20)
print("=== smoke (-h) ===\n", o, ("ERR:"+e if e.strip() else ""))
ssh.close()
