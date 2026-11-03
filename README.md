# WxChat-Message

WxChat-Message 是一个无需 Docker 的企业微信消息代理工具，提供 Web 管理、代理配置和请求日志查询。

Nginx 负责转发企业微信 API 请求，Python 提供管理后台。支持通过一键脚本安装为 Linux 系统服务。

主要供自用和小范围朋友使用。日常按“修改 → 必要检查 → 保存到 GitHub”维护，需要给使用者更新时再发布版本。开发、目录约定和检查方法见 [开发指南](CONTRIBUTING.md)。

界面版本：`0.1.0` · [MIT License](LICENSE)。一键安装默认使用最新正式 Release 对应的源码。

## 功能

- 首次访问设置管理员账号和密码，后续登录管理后台。
- 自定义代理端口，启停代理；端口占用或校验失败时保留原配置。
- 自定义上传请求大小上限，支持 1–100 MiB，默认 1 MiB。
- 查看、搜索、筛选和清空代理请求日志，显示时间、方法、接口、HTTP 状态、来源和耗时。
- 请求日志不记录查询参数、请求体或认证头，密钥和消息内容不会进入请求日志。
- 日志默认保留最近 200 条，可在后台设置为 1–100000 条；超过上限自动清理最旧记录。每 10 秒检查一次，保留记录按每页 200 条查看。
- 请求日志同时受文件大小限制：活动文件达到 5 MiB 后轮转，归档合计最多 15 MiB；错误日志每文件 5 MiB，最多 3 份归档。
- 转发 `/cgi-bin` 下的企业微信接口，包括获取 Token、发送消息、创建菜单和上传素材。
- 提供浏览器 Favicon、Apple 主屏图标和 Web App 应用图标。

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

以上地址保留为安装入口，程序源码按 GitHub 最新正式 Release 的标签下载。草稿、预发布和仅推送的开发代码不属于默认安装目标。没有正式 Release 或获取失败时，安装器会报错停止，不会改装 `main`，也不会进入系统依赖安装或服务切换。

脚本会安装系统 Python、venv、CA 证书和 Nginx，将锁定版本的 Python 依赖放入项目独立环境，并创建 `wxchat-message` 专用账号和 systemd 服务。程序和它启动的 Nginx 均使用该普通账号运行。Nginx 使用本项目的数据目录，不改写已有的 `/etc/nginx/nginx.conf`。

默认端口：

| 服务 | 默认监听地址 | 用途 |
| --- | --- | --- |
| 管理页面 | `0.0.0.0:7081` | 登录、设置和日志查询 |
| 微信代理 | `0.0.0.0:30888` | 接收客户端的企业微信 API 请求；首次创建管理员后启动 |

如果端口已被占用，安装器会报告冲突。可以在首次安装时指定其他代理端口：

```bash
WXCHAT_PROXY_PORT=30889 bash <(wget -qO- https://raw.githubusercontent.com/weidaye1122/WxChat-Message/main/install.sh)
```

首次安装还可以设置 `WXCHAT_ADMIN_HOST`、`WXCHAT_ADMIN_PORT`、`WXCHAT_SETUP_ALLOWED_IPS` 和 `WXCHAT_PROXY_HOST`。升级时保留已经保存的环境文件和代理设置。

### 首次访问

管理后台和代理默认监听所有 IPv4 网卡。在云服务器安全组和系统防火墙中放行 **TCP 7081、30888**，然后访问：

- 管理后台：`http://服务器公网IP:7081`
- 客户端代理地址：`http://服务器公网IP:30888`

`127.0.0.1` 是访问设备自身，不能作为其他设备连接服务器的地址；`0.0.0.0` 是监听配置，也不要填入客户端。

首次创建管理员仅允许服务器本机，以及 `WXCHAT_SETUP_ALLOWED_IPS` 中指定的来源 IP。通过 SSH 安装时，安装器自动登记当前 SSH 客户端的公网 IP，在同一网络打开公网管理页面即可创建账号。账号创建后，其他来源也可正常登录；首次设置入口不可重复使用。

如果通过云控制台安装，或首次设置前更换了网络，可在 `/etc/wxchat-message.env` 添加 `WXCHAT_SETUP_ALLOWED_IPS=你的客户端公网IP`，然后执行 `systemctl restart wxchat-message`。多个 IP 用逗号分隔。该设置只限制首次创建账号，不限制日常登录或企业微信代理请求。

