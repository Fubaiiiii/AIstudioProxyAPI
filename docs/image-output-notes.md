# 生图输出支持 — 实现说明（2026-10-21）

## 已实现

`stream/interceptors.py` 的 `parse_response_from_buffer` 增加图片部件提取：

- 上游图片部件的 wire 结构（真机抓取核验，非假设）：一个以 `,"model"]` 结尾的
  wire 对象，其 payload 满足 `payload[1] is None` 且
  `payload[2] == ["image/jpeg", "<base64>"]`（payload 总长 13）。
- 命中时把图片以 Markdown data URI 追加进 body：
  `![generated image](data:<mime>;base64,<...>)`。
  OpenAI 应答仍是纯文本 content，形状零变化，文本路径零回归（解析器层面的
  守卫条件与文本/函数调用分支互不重叠）。
- 去重：同一请求内按 `(mime, len, 前64字符)` 去重，只发一次。抓包实测同一
  图片在一条流里被上游原样重发 26 次（base64 长度恒为 547280），不去重会
  输出 26 张相同的图。
- 去重集合在 `reset_for_new_request` 时清空（与 response_buffer 同生命周期）。

配套（非代码）：`RESPONSE_COMPLETION_TIMEOUT` 默认 300000ms 对生图太短
（实测生成约 360 秒，非流式收集器约 340 秒先超时），部署时以环境变量
`RESPONSE_COMPLETION_TIMEOUT=900000` 启动。

## 抓包方法（可复现）

`AI_PROXY_WIRE_DUMP=1` 启动时，interceptor 把解码后的原始流字节落盘到
`wire_samples/`：单条响应在 `is_done` 或超 32MB 时刷出，GenerateContent
长流在下一个请求 `reset_for_new_request` 时刷出上一份。注意该格式是累积
重发的：一条生图流总量约 34MB（图片 base64 在每个后续块里整份重发）。
验证完成后应关闭此开关并删除样本（样本含账号流量）。

## 未完成 / 待验

- **端到端实测未完成**：补丁写完当晚，账号撞上 AI Studio 配额（429，
  gemini-3.8-flash 先触发，worker 进入 Auth Rotation 暂停）。补丁的结构
  依据是真机抓包（同一条流的原始字节 + 现行正则成功解析出 26 个图片
  payload），但补丁后的一次完整生图返回尚未跑通——等配额恢复后用流式
  请求验一次：应答中应出现且仅出现一次
  `![generated image](data:image/jpeg;base64,/9j/4...`。
  （更正：当晚曾记录 kz5ut3y 文本请求「内容混入旧文本、耗时 250 秒」，
  后经正式完成记录与服务日志双向核对，该请求实际 28 秒完成、内容为
  干净的 REG_OK；异常系结果投递文本串扰所致，不成立，予以撤销。）
- `docs` 取舍：图片以 Markdown data URI 进 body，而非 OpenAI content
  parts 数组——前者对现有流式/非流式组装零改动，所有客户端可直接渲染
  或提取；若以后需要 parts 形式，再改 `api_utils` 的应答组装层。

## 2026-10-22 实测与完成补丁
- 新鲜 cookie（09:43 导入，25 个）单实例启动成功；文本回归 24s；经 magpie 网关 Argon 成功；ai-studio-full 已 refresh 并暴露全量 39 模型（「都走 2048」达成）。
- 生图非流式三连败（09:47 经网关、09:57 网关重试、10:04 直连）：分别流了 255/230/222 个数据项、600~900 秒仍无传输层结束（done 来自 _decode_chunked 的分块终止符，生图流不发）。网关对上游约 600s 上限，先于反代 900s 超时掐断并自动重试一次。
- 10:34 流式探针：提交 1 秒即 429（生图配额已被上午反复生成耗尽）→ 应用给 gemini-3.1-flash-image 记冷却到当日 14:34（config/cooldown_status.json）；轮换重试挂在 Waiting for data，服务一度 503 不自恢复，重启进程解决。
- 重启数据点：应用运行中会把实时 cookie 回存 active/auth.json（10:15，9576B，AUTO_SAVE_AUTH=false 也照存——该开关只管初始化路径）；用这份自存档重启，18s 起来且文本生成正常（RESTART_OK）。昨晚「回存即中毒」的结论需修正：至少单实例、无并发污染时自存档可用。
- 完成补丁（stream/interceptors.py）：_emitted_image_keys 非空后，连续 3 次 parse 无新增 body/reason/function 即合成 done=True；新增内容会清零计数，不误截图文混排的尾部文本。reset_for_new_request 同步清零 _img_tail_streak。多图连发场景可能只保留首图，已知取舍。
- 待验（已约 2026-10-22 14:40 定时任务）：冷却后经网关一发生图，应 <600s 返回且含恰好一张 data URI 图。（后续：14:40 任务因会话已死撤销，改晚间新会话验；见下节。）

## 2026-10-22 晚间：v1 补丁失效根因 + v2
- 18:00 用户重导两份 cookie（25 个合并）；新会话验证文本（EVE_OK）、经网关 Argon（EVE_ARGON_OK）均通。
- 18:05 经网关生图：流 247 项、600s 被网关掐断——**v1 补丁未触发**。根因：生图流是累积重发格式，每次 parse 都能从全量帧里重新提取出同一段文本，resp 的 body/reason 永远非空，v1 的「无新增内容」永不成立。是判定写错，非补丁未生效。
- 18:16 网关重试、18:22 直连各一发：提交后 2 秒即上游 **429**（生图配额再次耗尽；18:05 那发大概率是当天最后一发额度）。轮换重试还把页面搞乱（textarea 定位失败、模型切换失败），重启进程恢复（RESET_OK）。
- **v2 补丁**（同文件，判定改「增长比较」）：已出图后，比较相邻 parse 提取的 (body+reason) 长度；连续 3 次不增长 = 上游只在重发已完成状态，合成 done=True（日志打 [IMG] 行）。逻辑已离线单测（造文本帧/图片帧/重发帧/增长帧喂解析器：P6 触发 done、增长清零，均符合预期）。**实弹待验**：需等生图配额恢复后单发一发（直连、不用网关，避免 600s 掐断与自动重试翻倍消耗）。
- 配额观察（两日汇总）：生图桶很小且恢复慢；调试式连发必耗尽。后续验图纪律：一发定胜负，不连打。

## 2026-10-22 午后会话失效（定性）
- 13:50 起反代两次启动都卡在 [Navigation]。探针（同 auth + ignore_https_errors）实证：页面被重定向到 accounts.google.com 登录页。10:15 自存档与 09:43 原始导入两份都一样 → 会话已被 Google 服务端作废（最后一次实证生成成功是 10:43 PATCH_OK）。
- 排查副产品：出站代理确实做 TLS 中间人（签发方 Hatch Sandbox Egress CA，根证书在系统 CA 店 /usr/local/share/ca-certificates/hatch-egress-ca.crt，curl 因此正常）；裸 Camoufox 探针会撞 HSTS 证书墙（SEC_ERROR_UNKNOWN_ISSUER），但应用本体在 core.py 给 context 设了 ignore_https_errors=True，不受影响——探针必须带这个参数才有诊断价值。
- 教训修正：历次「卡在 Navigation」的统一解释大概率都是会话失效（跳登录页后初始化等不到 UI），不是网络也不是快照格式。恢复唯一路径：用户从 PC 重导 cookie。
