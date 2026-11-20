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

本工具改写目标构造函数（注入宿主的地址、共享 token 与 E2E 公钥，并移除
`gatewayUrl` / `grant`），同时为配置的局域网来源放宽 CSP。目标函数按**代码形状**
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

## 协作 vs 直连

直连模式绕过 gateway，用宿主的共享 legacy token 认证。云协作（成员身份、在线状态、
协作模式）由 **gateway/账号会话**承载，所以直连的空间可能显示协作不可用。需要协作时，
把这个空间切回 gateway（中继）并重打：

```sh
mld mode <node-id-或-label> gateway
mld patch --force --restart
```

切回直连：`mld mode <...> direct`，再 `mld patch --force --restart`。宿主还需保持
「协作空间」开启、平台连接正常。

## 命令

| 命令 | 作用 |
|---|---|
| `mld init` | 拉取/导入目标数据并写配置 |
| `mld patch [--force] [--dry-run] [--restart]` | 生成并安装渲染层补丁 |
| `mld check` | 显示 App 版本、已装标记、目标可达性、代理状态 |
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

代理运行的是 `<配置目录>/runtime` 里的代码副本，所以仓库移动/删除不影响它
（改代码后重新执行 `mld agent install` 即可更新副本）。

日志：`<配置目录>/autopatch.log`；备份：`<配置目录>/backups/`。

停用：`mld agent uninstall`，或 `mld restore`（同时写入 `DISABLED`）。重新启用：
`mld patch` 或删除 `DISABLED`。

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