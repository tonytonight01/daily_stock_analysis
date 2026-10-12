# 通达信公式每日选股与分析

当前部署方案使用日线、前复权，扫描沪深主板、创业板、科创板 A 股并排除名称含 ST 的股票。北交所、ETF、指数、B 股不在范围内。选股不调用 LLM；选中名单交给既有每日股票分析流程，使用用户配置的模型生成报告并通过既有通知服务推送。无需本地通达信运行或同步名单。

## 原公式与计算边界

```text
N:=30;
RSV:=(CLOSE-LLV(LOW,9))/(HHV(HIGH,9)-LLV(LOW,9))*100;
K:=SMA(RSV,3,1); D:=SMA(K,3,1); J:=3*K-2*D;
DIF:=EMA(CLOSE,12)-EMA(CLOSE,26);
VH1:=HHV(VOL,N);
VH2:=HHV(IF(VOL<VH1,VOL,0),N);
VH3:=HHV(IF(VOL<VH2,VOL,0),N);
AVGHIGH:=(VH1+VH2+VH3)/3;
VL1:=LLV(VOL,N);
VL2:=LLV(IF(VOL>VL1,VOL,9999999),N);
VL3:=LLV(IF(VOL>VL2,VOL,9999999),N);
AVGLOW:=(VL1+VL2+VL3)/3;
SELECT:J<18 AND DIF>0 AND AVGHIGH>4*AVGLOW;
```

保留逐日 IF 序列和嵌套 HHV/LLV，不使用最近 30 日成交量排序取前三/后三。SMA 是递归平滑，非三日简单平均。成交量单位为手，保留原公式的 `9999999` 字面值。默认读取腾讯前复权日线 250 根；为避免混用复权和成交量单位，日线不切换其他源，复用项目原有日线读取与交易日期校验。股票全集来自项目原有全市场快照读取，按新浪、efinance、AkShare 的顺序尝试。

EMA 用第一根收盘价初始化，K/D 用第一个完整 9 日窗口的 RSV 初始化。不足 90 根日线或 RSV 分母为零时无法计算，写入报告的 `undefined`，不视为正常未命中。请求错误、缺少当日收盘 K 线、陈旧行情、非法 OHLCV 写入 `errors`，整个任务返回失败并阻止下游分析，避免将不完整扫描冒充全市场结果。长期停牌股票若没有当日 K 线也会触发该严格检查；此版本尚未接入可靠的停复牌状态源。

股票全部涨跌幅、复权精度、成交量精度、历史起点均可能与通达信不同。离线测试验证公式实现，不代表已经和通达信逐只对齐。启用之前应比较同一收盘日的通达信名单、J/DIF 和成交量指标；接近阈值的股票尤其需要核对。

## GitHub Actions 配置

在自己的 Fork 的 Settings → Secrets and variables → Actions → Variables 配置：

