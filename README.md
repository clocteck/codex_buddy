# Codex Buddy

Codex Buddy 是一个用于 `clocteck-holocubic` 的 Codex 桌面伙伴应用，运行在 320x240 设备屏幕上。设备端应用会连接电脑端 bridge 服务，显示 Codex 会话状态、额度信息、运行状态和授权请求，并可通过设备按键直接批准或拒绝一次授权。

## 目录结构

```text
package/
  app.info                 应用信息，入口为 main.lua
  main.lua                 设备端主程序
  config.example.json      配置示例
  main.png                 应用图标
  assets/bufo/             默认角色 GIF 资源
src/
  bridge_server.py         电脑端 Codex bridge 服务
  assets/                  预留素材目录
```

## 设备端部署

以下步骤面向 `clocteck-holocubic` 设备。

1. 让设备和电脑连接到同一个局域网。
2. 在设备上查看设备 IP 地址。
3. 在电脑浏览器打开：

```text
http://设备ip/devtools
```

例如设备 IP 是 `192.168.0.23`，则打开：

```text
http://192.168.0.23/devtools
```

4. 在 DevTools 的文件管理或应用管理页面中，创建或进入下面的目录：

```text
/sd/apps/codex_buddy
```

5. 将 `package/` 目录下的文件上传到该目录，保持目录结构不变：

```text
/sd/apps/codex_buddy/app.info
/sd/apps/codex_buddy/main.lua
/sd/apps/codex_buddy/main.png
/sd/apps/codex_buddy/config.json
/sd/apps/codex_buddy/assets/bufo/*.gif
```

6. 将 `package/config.example.json` 复制为 `config.json`，并把 `bridge_url` 改成电脑端 bridge 服务地址：

```json
{
  "bridge_url": "http://电脑ip:8788",
  "character": "bufo",
  "use_gif": true
}
```

7. 在 DevTools 中刷新应用列表或重载设备应用，然后启动 `Codex Buddy`。

> 注意：设备端代码默认安装目录是 `/sd/apps/codex_buddy`。如果目录名变了，需要同步修改 `package/main.lua` 中的 `APP_DIR`。

## 电脑端部署

本仓库同时包含设备端应用包和电脑端 Python bridge 服务。电脑端服务负责读取 Codex 本地 session 日志，并把 Codex 运行状态转换成设备端可轮询的 `/state` 数据。

电脑端部署要点：

1. 获取电脑局域网 IP，例如 `192.168.0.80`。
2. 启动 bridge 服务，并监听所有网卡或电脑局域网 IP，推荐端口为 `8788`。
3. 确认电脑防火墙允许设备访问该端口。
4. 在设备端 `config.json` 中配置：

```json
{
  "bridge_url": "http://192.168.0.80:8788"
}
```

5. 在电脑浏览器验证 bridge 服务是否可用：

```text
http://电脑ip:8788/state
```

启动本仓库提供的 Python bridge 服务：

```powershell
python src/bridge_server.py --host 0.0.0.0 --port 8788
```

默认情况下，服务会读取 `%USERPROFILE%\.codex\sessions\**\*.jsonl` 中最新的 Codex session 文件；也可以用 `--codex-home` 指定 Codex 数据目录：

```powershell
python src/bridge_server.py --host 0.0.0.0 --port 8788 --codex-home C:\Users\你的用户名\.codex
```

启动后访问：

```text
http://电脑ip:8788/state
```

健康检查：

```text
http://电脑ip:8788/health
```

设备端主程序会调用以下接口：

### `GET /state`

返回当前 Codex 状态。设备端会每隔约 2.5 秒轮询一次。

常用字段示例：

```json
{
  "seq": 1,
  "total": 2,
  "running": 1,
  "waiting": 0,
  "tokens_today": 12000,
  "cost_today": 0.25,
  "cost_month": 3.5,
  "quota_5h_pct": 80,
  "quota_7d_pct": 65,
  "entries": ["Codex is working", "Waiting for next update"],
  "pet": {
    "state": "busy"
  }
}
```

当需要用户授权时，可以返回 `prompt`：

```json
{
  "seq": 2,
  "waiting": 1,
  "prompt": {
    "id": "permission-001",
    "tool": "exec_command",
    "hint": "Run local command"
  }
}
```

### `POST /permission`

设备端左键批准，右键拒绝。请求体格式：

```json
{
  "id": "permission-001",
  "decision": "once"
}
```

拒绝时：

