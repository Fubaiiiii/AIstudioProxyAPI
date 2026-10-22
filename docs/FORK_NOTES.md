# 本仓库说明：来源与本地修改

## 来源

本仓库是开源项目 **AIstudioProxyAPI** 的个人 fork：

- 上游项目：[CJackHwang/AIstudioProxyAPI](https://github.com/CJackHwang/AIstudioProxyAPI)
- 上游作者：CJackHwang 及该项目贡献者（版权归原作者所有）
- 许可证：**GNU Affero General Public License v3.0（AGPL-3.0）**，全文见仓库根目录 `LICENSE`，未作任何改动
- 本 fork：[Fubaiiiii/AIstudioProxyAPI](https://github.com/Fubaiiiii/AIstudioProxyAPI)，供个人部署使用
- 代码基准：上游 `main` 分支 commit `044c3db`（Merge PR #317）；本 fork 的 `main` 由上游旧版 `a0b0915` 快进至该基准后叠加下述本地修改

依 AGPL-3.0 第 5 条，本文件即为修改说明：所有本地修改逐项列在下一节，并已通过本仓库源码公开（同时满足第 13 条网络服务场景的源码提供要求）。除特别注明外，修改均为部署适配与缺陷修复，不改变上游的整体架构与接口定义。

## 本地修改清单（相对上游 044c3db）

### 生图输出支持（核心新增）

- `stream/interceptors.py`
  - 新增图片提取：响应流中 `payload[2]` 为 `[mime, base64]` 的部件，提取为 Markdown data URI 追加进正文；同一图片在累积重发中只发出一次（按数据内容去重）。结构实证与细节见 `docs/image-output-notes.md`。
  - 新增**完成合成补丁 v2**：上游生图流不发送传输层结束信号，非流式收集方与下游网关只能超时。本补丁在图片已发出后，比较相邻解析轮次提取的文本长度，连续 3 次不再增长即判定上游仅在重发已完成状态，合成 `done=True`。已通过离线单元测试；真实链路端到端验证待生图配额恢复后单发完成（截至 2026-10-22）。
  - 新增 wire 落盘调试钩子：环境变量 `AI_PROXY_WIRE_DUMP=1` 时将原始响应流存入 `wire_samples/`，默认关闭。
- `cookie_editor_to_storage_state.py`（新增）：把 Cookie-Editor 导出的 JSON 合并转换为本项目 `auth.json`（Playwright storage state）格式的实用脚本。

### 本地部署适配

- `launch_camoufox.py`：`headless == "virtual"` 时改为非 headless 并配合虚拟显示（Xvfb）；注入窗口尺寸 1280×800。
- `browser_utils/initialization/core.py`：模型名读取改为等待节点 attached 后读 `textContent`，失败仅警告不中断初始化；视口统一 1280×800；临时聊天模式在函数级硬关。
- `api_utils/app.py`：启动时的临时聊天模式调用已注释（与上一项配套）。
- `browser_utils/models/switcher.py`：模型切换校验放宽——节点 attached/读 `textContent` 判定；`localStorage` 已是目标模型时直接放行；切换后不再重开临时模式。
- `browser_utils/page_controller.py`、`browser_utils/page_controller_modules/input.py`：提交路径改用 textarea 的 `click()` + `fill()`（弃用 JS 直接赋值）；Run 按钮定位器更新为 `ms-run-button button, button:has-text("Run")`。

### 网关兼容

- `api_utils/routers/models.py`：`/v1/models` 输出条目补充 `supported_generation_methods`、`capabilities.chat_model` 与 token 上限字段（非聊天模型不标 `chat_model`），使 magpie 的 Gemini 插件能正确识别本地模型列表。

### 运行配置

- `supervisord.conf`、`RESPONSE_COMPLETION_TIMEOUT`：响应完成超时放宽到 900000ms，适配生图长流。
- 依赖版本锁定（部署环境约定）：`camoufox 0.4.11` + `playwright 1.56.0`（playwright 1.62 与当前 camoufox 不兼容，勿升级）。

## 未纳入仓库的内容

以下为本地运行产物，含敏感信息或仅供调试，已加入 `.gitignore`，不属于本 fork 发布内容：`auth_profiles/` 下的实际凭证（仓库仅保留 `.gitkeep`）、日志、`login_shots/`、`wire_samples/`、`probe*.py` 等调试脚本。**任何人部署本项目都应使用自己的 Google 账号凭证，切勿提交真实 cookie。**

## 已知限制

- 单账号会话存在被 Google 服务端作废的可能，届时需重新导入 cookie；同一份 cookie 只可由单个浏览器实例使用。
- 生图模型有独立且较小的配额桶，频繁重试会迅速耗尽。
- 本地补丁未向上游提交 PR；上游升级时需按本清单逐项核对合并。
