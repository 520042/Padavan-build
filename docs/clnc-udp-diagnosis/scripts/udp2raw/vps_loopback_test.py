import os, paramiko
HOST="<VPS_IP>"; USER="root"; PASS=os.environ["VPS_PASS"]
ssh=paramiko.SSHClient(); ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(HOST,port=22,username=USER,password=PASS,timeout=15,look_for_keys=False,allow_agent=False)
def run(c, t=40):
    i,o,e=ssh.exec_command(c,timeout=t); return o.read().decode(errors="replace"), e.read().decode(errors="replace")

test = r'''
set -e
iptables -I INPUT -i lo -j ACCEPT
/opt/udp2raw/bin/udp2raw_amd64 -c -l 127.0.0.1:4000 -r 127.0.0.1:4096 -k <UDP2RAW_KEY> --raw-mode faketcp --disable-color >/tmp/u2r_client.log 2>&1 &
CLIENT=$!
sleep 3
python3 - <<'INNER'
import socket, struct
def q(name):
    tid=0x1234
    hdr=struct.pack('>HHHHHH',tid,0x0100,1,0,0,0)
    qn=b''
    for p in name.split('.'):
        qn+=bytes([len(p)])+p.encode()
    qn+=b'\x00'
    return hdr+qn+b'\x00\x01'+b'\x00\x01'
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.settimeout(8)
s.sendto(q('google.com'),('127.0.0.1',4000))
try:
    data,addr=s.recvfrom(4096)
    ancount=struct.unpack('>H',data[6:8])[0]
    print("DNS_RESP len=%d ANCOUNT=%d first4=%s" % (len(data), ancount, data[:4].hex()))
except Exception as e:
    print("DNS_ERR", repr(e))
INNER
kill $CLIENT 2>/dev/null || true
sleep 1
iptables -D INPUT -i lo -j ACCEPT
echo "lo-accept-removed"
'''
o,e=run(test, t=40)
print("=== loopback e2e test (client relay -> 8.8.8.8:53) ===\n", o)
if e.strip(): print("ERR:", e)
o,e=run("tail -n 6 /tmp/u2r_client.log"); print("=== client log ===\n", o)
o,e=run("systemctl is-active udp2raw; pgrep -a udp2raw_amd64 | head -1"); print("=== server still up ===\n", o)
ssh.close()