```json
{
  "id": "permission-001",
  "decision": "deny"
}
```

bridge 服务返回 `200` 或 `202` 时，设备端会认为提交成功并重新拉取 `/state`。

### 电脑端代码实现流程

电脑端入口是 `src/bridge_server.py`，核心流程如下：

1. 启动 HTTP 服务，监听 `0.0.0.0:8788` 或电脑局域网 IP 的 `8788` 端口。
2. `CodexSessionReader` 定位 Codex 数据目录，默认使用 `%CODEX_HOME%` 或 `%USERPROFILE%\.codex`。
3. 在 `sessions` 目录下查找最新的 `*.jsonl` session 文件，并只读取末尾一段日志，避免每次轮询读取过多内容。
4. 解析 Codex 事件，包括 `session_meta`、`turn_context`、`task_started`、`task_complete`、`turn_aborted`、`error`、`token_count.rate_limits` 和工具调用事件。
5. 根据事件计算设备端状态：运行中为 `busy`，等待授权为 `attention`，完成为 `celebrate`，错误或中断为 `dizzy`，空闲为 `idle`。
6. 从 `token_count.rate_limits` 计算剩余额度：`quota_5h_pct` 和 `quota_7d_pct`。
7. 实现 `GET /state`，把会话数量、运行状态、等待状态、token、额度、消息列表、授权提示和角色状态返回给设备端。
8. 实现 `POST /permission`，接收设备端提交的 `once`、`approve` 或 `deny`，并记录到 `last_permission`。
9. 可选使用 `--state-file state.json` 合并手工状态，用于调试或临时覆盖 `/state` 字段。
10. 如果没有找到 Codex session，服务仍会返回稳定 JSON，设备端会显示无 Codex 会话或离线/睡眠状态。

注意：当前 bridge 会记录设备端授权选择，但不会直接替 VSCode Codex 执行批准动作，因为 VSCode Codex 没有向这个 bridge 暴露外部授权 API。

## 设备按键

- 左键：切换主屏幕；有授权请求时批准一次。
- 右键：滚动消息或切换子页面；有授权请求时拒绝。

主屏幕包括：

- `Codex`：会话消息、联网状态、额度摘要。
- `Pet`：角色状态、token、额度和说明。
- `Info`：bridge 地址、最近更新时间、费用和会话统计。

## 代码实现流程

设备端入口是 `package/main.lua`，整体流程如下：

1. 如果旧实例还在运行，先调用 `_G.CODEX_BUDDY_APP.stop("reload")` 停止计时器和按键绑定，避免热重载后重复轮询。
2. 初始化应用常量、颜色、UI 状态和默认配置。
3. 调用 `load_config()` 从 `/sd/apps/codex_buddy/config.json` 读取 `bridge_url`、角色目录和 GIF 开关。
4. 调用 `build_ui()` 构建 LVGL 界面，包括顶部状态栏、角色区、消息区、授权区和分页信息区。
5. 调用 `bind_keys()` 绑定左右按键：
   - 左键在普通状态切换屏幕，在授权状态提交 `once`。
   - 右键在普通状态滚动或翻页，在授权状态提交 `deny`。
6. 调用 `start_timers()` 启动两个定时器：
   - `poll` 定时器每 `POLL_MS` 请求一次 `GET /state`。
   - `anim` 定时器每 `ANIM_MS` 更新角色动画和离线状态。
7. `fetch_state()` 请求 bridge，成功后解析 JSON 并交给 `handle_snapshot()` 更新本地状态。
8. `choose_pet_state()` 根据在线状态、授权请求、运行任务和 bridge 返回的 `pet.state` 选择角色状态。
9. `update_ui()` 根据当前状态刷新顶部额度、消息、分页内容、授权提示和角色动画。
10. `post_permission()` 将按键授权结果发送到 `POST /permission`，并在提交后立即更新界面反馈。

角色状态和资源映射：

```text
sleep      assets/bufo/sleep.gif
idle       assets/bufo/idle_0.gif
busy       assets/bufo/busy.gif
attention  assets/bufo/attention.gif
celebrate  assets/bufo/celebrate.gif
dizzy      assets/bufo/dizzy.gif
heart      assets/bufo/heart.gif
```

如果设备固件不支持 GIF，代码会回退到 canvas 绘制的简化角色。

## 开源协议

本项目采用 GNU General Public License v3.0 only 开源协议，详见 [LICENSE](LICENSE)。

SPDX-License-Identifier: GPL-3.0-only
