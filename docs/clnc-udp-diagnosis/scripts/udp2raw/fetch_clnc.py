import os, paramiko
HOST="<VPS_IP>"; USER="root"; PASS=os.environ["VPS_PASS"]
LOCAL=os.path.abspath("clnc-src/raw.txt")
URL='https://smh3nbk3wo6b17bm.api.tencentsmh.cn/api/v1/file/smh3nbk3wo6b17bm/space3hysigi9ug4f4/uploads/phone/1791369130980_%E7%B4%AB%E5%85%89%E5%B1%95%E9%94%90%E7%89%88clnc%281%29.txt?access_token=acctk023e8e3556mukn7ykweha5afk2hw9t4tgr53eu9ydmksedpqyufhfyj336l9d86e4n4cdcc8y54jf6rc7pc7bnnkglf8t9bkr2g2dzb6snf3t2l5hbf3c56914b'
ssh=paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST,port=22,username=USER,password=PASS,timeout=15,look_for_keys=False,allow_agent=False)
def run(c, t=120):
    i,o,e=ssh.exec_command(c,timeout=t); return o.read().decode(errors="replace"), e.read().decode(errors="replace")

# download on VPS (has working internet/DNS)
c = ("curl -sL -o /tmp/clnc_shared.bin '%s'; "
     "python3 -c \"import sys;d=open('/tmp/clnc_shared.bin','rb').read();print('size',len(d),'magic',d[:8])\"" % URL)
o,e=run(c, t=120)
print("=== VPS download ===\n", o, ("ERR:"+e if e.strip() else ""))
if "size" in o:
    sz=int(o.split("size")[1].split()[0])
    if sz < 1000:
        # likely error page; dump head
        o2,e2=run("head -c 500 /tmp/clnc_shared.bin"); print("SMALL FILE HEAD:\n", o2)
ssh.close()

if "size" in o and sz >= 1000:
    # SFTP back to PC
    ssh2=paramiko.SSHClient(); ssh2.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh2.connect(HOST,port=22,username=USER,password=PASS,timeout=15,look_for_keys=False,allow_agent=False)
    sftp=ssh2.open_sftp()
    sftp.get("/tmp/clnc_shared.bin", LOCAL)
    sftp.close(); ssh2.close()
    data=open(LOCAL,"rb").read()
    print("LOCAL saved:", LOCAL, "size=", len(data), "magic=", data[:8])
else:
    print("NOT transferring (download failed/too small)")
