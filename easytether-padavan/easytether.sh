#!/bin/sh
# EasyTether USB 客户端 (Padavan/老毛子专用)
# Padavan 是 uclibc 体系, 而 easytether-usb 是 musl 链接的二进制,
# 故捆绑 musl 加载器 + libgcc, 通过 musl 的动态加载器直接运行, 不污染 /lib
DIR=/usr/lib/easytether
exec "$DIR/ld-musl-mipsel-sf.so.1" --library-path "$DIR" "$DIR/easytether-usb" "$@"
