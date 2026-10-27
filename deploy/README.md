# 部署说明

以下步骤针对全新 Ubuntu x86-64 服务器。请先备份服务器配置；请勿把账号 Cookie、密码或证书提交到仓库。网页通过 HTTPS 访问，用户名为 admin。

1. 安装依赖：`sudo apt update && sudo apt install -y nginx python3 python3-venv python3-pip sudo curl`。
2. 下载官方 v2.0.0 Linux x64 发行包和 SHA256SUMS，校验后解压到 `/opt/tankstorm/releases/v2.0.0/unpacked/`，确保存在 `tankstorm-linux-x64/tankstorm` 和 `config.json`。发行包在 https://github.com/Dimlitter/tankstorm-keepalive/releases/tag/v2.0.0 。
3. 将本仓库复制到服务器，在仓库目录执行 `sudo bash deploy/install.sh your-domain.example`。首次执行会为控制台生成随机密码，保存在 `/root/tankstorm-panel-access.txt`（仅 root 可读）。
4. 为域名配置已验证的 TLS 证书，并参照 `deploy/nginx.conf.example` 修改 server_name、证书路径，再启用 nginx 配置。开放 TCP 80/443。不要在公网使用明文 HTTP 登录。
5. 打开 HTTPS 地址，用生成的 admin 密码登录。在网页中添加账号，然后使用 QQ 扫码登录。若手机与网页在同一设备，通常需要另一块屏幕显示二维码。

配置文件 `/etc/tankstorm-panel.env` 含应用密钥和密码散列，权限为 600；不可上传或分享。账号目录 `/opt/tankstorm/accounts` 包含敏感资料，删除的账号备份位于其 `.backups` 子目录。备份与恢复由管理员操作。

证书续期通过发行版 certbot 定时器或自行配置的自动续期完成，并在续期后重载 nginx。不要把 `systemd/tankstorm-cert-renew.*` 直接用于其他服务器，需按本机 certbot 路径修改。
