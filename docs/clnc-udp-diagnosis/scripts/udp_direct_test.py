import socket, struct, sys

PROXY = ("192.168.2.1", 1081)
SRC = ("192.168.2.165", 0)  # 绑 PC 的 R3G LAN 口
TARGET = ("8.8.8.8", 53)

def build_dns_query():
    txid = b"\x12\x34"
    flags = b"\x01\x00"
    q = b"\x03www\x05baidu\x03com\x00"
    body = txid + flags + b"\x00\x01\x00\x00\x00\x00\x00\x00" + q + b"\x00\x01\x00\x01"
    return txid, body

def socks5_udp_associate(proxy, src):
    s = socket.create_connection(proxy, timeout=5, source_address=src)
    s.sendall(b"\x05\x01\x00")
    assert s.recv(2) == b"\x05\x00"
    s.sendall(b"\x05\x03\x00\x01\x00\x00\x00\x00\x00\x00")
    rep = s.recv(10)
    print("ASSOCIATE reply ver/rep/rsv/atype=", rep[0], rep[1], rep[2], rep[3])
    if rep[1] != 0:
        print("UDP ASSOCIATE 失败, rep=", rep[1]); return None
    if rep[3] == 1:
        relay_ip = ".".join(str(b) for b in rep[4:8])
        relay_port = struct.unpack(">H", rep[8:10])[0]
    elif rep[3] == 3:
        l = rep[4]; relay_ip = rep[5:5+l].decode(); relay_port = struct.unpack(">H", rep[5+l:7+l])[0]
    elif rep[3] == 4:
        relay_ip = socket.inet_ntop(socket.AF_INET6, rep[4:20]); relay_port = struct.unpack(">H", rep[20:22])[0]
    else:
        print("未知 atype"); return None
    print("clnc UDP 中继地址:", relay_ip, relay_port)
    return s, (relay_ip, relay_port)

def main():
    txid, q = build_dns_query()
    r = socks5_udp_associate(PROXY, SRC)
    if not r:
        sys.exit(1)
    ctrl, relay = r
    u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    u.bind(SRC)
    u.settimeout(6)
    hdr = b"\x00\x00\x00\x01" + struct.pack(">H", TARGET[1]) + socket.inet_aton(TARGET[0])
    u.sendto(hdr + q, relay)
    print("已发 UDP DNS 查询到", TARGET, "经中继", relay)
    try:
        data, frm = u.recvfrom(1024)
        print("收到 UDP 回复, 来自", frm, "长度", len(data))
        print("TXID 匹配:", data[:2] == txid, "| 含答案段:", len(data) > 12)
        print("RESULT: UDP 直连通路 OK (clnc 转发了 UDP 并收到回应)")
    except socket.timeout:
        print("RESULT: UDP 超时无回应 —— 可能 WAP 未桥接/直连被拦 (与 CNS 模式同前提)")

if __name__ == "__main__":
    main()
