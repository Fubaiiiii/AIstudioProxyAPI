# 变更日志

本文件记录**本 fork 相对上游**的变化；上游项目自身的历史见 [上游仓库](https://github.com/CJackHwang/AIstudioProxyAPI)。来源、许可证与修改总说明见 `docs/FORK_NOTES.md`。

## 2026-10-22（本地补丁集，commit 59307af）

### 同步

- 上游基准由 `a0b0915` 更新至 `044c3db`（Merge PR #317），fork 的 `main` 随之快进。

### 新增

- 生图输出支持：响应流中的图片部件提取为 Markdown data URI 写入正文，累积重发自动去重（`stream/interceptors.py`）。
- 生图完成合成补丁 v2：上游生图流不发结束信号，本补丁以“提取文本长度连续 3 次不增长”判定完成（已离线测试；实弹验证待配额恢复）。
- `cookie_editor_to_storage_state.py`：Cookie-Editor JSON 合并转换为 `auth.json` 的工具脚本。
- `docs/FORK_NOTES.md`（来源与修改说明）、`docs/image-output-notes.md`（生图抓包与实现笔记）。

### 变更

- `/v1/models` 输出条目补充 `capabilities` 等字段，兼容 magpie 网关的模型识别（`api_utils/routers/models.py`）。
- 部署适配：虚拟显示（Xvfb）下非 headless 启动、视口 1280×800、临时聊天模式关闭、模型名读取与切换校验放宽、提交路径改 `click()` + `fill()` 并更新 Run 按钮定位器。
- `RESPONSE_COMPLETION_TIMEOUT` 放宽至 900000ms。
- `.gitignore` 排除本地运行产物（凭证、截图、抓包、调试脚本），防止误提交。
