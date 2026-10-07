import os, paramiko, hashlib
HOST="<VPS_IP>"; USER="root"; PASS=os.environ["VPS_PASS"]
LOCAL=os.path.join(os.path.dirname(os.path.abspath(__file__)), "udp2raw_mips24kc_le")
REMOTE="/opt/udp2raw/bin/udp2raw_mips24kc_le"
ssh=paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST,port=22,username=USER,password=PASS,timeout=15,look_for_keys=False,allow_agent=False)
sftp=ssh.open_sftp()
sftp.get(REMOTE, LOCAL)
sftp.close(); ssh.close()
with open(LOCAL,"rb") as f: d=f.read()
print("downloaded %d bytes md5=%s" % (len(d), hashlib.md5(d).hexdigest()))
