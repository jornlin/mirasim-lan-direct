# 更新日志

[English](CHANGELOG.md) | 简体中文

## 0.6.3 — 2026-11-22

- 新增 `CHANGELOG.zh-CN.md`，完整的简体中文更新日志，并与本文件互相链接。
- GitHub Release 正文改为中英双语（English + 简体中文），约定写入
  `CONTRIBUTING.md`。
- 自 0.6.2 起无运行时改动。

## 0.6.2 — 2026-11-22

- 周期性 pair 刷新不再重置 target 的 `mode`、`collab`、`grant`、`member`、
  `label` 或 `installId`。此前 `_refresh_pair` 会整体替换条目，导致
  hybrid/direct-collab 目标每隔几小时被悄悄降级为纯 `direct`，窗口回退到
  本地 messenger 布局（“这台电脑还不是协作空间”）。
- macOS 上的 `is_running` 现在只检查 GUI 主进程。Mirasim 还会用同一个可执行
  文件运行 `server.cjs`、`cli.cjs` 和 `screen-lane.cjs`；旧的 `pgrep -f`
  检查会把这些辅助进程当成 App 仍在运行，导致 `mld patch --restart` 报
  “Mirasim did not quit”。

## 0.6.1 — 2026-11-21

- `mld check` 现在会通过配置的 SSH target 检查可选的 host g2/role 验证器，
  并对 member target 打印 `host auth: ...`。
- `mld member` 在 host 验证器缺失时给出警告。

## 0.6.0 — 2026-11-21

- `mld init --member` 只根据 node/host/e2e 创建 member target，不读取也不
  嵌入 host 的共享 token。
- `mld invite <node>` 打印公开的 node/host/e2e、完整的 member 命令以及 host
  g2 验证器的命令，让 owner 可以在不暴露 token 的前提下把一份自包含的配置
  步骤交给 member。

## 0.5.0 — 2026-11-21

- Member 模式改为 hybrid：保留云端 `gatewayUrl` + g2 会话；chat、presence、
  任务分发和成员管理走 gateway（agent turn 所需的 requester 凭据由 gateway
  提供），而会话、终端、文件和快照通过 g2 grant 走 LAN。不嵌入共享 token。
- `mld member <node>` 不再需要 grant 文件；客户端自动使用云端 gateway 会话。
  仍可用显式的 `--grant/--grant-file` 做诊断。
- 新增 `scripts/host-g2-auth.py`：可选的 host 验证器，接受 g2 gateway 会话作为
  直连账号 grant（`kind=gateway`、`aud` = host cloud node id、`sub`、`exp`）。
  首次注册会存成普通的 `via=account` 设备；后续重连使用设备密钥
  （`via=known`）。包含备份/恢复和语法检查。
- Host 验证器同时修正 attached-host 的角色回退：非 owner 的账号设备默认变为
  `member` 而不是 `admin`；owner 和 `mirachannelMachineAdmins` 仍保持 admin。
- 记录 host 补丁、角色模型、更新生命周期和撤销方法。

## 0.4.0 — 2026-11-21

- Member 模式原型：自动使用云端 gateway 会话作为直连 grant，加入
  `managed`/`remoteByChoice` 标志，并对显式 grant 做 JWT 校验。

## 0.3.0 — 2026-11-20

- Member-grant 模式：`mld member <node> --grant-file <jwt>` 使用平台签发的
  账号 grant（`sub` = member 账号，`aud` = host node）替代共享 token。Host 的
  `Flo` 账号路径会记录 `via=account`，因此 `wn`/`identify` 返回 member 及其
  角色；target 保留 `host`/`e2e`/`grant`，不带 `gatewayUrl`/`token`。
- Renderer 仍会收到 `clientHello remoteByChoice`、`managed:true` 和协作布局。
  `mld check` 显示 grant 的 subject 和过期时间。
- 要求 member 的账号已在 host 的 `mirachannelSharedAccounts` 中（先加入空间）。
  grant 本身必须通过 Mirasim 的账号/设备配对或云端流程获取；本工具不会签发。
  在拿到 grant 之前，member 仍走官方 gateway。

## 0.2.2 — 2026-11-20

