# 开发与维护指南

这是一个自用和小范围朋友使用的小项目。复用现有代码、脚本和测试，按“修改 → 必要检查 → 保存到 GitHub；需要给使用者更新时再发布版本”维护。

## 日常开发

1. 用 `git status --short`、`git diff` 看清已有改动，保留与本次无关的工作。
2. 直接在 `main` 做日常小修改；较大或不确定的修改需要隔离时再建分支，不强制 PR、多人审核或审批。
3. 按下面的检查范围验证，说明已经验证和尚未验证的部分。
4. 只暂存本次核对过的文件，查看 `git diff --cached`，再提交并推送 GitHub。不要习惯性执行 `git add .`。

例如，本次只调整 README 时，检查内容和链接后可执行：

```bash
git add -- README.md
git diff --cached
git commit -m "docs: 补充使用说明"
git push origin main
```

推送不会自动部署，也不需要每次提交都改版本号或创建标签。需要给使用者更新时，再整理使用变化、兼容性和验证结果，做对应检查，按需创建版本标签和 GitHub Release；日常变更通过 Git 历史查看即可。保留已有历史、标签、MIT 许可证和上游版权声明。

默认安装和升级只选择最新正式 Release。日常将代码推送到 `main` 不会改变默认安装版本；准备给使用者更新时，从已检查的提交创建版本标签和正式 Release，再由使用者按需升级。只有标签、草稿或预发布不影响默认安装。需要固定版本或试用开发代码时仍可显式指定，详见 [README 的升级说明](README.md#升级)。

## 开发环境与启动

需要 Python 3.10+ 和 Nginx。macOS 可通过 `brew install nginx` 安装 Nginx，不需要启动 Homebrew 的 Nginx 服务。

```bash
git clone https://github.com/weidaye1122/WxChat-Message.git
cd WxChat-Message
WXCHAT_PROXY_HOST=127.0.0.1 ./run.sh --host 127.0.0.1
```

首次运行会创建 `.venv/`，按 `requirements.txt` 安装依赖。打开 <http://127.0.0.1:7081> 创建管理员。源码程序本身仍默认监听 `0.0.0.0`；上面的命令只是让本机开发显式监听本机地址，不改变产品默认配置。首次创建管理员后自动启动代理，初始端口 `30888`，端口、上传上限和日志条数可在后台调整。

需要可重复的依赖版本时，先执行 `python3 -m venv .venv`，再执行 `.venv/bin/python -m pip install -r requirements.lock`。Linux 安装器本来就使用该锁定文件；不要因文档整理或顺手升级依赖而重写它。

使用独立数据和另一个管理端口：

```bash
WXCHAT_PROXY_HOST=127.0.0.1 ./run.sh --host 127.0.0.1 --port 17081 --data ../本地资料/开发数据
```

这只改变管理端口和数据目录，代理初始端口仍是 `30888`；已有实例占用时不要停止其他实例，应为新实例另选代理端口。手动启动默认仍使用真实企业微信上游，只用于本机试用；转发测试使用下文已有的模拟测试，不填真实凭据、不向企业微信发送测试消息。

按 Ctrl+C 停止管理程序时，也会停止它管理的 Nginx，数据和设置保留。程序使用自己的 Nginx 配置，无需修改或启动系统 Nginx 服务。

## 文件放哪里

保留现在的代码结构，不为目录整齐搬动代码。

| 路径 | 用途与 Git 约定 |
| --- | --- |
| `app.py`、`proxy.py`、`static/` | 管理后台、Nginx 管理和页面，提交 Git |
| `install.sh`、`run.sh`、`scripts/` | 启动、安装、升级、备份和卸载，提交 Git |
| `deploy/` | systemd 服务和无真实凭据的环境示例，提交 Git |
| `tests/`、`.github/workflows/` | 现有测试和 CI，提交 Git |
| `README.md`、`CONTRIBUTING.md`、`LICENSE` | 使用说明、维护约定和许可证，提交 Git |
| `requirements.txt`、`requirements.lock` | 依赖声明和安装版锁定版本，提交 Git |
| `.venv/`、`__pycache__/`、`*.pyc` | 本地依赖与缓存，不提交 |
| `.data/`、自选数据目录、真实 `.env` 文件 | 运行数据和真实配置，不提交 |
| `test-artifacts/` | 已有本地验证材料，不提交；现有文件保留原位 |
| 仓库旁的 `../本地资料/` | 讨论、验证材料和人工备份，不属于仓库 |

`../本地资料/` 按用途使用 `讨论/`、`验证/`、`备份/`，需要时再建子目录；独立开发实例的数据可放 `开发数据/`。长期有效的用法和维护约定回到仓库文档，临时讨论不另建一套工程文档。

`.gitignore` 已排除常见环境文件、账号、会话密钥、请求日志和备份格式，并保留环境示例。自选目录仍需确认被忽略，不能只依赖忽略规则；提交前查看暂存内容，确保没有真实密码、Token、会话密钥、账号数据、请求日志或备份。截图和验证输出分享前也要检查敏感内容。

## 运行配置

| 变量 | 用途 |
| --- | --- |
| `NGINX_BIN` | 指定 Nginx 可执行文件 |
| `WXCHAT_DATA` | 数据目录，可通过 `--data` 覆盖 |
| `WXCHAT_ADMIN_HOST` | 管理监听地址，默认 `0.0.0.0`，可通过 `--host` 覆盖 |
| `WXCHAT_ADMIN_PORT` | 管理端口，默认 `7081`，可通过 `--port` 覆盖 |
| `WXCHAT_SETUP_ALLOWED_IPS` | 首次设置允许的来源 IP，逗号分隔，本机始终允许 |
| `WXCHAT_PROXY_HOST` | 代理监听地址，默认 `0.0.0.0` |
| `WXCHAT_SECURE_COOKIE` | 经 HTTPS 访问后台时设为 `1` |
| `WXCHAT_UPSTREAM` | 可指定模拟上游，默认 `https://qyapi.weixin.qq.com` |

Linux 安装版使用固定数据目录 `/var/lib/wxchat-message/`，配置文件为 `/etc/wxchat-message.env`。安装、更新、备份范围、手动恢复和日志保留规则统一见 [README](README.md#配置与数据)，不重复实现脚本。

## 按改动选择检查

| 改动 | 必要检查 |
| --- | --- |
| 只改文档 | 核对说明与源码、命令和链接，运行 `git diff --check` |
| 普通代码、配置或依赖 | 基本检查；管理 API、认证、页面交互或转发变化时运行应用集成测试，并检查相关页面 |
| 安装、升级、备份、数据兼容、Nginx 管理 | 基本检查、应用集成测试及完整 Linux 安装测试；现有测试没有覆盖的恢复或迁移步骤另在隔离环境验证 |

基本检查不需要安装系统包，也不启动 Nginx 或 Docker：

```bash
git diff --check
for script in install.sh run.sh scripts/*.sh tests/installer/run.sh; do bash -n "$script"; done
python3 -m compileall -q app.py proxy.py scripts tests
python3 -m json.tool static/manifest.webmanifest > /dev/null
python3 -m unittest discover -s tests -p 'test_log_retention.py' -v
```

这些日志保留测试复用现有测试文件，使用临时目录。应用集成测试还需要 `.venv/` 中的项目依赖和 PATH 中的 Nginx：

```bash
WXCHAT_PROXY_HOST=127.0.0.1 .venv/bin/python -m unittest discover -s tests -v
```

集成测试使用临时账号、独立临时数据目录、临时端口和本机模拟上游，覆盖首次设置、登录、CSRF、端口冲突、设置保留、上传、报文转发、日志和来源控制。缺少 Nginx 时相关测试会显示 `skipped`，不能把跳过视为通过。

完整安装测试复用现有脚本：

```bash
bash tests/installer/run.sh
```

它需要 Docker，可启动 privileged、private cgroup namespace 的一次性 Debian + systemd 容器，验证 wget/curl 的正式版本选择、显式版本、下载失败与无 Release 时停止，以及真实依赖安装、端口冲突、账号与会话保留、升级、失败回滚、备份、卸载重装及已有 Nginx 不受影响。版本与企业微信上游都由容器内模拟服务提供，不映射宿主机端口、不挂载 Docker socket，结束后删除本次容器和源码快照；构建镜像会留作复用。项目运行本身无需 Docker。

[GitHub Actions](https://github.com/weidaye1122/WxChat-Message/actions) 在推送或 PR 时只执行基本检查中的 Shell、Python、manifest 检查和日志保留测试。需要完整安装验证时，打开 **Checks → Run workflow**，选择待测分支并勾选 **运行完整 Linux 安装、升级、回滚和卸载测试**；默认不勾选。也可先在本地执行上面的完整测试。文档修改在本地只需核对内容、链接和差异，推送后仍会运行轻量 CI。

不要用真实运行数据做测试。模拟测试、无效凭据或 HTTP 200 都不能证明真实微信消息已送达；转发行为修改还需要有效企业微信账号和客户端单独验收，并明确记录是否已验证。

## 备份与清理约定

Linux 安装版沿用现有备份和日志管理，具体规则见 [README](README.md#备份与恢复)。源码运行没有自动备份：停止程序后，可将整个实际数据目录复制到 `../本地资料/备份/`；恢复前先保存当前数据，再复制回原目录并核对权限。`.venv/` 不属于数据备份。管理员、`session-key` 和 `proxy/settings.json` 是身份和设置恢复的关键文件。

保留有效备份和关键验证结果。一次性输出用完后，只清理当前任务自己创建、归属明确的临时目录或容器；已有 `.data/`、历史截图、不明数据和其他项目的 Docker 资源保留。不要执行全局 Docker 清理，不新增定时删除任务。本地依赖和缓存通常不进 Git，无需为了目录整齐定期删除。

## 更新记录与验证状态

### 2026-11-03 · 默认安装正式 Release（未发布）

- 一键安装默认选择最新正式 Release 对应的标签源码；没有正式版本、地址无效或下载失败时停止，保留现有程序和数据，不回退到开发分支。
- 保留安装入口、显式指定标签/分支/提交及本地源码安装。系统服务、账号、会话密钥、端口、上传限制、日志、备份和失败回滚沿用原有实现。
- 扩展现有隔离安装测试，覆盖两种下载工具的版本选择和失败处理，以及正式版本间的升级保留；验证结果记录在仓库旁 `本地资料/验证/2026-11-03-正式Release安装/`。
- 已通过本机 22 项应用与日志测试，以及 Debian + systemd 容器内 13 组完整安装检查，包括升级保留、失败回滚、备份和卸载重装。测试镜像的软件包安装最多重试 3 次，以处理本次遇到的下载代理临时错误。
- 本次只修改并保存代码，不创建正式 Release 或部署；真实服务器、Ubuntu 和真实企业微信送达未在本次验收。

### 2026-11-03 · 开发整理（未发布）

- 沿用现有代码结构、安装入口、默认配置、接口、备份和日志管理；保留已有界面未提交改动。
- 补充轻量开发流程、Git 与本地资料边界、版本固定、手动恢复和清理说明，增强忽略规则；CI 改为日常基本检查、完整安装测试手动选择。
- 已按源码核对备份范围、程序版本保留和日志轮转；本地通过基本检查及现有 5 项日志保留测试，并核对文档链接、忽略规则和原有界面改动未被覆盖。具体结果保存在仓库旁 `本地资料/验证/2026-11-03-开发整理/`，不代表 GitHub CI 已运行。
- 本次未连接生产服务器、部署或发布；未运行真实 Nginx 应用集成测试、Linux 完整安装测试，未实测升级回滚、备份恢复及真实企业微信送达。现有测试覆盖范围见上文，不能替代本次实测结果。
