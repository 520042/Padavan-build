import os, paramiko
HOST="<VPS_IP>"; PORT=22; USER="root"; PASS=os.environ.get("VPS_PASS","")
ssh=paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST,port=PORT,username=USER,password=PASS,timeout=15,look_for_keys=False,allow_agent=False)
checks=[
 "echo '== tccli =='; which tccli 2>/dev/null || echo no-tccli",
 "echo '== instance role (metadata) =='; curl -s --max-time 5 http://metadata.tencentyun.com/latest/meta-data/cam/security-credentials/ 2>/dev/null || echo 'no-metadata-role'",
 "echo '== public ipv4 =='; curl -s --max-time 6 ipinfo.io/ip 2>/dev/null || curl -s --max-time 6 ifconfig.me 2>/dev/null || echo 'no-ipv4-api'",
 "echo '== ip addr =='; ip -4 addr show 2>/dev/null | grep inet",
]
for c in checks:
    stdin,stdout,stderr=ssh.exec_command(c,timeout=25)
    print(">>",c); print(stdout.read().decode(errors="replace").strip()); print("ERR:",stderr.read().decode(errors="replace").strip())
ssh.close()
