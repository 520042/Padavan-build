#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""UDP 透明代理端到端测试（经 R3G 免流链）。

强制绑定 R3G WiFi 源(192.168.2.165)，UDP 包才会经 R3G PREROUTING 被 REDIRECT 到 7891。
测试项:
  1. 纯 IP 型 NTP(202.120.2.101:123)  —— 不依赖 DNS，验证 UDP 转发链路本身
  2. 域名型 NTP(ntp.aliyun.com:123)   —— 走 fake-ip，贴近游戏/云游戏真实场景
"""
import socket
import struct
import time

SRC = "192.168.2.165"
NTP_MSG = b"\x1b" + 47 * b"\0"


def test(target, label):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(7)
    try:
        s.bind((SRC, 0))
    except OSError as e:
        print("%s: 绑定源 %s 失败: %s" % (label, SRC, e))
        s.close()
        return
    t0 = time.time()
    try:
        s.sendto(NTP_MSG, (target, 123))
        data, _ = s.recvfrom(1024)
        sec = struct.unpack("!I", data[40:44])[0] - 2208988800
        print("%s (%s:123): UDP OK  NTP时间=%s  耗时=%.0fms"
              % (label, target, time.strftime("%H:%M:%S", time.localtime(sec)),
                 (time.time() - t0) * 1000))
    except Exception as e:
        print("%s (%s:123): UDP FAIL: %s" % (label, target, e))
    finally:
        s.close()


if __name__ == "__main__":
    print("源接口:", SRC)
    test("202.120.2.101", "[纯IP-NTP]")
    test("ntp.aliyun.com", "[域名-NTP(fake-ip)]")