| 名称 | 值 | 用途 |
| --- | --- | --- |
| `TDX_SCREENING_ENABLED` | `true` | 开启本公式，取代固定 STOCK_LIST |
| `TDX_SCREENING_WORKERS` | `4` | 选股日线并发，允许 1–8 |
| `TDX_SCREENING_LOOKBACK` | `250` | 历史日线根数，允许 90–1000 |
| `ANALYSIS_TIMEOUT_MINUTES` | `180` | 全市场扫描较慢，按实际耗时调整 |
| `LLM_CHANNELS` | `deepseek` | 仅启用 DeepSeek 渠道 |
| `LLM_DEEPSEEK_PROTOCOL` | `deepseek` | DeepSeek 协议 |
| `LLM_DEEPSEEK_API_SURFACE` | `chat_completions` | Chat Completions API |
| `LLM_DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | 官方接口地址 |
| `LLM_DEEPSEEK_MODELS` | `deepseek-flash` | 官方当前 Flash 模型名称 |
| `LITELLM_MODEL` | `deepseek/deepseek-flash` | 分析与验证使用的模型 |
| `MARKET_REVIEW_ENABLED` | `false` | 本方案只分析公式命中的个股 |

Secrets 配置 `LLM_DEEPSEEK_API_KEY`，值为 DeepSeek 平台创建的 API Key，不能复用 OpenAI Key。当前可行性验证不需要推送配置。正式需要飞书推送时再配置 `FEISHU_WEBHOOK_URL`。飞书机器人如果开启关键词或签名验证，还需填写工作流已有的 `FEISHU_WEBHOOK_KEYWORD` 或 `FEISHU_WEBHOOK_SECRET`。不要把密钥提交进仓库。该项目使用 API 调用凭据，不使用聊天会话作为模型服务。

从 GPT 切换时必须修改已有的 `LLM_CHANNELS` 和 `LITELLM_MODEL`，再添加四项 `LLM_DEEPSEEK_*` Variables；只新增 DeepSeek Key 不会切换模型。原来的 `LLM_OPENAI_*` 配置可保留，单渠道 `deepseek` 不会加载该渠道。若曾配置 `LLM_DEEPSEEK_ENABLED=false`，须改为 `true` 或删除该项。最新模型名与地址见 [DeepSeek 官方文档](https://api-docs.deepseek.com/en/)。

启用 Actions 后选择「每日股票分析」→ Run workflow → mode 选择 stocks-only。选股只在 A 股交易日北京时间 15:30 后运行；`force_run` 不绕过选股的收盘时间和交易日检查。默认周一至周五北京时间 18:00 触发，开始时间可能受 GitHub 调度延迟影响。无匹配或非交易日时跳过后续分析，不回退默认股票，也不发送个股报告。选中股票全部分析，不暗中截断名单；数量多时模型费用和运行时间随之增加。

任务产物 `analysis-reports-*` 含 `reports/tdx-screening.json`，记录匹配名单和数值、扫描覆盖、取数错误和不可计算股票。即使扫描失败也上传该报告（全市场快照获取前失败或任务超时则可能无法生成完整文件），先检查它再查看个股报告。公开仓库的 Actions 日志和产物可被其他人读取，不应包含私有持仓。

## 本地验证与回滚

### 截图中的 Web 工作台

项目已包含产品预览中的 Web 前端，无需另写界面。GitHub Actions 负责运行任务，不托管持续运行的 Web 服务；网页需要在本地电脑或云服务器单独启动。

**Windows 本地启动入口**：从本 Fork 下载源码 ZIP 并完整解压，安装 Python 3.11+（安装时勾选 Add Python to PATH）与符合前端要求的 Node.js（当前为 20.19–26.x，建议使用 LTS），双击根目录的 `start-webui-local.cmd`。启动器会创建项目内 `.venv`、安装 Python 依赖、通过现有启动流程构建前端，服务就绪后自动打开浏览器。首次安装需联网且可能耗时数分钟；后续启动按依赖文件变化决定是否重新安装。保留命令窗口，按 Ctrl+C 停止服务。Windows 启动入口尚需在用户机器验证，不依赖远程控制或读取本机通达信数据。

首次启动仅在 `.env` 不存在时复制 `docs/examples/tdx-webui.env.example`，已有配置不会被覆盖。模板已选择 DeepSeek Flash，Key 留空；进入网页「设置」填写 `LLM_DEEPSEEK_API_KEY` 并保存，按页面提示重启。也可直接在本地 `.env` 填写。设置浅色主题后可使用截图中的工作台。在 macOS/Linux 可运行 `python3 scripts/start-webui-local.py`；`--no-browser` 可关闭自动打开浏览器。

在已安装 Python 3.11+、Node.js 20.19+ 和 npm 10+ 的部署机器上，下载本 Fork，安装 `requirements.txt` 中的依赖，然后构建前端：

```bash
cd apps/dsa-web
npm ci --registry=https://registry.npmjs.org --replace-registry-host=always
npm run build
cd ../..
python main.py --webui-only --host 127.0.0.1 --port 8000
```

该构建将页面写入 `static/`，由同一个 Python 服务提供页面与 API。本机浏览器打开 `http://127.0.0.1:8000`，在主题菜单选择浅色，首页可查看历史报告、情绪评分、策略点位和资讯；具体外观随当前前端版本有所变化。启动参数可按实际部署修改，不把当前云环境的 loopback 地址当作用户电脑的访问地址。公网部署请使用 [云服务器 Web 界面访问指南](deploy-webui-cloud.md) 配置登录认证和访问入口。

部署机器的 `.env` 需要填写上表六项 DeepSeek 配置，以及 `LLM_DEEPSEEK_API_KEY`；GitHub Secrets 不会自动同步到该机器。密钥只填写在部署机器的配置或 Web 系统设置中，不提交仓库。不要为此启用微信或飞书推送。

历史列表读取该 Web 服务的数据库。Actions ZIP 里的 `tdx-model-check.json` 是通路验证短报告，不是完整个股分析记录，不会自动出现在历史列表中。首次启动历史列表为空是正常情况；在首页运行个股分析后可查看真实结果。当前通达信公式运行在 Actions 选股脚本中，启用 Web 服务本身不会将这条公式接入网页选股页或自动同步每日名单；正式部署时需要明确数据同步与调度方式，不能把产品预览中的样例数据作为真实报告。

### 云服务器常驻 Web 工作台

本方案在目标 Linux 服务器安装 Docker Engine 与 Compose v2 后，从自己的 Fork 构建前端和后端，保留本 Fork 的改动，不依赖上游预构建镜像。首次构建需要联网安装依赖，建议先确认服务器可以访问 GitHub、Docker Hub、npm、PyPI、DeepSeek 和行情服务。

```bash
git clone https://github.com/tonytonight01/daily_stock_analysis.git
cd daily_stock_analysis
sh scripts/deploy-webui-cloud.sh
```

