# WxChat-Message

无需 Docker 的企业微信代理管理工具。Nginx 负责接口转发，Python 提供本地管理页面。

当前为 `0.1.0` 开发版，提供 Linux 原生安装和本地开发两种运行方式。

## 适用场景

适合未使用 Docker，或 Docker 仅用于运行微信代理的主机。原生运行可避免单独维护 Docker、containerd 和容器辅助进程。

如果 Docker 已承载其他业务，可以继续使用原版微信代理容器。本项目增加了管理后台，后台自身也会占用内存；是否节省资源，应比较同一台机器上完整运行方案的占用。

## 已实现

- 首次访问设置管理员账号和密码，后续登录管理后台。
- 自定义代理端口，启停代理；端口占用或校验失败时保留原配置。
- 自定义上传请求大小上限，支持 1–100 MiB，默认 1 MiB。
- 查看、搜索、筛选和清空代理请求日志，显示时间、方法、接口、HTTP 状态、来源和耗时。
- 请求日志不记录查询参数、请求体或认证头，密钥和消息内容不会进入请求日志。
- 日志自动轮转，单文件 5 MiB，最多保留 3 份归档。
- 转发 `/cgi-bin` 下的企业微信接口，包括获取 Token、发送消息、创建菜单和上传素材。

后台账号仅保护管理功能。现有企业微信客户端无需额外填写后台账号密码。

## 一键安装

支持 Debian 12+ / Ubuntu 22.04+，需要系统使用 systemd。使用 root 执行：

```bash
bash <(wget -qO- https://raw.githubusercontent.com/weidaye1122/WxChat-Message/main/install.sh)
```

