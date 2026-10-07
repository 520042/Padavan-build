#!/bin/sh
# Clash 控制面板 Web 服务 (busybox httpd, 端口 9091) — 仅提供页面, 不自动启动 clash
[ -f /www2/index.html ] && busybox httpd -p 0.0.0.0:9091 -h /www2