独立 Compose 文件为 `docker/docker-compose.cloud.yml`，只启动 Web/server 服务，`restart: unless-stopped` 提供容器重启恢复；服务器自身还需启用 Docker 开机启动。它不会启动 analyzer，也不会把 Actions 的公式调度迁移到服务器。

启动器只在不存在时创建 `data/runtime.env`；在服务器上填写该文件里的 DeepSeek Key，或通过网页「设置」保存。该文件被整个 data 目录挂载，重建时不会覆盖，所以网页保存的模型配置会保留；没有把同名模型/密钥从宿主机 `.env` 再次注入容器覆盖它。数据库、登录状态、日志和报告也保存在挂载目录中，密钥留空时界面仍可配置，但不能运行实际模型分析。

默认开启管理员认证，首次访问创建登录密码。默认宿主机只监听 loopback，先在你的电脑建立 SSH 隧道（将占位符替换为真实 SSH 用户名和服务器地址）：

```bash
ssh -N -L 8000:127.0.0.1:8000 SSH_USER@SERVER_ADDRESS
```

保持隧道窗口打开，在电脑浏览器访问 `http://127.0.0.1:8000`；服务实际运行在云服务器。若本机端口已占用，可改隧道左侧端口。需要直接通过公网网址访问时，先配置域名与 HTTPS 反向代理，再将代理上游指向服务器 loopback 端口；参考 [云服务器 Web 界面访问指南](deploy-webui-cloud.md)。Compose 插值变量 `API_PORT` 可修改服务端口，`API_BIND_HOST` 默认 `127.0.0.1`，不要在没有配置访问入口时随意改为公网监听。

构建默认使用官方 npm 源，并替换锁文件中的镜像下载主机；`NPM_REGISTRY` 和 `NPM_REPLACE_REGISTRY_HOST` 可通过 Compose 插值变量调整。查看、重启和停止服务：

```bash
docker compose -f docker/docker-compose.cloud.yml ps
docker compose -f docker/docker-compose.cloud.yml logs --tail=100 server
docker compose -f docker/docker-compose.cloud.yml restart server
docker compose -f docker/docker-compose.cloud.yml down
```

停止不会删除宿主机 data/logs/reports；更新前应备份这些目录（包含凭据，备份也需妥善保存）。更新并重建可运行 `git pull --ff-only`，然后再次执行启动器；回滚到此前提交并重建前，也应先备份数据库。

### 当前阶段：小样本可行性验证，不配置推送

在 Actions → 每日股票分析 → Run workflow 勾选 `verify_only`，样本数 `screening_sample_size` 默认 20（范围 1–100）。`verify_as_of` 留空时须在当天收盘后（北京时间 15:30 后）启动；盘前、周末或休市时可填近期已收盘交易日，例如 `2026-10-09`。历史验证只用目标日及之前的 K 线，当前接口仅提供最近一段历史，过早的目标日可能不足 90 根。股票全集仍来自当前快照，不用于历史全市场回测。

这个模式无需开启 `TDX_SCREENING_ENABLED`，从沪深非 ST 股票代码中均匀抽取样本，不把样本名单写入正式分析。保留每只已计算样本的 J、DIF、AVGHIGH、AVGLOW 和选中状态，记录行情获取耗时、覆盖数和失败原因。样本扫描完成后，用现有 `GeminiAnalyzer.generate_text_with_metadata` 对最多三个实际样本生成一份短报告，记录请求模型与实际模型。空模型输出或切换到另一模型会验证失败；费用及重试沿用项目现有模型路由。该检查验证生成通路，不代表已完成完整个股分析或正确性评估。

无需配置企业微信或飞书；验证分支不调用通知服务。保留模型 Variables 和 `LLM_DEEPSEEK_API_KEY` Secret 即可。下载 `analysis-reports-*`，检查 `tdx-screening.json`（行情与公式）和 `tdx-model-check.json`（模型通路及短报告）。小样本成功后再扩大样本，并用同日期的通达信结果对照。全市场停牌/行情缺失导致任务中断的严格策略尚需在正式启用前处理。

```bash
python -m unittest tests.test_tdx_formula tests.test_tdx_screening_job tests.test_tdx_llm_verification -v
python scripts/screen_tdx.py --output reports/tdx-screening.json
```

线上运行尚需验证免费行情源可用性、全市场完成时间、GPT-6.1 Sol 调用及飞书推送。离线测试不会调用模型或发送消息。

设 `TDX_SCREENING_ENABLED=false` 即恢复原工作流的固定 STOCK_LIST 路径。需暂停所有分析时在 GitHub Actions 禁用「每日股票分析」。密钥保留在 GitHub Secrets；无需改其他策略或 API。此部署专题目前只提供中文，因目标用户和通达信公式语境为中文，未同步英文首页。