- 不依赖 gateway 的直连协作：启用 `collab` 的 `direct` target 现在会用
  `clientHello {remoteByChoice:true}`、`managed:true` 和原始 `post` 捕获来包装
  LAN 客户端。已在 0.0.828 上验证：chat、presence 和协作布局可以通过单条 LAN
  链路工作。
- 记录身份边界：legacy LAN 连接是 `role=admin`，没有 gateway viewer，因此 host
  的 chat 身份会回退到它自己已登录的 owner 账号。所以 direct/hybrid 仅适用于
  owner 自己的设备；其他成员必须使用官方 gateway/云客户端，且不得分发打过补丁
  的 App/共享 token。

## 0.2.1 — 2026-11-20

- 文档：推荐用 hybrid 组合 LAN 数据 + 协作；记录 `clientHello remoteByChoice` /
  `managed` 布局标志以及 gateway 与 LAN 的精确帧分工。
- 移除一条冗余的 collab 路由（`chat*` 已覆盖）；为 `clientHello`、`managed` 和
  `setWorkspaceMembers` 路由增加回归测试。
- 在退出前探测 `app.asar` 是否可写；即使备份/安装失败也会重新启动 Mirasim。
  macOS App Management 拒绝写入时不会再让 App 保持关闭。

## 0.2.0 — 2026-11-20

Hybrid 现在可用于已绑定账号的云空间。

- 把整套协作协议路由到 gateway：`presenceUpdate`、`tasksenseFocus`、
  turn/attention watch、session access、member usage、`chat*`、`peer*`、
  消息会话列表、member workspace 以及 cloud/controlled-space 管理。会话、终端、
  文件、快照和 prompt 数据仍走 LAN 链路。
- 在客户端 `ready` 之前（以及每次重连时）在直连链路上发送
  `clientHello {remoteByChoice: true}`。否则 host 会把同机 legacy 连接当成
  local（`clientLocal: true`），renderer 就会画本地 messenger 布局。
- 在复合客户端的 gateway 半边暴露 `managed: true`；只有客户端为 managed（或
  client-local）时 renderer 才会选择云/协作布局。
- 暴露 gateway 的 `setHello`；把 `ready`、`clientVisibility`、stream cadence
  和 settings push 广播到两条链路，使 gateway 连接被接纳，并在重连后重放
  hello。
- 在 renderer 包装 `post` 之前捕获直连的 `post`，并支持 `post` 覆盖，避免复合
  客户端自调用递归。
- 移除临时诊断。补丁修订号 12。

## 0.1.15 — 2026-11-20

- Hybrid：在复合客户端上暴露 `managed: true`。除非
  `client.managed === true`，renderer 会选择本地/messenger 布局（并显示
  “这台电脑还不是协作空间”卡片）；官方 gateway 客户端带这个标志，直连 `Ss`
  客户端没有。补丁修订号 11。

## 0.1.14 — 2026-11-20

- Hybrid：在客户端 `ready` 之前，在直连链路上发送
  `clientHello {remoteByChoice: true}`。否则 host 会把同机/loopback 风格的
  legacy 客户端视为 local（`clientLocal: true`），即使空间已绑定、协作已生效，
  窗口仍会画本地 messenger 布局和“这台电脑还不是协作空间”卡片。直连 state
  重新成为权威；gateway state 只用于 presence/chat 帧。补丁修订号 10。

## 0.1.13 — 2026-11-20

- Hybrid：让 gateway 的 state 帧成为窗口 UI 的权威来源。直连 legacy state 会
  报告 `chatPersonal: true`（于是 UI 显示“这台电脑还不是协作空间”），而
  gateway state 携带已绑定/共享的 chat 标志。转发完整的 gateway state，抑制
  后续直连 state 帧，并向新订阅者重放最后的 gateway state。补丁修订号 9。

## 0.1.12 — 2026-11-20

- Hybrid：把协作协议（chat/channels/peers/messaging 成员列表）路由到 gateway
  链路，而不是直连链路。直连 host 不为 legacy 连接提供 collab chat/member
  API，导致 presence 虽然在线但成员栏为空。会话/终端/文件数据仍走 LAN 链路。
  补丁修订号 8。

## 0.1.11 — 2026-11-20

- 诊断：记录 presence 名册大小、viewer 和帧订阅者数量。

## 0.1.10 — 2026-11-20

