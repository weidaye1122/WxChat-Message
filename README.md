# WxChat-Message

无需 Docker 的企业微信代理管理工具。Nginx 负责接口转发，Python 提供本地管理页面。

当前为 `0.1.0` 本地开发版，尚未替换任何线上容器。

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

本地数据默认保存在 `.data/`：

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

## 验证

测试使用临时账号、独立数据目录、临时端口和本地模拟上游，会实际启动 Nginx，不触碰现有代理：

```bash
.venv/bin/python -m unittest discover -s tests -v
```

覆盖首次设置、登录退出、访问控制、CSRF、端口切换与冲突、配置恢复、上传大小调整、multipart 报文转发、日志筛选清空和敏感数据脱敏。

当前 14 项集成测试已在 macOS 和 Debian 12 x86_64 临时环境中通过。Linux 测试使用普通用户运行。与原版容器比较的 9 组无效凭证接口请求，HTTP 状态和企业微信错误码一致。

模拟上游测试不能代替真实业务验收。正式迁移前仍需用现有客户端验证文字和图片的实际送达。

上传限制针对整次 HTTP 请求，包含文件和表单内容；企业微信还会按对应接口规则校验素材。HTTP 200 也不等同于微信业务成功。

## 来源与许可证

本项目参考 [YanTaocheng/wxchat-Docker](https://github.com/YanTaocheng/wxchat-Docker)（上游为 [DDSRem-Dev/wxchat-Docker](https://github.com/DDSRem-Dev/wxchat-Docker)）的企业微信转发规则，保留 MIT 许可证和原版权声明。管理界面与本地进程管理为本项目新增实现，未复制 lifj25 改版的页面。

项目仓库：<https://github.com/weidaye1122/WxChat-Message>。
