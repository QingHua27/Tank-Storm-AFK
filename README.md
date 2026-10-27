# 坦克风暴云端挂机管理

本项目**基于 [Dimlitter/tankstorm-keepalive](https://github.com/Dimlitter/tankstorm-keepalive) 修改**，使用其 v2.0.0 Linux 引擎，新增多账号隔离、systemd 服务与网页控制台。原项目源码保存在 `upstream/`；原作者、版权和许可信息保留在源码与 `LICENSE` 中。引擎采用 GNU AGPL-3.0 或更新版本，使用和再分发请遵守相应许可证。

支持账号独立登录、状态、任务进度、二维码、日志、启动停止、账号添加删除（删除时备份）、QQ 昵称及头像、服务器负载和网页打开时的浏览器通知。QQ 登录仍依赖腾讯的扫码验证。

## 部署

适用于 Ubuntu x86-64，需要 root、systemd、nginx、Python 3、已配置 HTTPS 的域名。请先按照 `deploy/README.md` 安装依赖、配置域名证书，再执行部署步骤。网页管理账号和密码由部署者自行生成；仓库不包含真实账户、QQ 登录信息或私钥。

目录说明：`web/` 网页及服务端源码；`systemd/` 服务模板；`tankstormctl` 管理脚本；`upstream/` 原始引擎源码；`deploy/` 部署说明和示例配置。`web/static/command-bg.png` 为本项目网页背景素材。

## 测试

在安装 `web/requirements.txt` 后，进入 `web/` 执行 `python -m unittest -v test_web`；安装 Node.js 依赖后执行 `npm test`。

浏览器通知受系统后台限制；页面关闭或设备休眠时不保证收到消息。QQ 登录状态由腾讯控制，不能保证永久有效。
