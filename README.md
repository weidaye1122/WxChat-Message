# WxChat-Message

WxChat-Message 是一个无需 Docker 的企业微信消息代理工具，提供 Web 管理、代理配置和请求日志查询。

Nginx 负责转发企业微信 API 请求，Python 提供管理后台。支持通过一键脚本安装为 Linux 系统服务。

当前版本：`0.1.0` · [MIT License](LICENSE)

## 功能

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

| 服务 | 默认监听地址 | 用途 |
| --- | --- | --- |
| 管理页面 | `127.0.0.1:7081` | 登录、设置和日志查询 |
| 微信代理 | `0.0.0.0:30888` | 接收客户端的企业微信 API 请求；首次创建管理员后启动 |

如果端口已被占用，安装器会报告冲突。可以在首次安装时指定其他代理端口：

```bash
WXCHAT_PROXY_PORT=30889 bash <(wget -qO- https://raw.githubusercontent.com/weidaye1122/WxChat-Message/main/install.sh)
```

首次安装还可以设置 `WXCHAT_ADMIN_PORT` 和 `WXCHAT_PROXY_HOST`。升级时保留已经保存的环境文件和代理设置。

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

## 配置与数据

| 路径 | 内容 |
| --- | --- |
| `/opt/wxchat-message/current/` | 当前程序和独立 Python 环境 |
| `/opt/wxchat-message/releases/` | 当前及上一个程序版本 |
| `/var/lib/wxchat-message/` | 管理员、代理设置和日志 |
| `/etc/wxchat-message.env` | 管理端口、代理监听地址和运行环境 |
| `/var/backups/wxchat-message/` | 安装、升级、卸载及手动创建的配置备份 |

`/var/lib/wxchat-message/` 中的主要文件：

```text
auth.json              管理员账号和密码哈希
session-key            会话签名密钥
proxy/settings.json    端口、启用状态与上传上限
proxy/nginx.conf       此实例的 Nginx 配置
proxy/requests.jsonl   代理请求日志
```

服务配置位于 `/etc/wxchat-message.env`：

| 变量 | 用途 |
| --- | --- |
| `WXCHAT_ADMIN_PORT` | 管理页面端口，默认 `7081` |
| `WXCHAT_PROXY_HOST` | 代理监听地址，默认 `0.0.0.0` |
| `WXCHAT_SECURE_COOKIE` | 经 HTTPS 访问后台时设为 `1` |

修改管理端口或代理监听地址后，执行 `sudo systemctl restart wxchat-message` 生效。代理端口、启用状态和上传大小通过管理页面设置。

## 使用说明

上传限制针对整次 HTTP 请求，包含文件和表单内容；企业微信还会按对应接口规则校验素材。HTTP 200 也不等同于微信业务成功。

接入客户端时，应验证文字、图片等实际消息的送达结果。

## 参与开发

开发环境、源码运行和测试方法见 [贡献指南](CONTRIBUTING.md)。问题反馈和功能建议可提交到 [Issues](https://github.com/weidaye1122/WxChat-Message/issues)。

## 来源与许可证

本项目参考 [YanTaocheng/wxchat-Docker](https://github.com/YanTaocheng/wxchat-Docker)（上游为 [DDSRem-Dev/wxchat-Docker](https://github.com/DDSRem-Dev/wxchat-Docker)）的企业微信转发规则。Web 管理界面与代理进程管理由本项目实现。

项目采用 [MIT 许可证](LICENSE)，保留上游版权声明。
