# 贡献指南

欢迎提交问题反馈、功能建议和 Pull Request。

## 开发环境

需要 Python 3.10+ 和 Nginx。macOS 可通过 Homebrew 安装 Nginx：

```bash
brew install nginx
```

获取源码并启动：

```bash
git clone https://github.com/weidaye1122/WxChat-Message.git
cd WxChat-Message
./run.sh
```

首次运行会创建 `.venv/` 并安装 Python 依赖。打开 <http://127.0.0.1:7081> 创建管理员账号。

源码运行时，管理页面和代理默认均监听 `0.0.0.0`，代理默认端口为 `30888`。创建管理员后自动启动代理，端口、上传大小和日志保存条数可在“代理设置”中修改，日志默认保留 200 条。远程首次创建账号需设置 `WXCHAT_SETUP_ALLOWED_IPS`，本机访问可直接创建。

使用其他管理端口或独立数据目录：

```bash
WXCHAT_PROXY_HOST=127.0.0.1 ./run.sh --host 127.0.0.1 --port 7082 --data /tmp/wxchat-message-dev
```

停止管理程序时会同时停止它管理的 Nginx 实例，数据和设置会保留。程序使用自己的 Nginx 配置，无需另外启动系统 Nginx 服务。

## 项目结构

| 路径 | 用途 |
| --- | --- |
| `app.py` | 管理 API、认证和服务入口 |
| `proxy.py` | Nginx 配置、进程管理和请求日志 |
| `static/` | 管理页面 HTML、CSS 和 JavaScript |
| `install.sh`、`scripts/` | Linux 安装、升级、备份和卸载 |
| `deploy/` | systemd 服务和环境配置示例 |
| `tests/` | 应用集成测试和安装流程测试 |

源码运行的数据默认保存在 `.data/`。`.data/`、`.venv/` 和 `test-artifacts/` 已排除在 Git 之外。提交时不要包含管理员数据、会话密钥或请求日志。

## 运行配置

| 变量 | 用途 |
| --- | --- |
| `NGINX_BIN` | 指定 Nginx 可执行文件 |
| `WXCHAT_DATA` | 数据目录，可通过 `--data` 覆盖 |
| `WXCHAT_ADMIN_HOST` | 管理监听地址，默认 `0.0.0.0`，可通过 `--host` 覆盖 |
| `WXCHAT_SETUP_ALLOWED_IPS` | 首次设置允许的来源 IP，逗号分隔，本机始终允许 |
| `WXCHAT_ADMIN_PORT` | 管理端口，默认 `7081`，可通过 `--port` 覆盖 |
| `WXCHAT_PROXY_HOST` | 代理监听地址，默认 `0.0.0.0` |
| `WXCHAT_SECURE_COOKIE` | 经 HTTPS 访问后台时设为 `1` |
| `WXCHAT_UPSTREAM` | 测试上游地址，默认 `https://qyapi.weixin.qq.com` |

Linux 一键安装使用固定数据目录 `/var/lib/wxchat-message/`，代理默认监听 `0.0.0.0`。安装与维护方式见 [README](README.md)。

## 测试

应用集成测试会实际启动 Nginx，使用临时账号、独立数据目录、临时端口和模拟上游：

```bash
.venv/bin/python -m unittest discover -s tests -v
```

覆盖首次设置、登录退出、访问控制、CSRF、端口切换与冲突、配置恢复、上传大小调整、multipart 报文转发、日志分页、条数保留、并发转发中的日志清理、远程首次设置来源控制和敏感数据脱敏。

安装流程测试会创建一次性 Debian + systemd 容器，实际执行依赖安装、端口冲突检查、首次设置、升级、失败回滚、备份、卸载和重装，并检查已有 Nginx 服务的状态：

```bash
bash tests/installer/run.sh
```

此项测试需要 Docker，并允许启动 privileged、private cgroup namespace 的容器。测试容器不映射宿主机端口、不挂载 Docker socket，结束后自动删除。项目部署运行无需 Docker。

[GitHub Actions](https://github.com/weidaye1122/WxChat-Message/actions) 会执行 Shell 语法检查和安装流程测试。

模拟上游和无效凭证请求不能验证真实消息送达。涉及转发行为的修改，还应使用有效企业微信账号与客户端验证文字、图片等实际业务结果。

## 提交变更

请说明变更目的、使用方式和验证结果。涉及页面的变更可附截图；涉及接口或安装流程的变更应更新相应文档与测试。

请保留 MIT 许可证和上游版权声明。