需要仅本机管理时，将 `WXCHAT_ADMIN_HOST=127.0.0.1` 写入环境文件并重启服务，再建立 SSH 隧道：

```bash
ssh -N -L 7081:127.0.0.1:7081 root@服务器IP
```

此时打开本机 <http://127.0.0.1:7081>；客户端代理仍填写服务器公网 IP。管理端口可在安全组中仅允许自己的来源 IP；需要加密访问时，可使用 HTTPS 反向代理。

### 升级

再次执行同一条安装命令即可升级。安装器会先创建新的程序目录和 Python 环境，通过校验后再切换版本；服务启动检查失败时恢复之前的版本。账号、会话密钥、代理端口、上传限制和日志位于独立数据目录，不随程序文件替换。

未设置 `WXCHAT_VERSION` 或设为空时，默认选择最新正式 Release。需要固定版本时，将它设为确实存在的标签或完整提交 SHA。开发排查仍可显式指定已有分支，例如 `WXCHAT_VERSION=main`；这些显式选择保留原有行为，所选源码需包含安装脚本。

日常保存代码到 GitHub 不会改变默认安装版本。准备给使用者更新时，再从已检查的代码发布正式 Release；只有标签、草稿或预发布都不会成为默认安装目标。使用者需要更新时，重新执行同一安装命令即可取得最新正式版本，已安装服务不会自行升级。

升级成功后保留当前及上一个程序目录，启动检查失败时自动切回原程序和服务配置；这不等同于恢复历史数据备份。查找或下载版本失败时，现有程序、服务和数据保持原样。

查看服务状态和运行日志：

```bash
sudo systemctl status wxchat-message
sudo journalctl -u wxchat-message -n 100 --no-pager
```

### 备份与恢复

备份管理员、会话密钥、代理设置、环境文件和 systemd 配置：

```bash
sudo /opt/wxchat-message/current/scripts/backup.sh
```

备份保存在 `/var/backups/wxchat-message/`，每次生成独立目录，不自动过期。安装、升级和卸载也会先备份。备份只复制当时存在的文件，包含：

```text
data/auth.json         管理员账号和密码哈希
data/session-key       会话签名密钥
data/proxy/settings.json  代理端口、启用状态、上传上限、日志条数
wxchat-message.env     运行环境
wxchat-message.service  服务配置（当时存在才会复制）
backup.json            原程序位置和数据目录说明
```

备份不包含程序、Python 环境、请求日志和临时上传文件。首次安装前的备份可能没有账号和设置文件，不能当作完整恢复点。备份含账号与密钥，只应私下保存；清理前保留一份确认可用的备份和重要升级前的备份，不按日期自动删除。

现有脚本没有一键恢复命令。Linux 默认安装路径下可手动恢复，建议先在独立测试环境演练：

1. 选定备份，核对上述账号、密钥、代理设置和环境文件均存在，查看 `backup.json` 确认来源。程序和依赖需另行保留可取得的标签或提交 SHA；新机器或程序损坏时，先安装对应版本，确保服务账号和目录已建立。
2. 停止服务，再用现有备份脚本保存恢复前的状态。备份期间不要同时安装、升级或修改设置。
3. 将下面的路径替换为选定的备份目录，恢复账号、密钥、代理设置和环境文件。若任一步失败，先排查，不继续启动。

```bash
wxchat_backup='/var/backups/wxchat-message/替换为实际备份目录'
sudo systemctl stop wxchat-message &&
sudo /opt/wxchat-message/current/scripts/backup.sh &&
sudo install -o wxchat-message -g wxchat-message -m 600 "$wxchat_backup/data/auth.json" "$wxchat_backup/data/session-key" /var/lib/wxchat-message/ &&
sudo install -o wxchat-message -g wxchat-message -m 600 "$wxchat_backup/data/proxy/settings.json" /var/lib/wxchat-message/proxy/settings.json &&
sudo install -o root -g root -m 600 "$wxchat_backup/wxchat-message.env" /etc/wxchat-message.env &&
sudo systemctl start wxchat-message
sudo systemctl status wxchat-message --no-pager
```

通常使用当前安装生成的 systemd 服务文件。只有确实需要恢复原来的自定义服务配置、且确认其中的程序路径有效时，才恢复备份的 `wxchat-message.service`，并在启动前执行 `sudo systemctl daemon-reload`。换机器时还要核对环境文件中的监听地址、端口、Nginx 路径和首次设置来源 IP。

