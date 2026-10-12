# 极空间 NAS：Web 工作台与 DeepSeek

本方案先在极空间局域网运行项目原生 Web 界面。J4125 为 x86_64（Docker 的 linux/amd64），8GB 内存可用于 Web 与低并发分析。DeepSeek 通过远程 API 调用，不在 NAS 部署模型权重；开始时建议只运行一只股票的分析。

使用官方预构建镜像 `ghcr.io/zhulinsen/daily_stock_analysis:latest`，避免在 NAS 上编译前端与安装全部 Python 依赖。已核对该镜像提供 linux/amd64 和 linux/arm64。该镜像包含上游 Web 工作台，不包含本 Fork 新增的通达信 Actions 脚本；当前每日公式任务仍在自己的 GitHub Actions 运行，产物不会自动进入 NAS 的历史列表。

## 准备文件与目录

**支持 Compose 的极空间可优先使用无需手工建目录的快速入口**：将 `docker/docker-compose.nas-quick.yml` 内容导入一个新的 Compose 项目，启动后访问 `http://NAS局域网IP:8000`。该文件自动创建三个 Docker 命名卷，并仅在首次启动时生成 DeepSeek 配置；在网页「设置」填写 Key 后重启，配置不会被初始化逻辑覆盖。它不要求上传 `runtime.env` 或填写 NAS 的绝对路径。选择这个入口后，不要同时启动下文的另一套容器。

命名卷由 Docker 管理，不能仅备份 Compose 文本就视为已备份数据；可通过 Docker/NAS 的卷管理导出 data/logs/reports。正常停止或更新容器保留命名卷，**不要选择删除关联卷，也不要执行 `docker compose down -v`**。若更换 Compose 项目名称，会创建另一组卷，原记录不会自动迁移。偏好在 NAS 文件管理器直接管理数据目录时，可使用下文的文件夹映射方案。

快速入口已在当前 Docker 环境实际验证首次生成配置、私有文件权限、管理员登录、首页响应，以及重启后保留原配置与登录开关。模型 Key 留空，未发起新的 DeepSeek 调用；仍需在实际 NAS 上验证访问与分析。

首次页面可能显示镜像拉取/初始化尚未完成，应先确认容器正常运行；NAS 的 8000 端口已占用时，在 Compose 环境设置 `NAS_WEB_PORT` 为另一个空闲端口，或只修改 ports 映射的宿主机端口。外网 IPv4 地址本身不代表该端口已经可达，远程访问方式确认前先完成局域网验证。

在极空间文件管理器中新建专用目录（例如 `docker/daily-stock-analysis`），在其中建立 `data`、`logs`、`reports` 三个子目录。

- 把本仓库 `docs/examples/tdx-webui-cloud.env.example` 的内容保存为 `data/runtime.env`。该文件已设置 DeepSeek Flash，API Key 留空；务必保存成文本文件 `runtime.env`，不能带 `.txt` 后缀。
- 若使用 Compose，把 `docker/docker-compose.nas.yml` 保存到该专用目录，并命名为 `compose.yml`。Compose 的三个相对目录均以该文件所在位置为基准；如果极空间编排工具移动了配置文件，需将它们改为 NAS 上的实际绝对路径。
- DeepSeek Key 仅填写到 NAS 本机的 `runtime.env` 或网页「设置」中，不发到聊天、不上传 GitHub。已有文件和目录不应被替换，数据目录包含配置与登录信息。

## 用 Docker 图形界面创建容器

极空间 Docker 界面菜单名称可能随系统版本变化，按以下容器字段填写即可，无需在 NAS 安装 Python 或 Node.js。

| 字段 | 值 |
| --- | --- |
| 镜像 | `ghcr.io/zhulinsen/daily_stock_analysis:latest` |
| 网络模式 | bridge（桥接） |
| 端口映射 | NAS TCP `8000` → 容器 TCP `8000`；NAS 端口可改为其他空闲端口 |
| 启动命令 | `python main.py --serve-only --host 0.0.0.0 --port 8000` |
| 重启策略 | unless-stopped（或 NAS 提供的自动重启选项） |

保留镜像自带 entrypoint，只修改 command；不要设置特权模式，也不要覆盖镜像用户。镜像启动入口会修复可写目录权限并降权运行。

目录映射（均可写）：

| NAS 文件夹 | 容器目录 |
| --- | --- |
| 专用目录下的 `data` | `/app/data` |
| 专用目录下的 `logs` | `/app/logs` |
| 专用目录下的 `reports` | `/app/reports` |

环境变量：

| 名称 | 值 |
| --- | --- |
| `TZ` | `Asia/Shanghai` |
| `ENV_FILE` | `/app/data/runtime.env` |
| `WEBUI_HOST` | `0.0.0.0` |
| `WEBUI_PORT` | `8000` |
| `WEBUI_AUTO_BUILD` | `false` |
| `ADMIN_AUTH_ENABLED` | `true` |

DeepSeek 模型和 Key 在 `data/runtime.env` 中配置，不要重复作为容器启动环境注入，否则后续网页保存的配置可能被旧环境值覆盖。NAS 首次拉取镜像可能需等待；若拉取失败，保留错误信息排查，不使用来历不明的替代镜像。

## 使用 Compose 的等效配置

若设备已有 Compose 或支持导入编排，在上述专用目录执行：

```bash
docker compose -f compose.yml up -d
docker compose -f compose.yml ps
docker compose -f compose.yml logs --tail=100 server
```

`NAS_WEB_PORT` 可调整 NAS 对外端口，`API_PORT` 同时调整容器命令和健康检查端口；默认均为 8000。`DSA_NAS_IMAGE` 可指定已验证的版本或镜像 digest，更新前先备份 data/logs/reports。不要删除这些宿主机目录。

## 打开网页与首次验证

容器启动后，在同一局域网的电脑浏览器访问 `http://NAS局域网IP:映射端口`。首次访问创建管理员密码，再到「设置」填写 DeepSeek Key 并保存，按页面提示重启容器；切换浅色主题即可使用产品预览中的工作台。

首次历史列表为空是正常情况。用一只 A 股代码运行手动分析，完成后可在历史列表打开实际报告。GitHub 的 `tdx-model-check.json` 仅为通路验证短报告，不会显示在这里。外网访问需要另行确认极空间系统提供的容器访问/组网方式，NAS 自带远程文件访问不等于已能远程访问该 Web 端口。

已在当前 Docker 环境拉取并启动 linux/amd64 镜像，验证健康检查、首页、引用的六个前端资源、启用管理员登录及读取持久化 DeepSeek 模型配置。检查时没有填写 API Key，因此未进行新的模型调用。所测镜像索引 digest 为 `sha256:6eb3750a9e9f5581afb75047f53074011fd50ca6b9278634d502e6b73fb666c4`；`latest` 会随上游发布变化。

这些检查不等于已部署到用户 NAS。设备尚未接入当前执行环境，需在实际极空间上完成镜像拉取、目录权限、浏览器访问和 DeepSeek 调用验证。
