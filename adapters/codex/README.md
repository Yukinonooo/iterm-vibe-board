# Codex CLI 适配

通过 Codex 的 `SessionStart` / `SessionEnd` hooks，将当前 iTerm2 窗格与
Codex 会话、工作目录绑定。任务仍由 agent 使用现有 `vibeboard` 命令维护，
不抓取聊天记录，也不自动同步 Codex 内部的计划列表。

## 安装

在仓库根目录运行：

```sh
./install.sh --agent codex
```

安装共享 CLI 和 iTerm2 面板，同时：

- 将本目录的 skill 链接到 `${CODEX_HOME:-~/.codex}/skills/vibeboard`。
- 将两个命令 hook 合并到 `${CODEX_HOME:-~/.codex}/hooks.json`。
- 保留已有 hooks 和其他配置；文件不是有效 JSON 时拒绝覆盖。
- 不修改 Claude Code 配置；同时使用两种 agent 时运行 `./install.sh --agent all`。

随后在 **iTerm2 的普通窗格** 中启动：

```sh
codex --no-daemon
```

在 CLI 中输入 `/hooks`，查看并信任两条标为 `Vibe Board: bind Codex session`
的 hook，然后重新打开会话。安装脚本不会代替你建立 hook 信任，也不会禁用
Codex 的权限检查。若已有启动包装脚本传入 `--no-daemon`，直接用该脚本即可。

`--no-daemon` 用于让会话使用自己窗格的环境。共享后台进程可能继承另一个
窗格的 `TERM_SESSION_ID`，不能据此保证绑定准确。此适配针对本地 CLI；不支持
远程 app-server、云端会话，也不保证后台脱离终端的任务仍属于原窗格。

iTerm2 需要 3.5 以上版本，开启 Python API，并安装 iTerm2 Python runtime。
面板在 **View → Toolbelt → Vibe Board** 中启用。Codex 需要支持命令型
`SessionStart` / `SessionEnd` hooks 和 `/hooks` 的版本；旧版本应先升级。

## 验证

新会话中让 Codex 使用 `$vibeboard` 创建一个测试任务，再更新为完成；确认：

1. `vibeboard list --mine --json` 中，`driver` 是当前会话 ID，项目为当前工作目录。
2. 切换 iTerm2 窗格时，面板的 Project / Session 页随之切换。
3. 退出 Codex 后，对应会话显示结束；任务保留，不会自动标成完成。

结束或恢复会话由 Codex 的生命周期决定。强制杀进程不会可靠触发 `SessionEnd`；
再次启动或恢复会话会刷新该窗格的绑定。上下文压缩重复触发 `SessionStart`
时复用同一会话，不应新建任务。

tmux 中不会登记窗格，避免把多会话误绑定到启动 tmux 的那个窗格。非 iTerm2
环境也不登记。此时可用 `--project PATH --driver none` 手动维护看板，不能获得
按会话过滤和跳转的完整体验。

## 卸载和更新

```sh
git pull
./install.sh --agent codex

# 卸载 Codex 适配；保留已有任务数据
./install.sh --agent codex --uninstall
```

如果还装着 Claude Code 适配，共享 CLI 和面板会保留。自定义 `CODEX_HOME`
或 `VIBEBOARD_HOME` 时，安装、运行和卸载应使用相同设置。仓库是运行时入口，
安装后不要删除或移动；换路径后重新安装并在 `/hooks` 里重新确认定义。

## 实现与验证范围

- `hook.py` 只读取官方 hook 字段 `session_id`、`cwd`、`hook_event_name`，
  调用已有的 `pane start/end`，不套用 Claude 的会话文件布局。
- `install.py` 原子更新 JSON，仅移除属于本适配器的 hook handler，保留同组其他 handler。
- `tests/test_codex_adapter.py` 通过独立进程验证会话身份、任务归属、恢复、
  结束、嵌套会话、非 iTerm2 环境和安装配置保护。

官方接口说明：[Codex Hooks](https://learn.chatgpt.com/docs/hooks)。

2026-10-22 已使用 macOS 上的 `codex-cli 0.163.0-alpha.10.2` 完成真实 CLI
生命周期验证：启动后登记窗格，正常退出后写入结束时间。验证使用隔离的配置和
数据目录，以及本地固定 SSE 响应，不消耗模型 API，也不访问个人会话。
可复现检查（默认测试会跳过此项）：

```sh
VIBEBOARD_TEST_CODEX=/absolute/path/to/codex pytest -q tests/test_codex_runtime.py
```

这个测试仅在隔离调用中临时跳过测试 hooks 的信任校验；正常安装始终要求
用户通过 `/hooks` 审核。iTerm2 面板的实际点击和焦点切换仍需启用其 Python API
与 runtime 后验证，不把 CLI 生命周期测试当作 UI 测试。
