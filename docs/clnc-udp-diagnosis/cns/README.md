# CNS 服务端（VPS 部署）

CNS 是 [CLNC](https://github.com/mmmdbybyd/CLNC) 的配套**服务端**（本仓库来自 [mmmdbybyd/CNS](https://github.com/mmmdbybyd/CNS)，Go 实现），用于：
- HTTP CONNECT / 隧道代理（从请求头按 `proxy_key` 取目标 host；
- HTTP DNS（`?dn=域名`）；
- TCP DNS → UDP DNS；
- **UDP over HTTP 隧道（httpUDP）**：请求头含 `udp_flag`（默认 `httpUDP`）时按 UDP 会话处理。

## 本次部署（脱敏）

| 项 | 值 |
|---|---|
| 版本 | CNS **v0.4.3** `linux_amd64`（md5 `7d4edf532bfa7d5b74578526cfdc12ef`） |
| 二进制 | `/opt/cns/cns` |
| 配置 | `/opt/cns/cns.json` |
| 常驻 | systemd `cns.service`（enabled + active，`Restart=always`） |
| 监听 | `*:443` |
| 密码 | `encrypt_password = "<CNS_PWD>"` |
| proxy_key | `Meng` |

## 文件

| 文件 | 说明 |
|---|---|
| `cns.json` | 实际使用的配置（脱敏版，可直接改用） |
| `deploy_cns.py` | 部署脚本：SFTP 上传二进制 + 写配置 + 装 systemd 单元 + 校验。密码经环境变量 `VPS_PASS` 传入（不落盘） |
| `verify_cns.py` | 只读复验：服务状态 / 监听 / 本机连通 / HTTP-DNS 自测 / 日志 |

## 使用

```bash
# 部署（VPS_PASS 为 VPS root 密码；<VPS_IP> 替换为你的公网 IP）
VPS_PASS='<你的root密码>' python deploy_cns.py

# 复验
VPS_PASS='<你的root密码>' python verify_cns.py
```

## 注意

- 监听 443 需要 root；云端**安全组必须放通该端口**。
- 设置 `encrypt_password` 后，`proxy_key` 头的值需按 CNS 约定做 **Base64 + XOR** 加密（明文 curl 测不通属正常，要用 clnc 客户端）。
- `proxy_key` 默认 `Host`；本项目按 clnc 免流惯例用 `Meng`（clnc 的 `cns_header` 用 `Meng: [H]` 携带真实目标）。