也可以使用 curl：

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/weidaye1122/WxChat-Message/main/install.sh)
```

脚本会安装系统 Python、venv、CA 证书和 Nginx，将锁定版本的 Python 依赖放入项目独立环境，并创建 `wxchat-message` 专用账号和 systemd 服务。程序和它启动的 Nginx 均使用该普通账号运行。Nginx 使用本项目的数据目录，不改写已有的 `/etc/nginx/nginx.conf`。

默认端口：

| 服务 | 安装版监听地址 | 用途 |
| --- | --- | --- |
| 管理页面 | `127.0.0.1:7081` | 登录、设置和日志查询 |
| 微信代理 | `0.0.0.0:30888` | 接收客户端的企业微信 API 请求；首次创建管理员后启动 |

如果原版容器已经占用 `30888`，安装器会报告端口冲突，保留现有服务。可以选择其他代理端口试用：

```bash
WXCHAT_PROXY_PORT=30889 bash <(wget -qO- https://raw.githubusercontent.com/weidaye1122/WxChat-Message/main/install.sh)
```

首次安装还可以设置 `WXCHAT_ADMIN_PORT` 和 `WXCHAT_PROXY_HOST`。升级时优先保留已经保存的环境文件和代理设置。脚本不会停止、卸载 Docker 或切换现有客户端的代理地址。

### 首次访问

管理页面默认仅监听服务器本机。在自己的电脑建立 SSH 隧道，将 `服务器IP` 替换为目标地址：

```bash
ssh -N -L 7081:127.0.0.1:7081 root@服务器IP
```

再在本机浏览器打开 <http://127.0.0.1:7081>，设置管理员账号和密码。自定义 SSH 端口时增加 `-p 端口`；自定义管理端口时同步修改隧道端口。

客户端使用服务器的代理地址，例如 `http://服务器IP:30888`。通过 SSH 隧道访问面板时，客户端地址中的 `127.0.0.1` 要替换为服务器实际地址。需要外部访问时，在服务器的防火墙和安全组中放行所选代理端口。管理端口通过 SSH 隧道访问即可。

### 升级、备份和卸载

再次执行同一条安装命令即可升级。安装器会先创建新的程序目录和 Python 环境，通过校验后再切换版本；服务启动检查失败时恢复之前的版本。账号、会话密钥、代理端口、上传限制和日志位于独立数据目录，不随程序文件替换。

`WXCHAT_VERSION` 可选择已有分支、标签或完整提交 SHA，默认 `main`。安装入口与所选源码版本需包含安装脚本。

查看服务状态和运行日志：

```bash
sudo systemctl status wxchat-message
sudo journalctl -u wxchat-message -n 100 --no-pager
```

备份管理员、会话密钥、代理设置、环境文件和 systemd 配置：

```bash
sudo /opt/wxchat-message/current/scripts/backup.sh
```

备份保存在 `/var/backups/wxchat-message/`。该备份不包含请求日志和临时上传文件。

卸载程序并保留账号、环境文件及运行数据：

```bash
sudo /opt/wxchat-message/current/scripts/uninstall.sh
```

卸载只移除本项目的程序和 systemd 服务，系统 Python、Nginx、专用账号和备份保留；已有的其他 Nginx 服务继续运行。重新安装时会复用保留的账号和设置。

### 从源码安装

```bash
git clone https://github.com/weidaye1122/WxChat-Message.git
cd WxChat-Message
sudo bash ./install.sh
```

## 本地运行

需要 Python 3.10+ 和 Nginx。macOS 可以先安装 Nginx：

```bash
brew install nginx
```

在项目目录执行：

```bash
./run.sh
```

首次执行会创建 `.venv` 并安装 Python 依赖。打开 <http://127.0.0.1:7081> 设置管理员。

默认代理端口为 `30888`，账号设置完成后自动启动；代理和管理页面默认均只监听本机。代理端口及上传大小可在页面的“代理设置”中修改。

自定义管理端口或使用独立数据目录：

```bash
./run.sh --port 7082 --data /tmp/wxchat-message-preview
```

停止管理程序时会同时停止它管理的 Nginx 实例。数据和设置会保留，下次启动自动恢复。程序不读取或改写系统的 `nginx.conf`，也不需要执行 `brew services start nginx`。

## 数据

Linux 安装版目录：

| 路径 | 内容 |
| --- | --- |
| `/opt/wxchat-message/current/` | 当前程序和独立 Python 环境 |
| `/opt/wxchat-message/releases/` | 当前及上一个程序版本 |
| `/var/lib/wxchat-message/` | 管理员、代理设置和日志 |
| `/etc/wxchat-message.env` | 管理端口、代理监听地址和运行环境 |
| `/var/backups/wxchat-message/` | 安装、升级、卸载及手动创建的配置备份 |

本地开发的数据默认保存在 `.data/`，数据内容与安装版相同：

```text
auth.json              管理员账号和密码哈希
session-key            会话签名密钥
proxy/settings.json    端口、启用状态与上传上限
proxy/nginx.conf       此实例的 Nginx 配置
proxy/requests.jsonl   代理请求日志
```

`.data/` 与 `.venv/` 已排除在 Git 之外。请勿上传管理员数据、会话密钥或生产请求日志。

环境变量：

| 变量 | 用途 |
| --- | --- |
| `NGINX_BIN` | 指定 Nginx 可执行文件 |
| `WXCHAT_DATA` | 指定数据目录 |
| `WXCHAT_ADMIN_PORT` | 管理页面端口，默认 `7081` |
| `WXCHAT_PROXY_HOST` | 代理监听地址，默认 `127.0.0.1`，也支持显式设为 `0.0.0.0` |
| `WXCHAT_SECURE_COOKIE` | 经 HTTPS 访问后台时设为 `1` |
| `WXCHAT_UPSTREAM` | 集成测试用上游，默认 `https://qyapi.weixin.qq.com` |

安装版将 `WXCHAT_DATA` 固定为 `/var/lib/wxchat-message`，默认代理监听地址为 `0.0.0.0`。需要修改安装版管理端口或监听地址时，编辑 `/etc/wxchat-message.env` 后执行 `sudo systemctl restart wxchat-message`；代理端口和上传大小通过管理页面设置。

## 验证

测试使用临时账号、独立数据目录、临时端口和本地模拟上游，会实际启动 Nginx，不触碰现有代理：

```bash
.venv/bin/python -m unittest discover -s tests -v
```

覆盖首次设置、登录退出、访问控制、CSRF、端口切换与冲突、配置恢复、上传大小调整、multipart 报文转发、日志筛选清空和敏感数据脱敏。

当前 14 项集成测试已在 macOS 和 Debian 12 x86_64 临时环境中通过。Linux 测试使用普通用户运行。与原版容器比较的 9 组无效凭证接口请求，HTTP 状态和企业微信错误码一致。

安装脚本的完整测试使用本机 Docker 创建一次性 Debian + systemd 环境，实际执行依赖安装、端口冲突检查、首次设置、升级、失败回滚、备份、卸载和重装，并核对已有 Nginx 保持运行：

```bash
bash tests/installer/run.sh
```

该测试需要允许启动 privileged、private cgroup namespace 的本机测试容器。测试容器不映射宿主机端口、不挂载 Docker socket，结束后自动删除。本项目部署运行本身无需 Docker。

模拟上游测试不能代替真实业务验收。正式迁移前仍需用现有客户端验证文字和图片的实际送达。

上传限制针对整次 HTTP 请求，包含文件和表单内容；企业微信还会按对应接口规则校验素材。HTTP 200 也不等同于微信业务成功。

## 来源与许可证

本项目参考 [YanTaocheng/wxchat-Docker](https://github.com/YanTaocheng/wxchat-Docker)（上游为 [DDSRem-Dev/wxchat-Docker](https://github.com/DDSRem-Dev/wxchat-Docker)）的企业微信转发规则，保留 MIT 许可证和原版权声明。管理界面与本地进程管理为本项目新增实现，未复制 lifj25 改版的页面。

项目仓库：<https://github.com/weidaye1122/WxChat-Message>。