恢复后检查管理员登录、代理端口、上传限制、日志条数与代理状态。请求日志不会由配置备份恢复；真实企业微信消息的送达仍需单独确认。上述手动恢复步骤已按现有备份格式核对，本次整理未实测恢复，验证边界见 [开发指南](CONTRIBUTING.md#更新记录与验证状态)。

### 卸载

卸载程序并保留账号、环境文件及运行数据：

```bash
sudo /opt/wxchat-message/current/scripts/uninstall.sh
```

卸载只移除本项目的程序和 systemd 服务，系统 Python、Nginx、专用账号和备份保留；已有的其他 Nginx 服务继续运行。重新安装时会复用保留的账号和设置。

### 从源码安装

这是开发或排查时的显式源码入口，安装当前检出的文件，不会联网替你选择正式 Release。需要固定源码时先检出相应标签或提交；日常使用者采用上面的一键安装命令。

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
proxy/settings.json    端口、启用状态、上传上限与日志条数
proxy/nginx.conf       此实例的 Nginx 配置
proxy/requests.jsonl   代理请求日志
```

源码运行的数据默认位于仓库的 `.data/`，也可用 `--data` 指定其他目录；与 Linux 安装版的数据分开。数据、日志、真实环境文件和备份都不进入 Git。

服务配置位于 `/etc/wxchat-message.env`：

| 变量 | 用途 |
| --- | --- |
| `WXCHAT_ADMIN_HOST` | 管理页面监听地址，默认 `0.0.0.0`；可设为 `127.0.0.1` |
| `WXCHAT_ADMIN_PORT` | 管理页面端口，默认 `7081` |
| `WXCHAT_SETUP_ALLOWED_IPS` | 首次创建管理员允许的来源 IP，逗号分隔；SSH 安装自动登记 |
| `WXCHAT_PROXY_HOST` | 代理监听地址，默认 `0.0.0.0` |
| `WXCHAT_SECURE_COOKIE` | 经 HTTPS 访问后台时设为 `1` |

修改管理监听地址、管理端口或代理监听地址后，执行 `sudo systemctl restart wxchat-message` 生效。代理端口、启用状态、上传大小和最多保存日志条数通过管理页面设置。旧配置没有日志条数时默认使用 200 条。旧版环境文件未指定 `WXCHAT_ADMIN_HOST` 时，升级后管理页面默认监听 `0.0.0.0`；需要仅本机管理请显式设为 `127.0.0.1`。

### 保留与清理

| 内容 | 现有规则 |
| --- | --- |
| 安装版程序目录 | 升级成功后仅保留当前及上一个版本；失败时清理本次新版本并尝试恢复旧服务 |
| 配置备份 | 每次新增目录，无自动数量或天数限制；人工核对后再处理旧备份 |
| 请求日志 | 默认保留最近 200 条，可设 1–100000 条；活动文件达到 5 MiB 时轮转，归档合计最多 15 MiB |
| Nginx 错误日志 | 活动文件达到 5 MiB 时轮转，最多保留 3 份归档 |
| systemd 运行日志 | 由系统 journald 管理，不受后台请求日志条数设置控制 |

程序约每 10 秒维护一次日志；正在写入的归档会延后处理，因此条数和大小可短暂超限。日常查看或清空请求日志使用后台已有功能，不再增加轮转脚本或定时删除任务。

## 使用说明

上传限制针对整次 HTTP 请求，包含文件和表单内容；企业微信还会按对应接口规则校验素材。HTTP 200 也不等同于微信业务成功。

接入客户端时，应验证文字、图片等实际消息的送达结果。

## 参与开发

开发环境、源码运行、日常提交和测试方法见 [开发指南](CONTRIBUTING.md)。问题反馈和功能建议可提交到 [Issues](https://github.com/weidaye1122/WxChat-Message/issues)。

## 来源与许可证

本项目参考 [YanTaocheng/wxchat-Docker](https://github.com/YanTaocheng/wxchat-Docker)（上游为 [DDSRem-Dev/wxchat-Docker](https://github.com/DDSRem-Dev/wxchat-Docker)）的企业微信转发规则。Web 管理界面与代理进程管理由本项目实现。

项目采用 [MIT 许可证](LICENSE)，保留上游版权声明。
