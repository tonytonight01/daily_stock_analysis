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
| `LLM_CHANNELS` | `openai` | 模型渠道 |
| `LLM_OPENAI_PROTOCOL` | `openai` | OpenAI 协议 |
| `LLM_OPENAI_API_SURFACE` | `responses` | Responses API |
| `LLM_OPENAI_BASE_URL` | `https://api.openai.com/v1` | 官方接口地址 |
| `LLM_OPENAI_MODELS` | `gpt-6.1-sol` | 所选模型；需账号有对应权限 |
| `LITELLM_MODEL` | `openai/gpt-6.1-sol` | 分析使用的模型 |
| `MARKET_REVIEW_ENABLED` | `false` | 本方案只分析公式命中的个股 |

Secrets 配置 `LLM_OPENAI_API_KEY` 和 `FEISHU_WEBHOOK_URL`。飞书机器人如果开启关键词或签名验证，还需填写工作流已有的 `FEISHU_WEBHOOK_KEYWORD` 或 `FEISHU_WEBHOOK_SECRET`。不要把密钥提交进仓库。该项目使用 API 调用凭据，不使用聊天会话作为模型服务。

启用 Actions 后选择「每日股票分析」→ Run workflow → mode 选择 stocks-only。选股只在 A 股交易日北京时间 15:30 后运行；`force_run` 不绕过选股的收盘时间和交易日检查。默认周一至周五北京时间 18:00 触发，开始时间可能受 GitHub 调度延迟影响。无匹配或非交易日时跳过后续分析，不回退默认股票，也不发送个股报告。选中股票全部分析，不暗中截断名单；数量多时模型费用和运行时间随之增加。

任务产物 `analysis-reports-*` 含 `reports/tdx-screening.json`，记录匹配名单和数值、扫描覆盖、取数错误和不可计算股票。即使扫描失败也上传该报告（全市场快照获取前失败或任务超时则可能无法生成完整文件），先检查它再查看个股报告。公开仓库的 Actions 日志和产物可被其他人读取，不应包含私有持仓。

## 本地验证与回滚

```bash
python -m unittest tests.test_tdx_formula tests.test_tdx_screening_job -v
python scripts/screen_tdx.py --output reports/tdx-screening.json
```

线上运行尚需验证免费行情源可用性、全市场完成时间、GPT-6.1 Sol 调用及飞书推送。离线测试不会调用模型或发送消息。

设 `TDX_SCREENING_ENABLED=false` 即恢复原工作流的固定 STOCK_LIST 路径。需暂停所有分析时在 GitHub Actions 禁用「每日股票分析」。密钥保留在 GitHub Secrets；无需改其他策略或 API。此部署专题目前只提供中文，因目标用户和通达信公式语境为中文，未同步英文首页。