- Hybrid：把 gateway 的 `state.collab` 镜像到直连 state（renderer 的协作 UI
  由 `hostState.collab` 控制，直连 state 可能不会设置它），暴露 gateway 的
  `setHello`，并把客户端生命周期帧（`ready`、`clientVisibility`、stream
  cadence、settings push）广播到两条链路，使 gateway 连接被接纳以启用
  presence。临时 `MLD` 控制台诊断。补丁修订号 6。

## 0.1.9 — 2026-11-20

- 修复 hybrid 复合客户端的真实递归：renderer 通过赋值包装客户端的 `post`，
  而 proxy 的 `post` 又转发到 target 已被包装的 `post`，导致无限自调用。捕获
  原始直连 `post`，支持赋值的 `post` 覆盖，并加入 `set` trap 让包装链终止。
  补丁修订号 5。

## 0.1.8 — 2026-11-20

- 加固 hybrid 复合客户端以应对可重入回调：遍历帧/连接订阅者的快照，并丢弃同步
  可重入帧。补丁修订号 4。

## 0.1.7 — 2026-11-20

- 修复 hybrid 复合客户端初始 `onConnection(false)` 回调递归（renderer 报
  `Maximum call stack size exceeded`）；连接回调现在异步投递，且只针对已连接
  的链路。稳定的方法标识避免重复订阅抖动。补丁修订号 3。

## 0.1.6 — 2026-11-20

- `mld mode <target> <mode>` 现在一条命令完成切换（patch + 重启）；
  `--stage` 只写配置。`mld check` 打印每个 target 的模式。

## 0.1.5 — 2026-11-20

- 实验性 `hybrid` 模式：复合传输保留 gateway 链路用于 presence/collab/
  turn-activity 帧，而 session 和数据帧走直连 LAN 链路。使用
  `mld mode <node> hybrid`；如果 gateway 半边无法认证，回退到 `gateway`。

## 0.1.4 — 2026-11-20

- 可选为 direct target 启用 collab presence：`mld collab <node|label> on` 在
  构建 target 时强制打开 renderer 的 presence gate 并设置
  `globalThis.__mldCollab`。Host 的 presence 服务仍受空间的云端绑定状态控制；
  如果 UI 没有激活，请使用 gateway 模式。

## 0.1.3 — 2026-11-20

- 按空间设置 `mode`：`direct`（LAN，无 gateway）或 `gateway`（relay，保留云端
  协作身份）。使用 `mld mode <node|label> direct|gateway`；再用
  `mld patch --force --restart` 重新应用。

## 0.1.2 — 2026-11-20

- 把 `installId` 传入 mirachannel transport 选项。target 和最终 target 构建器
  已经携带它，但 transport 分发器（`xs`）把它丢掉了，所以 v2 HELLO 从未发送
  `client.installId`，host 仍会为每次连接存一个新的 legacy 设备。
- 在 marker 哈希中加入补丁修订号，让 agent 能发现需要更新的重写。

## 0.1.1 — 2026-11-20

- 向直连 target 注入稳定的 `installId`（并让它通过最终 target 构建器）。Host
  现在会撤销上一条 legacy 设备记录，而不是每次连接都新增一条。
- 在 SSH init/refresh 时从 `~/.mirasim/run/local-*.token` 发现 host 的服务器
  端口；host 可能在新端口重启（桌面 App 默认 4970）。
- 当配置的 origin 都不可达时刷新 pair 数据，而不只依赖 6 小时定时器。
- 通过重写后的函数签名识别更早的无 marker 补丁，这样即使 host/端口变化也会从
  原始副本重建，而不是失败。
- `mld patch` 清除 `DISABLED` 标志；对变更文件列表去重。

## 0.1.0 — 2026-11-20

- 首次公开发布。
- 无第三方依赖的 asar 读写器，支持偏移量和 SHA-256 完整性重建。
- 基于代码形状重写 cloud-target 构建器；支持多个 target。
- 为配置的 LAN origin 放宽 CSP。
- 使用 App 自带的 Electron 二进制校验打补丁后的 JavaScript。
- `mld init|patch|check|autopatch|restore|agent|doctor`。
- 生成 macOS LaunchAgent 和 Windows 计划任务。
- 按 App 版本跟踪原始源、版本化备份、过期锁恢复、host 宕机保护和 token
  指纹健康检查。
