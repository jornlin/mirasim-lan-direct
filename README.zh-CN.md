# mirasim-lan-direct

[English](README.md) | **简体中文**

让选定的 **Mirasim 云空间**绕过 `relay.mirasim.ai`，直接通过**局域网**连接到它的宿主电脑。

本项目与 Mirasim / Mirofish 官方无关，只应使用在你自己的机器和空间上。详见[免责声明](#免责声明)。

---

## 为什么需要它

Mirasim 桌面版打开云空间窗口时，固定先连
`wss://relay.mirasim.ai/v2/gateway/ws`。出厂代码里有三处让局域网直连无法生效：

1. 渲染层的云目标构造函数会带上 `gatewayUrl`，而传输层命中 gateway 后根本不会再看直连候选；
2. 云目录条目里的 `e2e` 是空串，手工构造的 LAN 目标无法完成加密握手；
3. 渲染层 CSP 的 `connect-src` 不允许 `ws://<局域网 IP>:*`，直连会被浏览器拦截并静默回落中继。
4. 用共享 token 的 v2 直连会让宿主**每次连接都新增一条 legacy 设备记录**；补丁注入稳定的
   `installId`，宿主会顶掉上一条，不再无限增加。

本工具改写目标构造函数（注入宿主的地址、共享 token 与 E2E 公钥；直连目标移除
`gatewayUrl` / `grant`，混合目标保留它们），同时为配置的局域网来源放宽 CSP。目标函数按**代码形状**
查找，不依赖带 hash 的资源文件名。

## 环境要求

- Python 3.9+（只用标准库，无第三方依赖）
- 已安装 Mirasim 桌面版
- 以下凭证来源之一：
  - 能 SSH 到宿主（pair 接口只监听 loopback），或
  - 宿主导出的 pair JSON 文件，或
  - 宿主的 token、E2E 公钥和云 node id

## 快速开始（macOS）

```sh
git clone https://github.com/jornlin/mirasim-lan-direct.git
cd mirasim-lan-direct

# 通过 SSH 读取宿主的 pair 数据并写入配置
PYTHONPATH=src python3 -m mld init --ssh my-host --app /Applications/Mirasim.app

# 生成并安装补丁（会退出并重开 Mirasim）
PYTHONPATH=src python3 -m mld patch --restart

# 验证：地址可达性 + 已安装的补丁标记
PYTHONPATH=src python3 -m mld check

# 可选：App 升级后自动重打
PYTHONPATH=src python3 -m mld agent install
```

也可以安装成命令：

```sh
python3 -m pip install -e .
mld init --ssh my-host
```

> 如果 App 已被旧版工具打过补丁，而你没有未打补丁的副本，请在 `init` 时加
> `--original /path/to/app.asar.orig`，它会保留该副本供以后重建。

## 快速开始（Windows）

```powershell
git clone https://github.com/jornlin/mirasim-lan-direct.git
cd mirasim-lan-direct

$env:PYTHONPATH = "src"
py -3 -m mld init --ssh my-host
py -3 -m mld patch --restart
py -3 -m mld check
py -3 -m mld agent install      # 计划任务：登录时 + 每 10 分钟
```

如果 App 装在 `Program Files`，请用管理员 PowerShell 注册计划任务。Windows 上不需要
重新签名：Authenticode 签的是 exe，改 `app.asar` 不影响。

## 配置：IP、端口、多主机

所有地址和凭证都放在仓库之外的 `config.json`：

- macOS：`~/Library/Application Support/mirasim-lan-direct/config.json`
- Windows：`%APPDATA%\mirasim-lan-direct\config.json`
- Linux：`$XDG_CONFIG_HOME/mirasim-lan-direct/config.json`
- 覆盖路径：`MLD_CONFIG_DIR=/path mld ...`

提供目标的方式：

```sh
mld init --ssh my-host --port 4939
mld init --pair pair.json
mld init --node pc-... --host 192.168.1.50:4939 --host 10.0.0.5:4939 \
         --token ... --e2e ...
```

- `--host` 可重复；工具会逐个测试并选第一个可达地址，其余保留作回退。
- `--port`（默认 `0`）会从宿主的 `~/.mirasim/run/local-*.token` 自动发现端口；桌面版可能
  重启到 4970，手动 `serve` 可能是别的端口，SSH 初始化和刷新会跟着走。
- 端口写在 host 字符串里（`host:port`）；SSH 拉取用 `--port`。
- 再执行一次 `mld init --node ...` 可以追加另一个空间，各目标独立打补丁。
- `--app` 用于非默认安装路径（macOS 的 `.app`，或 Windows 的安装根目录）。
- 配置在 POSIX 上以 `0600` 写入，含 bearer token，**不要提交**；`.gitignore` 已排除。
- 只有配置了 SSH 目标时才会自动刷新 pair（token/E2E/地址）；否则宿主变化后需重新
  `mld init`。

## 协作：direct、hybrid、member、gateway

- **direct**：只走局域网，没有云身份/在线状态/聊天；不需要协作时使用。
- **hybrid**：会话、终端、文件走局域网，协作能力走 gateway。适合 owner 自己的设备。
- **member**：空间里的其他账号；聊天/任务/presence 走 gateway，数据走局域网并用成员的
  g2 grant。需要可选的宿主校验。
- **gateway**：全部走中继。hybrid/member 的网关半无法认证，或只希望一条链路时使用。

```sh
mld mode <node-id-或-label> hybrid       # owner 设备：局域网数据 + 协作
mld mode <node-id-或-label> direct       # 仅局域网
mld mode <node-id-或-label> gateway      # 仅中继
mld member <node-id-或-label>            # 其他账号：局域网数据 + 网关任务
```

### 混合模式细节

混合模式用 **gateway 链路**承载全部协作能力：在线状态、成员/频道/聊天协议、轮次与
关注、会话访问、成员用量、云空间与成员管理；会话、终端、文件、快照和提示词等数据
仍走**局域网直连**。

渲染层有两个必要细节，补丁已经处理：

- 直连链路在 `ready` 之前发送 `clientHello { remoteByChoice: true }`，否则宿主会把
  局域网客户端当成同机本地客户端；
- 复合客户端从网关半暴露 `managed: true`，界面才会选择云/协作布局，而不是本机布局。

空间仍需保持云附加（cloud attach），且 gateway 半必须能认证（目标保留云 grant）。
gateway 半认证失败时，切回 `gateway` 模式。

### 传统 direct/hybrid：只适合 owner 自己的设备

这两种模式会把宿主的共享 token 写进补丁，用局域网 legacy 连接，角色是 `role=admin`。
局域网连接没有 gateway viewer 身份，宿主的聊天身份会回落到**宿主自己登录的 owner
账号**。只应在**与宿主同一账号**的设备上使用，且不要分发共享 token。

### 成员用自己的账号（member 模式）

`member` 模式给共享空间里的其他成员使用，不使用共享 token：

```sh
mld member <node-id-或-label>        # 不需要 grant 文件
mld check                            # member (cloud grant)
```

owner 给另一台设备准备：

```sh
mld invite <node-id-或-label>        # 打印 node/host/e2e 和成员命令
```

成员设备上：

```sh
mld init --member --node <id> --host <ip:port> --e2e <host key>
mld patch --restart
```

不读取、不写入共享 token。

目标保留云端 `gatewayUrl` 和 `grant`，去掉 `token`，运行双链路混合模式：

- **gateway**：聊天/频道、presence、任务派发和成员管理；relay 会补上 agent
  轮次需要的请求人凭证；
- **局域网直连**：会话、终端、文件、快照；用成员的 g2 gateway session 作为账号 grant。
  宿主校验同时把 attached 主机上的非 owner 账号设备默认设为 `member`；需要管理员数据
  权限时把该账号加入 `mirachannelMachineAdmins`。

第一次直连需要宿主侧的一个小验证补丁（宿主直连监听默认只认 g1 enroll grant）：

```sh
# 在宿主（拥有这个空间的那台电脑）上执行
python3 scripts/host-g2-auth.py --apply
# 回滚：
python3 scripts/host-g2-auth.py --restore
```

第一次直连成功后，宿主会保存一条普通的 `via=account` 设备，带成员的 `accountId`；
后续重连走设备密钥（`via=known`），不再依赖 10 分钟 session。宿主 App 升级会覆盖
`server-main.cjs`，升级后需要重新 `--apply`。详见
[docs/host-g2-auth.md](docs/host-g2-auth.md)。

gateway 半无法认证时，改用官方 `gateway` 模式。

### 查找成员 grant（诊断）

桌面客户端通常会自动带上 g2 session。要在成员设备上查看本机云 RPC 返回什么（token
与邮箱会脱敏）：

```sh
node scripts/probe-cloud.mjs
# 没有 Node 时用 Electron 当 Node：
ELECTRON_RUN_AS_NODE=1 /Applications/Mirasim.app/Contents/MacOS/Mirasim scripts/probe-cloud.mjs
```

找 claims 里带 `sub`（成员账号）、`aud`（宿主 nodeId）、`exp` 的 token。
`mld member <node> --grant-file member.jwt` 仍可显式指定 grant；正常路径不需要文件。

### 直连协作开关（旧）

`mld collab <node> on` 可以强制打开直连目标的渲染层在线状态开关，但空间是否真的协作
仍由宿主的 presence 服务决定。需要协作时优先用 `hybrid`。

## 一键切换模式

一条命令切换并应用（会重启 Mirasim）：

```sh
mld mode <node-id-或-label> direct|gateway|hybrid
```

- `direct`：局域网数据，无 gateway/协作。
- `gateway`：走 relay/gateway，完整协作。
- `hybrid`：协作全部走 gateway，会话数据走局域网。

加 `--stage` 只写配置（之后再 `mld patch --force --restart`）。需要重启是因为传输
目标被编进窗口渲染层，切换要重打 `app.asar`。

## 命令

| 命令 | 作用 |
|---|---|
| `mld init` | 拉取/导入目标数据并写配置 |
| `mld patch [--force] [--dry-run] [--restart]` | 生成并安装渲染层补丁 |
| `mld mode <node> direct\|gateway\|hybrid` | 切换空间并应用（`--stage` 只改配置） |
| `mld init --member ...` | 创建成员目标，不需要共享 token |
| `mld invite <node>` | 打印 node/host/e2e 与成员命令（不含 token） |
| `mld member <node>` | 其他账号：网关协作 + 局域网数据（可选 `--grant-file`） |
| `mld check` | 显示 App 版本、已装标记、目标模式/可达性、代理状态 |
| `mld autopatch` | 代理入口：缺失/过期/不可达时才处理 |
| `mld restore` | 恢复原始 `app.asar` 并停用自动重打 |
| `mld agent install\|uninstall\|status` | 管理后台重打代理 |
| `mld doctor` | 检查路径、权限、App/可执行文件是否存在 |

`mld patch` 在 App 运行时拒绝安装，除非加 `--restart`；`--dry-run` 只在内存中构建与
校验，不改动 App。

## 自动重打

`mld agent install` 会创建：

- macOS：LaunchAgent `io.github.mirasim-lan-direct.autopatch`，监听 `app.asar`
  变化、登录时运行、按 `StartInterval`（默认 300 秒）运行；
- Windows：登录时 + 每 10 分钟的计划任务。

每次运行：

1. 最多每 6 小时刷新一次宿主 pair（仅当配置了 SSH）；
2. 比较已安装标记与当前目标哈希；
3. 检查配置的来源地址是否可达；
4. 需要时从**当前版本的原始副本**重建；
5. 用 App 自带 Electron（`ELECTRON_RUN_AS_NODE=1 --check`）校验补丁 JS；
6. 退出 Mirasim → 备份原始 asar → 安装 → 重新启动。

宿主不可达时保留现有补丁，不会反复重启 App；崩溃残留的锁在 15 分钟后自动清理。

代理只重打客户端的 `app.asar`。可选的宿主 g2 校验（`scripts/host-g2-auth.py`）位于宿主
的 `server-main.cjs`，Mirasim 升级同样会覆盖它；升级后需要在宿主上重新 `--apply`。

代理运行的是 `<配置目录>/runtime` 里的代码副本，所以仓库移动/删除不影响它
（改代码后重新执行 `mld agent install` 即可更新副本）。

日志：`<配置目录>/autopatch.log`；备份：`<配置目录>/backups/`。

停用：`mld agent uninstall`，或 `mld restore`（同时写入 `DISABLED`）。重新启用：
`mld patch` 或删除 `DISABLED`。

macOS 上，由 LaunchAgent 启动的解释器可能被「App 管理」/TCC 拦住，无法写入
`/Applications` 内的 `app.asar`。手动 `mld patch` 不受影响；要保留自动重打，请在
「系统设置 → 隐私与安全性」里给 `/usr/bin/python3` 授予「完全磁盘访问权限」（如列出
「App 管理」也一并授予），再执行 `mld agent install`。安装器会在退出前探测目标是否
可写，并在写入失败时重新拉起 Mirasim，不会把 App 留在关闭状态。

## 回滚

```sh
mld restore
```

恢复与当前 App 版本匹配的最新原始 `app.asar`，然后重启 App；版本不匹配时拒绝安装。

## 工作原理

详见 [docs/how-it-works.md](docs/how-it-works.md)。简要：

- `src/mld/asar.py`：零依赖 asar 读写，重算偏移与 SHA-256；
- `src/mld/patch.py`：形状匹配、目标表注入、CSP、JS 校验；
- `src/mld/hostinfo.py`：SSH 拉 pair、地址归一化、可达性；
- `src/mld/system.py`：App 发现、备份、锁、进程控制；
- `src/mld/agent.py`：LaunchAgent / 计划任务；
- `src/mld/cli.py`：`mld` 命令。

## 限制

- App 的资源封印会失效（`codesign --verify` 报一个文件不一致）。Mach-O 签名没动，
  macOS 上仍可启动，`spctl` 仍接受；App 升级会覆盖补丁，代理会重打。
- 工具依赖一个压缩函数的形状和渲染层 CSP 的写法。未来版本若改动，`mld patch`
  会安全失败（不动 App，旧补丁或中继继续可用）。
- 宿主的共享 token 会写进补丁后的 `app.asar`。POSIX 上文件为 `0600`；Windows 请
  注意安装目录的 ACL。
- 共享 token 的 legacy 设备会在宿主留下有上限（200 条）的历史；稳定的 `installId` 让
  活跃记录保持一条，界面会隐藏已撤销的记录。
- 宿主开启 `mirachannelStrictAuth` 时，共享 token 会被拒，直连回落中继。
- 离开局域网会回落中继；回到同网段后重开空间窗口恢复直连。
- member 模式第一次直连需要可选的宿主 g2 校验。首次 enrollment 后宿主会保存一条
  `via=account` 设备；成员退出空间只会停止签发新 session，已保存设备需要单独撤销。
  宿主 App 升级会覆盖 `server-main.cjs`，需重新执行 `scripts/host-g2-auth.py`。
- member 模式是混合模式：聊天/任务派发/presence 仍走 gateway，只有会话/终端/文件数据
  走局域网；纯直连拿不到 agent 轮次需要的请求人凭证。

## 安全

- 配置含 token，权限 `0600`，不要提交或外发；
- 补丁后的 `app.asar` 内嵌 token，注意本机其他用户/ACL；
- 仓库不含任何厂商代码、资源、token 或 pair 数据；
- 发现安全问题请开私密安全公告，不要贴真实凭证。

## 开发与测试

```sh
make test       # 单元测试，无需安装 Mirasim
make compile
```

测试使用合成的 asar（不含 Mirasim 代码或资源），覆盖解析、重打包、函数改写、CSP、
以及改写后函数的运行行为（通过 Node）。

## 免责声明

非官方工具。它会修改你本机上的第三方应用资源，并依赖你自己账号下的能力。与
Mirasim / Mirofish 无隶属、背书或支持关系。修改应用可能违反其服务条款，使用后果
由你自行承担。软件按“现状”提供，不附带任何担保。详见 [LICENSE](LICENSE)。

本项目采用 MIT 许可证。