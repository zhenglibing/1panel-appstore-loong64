# 龙芯 LoongArch64 移植总报告：1Panel 与应用商店

- **报告日期**：2026-11-23
- **目标平台**：零刻 ME Pro 迷你主机（龙芯 2K3000，8×LA364E，loongarch64）
- **周期**：2026-11-05（设备装机）～ 2026-11-23（波次 79 收官），共 80 个工作波次
- **成果一句话**：1Panel v2.4.2 面板本体 + 自维护 loong64 应用商店体系在 2K3000 上全面落地——**上游 268 个商店应用全部收敛为「本地可装 / lcr 映射可装 / 明确拦截」三类，无灰区**；本地 registry 179 仓库 / 355 tag，阿里云 ACR 公共主源 370 tag 记录（匿名可拉、digest 全量校验一致）；离线可装性体检（audit14）**170/170 全绿**。

---

## 目录

1. [平台与设备基础](#1-平台与设备基础)
2. [1Panel 移植](#2-1panel-移植)
3. [移植方法论](#3-移植方法论)
4. [应用移植清单](#4-应用移植清单)
5. [移植记录（按时间）](#5-移植记录按时间)
6. [不可移植项与拦截清单](#6-不可移植项与拦截清单)
7. [当前状态与遗留事项](#7-当前状态与遗留事项)
8. [附录](#8-附录)

---

## 1. 平台与设备基础

### 1.1 硬件

| 项 | 规格 |
|---|---|
| 机型 | 零刻 ME Pro（BEELINK，官方无龙芯专用 NAS 系统，官方路线 = Loongnix + 自装私有云应用） |
| CPU | 龙芯 2K3000，8× LA364E（loongarch64），集成 LG200 核显 + VPU 硬解 |
| 内存 | 8 GiB → **2026-11-15 升级 32 GiB**（单 SO-DIMM 槽）；BIOS 为核显/VPU 截留约 2 GiB 属正常 |
| 存储 | NVMe 953.9G（p1 EFI / p2 /boot / p3 / 163G / p4 备用 / p5 /data 601G——/home /opt /root /var 均 bind 挂载于此 / p6 swap 8.8G）；SATA 465.8G 挂 /mnt/hdd（大构建工作区） |
| 网络 | 双 RTL8125 2.5GbE（**revision 0x0c / XID 689 新批次**，eno1/eno2）+ WiFi RTL8852BE（rtw89 正常） |
| 防火墙 | Loongnix 25.1 **firewalld 默认启用**（nftables 后端，iptables INPUT 全 ACCEPT 是假象）；新服务必须 `firewall-cmd --permanent --add-port` |

### 1.2 操作系统与内核

- **Loongnix 25.1**（Debian 系 apt），内核 `6.6.52-loong64`，gcc 14.2 + 内核头文件出厂自带（可直接本机编内核模块）。
- 2026-11-05 全新装机，SSH `lingke@<设备IP>`，面板 `http://<设备IP>:10086/（入口已隐去）`。
- 远程桌面：xrdp + x11vnc 屏幕镜像（xrdp 直起 Plasma 新会话黑屏，故走 console 镜像方案）；无头运行可用 HDMI 欺骗器兜底。

### 1.3 网卡驱动战役（2026-11-05，已终局）

1. **厂商 r8125 9.018.00 弃用**：在 RTL8125 rev 0x0c + 2K3000 上 **RX 单向损坏**（tcpdump 帧头错乱、`ip -s link` RX dropped 100% 而 ethtool 计数正常）——直连测试证实问题在厂商驱动 DMA/RX 路径，非硬件。
2. **ARP flux 教训**：双网卡同网段时 `arp_ignore=0` 抢答 ARP 造成「设备失联」假象；持久化 `arp_ignore=1 / arp_announce=2 / rp_filter=2`（/etc/sysctl.d/99-multinic-arp.conf）。
3. **正解 = 主线 r8169 RTL8125D 支持回移植到 6.6.52**：上游 commit f75d1fbe7809（XID 688）+ b3593df26ab1（XID 689）+ v6.14 的 PHY 重构回移。关键坑：r8169_main.c 的十余处 `case VER_40...VER_63` 版本区间 switch 必须逐一扩到 VER_64/65；6.6 的 realtek.c 无 vendor 兜底条目，需回移 `rtlgen_supports_mmd()` + NBase-T 内部 PHY 驱动条目。部署于 `/lib/modules/.../updates/`，重启自动加载，直连 1000M 全通。

### 1.4 Docker 运行时（2026-11-05 落地）

- **docker.io 26.1.5 + compose v2 2.26.1 + containerd 1.7.24**，全部来自 Loongnix 官方源（download.docker.com 无 loong64 包）。
- **镜像仓库铁律**：Docker Hub 基本无 loong64 架构且国内不可直连；首选龙芯官方容器仓库 **lcr.loongnix.cn**（library/nginx、redis、mysql、postgres、python、node、golang、rust、temurin 等全为 loong64，国内直连快）。
- daemon.json：日志 50m×3 封顶、`live-restore: true`（重启 docker 服务容器不断，NAS 场景刚需）。
- **事故记录（2026-11-10）**：一次 `docker image prune -a` 误删 181 个自建镜像——本地 registry volume 数据未受损，全量 pull 回填仅 9 分钟；lcr 底座缓存连带被删后回补 26 个。教训已制度化：registry 卷随大波次直接 tar 备份，不再依赖「可重建」。

### 1.5 远程运维通道

- **LAN 直连**（首选）：`192.168.3.36:22`（家中）/ `192.168.0.59`（公司），无隧道限速，大文件秒级。
- **公网隧道**（备用/公司环境）：`（公网运维隧道·地址端口已隐去）`（VPS 端口转发 → 设备 22）。特性：SFTP 单流 ~2.4MB/s、多流聚合 ~8MB/s；对持续 7 路大流量会批量 RST。大文件对策 = 256MB 分块 + 3 路并发 + 块级 sha256 校验（13.9G 实测 ~40 分钟）。
- **嵌套跳板**（LAN 全断救场）：paramiko 连 VPS → `direct-tcpip` 通道 → 设备 22（w64_hop.py，SFTP-over-hop 实测 5MB/s）。
- SSH 长任务纪律：`setsid nohup … > log 2>&1 < /dev/null &` 脱管 + 设备端 flock 防重入 + 只读轮询日志；`docker exec -d` 才是真脱管（exec 前台会随 SSH 通道断连被 SIGHUP 杀）。

---

## 2. 1Panel 移植

### 2.1 面板本体（v2.4.2）

- **Windows 交叉编译 loong64 二进制，源码零修改一次通过**（纯 Go / CGO-free）：`CGO_ENABLED=0 GOOS=linux GOARCH=loong64 go build -trimpath -ldflags '-s -w'`；工具链 go1.27.3（GOTOOLCHAIN=local + goproxy.cn）。
- 前端 `npm run build:pro`（npmmirror）产物经 vite outDir 直写 `core/cmd/server/web` 由 go:embed 打进二进制；ELF `e_machine=258` 验证。
- 安装包：以官方 amd64 包为模板换两个二进制（core+agent）；install.sh 内部无架构检查（架构门槛只在 CDN 引导层），免交互参数安装，安装器原生处理 firewalld 放行。
- **验收（2026-11-06）**：用户浏览器登录 + 商店装 Redis 端到端闭环（容器实为 lcr redis:7.4.1 由映射层自动改写）；重启持久化实测全部自启。

### 2.2 loong64 适配总体架构（五层体系）

```
┌─ ⑤ 上游联动：fork 分支 loong64-support（补丁 v19，~700 行）
│     + 1Panel-dev/appstore 配方 PR #10458（OPEN）
│     + 公开仓库 zhenglibing/1panel-appstore-loong64
├─ ④ ACR 公共主源：crpi 个人实例 / 1panel-loong64 命名空间
│     逐仓库公开 → 匿名可拉；agent 二级回源（registry miss → ACR）
├─ ③ 自建商店源：/opt/loong-store（nginx :8082 镜像站，268 应用全量）
│     tar 包内 compose 改写 + 占位文件规范化 + STORE_VERSION 版本戳
├─ ② 本地 registry：loong-registry 容器 127.0.0.1:5000/loong/<key>:<tag>
│     （2026-11-23 实测：179 仓库 / 355 tag）
└─ ① agent 映射层：app_loong64.go（runtime.GOARCH 门控）
      规则表 ~165 条 + 拦截表 58 条 + base 规则；安装链 3 处接线
```

### 2.3 agent 镜像映射层（核心机制）

- `app/service/app_loong64.go`：`runtime.GOARCH` 门控，对商店 compose 的 image 引用做**主版本路由**（ByMajor 矩阵，如 redis 6.2→6.2.13 / 8→7.4.1；postgres 13/14→13.19-alpine3.21、15/16→15.7-sid、17→17-sid）。
- 安装链 3 处接线：app.go installWithHooks / app_utils.go getUpgradeCompose / app_install.go InstallUpgrade；单测 19 用例起步（TestMain 挂静默 logger 防 nil logrus SIGSEGV），**交叉编译 test binary 后在真机跑**（agent 含 Linux-only syscall，Windows 宿主 go test 必败）。
- 规则形态：精确 repo 路径、`<repo>` ByMajor 矩阵、keep-tag（上游 loong64 化后不改写）、`<host前缀>全路径`（docker.cnb.cool 等）、codeberg 等非 Hub 源。
- **拦截表 `loong64BlockedRepos`**：不可移植项安装返回明确中文提示（UI 红色 toast），落盘前拦截；注意 `isBlockedLoong64Image` 在映射之前判定——**入库一批后必须清同 repo 的历史黑名单**（rustdesk 陈旧条目曾遮蔽活规则）。

### 2.4 自建商店源（离线可装的根基）

- `store_loong_build.py` 直解析映射规则生成改写镜像：CDN 下载 268 应用 → **双路改写**（安装走整包 `{key}-{ver}.tar.gz`，必须改写 tar 内部 compose；散装 yml 仅是 getRemoteCompose 兜底）→ nginx 容器 `loong-store` 只读托管 /opt/loong-store 于 :8082。
- agent 配置嵌入式（go:embed app.yaml）→ 外置 `/opt/1panel/conf/app.yaml`（名字必须 .yaml，须带完整 base+log 段）`base.app_repo_url` 覆盖 + `systemctl restart 1panel-agent` 切源。
- **上游包占位文件 × v2.4.2 SDK 严格解压器**：上游 1018/1021 个包带 0 字节占位条目且无目录条目，安装即 InstallErr；镜像侧全量规范化（删占位 + 补目录条目），旧残留缓存零清理自愈。
- 商店源切换后**应用更新不再依赖 agent 重编译**（索引/包改写在镜像侧完成），映射层退化为兜底。

### 2.5 ACR 公共镜像主源（2026-11-21 收官）

- 端点 `crpi-a02ej0ppuvq7b0mw.cn-hangzhou.personal.cr.aliyuncs.com`，命名空间 `1panel-loong64`；docker 凭据经 w66_acr_push.py `--user/--pass` 参数使用。
- **293 tag 全量上云（ok=293 fail=0，约 42G）+ 逐 tag digest 全量校验 293/293 bit-exact**；后续波次持续增量推送（done-list 累计 370 条记录，`loong/<repo>|<tag>` 格式——**同 tag 重推必须先删 done 行强推**）。
- **匿名拉取正解（终版实测）**：逐仓库设为 PUBLIC 即可匿名拉，无需实例级开关（主账号 AK 批量转公开 156/156 早已完成；两把 AK 已约定不再使用、由用户删除）。
- **agent 二级回源**（fork commit a5fe4ae）：mapImagesForLoong64 对本地 ref 探测 `HEAD /v2/loong/<repo>/manifests/<tag>`（3s 超时），miss/registry 停机即换 ACR ref。坑：必须同时覆盖**预烘焙 ref** 分支；探测 URL 必须带 `loong/` 命名空间。E2E 双阶段验证：A = registry 在线走本地；B = rmi + 停 registry → compose=ACR ref 且 15s Running = 云端真拉。

### 2.6 上游联动与开源回馈

- 上游 PR #14328 被关闭未合并（应用包体系未配套验证 + 维护成本）→ 转自维护。
- **路线 C**：1Panel-dev/appstore 数据层配方 **PR #10458（OPEN）**——638 文件 +25.4 万行：openresty 全源码 loong64 配方 + 7 应用 build/loong64 配方，官方 compose/data.yml 零改动。
- **路线 D**：公开仓库 **zhenglibing/1panel-appstore-loong64**（30M：pipeline + 23 specs + openresty 配方 + README，GPL-3.0，脱敏终扫零命中）。
- fork 分支 `loong64-support`（基线 v2.4.2 tag，补丁 v19 ~700 行），升级流程 = rebase → 真机门禁 → 交叉编译。

### 2.7 质量保障体系

- **体检链（audit 三件套）**：`audit26_parse.py`（从镜像树重建 checks：每应用最新版本改写后 compose 直查改写目标存在性 + NONLOCAL 告警）→ `audit14_gen.py`（生成设备 manifest 探测脚本）→ 设备跑（registry manifest 级 200 + lcr 缓存命中）→ `audit20_offline.py`（离线可装判定）。**铁律：每入库一批新应用必须重生成 checks 基线，否则新应用假绿。**
- **体检口径演进**：109 →（w29）115 →（w38）129 →（w48）148 →（w57）137 重定基 →（w62）122 probe →（w72）151 →（w75）158 + **NONLOCAL=0** →（w76）161 →（w78）169 →（w79）**170/170**（143 本地 + 27 lcr 缓存）。
- **E2E 真装链**（w29_e2e_device.py 及后代）：面板 API 登录（混合加密密码 + EntranceCode 头 + CSRF）→ 按安装名/伴生参数装机 → 轮询 Running → HTTP 探针 → 清理。伴生三坑：伴生容器必须同网络（1panel-network）、DB 用户必须显式 CREATE USER、面板容器名 = `1Panel-<appkey>-<随机>`（与安装名无关）。
- **守望与备份**：`roll_maint.py` 一键巡检（检测→重基线→设备体检→offline→结论）；每日漂移检测 automation（09:00）；周备份 crontab（周日 04:00，registry tar 轮换留 3 份）；资产保护（数据卷 + 面板库 = 真正不可再生资产）。

### 2.8 面板与商店关键坑集（Top 清单）

| # | 坑 | 对策 |
|---|---|---|
| 1 | 带 `build:` 段的商店模板映射被「守卫」吞掉 | 删守卫——规则表精确匹配本身即闸门；静默 continue 是坑源 |
| 2 | loongson LuaJIT 缺 OpenResty fork 的 `table.nkeys` | 镜像末层烘焙纯 Lua shim（lualib/table/nkeys.lua） |
| 3 | 上游包 0 字节占位条目 × 严格解压器 | 镜像侧重打包规范化（w21_fix_tars 内建于 builder） |
| 4 | 安装 compose 以 **agent.db 的 app_details.docker_compose 为准**，tar 改写不回刷 db | sqlite UPDATE + 缓存重提取（w32 修复法），改写已有应用后必跑 |
| 5 | 商店索引三层缓存（包缓存/DB compose/安装渲染） | 版本戳 STORE_VERSION bump + per-version lastModified 提升；bump 必须 printf **无换行**（echo 换行会让面板 strconv.Atoi 崩） |
| 6 | compose 二次插值吃 YAML block scalar 里的 shell 脚本 | compose 内嵌脚本所有运行时变量写 `$$` |
| 7 | 安装时 copyData 白名单拷贝，自建目录不落安装目录 | 新增文件走 scripts/ 或 entrypoint 内嵌生成 |
| 8 | 面板容器名 = `1Panel-<appkey>-<随机>`，CONTAINER_NAME 仅运行时类生效 | E2E 用 appkey 前缀 grep 或 install_and_resolve 动态解析 |
| 9 | 上游新版本目录漂移 404（商店同步后 keep-tag 无镜像） | 体检三分法：同谱系=别名、跨代=重建、F=清规则转拦截；每次商店同步后复跑体检 |
| 10 | 镜像站索引采纳后面板不自动刷新 | 必须重启 1panel-agent（内置 ~240h 定时同步太慢） |
| 11 | 登录失败 1 次触发验证码（IPTracker 内存态） | 重启 1panel-core 清；脚本失败即重启再战 |
| 12 | VAR 运行时类（php/node/java/python/go）`${VAR}` 引用 | CONTENT_PATCHES 行级钉定本地 registry ref，`${}` 尾巴保留 |

---

## 3. 移植方法论

### 3.1 工法九式

| # | 工法 | 适用 | 代表战例 |
|---|---|---|---|
| 1 | **Go 交叉编译**（PC，CGO=0） | 纯 Go 单体 + 前端 embed | gitea/forgejo/zitadel(173MB)/certimate/silo(30 秒)/mattermost/kubepi/mliev-dwz/redpanda-console |
| 2 | **Rust 设备原生编译**（非交叉） | Rust 服务 | meilisearch/rustfs/stalwart/vector/rustdesk/dbx；rustup loong64 官方通道 + rsproxy |
| 3 | **前端 PC 构建 + 设备原生模块** | Node 全栈 | rolldown/vite8、sass-embedded、lightningcss、@tailwindcss/oxide 等 Rust 绑定无 loong64 → PC x64 出纯 JS 产物；better-sqlite3/sharp/isolated-vm 等设备 node-gyp |
| 4 | **amd64/arm64 官方镜像层抽取换芯** | jar/war/静态树应用 | cloudbeaver/koodo-reader/nocobase/nexus(arm64)/rocketmq-dashboard/waline/affine/teable/synapse 前端等 |
| 5 | **deb/jar 抽取** | arch-all deb、fat jar | odoo（arch:all deb 抽树）、stirling-pdf（deb 取 jar）、kkfileview（源码 jar）、mblog（fat jar 换芯） |
| 6 | **全源码设备编译** | C/C++ 大件 | netdata（C+Rust+Go）、zabbix、TDengine、GreatSQL、libvips、OpenResty、sonarqube ES 配套 |
| 7 | **lcr 基片代位 / tag 别名** | 版本差补丁级 | node 22 代位 26、php 8.4.1 代位 8.5、postgres 15.7-sid 影子 17、gitea 27.3.12←27.3.11、wikijs 3.2/3.3←3.1 |
| 8 | **Python 源码编译链** | PyPI 无 loong64 wheel | trendradar/xiaomusic/filecodebox/domain-admin/qiandao/pgadmin4/odoo/synapse/linkding |
| 9 | **D 层拦截** | 不可移植项 | 58 条规则，安装返回明确中文提示（详见 §6） |

### 3.2 底座与工具链资产

| 资产 | 说明 |
|---|---|
| lcr node 20/22/26 全系 | Debian trixie 底座；注意部分烤的是已死的 debian-ports apt 源，需重写为**主档案 sid**（TUNA/SJTU，loong64 已从 debian-ports 毕业） |
| **自编 node 24.22.3**（w45 战略资产） | 设备源码编译 ~50 分钟；`--dest-cpu=loong64 --dest-os=linux --openssl-no-asm`；镜像 `loong/node:24.22.3` 入库；n8n/affine/teable 系直接复用 |
| lcr php 7.4.30 / 8.1-8.4 + 自编 `loong/php:8.4.1-ext` | fpm-alpine 基片 + 自研 install-ext（bundled/pecl 映射 63 项）；pear 配置带死代理 `10.130.43.249:7890` 必须先清 |
| **Loongnix 官方 JDK21（HotSpot JIT）** | **lcr eclipse-temurin = Zero VM（无 JIT 纯解释器，SHA 慢 130-180 倍）**——Java 密集应用必须 docker cp 宿主 openjdk-21 打进镜像（glibc 底座 sid，不能 alpine） |
| lcr golang 1.25/1.26/1.27 + PC toolchain | GOTOOLCHAIN=auto 经 goproxy 拉工具链；**GOTOOLCHAIN 版本敏感**（certimate 须 go1.25.14 对齐上游） |
| lcr rust:1.100 + rustup loong64 通道 | `1.98.1-loongarch64-unknown-linux-gnu` 官方分发；crates.io 走 rsproxy；**超大产物（.text>128MB）bfd R_LARCH_B26 溢出 → `/usr/local/bin/cc` 放 lld 包装器**（保 cargo 缓存的通解） |
| debian sid apt loong64 | deb.debian.org 主档案（trixie 起 loong64 入主档案）；TUNA deb822 源 `/etc/apt/sources.list.d/debian.sources`；PyPI 走 TUNA（SJTU pypi 隔离构建卡死） |
| PC 工具链 | node 24.22.3 win-x64（npm 11.19，前端构建解锁）、bun 1.4.3、pnpm 各版本钉版目录、goproxy、esbuild loong64 配方（golang 容器 30 秒出二进制） |
| 抽层工具 | w43_pull.py（PC 直连 Hub blob 拉取 + token 续期）、w75_blobs.py（ghcr 匿名 token dance）、w44_probe.py（manifest 探针） |

### 3.3 语言栈专项解法（速查）

- **Prisma 无 loong64 引擎** → 三代演进：①拦截（早期 umami/blinko）②**Prisma 7 driver-adapter 纯 TS**（engineType="client"，零引擎二进制；umami/arcadia/upage/lobe/affine）③**运行时岛屿 + 桥接**（teable：bundle 内联 6.2.1 客户端与 6.16 runtime 协议错位 → island runtime 检测实例形状现场重建原生 adapter）。配套自写 SQL 迁移器复刻 `migrate deploy`（_prisma_migrations 记账 + sha256 + CONCURRENTLY 拆分）。
- **Node 原生绑定缺失**：esbuild 0.12 拒 loong64 → --ignore-scripts；pnpm≥12 无 loong64 二进制 → 设备锁 pnpm≤11 / PC corepack 钉版；sharp 三种编法（npm 带 binding.gyp 直编 / 从 GitHub tag 抽 binding.gyp + node-addon-api / libvips 8.18.7 源码编译链）；libuv io_uring 在 loong64+6.6.52 自旋挂死 → 统一烘 `UV_USE_IO_URING=0`。
- **Python 3.14 系**：distutils 已移除（node-gyp 老版全挂 → node-gyp@10 或 apt python3-setuptools）；PEP 668（--break-system-packages / PIP_BREAK_SYSTEM_PACKAGES=1）；brotli 1.0.9 撞 GCC15 → 钉 1.1.0；pip 装 deb 管控路径被拒（no RECORD）→ zipfile 影子路径（odoo pytz 修复法）；源码编应用运行时底座必须补齐对应 .so 运行包（Pillow→libtiff6/libjpeg62-turbo；uwsgi→libpython3.14）。
- **C/C++ 巨件**：GreatSQL（gcc-14 强制 + 4 处缺 include 批补 + cmake flag 终集 + 官方 my.cnf 占位符替换）；TDengine（`-DBUILD_VER_CPUTYPE=loongarch64` 必须显式防 x64 回退 + rocksdb 三连修 + 内部 dmodule 符号真实现补位）；netdata（installer 空串载荷参数 + corrosion cmake 变量注入 + submodule 烤入 + t64 运行时包名族）。
- **rustdesk ring 0.16 三链拆解**：tokio-tungstenite 摘 connect/sqlx 换 native-tls/jsonwebtoken 8→9；nix 0.23 无 loong64 → 父级 mac_address 升级 + **Cargo.lock 必须 `cargo update -p`**（宽化 requirement 不自动刷新）。

---

## 4. 应用移植清单

### 4.1 总体统计（2026-11-23）

| 维度 | 数值 |
|---|---|
| 上游商店应用总数 | 268 |
| 已移植（本地镜像可装） | **148 / 268 ≈ 55%** |
| lcr 映射直供 | 27 检查项（postgres/mysql/redis/mongo/minio 等基座） |
| D 层拦截 | 58 条（LLM/GPU/闭源/原生二进制堆，安装有明确中文提示） |
| 运行时 VAR 代位 | php8/php7/node/java/python/go + openresty + NPM |
| **离线体检（audit14）** | **170/170 全绿**（143 本地 manifest 200 + 27 lcr 缓存命中，0 miss） |
| NONLOCAL（装不上的灰区） | **0**（w75 清零，此后持续保持） |
| 本地 registry | 179 仓库 / 355 tag |
| ACR 公共主源 | done-list 累计 370 条（全量匿名 digest 校验一致） |
| 商店镜像站 | 268 应用全量（/opt/loong-store，:8082） |
| 设备本地镜像 | 798 个（自建 + lcr 缓存 + 运行时） |

### 4.2 分类清单

> 工法代号：**交叉**=Go 交叉编译｜**源编**=设备全源码编译｜**层抽**=amd64/arm64 镜像层抽取换芯｜**PC前端**=前端 PC 构建+设备原生模块｜**别名**=lcr 基片/tag 别名代位｜**抽包**=deb/jar/war 抽取｜**源编Py**=Python 源码编译链｜**s6复刻**=复刻官方启动语义

**Go 单体（交叉/设备 CGO）**

| 应用 | 最新版本 | 工法 | 首入波次 |
|---|---|---|---|
| gitea | 28.4.1 | 交叉+vite 前端 embed | 波次一（27.3）→w33 v28→w76 28.4.1 |
| forgejo | 16.0.7 / 15.0.12 | 交叉（webpack/npm ci） | w42 / w77 |
| forgejo-runner | 13.2.2 | 交叉（goproxy 30 秒） | w5 / w39 / w76 |
| memos / gatus / beszel / glance | 新版各异 | 交叉（w15 真构建批） | w3/w15/w25 |
| adguardhome | v1.0.0 | 交叉（工具链 1.27.4） | w4 / w76 |
| opengist / screego / ezbookkeeping | — | 交叉（ezbookkeeping 设备 CGO） | w4 |
| prometheus | v3.16.0 | 交叉（mantine-ui 前端） | w3 / w27 |
| node-exporter | v1.13.1 | 交叉 | mega216 / w76 |
| maddy | 0.9.8 | 交叉（./cmd/maddy 主包） | mega216 / w27 / w76 |
| watchtower / cloudflared / miniflux | — | 交叉 | mega216 |
| frpc / frps / artalk / npc / nps | — | 交叉 | mega216 |
| act-runner / new-api / sub2api / pst / alist / sftpgo | — | 交叉（alist glebarez 纯 Go sqlite） | mega216 |
| ddns-go | v6.17.8 | 交叉 | 批次一 / w33 |
| gotify / sun-panel / navidrome | — | 交叉（navidrome 设备 CGO sqlite_fts5） | w3 |
| certimate | v0.4.37 | 交叉（go1.25.14 对齐）+ PC node24 前端 | w48 |
| silo | RELEASE.2026-10.15 | 交叉 30 秒（pgsty fork） | w59 |
| zitadel | v4.19.4 | 交叉（buf 9 插件 + statik×4 + Angular console embed，173MB） | w61 |
| kubepi | v2.0.3 | 交叉（3 前端 + gotty + kubectl/helm/k9s） | w55 |
| mattermost | 12.1.0 | amd64 层抽 + go.work 交叉 | w55 |
| mliev-dwz | v2.25.0 | 交叉 + vben 前端 embed（cnb.cool 源） | w50 / w78 |
| redpanda-console | v3.15.0 | 交叉 + bun 前端 embed | w50 / w78 |
| komari | 1.6.2 | **官方 loong64 release 资产直用**（w76） | w6 / w76 |

**Rust（设备原生）**

| 应用 | 最新版本 | 要点 | 波次 |
|---|---|---|---|
| meilisearch | v1.56.2 | rust:1.100 + rsproxy；ring generic C 可跑 | w56 |
| rustfs | 1.0.5 | lld cc 包装器破 B26 溢出；console zip 填充 + 子路径 | w57 |
| stalwart-mail | v1.1.0-alpine | rocks 砍特性；vendor hickory | w57 |
| vector | 0.58-0.61.0-debian | vendored 摘除 + nix 内嵌 allow | w57 |
| rustdesk-server | 1.1.16 | ring 0.16 三链拆解 + s6 替代双进程 + HOME=/data | w58 |
| dbx | 0.6.72 | git-dep vendor 三管齐下 + hotbundle feature 手术 | w69 / w78 |

**Java（层抽 / 抽包 / jar 换芯）**

| 应用 | 最新版本 | 工法 | 波次 |
|---|---|---|---|
| mblog | 1.1.0 | temurin17 + fat jar 换芯 + xerial native 自编（首例） | w47 |
| kkfileview | 4.1.0 | 设备 maven + sid apt libreoffice 全家 | w52 |
| nexus | 3.98.3 | arm64 层抽（boot-jar 新式包法） | w52 / w77 |
| sonarqube | 26.11 | arm64 层抽 + Loongnix JDK21 + ES bootstrap 关闭 | w53 |
| cloudbeaver | 26.2.5 | app 层/JRE 层分离抽取 + loong/java:21 | w59 |
| rocketmq-dashboard | 2.1.0 | jar 抽取 + loong/java:21 | w58 |
| cordys-crm | 1.9.7 | app 树抽取 + 三容器伴生改写（ENTRYPOINT 必须 bash） | w67/w68 |
| dataease | v2.10.28 / v3.3.1 | 阿里云 registry 层抽取 + temurin | w39 / w77 |
| onedev | 17.2.2 | /app 产品包抽取 + 纯 Java wrapper bypass | w39 / w77 |
| stirling-pdf | 3.4.0 | deb 解包取 jar + sid openjdk-25 | w30 / w77 |
| metabase | v0.65.6 | jar 层抽取（deb 法） | mega216 / w33 / w76 |
| keycloak / nacos / sentinel / komga / kafka / tomcat / rocketmq | — | 层抽/换芯/别名（mega216 批） | mega216 |
| halo-pro | 2.27.2 | 社区 jar 挂 pro tag + temurin21 | 批次三 |

**Node 全栈（PC 前端 + 设备原生）**

| 应用 | 最新版本 | 要点 | 波次 |
|---|---|---|---|
| uptime-kuma | 2.5.11 | @louislam/sqlite3 设备 node-gyp | 批次二 / w35 |
| chatgpt-next-web | 2.16.1 | Next standalone 装配 v4 | w31 |
| web-check | 2.4.0 | Astro + PUPPETEER_SKIP | w32 |
| outline | 1.12.0 | yarn4 PC standalone + rolldown 回退 PC 构建 | w32 |
| docmost | 0.97.0 | pnpm11/nx；.dockerignore 吞 dist 坑 | w36 |
| trilium | v0.107.0 | rolldown 系最完整战例（12 轮） | w36 |
| nodebb | v4.16.8 | sass-embedded→纯 JS sass 强回退 | w37 |
| tailchat | v1.11.18 | 17 轮：esbuild0.12 + node20 moleculer bind | w38 |
| rsshub | chromium-bundled | PC pnpm deploy hoisted 闭包 | w43 |
| ghost | 6.77.0 | libvips 8.18.7 源编解锁 sharp | w44 |
| n8n | 2.48.7 | node24 自编 + isolated-vm node-gyp | w45 / w78 |
| certd | 1.47.1 | amd64 树换芯 + symlink manifest 重建 | w45 |
| nocodb | 0.301.5 | 三原生（sharp/lz4/sqlite3） | w45 |
| newsnow / koishi | 0.0.41 / v1.16.0 | standalone 换芯 / zip→tar 直转 | w46 |
| jsonhero | latest | Remix 生产化重建 + SSR shim | w47 |
| logto | 1.46.0 | PC pnpm10 全量 + 设备 prod install | w51 |
| umami | 3.5.0 | Prisma7 纯 JS + 自写 SQL 迁移器 | w51 |
| nginx-proxy-manager（npm） | 2.17.1 | s6 复刻术 | w60 / w78 |
| verdaccio | 7.1.2 | 交叉 | w25 / w76 |
| waline | 1.43.8 | strace 破案（原生模块缺失假挂起） | w11 / w77 |
| mcsmanager-daemon / web | — | webpack BUNDLE=1 + lib 三源 | w63 |
| lobe-chat | 1.143.3 | Windows junction shim + nft 懒加载补链 | w74 |
| nocobase | 2.2.49 | 层抽保 symlink + license-kit Proxy stub | w68 / w78 |
| twenty CRM | v2.60.3 | nx 隐藏构建链 + nest-cli 资产布局（最重 JS 单体） | w62 / w79 |
| affine | 0.27.4 | 层抽 + Prisma 纯 TS + 自家 Rust napi 源编 | w75 |
| teable | latest | Prisma 岛屿 + connect 桥接（史上最深） | w75 |
| arcadia | 1.2.0 | Prisma 7 纯 TS + 设备源编 node-pty/better-sqlite3 | w73 |
| koishi / redis-commander / mongo-express / node-red | — | mega216 批 | mega216 |

**PHP / 静态**

| 应用 | 最新版本 | 要点 | 波次 |
|---|---|---|---|
| typecho / freshrss / emlog / zentao / firefly-iii / heimdall / kodbox / lsky-pro / php 系 9 家 | — | debian sid + apache/php8.4 模板复刻 | 批次二/三、mega216、w29、w68 |
| dashy / heimdall / homepage / flap 等静态 SPA | — | PC 构建 → nginx 托管 | w30/w33 |
| drawio | 32.6.10 | war 抽取 + tomcat 基片 | w43 |
| openresty | 1.31.8.1-2-2-noble | 全源码 17 轮（LuaJIT loongarch + table.nkeys shim）；CVE 同步 | 移植期 / w66 |

**Python（源编链）**

| 应用 | 最新版本 | 要点 | 波次 |
|---|---|---|---|
| pgadmin4 | — | PyPI wheel + 设备 venv（cffi/gssapi/brotli/psycopg 四坑） | w60 |
| trendradar | 6.11.0 | uv 导出 + litellm 全树源编 + supercronic 交叉 | w64 |
| xiaomusic | v0.6.1 | pdm 三坑（PEP668/pdpkg packaging/brotli）+ Pillow 运行时 .so | w64 |
| filecodebox | 2.7.0-2.8.5 五版 | 双前端 PC 预构建 + --require-hashes | w64 |
| domain-admin | v1.6.80 | PyPI sdist 逐版装 + v 前缀 tag 对齐 | w65 |
| calibre-web | 0.6.27 | 复刻 s6 启动命令 cps.py | w65 |
| qiandao | master | 钉版升 13 项 + pycurl 源编 | w65 |
| linkding | 1.47.0-plus | uv 导出 + maturin Rust cryptography + uwsgi 补 libpython3.14 | w63 |
| odoo | 19.0 | arch-all deb 抽树 + pytz 影子路径修 py3.14 | w69 |
| synapse | v1.164.2 | apt rustc 1.85 + 钉 cryptography 44 + 手写 log.config | w68 |
| mkdocs-material | 9.8.2 | pip 源编 pillow/cffi（PEP668 坑） | w67 / w77 |

**C/C++（全源码）**

| 应用 | 最新版本 | 要点 | 波次 |
|---|---|---|---|
| netdata | v2.13.0 | C+Rust+Go 三语言全源码（installer ARG/corrosion/submodule/t64） | w70 / w78 |
| zabbix-server（三镜像） | 7.4.5 | C 源编 + java-gateway javac + 纯 PHP ui | w69 |
| zabbix-xinchuang-edition（四镜像） | 7.0.27 | 官方 zabbix-docker entrypoints 照抄法 | w72 |
| TDengine | 3.4.3.9 | CPUTYPE 显式 + rocksdb 三连修 + dmodule 符号补位 | w73 |
| GreatSQL | 8.0.32-27 | gcc-14 + cmake flag 终集 + my.cnf 占位符替换 | w71 |

**数据库 / 伴生 / 集群（lcr 映射 + 语义重写）**

| 应用 | 说明 | 波次 |
|---|---|---|
| postgres / mysql / mariadb / redis / mongo / minio / memcached / rabbitmq / valkey 等 | lcr ByMajor 映射直供（27 检查项） | 移植期 |
| redis-cluster / postgresql-cluster | bitnami 语义重写：redis command 化主从、pg wrapper+basebackup 流复制 | w42 |
| mysql-cluster | bitnamilegacy 映射补规则 | w54 |
| wordpress | 全栈金丝雀（PHP 运行时 + MySQL 缓存别名 trick + 浏览器安装向导全通） | w18 |

---

## 5. 移植记录（按时间）

### 5.1 早期阶段：面板落地与首批 100+ 应用（2026-11-06 ～ 11-10）

**阶段二批次一~三（11-06）**：caddy / filebrowser / ddns-go / typecho / uptime-kuma / halo-pro / freshrss 7 应用入库；OpenResty loong64 自建（17 轮：tuna sid 源 + loongson LuaJIT + 全源码内编译消除 amd64 bootstrap + table.nkeys shim），商店安装 + WAF 2.0 + 建站闭环用户验收通过。

**波次一~十三（11-06~08）**：
- dockge（pnpm hoisted、libuv io_uring 挂死定论 UV_USE_IO_URING=0）；
- P 级 8+6 应用（memos/gatus/gitea-CE/beszel/prometheus/navidrome/gotify/sun-panel/opengist/screego/ezbookkeeping/adguardhome）——cobra serve 子命令、gitea 拒 root→su-exec、构建标签哨兵、mattn sqlite3 交叉是 stub 必须设备 CGO 等十四式沉淀；
- forgejo-runner / komari（defaultTheme 组装满足 go:embed）/ openldap（LMDB reader 表×Docker fd 上限 → ulimit -n 1024）/ casdoor / cloudreve / woodpecker / focalboard / vaultwarden / excalidraw（esbuild 钉 ^0.25）/ easytier / twikoo（tkserver 才是服务端）/ **waline 转正**（strace 破案：挂起=原生模块缺失 require 死循环，非架构问题）；
- **wikijs 3.1.0**（v3 官方 tarball node26 原生 TS 直跑 + Temporal polyfill --require 预载 + **debian-ports 无 loong64 → deb.debian.org sid 自带 PG18 → postgres:17-sid 影子 tag**）——首个商店 service 联动；
- **audiobookshelf**（客户端 PC 构建 + sqlite3 源编破 python3.14 distutils 之死 + sid ffmpeg）——B 层大项归零。

**mega216 B 层批（11-07）**：216 应用逐一评估，46 个构建入库（Go 17 + Java 8 + 静态 5 + PHP 9 + Node 4 + apt-sid 3）、62 暂缓、18 拒绝入拦截表；关键攻坚 alist→glebarez 纯 Go sqlite、sftpgo→bolt provider、komga→自编 libsqlitejdbc.so。

**波次十四~二十（11-08~09）**：
- 全舰队映射体检机制诞生（audit14 前身）：抓出 17 个版本漂移 404 → 14 别名 + 1 死规则清除 + 2 重建待办；**商店版本漂移是常态**三分法定型；
- 重建待办池 10/10 清空（pipeline git_tag 字段解决替代构建；stage2 COPY 遮蔽 CGO 产物坑）；
- **VAR 层打通**：php 运行时 alpine 化前置侦察 + go/node/python/java 运行时四件套（lcr node 三档别名、python sid 自装、java sid JDK）；WordPress 全栈金丝雀（缓存镜像别名 trick + 浏览器四步安装向导全通）；
- **A 层离线可装性定论**：纯映射仅在线成立，离线可装 = registry 支撑 ∪ lcr 缓存；audit20_offline 工具诞生（87/111→后续 111/111）。

**波次二十一~二十七（11-09~10）**：
- **自维护体系上线**：上游拒收 → fork 分支（3 commits）+ 自建商店源（268 应用双路改写 + 占位文件规范化）+ 外置 app.yaml 切源 + E2E 真装 memcached 全自动成功；面板 API 登录链/严格解压器/MSYS 路径等全套自动化基建沉淀；
- **lcr 复苏红利**：24 个 ONLINE-ONLY 项批量 pull 入缓存 → **111/111 离线可装（100%）**；postgres:17-sid 影子 tag 验真（现存数据卷 PG18 集群格式，刻意保留）；
- 备份制度化（卷+面板库+脚本三包 + manifest sha256）；
- **滚动维护首次实战**：上游全局重发布检测（严格 diff 判据 = 版本串/params，非 lastModified）、6-tag 重建（clone 缓存陷阱：换 tag 拿旧源码打新标 → ls-remote sha 校验强制重取）、体检重定基 109、7 项 lag 别名升级真构建（**真构建终审判据 = registry digest ≠ 前驱**）。

**波次二十八（11-10）**：prune -a 误删 181 镜像事故与全量恢复（registry 卷 13.87G 备份 + 异地双副本 + lcr 缓存回补 + 体检回绿 109/109）。

### 5.2 波次 29～79（2026-11-11 ～ 11-23）逐波记录

> 每波格式：交付 → 关键工法/坑 → 结果（体检/E2E）。体检数为当波 audit14 checks 口径。

**波次 29（11-11）** 缺口首批 10 应用：openlist 4.2.9（loong64 被故意路由 CGO → sed 摘除走 glebarez）/ answer 2.0.3（entrypoint 三步链 init/upgrade/run）/ bytebase 3.24.1（绕开 pnpm script 直跑 vite）/ dbhub 1.6.0（pnpm 命令必须 bash -lc 包装）/ emlog / zentao 22.7 / firefly-iii v6.4.2 + 运行时别名 3。E2E 面板 API 真装链定型（混合加密密码、detail 路由、验证码重启清）。体检 109→**115/115**。

**波次 30（11-11）** heimdall 2.8.4 / dashy 4.9.8 / stirling-pdf 3.3.0（**deb 解包取 jar** 工法首例）。事故：builder 崩溃连锁 rmtree 删空 mirror 树（后台 shell cwd 隐形目录锁）→ work 树重建恢复。体检 **118/118**。

**波次 31（11-12）** chatgpt-next-web 2.16.1（Next standalone 装配 v4：`cp -rT` 整棵覆盖）。homepage 2.7.0 挂起 6 轮未克（pnpm v12 workspace hoisted 之谜，w33 绕过）。体检 **120/120**。

**波次 32（11-12）** web-check 2.4.0（Astro）/ outline 1.12.0（yarn4 standalone CLI PC 下载 + rolldown 无绑定回退 PC 构建 + Windows MAX_PATH bash tar）。**大坑：db compose 不随 tar 改写刷新 → sqlite UPDATE 修复法**。体检 **122/122**。

**波次 33（11-13~14）** 11 个漂移 404 全修复；gitea v28 体系（webpack→vite8 rolldown + pnpm12 + go generate bindata）；homepage v2.7.0 npm 路线完胜（Next16 Host 校验 → `HOMEPAGE_ALLOWED_HOSTS=*`）。**系统性发现：设备 agent 是旧版缺规则**——deploy 假阳性（MSYS /tmp 路径）必须 cygpath 真路径 + md5 核对。体检 **122/122**（修复不扩面）。

**波次 34/35（11-14）** ntfy v2.37.2（go-sqlite3 CGO 设备编译，alpine 基片 apk gcc；E2E healthy）/ planka 2.3.1（dist 内容平铺 /app 根）；8 漂移修复（uptime-kuma node-gyp 成功；**wikijs 老 bug：WORKDIR 在 COPY 后 cp 静默失败**，3.3.1 才是第一个真正能跑的版本）。GOTOOLCHAIN=auto 破 go1.27.4 锁。体检 **124/124**。

**波次 36（11-14）** docmost 0.97.0（**官方 .dockerignore 含 `**/dist`** 吞产物 → 解包后删除）/ trilium v0.107.0（12 轮 rolldown 最完整战例：pnpm12 二进制无 loong64 → PC 预构建 client；better-sqlite3 三重坑；USER node 卷属主冲突）。LAN 直连取代隧道。Python 系整体推迟（uvloop/bcrypt）。体检 **126/126**。

**波次 37（11-14）** nodebb v4.16.8（**sass-embedded 的 require 不抛、compile 时才炸** → 显式卸载强走纯 JS 回退；sharp 懒加载降级）。**系统性坑：新应用 delta 必须含 docker-compose.yml**（否则 detail 回源 404 报下架）。体检 **127/127**。

**波次 38（11-14~15）** tailchat v1.11.18（17 轮：--filter 包名坑、prepare 打地鼠全 ignore-scripts、node20 moleculer performance.now 解构 bind 补丁）；**伴生型应用方法论**：原生 docker 栈等价验证（redis+mongo+minio+tailchat 四容器 200；minio 显式 `server /data`）。体检 **129/129**。

**波次 39（11-15）** EASY 复核批 3 应用：dataease 3.1.0（阿里云 amd64 层抽取 + `/dev/tcp` 探针）/ onedev 17.2.0（Tanuki wrapper 依赖 WRAPPER_PORT → **直接跑 Bootstrap 主类绕过 wrapper**）/ forgejo-runner 13.2.1（**goproxy 30 秒出 loong64**）。E2E 深坑：面板容器名用 appKey；dataease 冷启动 1678 秒 → **E2E poll ≥1800s**；伴生必须同网络 + DB 用户显式建。体检 **133/133**。

**波次 40（11-15）** VAR 批分诊：**node 运行时代位**（nodejs.org 停发 loong64 → lcr node22 retag 26.13.1 + CONTENT_PATCHES 行级钉定）；dotnet/keydb 入拦截；E2E 走 runtimes API（CONTAINER_NAME 必传、codeDir 预建、同名目录残留复用旧 .env）。体检 **133/133**。

**波次 41（11-15）** **php 运行时 alpine 化打通**：机制真相 = compose Up 本地命中即零拉取 + 容器内 install-ext 契约 → 预构建 `loong/php:8.4.1-ext`（102MB）+ 本地别名 `1panel-php:8.5.12` 对齐 UI 预填；**lcr php pear 配置死代理必须清**；builder 扩 CONTENT_REGEX_PATCHES/FILE_REPLACEMENTS。E2E php-fpm ready + 扩展清单。体检 **133/133** 无回归。

**波次 42（11-15）** redis-cluster / postgresql-cluster **语义重写**（bitnami env → command 化主从复制；pg wrapper + basebackup 流复制，E2E `pg_is_in_recovery=t` + walreceiver:streaming）；forgejo 16.0.7 交叉入库；dosgame 拦截（上游死亡）。**面板三大新坑**：compose 二次插值吃 entrypoint 脚本（必须 `$$`）、缓存白名单拷贝、DB compose 不随 sync 刷新。体检 **135/135**。

**波次 43（11-15）** drawio（Hub blob 级抽取 + tomcat 重打包）/ rsshub（PC pnpm deploy --node-linker=hoisted 无链接树）/ convertx 拦截（Bun 无 loong64）。**新工具 w43_pull.py**（PC 直连 Hub blob 拉取 + token 300s 过期自动续期）。体检 **136/136**。

**波次 44（11-15）** ghost 6.77.0：**libvips 8.18.7 源码编译链打通 sharp**（Node 图像系解锁）+ gosu shim 降权（`exec runuser -u "$u" -- "$@"`，v1 把 user 参数当命令）+ E2E mysql 显式建用户（wave39 教训重演）。体检 **137/137**。

**波次 45（11-16）** **战略资产 node 24.22.3 源码编译**（`--dest-cpu=loong64 --openssl-no-asm`，~50 分钟）；n8n 2.48.2（npm i -g --ignore-scripts + isolated-vm 手动 node-gyp；entrypoint CRLF → exec format error → 起临时容器修复 commit）/ certd 1.47.1（amd64 树换芯 + _symlinks.json manifest 设备重建 1337 symlink）/ nocodb 0.301.5（三原生：sharp c++17 / lz4 放弃 / sqlite3）。体检 **140/140**。

**波次 46（11-16）** **三镜像瘦身定型**（export/import 单层化：certd 4.38→1.4G / n8n 4.07→3.22G / nocodb 5.09→2.11G）；newsnow（standalone 树换芯）/ koishi（**zip→tar 直转保 symlink**）；**commit 继承 ENTRYPOINT 且空数组被静默忽略**；**隧道 SFTP ENOENT 真因 = MSYS 路径转换**（MSYS_NO_PATHCONV=1）。体检 **142/142**。

**波次 47（11-16）** jsonhero（Remix 生产化重建：esbuild v0.14.51 loong64 编译配方 + remix 统一 1.7.2 + **SSR shim**（node24 navigator 全局 → document/sessionStorage 内存 shim））；mblog（**Java 首例**：temurin17 + jar 换芯 + 宿主 gcc 编 xerial sqlite native 放 /usr/lib）。audit 修 **latest 版本目录漏统计**（142→147）。体检 **147/147**。

**波次 48（11-16）** certimate v0.4.37（**GOTOOLCHAIN 版本敏感**：1.27 编译产物 jsontext 爆栈，1.25.14 修复；go:embed dist.tgz 需 --strip-components）。gap 普查 120 项分级定论（D 拦截候选/挂起解锁/可打批）。体检 **148/148**。

**波次 49（11-16）** bililive-go（**deb.debian.org 主源已收录 loong64**；CRA 前端 embed + TSC_COMPILE_ON_ERROR）/ siyuan v3.8.10（设备 CGO sqlcipher kernel + PC pnpm12 前端手动五包 + **OCR 整链裁剪**（onnxruntime 无 loong64，`//go:build !cgo` 回退））；坑：sh -c 单引号截断变 `tr -d r` 删光字母 r、commit 不继承 run 的 -w WORKDIR。体检 **150/150**。

**波次 50（11-16）** mliev-dwz v2.24.1（cnb.cool 源 + vben pnpm10 嵌套解析钉版法）/ redpanda-console v3.14.0（bun 1.4.3 npm 装法 + rsbuild embed）；**面板忽略普通应用 CONTAINER_NAME**、kafka advertised listener 9092 装法。体检 **152/152**。

**波次 51（11-16）** logto 1.46.0（PC 全量构建 + 设备 prod install；上游 Windows bug 反斜杠未归一化；seed 要 CREATEROLE）/ umami 3.5.0（**Prisma 7 纯 JS adapter 解锁 + 自写 SQL 迁移器**；PC next standalone trace 不完整补洞）。**侦察版本必须对齐镜像站最新版**。体检 **154/154**。

**波次 52（11-16）** kkfileview（设备 maven + **TUNA 源 10 分钟替代 deb.debian.org 2 小时** + deb822 源文件路径 `.sources`）/ nexus（arm64 层抽 boot-jar 新式包法；**NEXUS_CONTEXT 空串 env 缺失即启动崩**——抄官方镜像 env 清单一个不落）。**持久容器分步组装法**定型。体检 **156/156**。

**波次 53（11-17）** sonarqube 26.11：**架构级发现——lcr temurin = Zero VM 无 JIT（SHA 慢 130-180 倍）** → Loongnix 官方 JDK21 HotSpot docker cp 打进镜像；ES 9 nativeaccess 无 loongarch64 目录 → FFM 全禁；远程 DB 检测强制 bootstrap checks → `sonar.es.bootstrap.checks.disable=true` 烤入。体检 **157/157**。

**波次 54（11-17）** 清尾款：TestGzipTemplate 三波遗留修复（Windows autocrlf → `$` 锚被 `\r` 挡）；**D 层拦截落表**（no_rule 99 应用全量分诊：34 拦 / 40 候选）；mysql-cluster 漏映射补规则。**builder 惯例：后加映射规则必须同时加空 CONTENT_PATCHES 键**。体检 **158/158**。

**波次 55（11-17）** kubepi（3 前端 embed + gotty creack/pty 升级破 loong64 + loongnix apt kubectl 提取）/ mattermost（amd64 层换芯 + **go.work 本地替换 server/public**；releases CDN 403 → 层抽取）。compose `${}` 布尔字段漏传即 15 秒 InstallErr。体检 **160/160**。

**波次 56（11-17）** **Rust 首试** meilisearch 1.56.2（rustup `1.98.1-loongarch64-unknown-linux-gnu` 官方通道 + rsproxy；ring generic C 可跑；**容器内写配置 base64 双层包裹**绕引号地狱；tini ENTRYPOINT 对齐 compose `sh -c`）。体检 **161/161**。

**波次 57（11-17~19）** rustfs + stalwart + vector 三应用全链（双会话并发碰撞事件与零击杀出货协议）：**rustfs 497MB 无 LTO 二进制 bfd R_LARCH_B26 溢出打地鼠 → `/usr/local/bin/cc` 放 lld 包装器通解**（保 cargo 缓存）；console UI = rust-embed 编译期内嵌（git 只有 .gitkeep → dl.rustfs.com zip 填充 + touch 强制重编）；UI 在 `/rustfs/console/` 子路径（`/login` 穿透 S3 被当桶名）；vector 四坑 + stalwart rocks 砍特性。体检终态 **137/137（全版本口径）+ audit20 163/163 离线口径** 双绿；E2E 3/3；repo 3 commits。

**波次 58（11-19）** rustdesk-server 1.1.16（8 轮：ring 0.16 三链拆解 + nix 0.23 升级 + **Cargo.lock 必须 cargo update** + s6 替代双进程 + **HOME=/data 才持久 keypair**）；rocketmq-dashboard（jar 抽取 + loong/java:21，30 分钟速胜）；qinglong（**loong64 已从 debian-ports 毕业 → 主档案 sid 正解**；umi 4.4.4 node≥22 需 http_parser shim + esmi stub；node-gyp@10 救 py3.13）。体检 **132/132**；repo bdbeef8+9aca173。

**波次 59（11-20）** cloudbeaver（app 层/JRE 层分离抽取泛化）/ silo（PC go 交叉 1 分钟 96MB，pgsty/silo）；blinko 双阻断拦截（Bun+Prisma）；**黑名单遮蔽活规则发现**（isBlocked 在 map 之前判定——入库后必须清同 repo 历史黑名单）。体检 **134/134**。

**波次 60（11-20）** nginx-proxy-manager（**s6 复刻术**：entrypoint 复刻 prepare 链 + 双进程；debian nginx 模块化 include + libnginx-mod-stream；nginx 临时目录 grep `*_path` 全预建）/ pgadmin4（PyPI wheel 自带预编译 JS 跳过 monorepo + 设备源编 venv：cffi 要 python3.14-dev、gssapi 要 libkrb5-dev、brotli 钉 1.1.0、psycopg[binary] 永无 loong64 → 纯 python + 运行时 libpq5；首启迁移读 PGADMIN_SETUP_*）。**铁律：复杂 Dockerfile patch 用 Write 整文件**。体检 **136/136**。

**波次 61（11-20）** zitadel v4.19.4 **史上最重 Go 单体**（173MB 单二进制嵌 Angular console）：PC 五段管线（buf 9 插件全本地 → statik×4 漏=运行期 panic → 三层 TS 依赖 → console 5 处 strict-null 补丁 → GOARCH=loong64 交叉）；v4.19 env 半失灵（MASTERKEY 只认旗标 / DB 只认 DSN 单变量 / TLS 只认旗标 → entrypoint 自动补）；E2E 密码策略差一个 `!` 就 InstallErr。体检 **137/137**。

**波次 62（11-20）** twenty CRM v2.58.0 **龙芯最重 JS 全栈单体**（22k 前端模块 + 2600 TS 服务端）：前端四修复（lingui enforce:pre shim / monaco worker 打桩 / renderer dist 桩 / 8GB 堆）+ **服务端必须全量 tsc**（SWC 枚举守卫 → UndefinedTypeError；tsbuildinfo 必删）+ 运行时三换芯（node_modules/src 软链 / macro CJS shim / bcryptjs）。商店侧删 13 个老版本目录只留 2.58.0；healthcheck retries=60（首启迁移 ~165s）。体检 probe **122/122**、E2E 3/3。

**波次 63（11-21）** mcsmanager-daemon/web（webpack BUNDLE=1 自包含 + **lib 三源**：PTY 官方 loong64 静态 ELF / Zip-Tools 交叉 / sid 7z 包装）/ linkding 1.47.0-plus（uv 导出 + maturin Rust cryptography + **uwsgi 运行态必须补 libpython3.14**（ldd 定位法）+ SQLite ICU 扩展自编）。**丢包链路作战纪律**（base64-over-exec / flock 守护脚本 / pkill 自匹配三连）。体检 probe **125/125**。

**波次 64（11-21）** Python 批：trendradar（uv 导出 + litellm 树全源码编 + supercronic PC 交叉）/ xiaomusic（pdm 三坑 + Pillow 运行时缺 libtiff6）/ filecodebox（五版全建 + 双前端 PC 预构建 + --require-hashes）；**断链救场 = paramiko 嵌套跳板**（VPS → direct-tcpip → 设备）；`${DATA_PATH}` 面板不写 → 改 `./data` 自包含。体检 probe **128/128**。

**波次 65（11-21）** domain-admin（PyPI sdist 逐版装 + **商店 compose 是 v 前缀 tag 需别名对齐**）/ calibre-web（复刻 s6 启动命令）/ qiandao（master HEAD + 钉版升 13 项 + pycurl 源编）；**Docker COPY 目录平铺语义炸包结构 → 整树 COPY**；prep 脚本 rmtree 吞手写 Dockerfile → 2B 空文件。体检 probe **131/131**。

**波次 66（11-21）** OpenResty 安全更新（CVE-2026-123007）：-2-2 补丁镜像重建（**sha256 钉值 bit-exact**；补丁从 Hub amd64 镜像层提取）+ **已装实例真升级**（installed/op upgrade API，pullImage 必须 false）；**商店自动同步链路发现**（上游发布→镜像合并→面板同步全自动，loong64 侧唯一必做 = 本地镜像构建+push）。体检 probe **131/131**。

**波次 66b（11-21）** 数据盘清理 263G（95%→49%；du -BG 向上取整陷阱、root 属主 rmtree 静默失败、三口径以 df 为准）；**ACR 主源收官**：293 tag 推送 + 全量 digest 校验 293/293 + **逐仓库设公开即匿名拉**（主账号 AK 批量公开 156/156）+ **agent 二级回源**（预烘焙 ref 盲区 + loong/ 命名空间两坑）。

**波次 67（11-21）** koodo-reader（amd64 层抽取 + Go 交叉 + caddy 底座同版；多层解包按层序防覆盖）/ cordys-crm（Java 伴生栈：**debian dash 不支持 `[[ ]]`，ENTRYPOINT 必须 bash** + appuser + libatomic1 + wait-for-it 1800s）/ mkdocs-material（PEP668 + 禁 pip 自升级 + 源编 pillow）；**选型矩阵法**（catalog-diff 会低估，须对规则表逐 ref 分类）；ACR 296/296 匿名一致。体检 **132/132**。

**波次 68（11-21）** nocobase（**MSYS tar 解层把 symlink 物化 → 设备侧解层重建**；license-kit Proxy stub + builtIn 剔 plugin-license；PANEL_DB_TYPE=postgres 方言名）/ synapse（apt rustc 1.85 + 钉 cryptography 44 + TUNA pypi + 手写 log.config + 首启 generate）/ lsky-pro（lcr php:8.2-apache 恰好同版；pear 死代理再清）；**商店 latest 版本目录陷阱**（官方带全版本历史，装的是 latest → 补建 cordys 1.9.7/mkdocs 9.8.1/nocobase 2.2.41 + NONLOCAL 告警机制诞生）。体检 **137/137**、ACR 302/302。

**波次 69（11-22）** odoo（**arch:all deb 抽树** + pytz 2024.1 zipfile 影子路径修 py3.14 崩溃 + gosu 入口修卷权限 + **规则键=裸 repo 名**）/ zabbix-server 7.4.5（C 源编三镜像 + jar 免 maven + 纯 PHP ui；libxml2-16 包名/libevent 4 拆包 + 首启 schema 导入 --skip-ssl）/ dbx（Rust 设备编 + 4 个 github git-dep vendor 三管齐下 + hotbundle feature 互斥删 dep 留 no-op 门）。体检 **142/142**、ACR 7/7。

**波次 70（11-22）** netdata v2.12.3（C+Rust+Go 全源码：**installer `--install-no-prefix / ""` 空串载荷参数** + go bin wrapper 强制代理 + **corrosion cmake 变量 sed 注入** + **submodule 烤入** + -disable-ml + runtime t64 名族）/ docker-mailserver 16.0.1（**rspamd 无 loong64 自动回落 amavis** + p7zip→7zip + ClamAV UA 直下 cvd + sid tar 1.35 -z 怪癖两步解包 + **DMS 无账号 40 秒关停生命周期**）。体检 **144/144**、ACR 2/2。

**波次 71（11-22）** **GreatSQL 8.0.32-27 全源码编**（无任何官方 loong64 二进制）：gcc-14 强制 + 4 处缺 include 批补（make -k 一轮收集）+ cmake flag 终集（WITH_ICU=**system** 字面量等）+ **官方 my.cnf 占位符替换**（bind 文件 cat 回写）+ entrypoint 丢 "mysqld" 参数 + ICU 版本漂移；**持久容器构建法定型**。体检 **145/145**、E2E 5/5（VERSION()=8.0.32-27 精确）。

**波次 72（11-22）** zabbix-xinchuang-edition 7.0.27 四镜像全栈：**官方 zabbix-docker 仓库照抄法**（源码 tarball 不含 Dockerfile，entrypoints 全 shell 无架构性直接 COPY）；configure 两坑（7.0 默认 PCRE1 须显式 --with-libpcre2 + IPv6 默认关须 --enable-ipv6）；web 镜像 DAEMON_USER 必显式；db-init 与 server 并发抢初始化是设计容忍。体检 **151/151**、面板真装 7 容器全栈。

**波次 73（11-22）** TDengine 3.4.3.9 全源码（**BUILD_VER_CPUTYPE=loongarch64 必须显式**否则回退 x64 炸 cpuid.h；rocksdb 三连修 -mcpu→-march/死代码重写/gcc16 -include cstdint；**内部 dmodule 符号补位**真实现）+ Arcadia 1.2.0（**Prisma 7 driver-adapter 纯 TS 解锁** + PC 预生成 + seed sqlite 首启注入 + node-pty/better-sqlite3 设备源编）；MAPPING_PORT 范围值坑。体检 **153/153**、ACR 2/2。

**波次 74（11-22~23）** LobeChat 1.143.3（**junction shim 破 Windows symlink 特权墙**（目录链接 junction + 文件 hardlink，tar -h 解引用）+ changelog SSG force-dynamic + nft 不穿透 junction → 懒加载长尾设备 fill.sh 补链 + 5 缺口判可接受降级）/ UPage 2.0.0（Prisma 6.16 engineType=client 复用 wave73 模式）；**NONLOCAL 10→3 终审**（music-tag-web 上游闭源化实证拦截、palworld/photoprism/laya-server/vane 落表）；`set(triple-quote)` 迭代字符不迭代行大坑。体检 **155/155**。

**波次 75（11-23）** affine（层抽取 + Prisma 6.16 纯 TS + **自家 Rust napi 设备源编**（aws-lc→ring）+ loong-sql-migrate 迁移器 + pgvector 伴生）/ teable（**Prisma 史上最深一战**：bundle 内联 6.2.1 客户端与 6.16 runtime 协议错位 → **运行时岛屿 + connect 桥接**（检测实例形状现场重建原生 adapter）8 轮迭代终解）；**audit 158/158 全 200、NONLOCAL=0（268 应用全量收敛，无灰区）**；ACR 3/3；累计 148/268 可装。

**波次 76（11-23）** 上游漂移响应（46 应用/68 新版本守望）：15 tag 构建（gitea 28.4.1 vite 迁移、**komari 官方 loong64 资产直用**、valkey×4 单像多 tag、maddy bins 路径坑）+ ACR 15/15 + 18 版本同步镜像站（**同步后必须重启 1panel-agent 才重拉索引**）；三例证据化延后（wikijs 3.x 无源 / nezha 前端缺 / dbhub 2.0 TS 重写）。体检 **161/161**。

**波次 77（11-23）** 待建清单续清 8 tag：stirling/mkdocs/nexus/onedev/waline/forgejo（**codeberg git 锁文件必须浅克隆；forgejo 15 还是 npm ci + webpack；templates/options 需落盘**）/dataease×2（阿里云层抽取）；镜像站 local 21 版本。体检 **161/161** 持续全绿。

**波次 78（11-23）** 重型清单 8 家：dwz/redpanda-console/nocobase 2.2.49/npm 2.17.1/siyuan v3.8.11（**kernel CLI 改 cobra serve 三修**）/n8n（**docker exec -d 真脱管防 SIGHUP 杀编译**；isolated-vm 需 g++-14 显式）/dbx（patch 改值而非插键）/netdata（官方 tarball 已内嵌 submodule）；同内容 build 两次 digest 不同 → ACR 删行强推。体检 **169/169**。

**波次 79（11-23）** twenty 2.60.3（上游最新，波次 62 配方的体系化升级）：**nx 隐藏构建步骤**（shared/emails/client-sdk dts 发射 + twenty-sdk 7 个 vite 配置 + client-sdk 拷入 dist/assets）+ **nest-cli 资产布局**（ASSET_PATH=dist/assets，w79_assets.js 复刻 18 规则 70 文件）+ vite8=rolldown 钉 7.3.7 + tsgo→tsc + sass-embedded 改名禁用 + 服务端裸 tsc（7 残余错误全为上游类型债，不影响 emit）；**补丁脚本从原始 tarball 逐字节验证**（抓出 4 处正则缺陷）；冒烟首启 160s 三 200；商店 compose healthcheck 收紧 → retries 60 修补；ACR 推送 + 匿名 MATCH；audit **170/170**、面板 E2E 3/3。

**波次 80（11-23，复核波）** w79 收官报告中「v2.58.0 缺 dist/assets」判定**复核推翻**：按 v2.58.0 自己的 nest-cli.json 逐规则核对 18/18 规则 70/70 文件全在，client-sdk 内嵌 metadata.mjs 在位，商店 compose 宽窗口——**2.58.0 无需重建**；根因是 w79 核查时查错路径（WORKDIR 是 /app/packages/twenty-server）。memory 已更正。

---

## 6. 不可移植项与拦截清单（D 层）

拦截机制：agent `loong64BlockedRepos` 表，安装时落盘前拦截并返回中文提示（UI 红色 toast 已实测）。现 **58 条**，按因分类：

| 因 | 代表项 |
|---|---|
| LLM/AI 生态（GPU/NPU 依赖） | vllm、ollama、localai、sglang、comfyui、langbot、langflow、astrbot、maxkb、sqlbot 等 14 |
| 重型 C++ DB | clickhouse（另实测 23.8.16.40-lts 启动即 SIGSEGV）、oceanbase、starrocks、manticore、typesense |
| Python 巨栈 / chromium | home-assistant、jupyter-scipy、archivebox、changedetection.io、browserless |
| 大型平台 | discourse、huginn、jumpserver、metersphere、onlyoffice、openlitespeed、gameservermanager 等 8 |
| 运行时缺失 | dotnet（mcr 无 loong64）、keydb、convertx/blinko（Bun）、umami 早期（Prisma，后随 Prisma 7 解锁转正） |
| 闭源 / x64 产物 | music-tag-web（上游闭源化实证：发布镜像为私有 Django 5.2.18 + Cython .so x86）、palworld（steamcmd）、photoprism（libtensorflow）、laya-server（torch）、vane（playwright+onnx）、windows、mssql、zfile（native-image） |
| 上游死亡/依赖腐化 | dosgame（repo 404）、rustdesk-server 早期（依赖腐化，w58 复活）、couchdb（mozjs 版本链断裂） |

证据化延后（非拦截，待条件）：wikijs 3.x（上游无源码发布）、nezha（前端 embed 产物缺）、dbhub 2.0（Go→TypeScript 重写需新配方）、codex-shell 类。

---

## 7. 当前状态与遗留事项

### 7.1 当前状态（2026-11-23）

- 体检 170/170 全绿；NONLOCAL=0；面板日常在用（用户浏览器验收过多轮）。
- 滚动维护闭环：`roll_maint.py` 一键巡检 + 每日漂移 automation + 周备份 crontab；上游持续发新版本 → 按「检测→评估→构建→采纳→E2E」循环常态响应（w76-79 即三轮实战）。
- 上游回馈：appstore 配方 PR #10458 OPEN；公开仓库 1panel-appstore-loong64 为双层分发（本地 registry 主源 + ACR 匿名备源 + agent 二级回源）。

### 7.2 遗留与已知边界

1. **用户侧待办**：两个阿里云 AccessKey（RAM `（RAM子账号AK·ID已隐去）`、主账号 `（主账号AK·ID已隐去）`）已约定不再使用，**请尽快在控制台删除**（主账号 AK 权限无边界，优先）。
2. **twenty v2.58.0**：无资产缺口（w80 已复核），但如需 w79 级验证深度（逐字节可复现 + E2E 3/3 新版口径）可选重建；现状 w62 E2E 3/3 仍有效。
3. **验证深度边界**：部分应用的 E2E 为端点级（HTTP 200/登录页），未覆盖全部业务功能；twenty 继承 w62 限制（lingui shim → 部分未翻译文案、renderer noop、bcryptjs 慢 10 倍）。
4. **延后池**：wikijs 3.x / nezha / dbhub 2.0 三例证据化延后；PHP8 老版本底座别名等低优先项。
5. **PC 侧文档**：`1panel_port/` 与公开仓库的 README 未必反映 w76-79 的最新配方（复用配方以 mega216/*.sh 与各波 memory 为准）。
6. **运维注意**：设备会随用户在公司/家之间搬动（IP 段 192.168.0.x / 192.168.3.x）；失联先找新 IP，勿急疑服务。

---

## 8. 附录

### 8.1 关键工具与脚本资产

| 位置 | 资产 |
|---|---|
| 设备 `/home/lingke/mega216/` | 各波 E2E/同步/体检脚本（w29_e2e_device.py 及后代、audit 三件套、roll_maint.py、upstream_check.py）、配方脚本 w5x-w79_*.sh |
| PC `w79_srcs/`（每波同名目录） | wave 专用脚本（patch/inner/assets/stage/smoke/verify/e2e/cleanup） |
| PC `1panel_port/` | 1Panel fork、补丁 v19、交叉编译 toolchain（go/node24/bun143）、pipeline.py + specs |
| 公开仓库 zhenglibing/1panel-appstore-loong64 | pipeline + 23 specs + openresty/7 应用 loong64 配方 + README |
| 设备 `/home/lingke/w66_acr_push.py` | ACR 推送器（--user/--pass 参数传凭据；done-list 断点续传） |
| 设备 `/home/lingke/openresty_build/` | OpenResty loong64 重建套件（~90M） |
| `E:\backup_2k3000\` | 备份异地副本（w23/w26 三包 + registry 卷 13.87G 双副本） |

### 8.2 权威数字速查（2026-11-23）

- 体检：**170/170**（143 local manifest 200 + 27 lcr 缓存命中，0 miss / 0 NONLOCAL）
- 本地 registry：**179 仓库 / 355 tag**；设备 docker images **798**
- ACR：done-list **370 条**（293 全量校验 bit-exact + 后续增量逐波 MATCH）
- 商店镜像站：**268 应用**全量（/opt/loong-store，nginx :8082）
- 已移植应用：**148 / 268**；拦截 **58 条**；运行时 VAR 代位 7 类
- 面板：v2.4.2 fork（补丁 v19，agent 规则随波演进至 w79）

### 8.3 相关文档（本仓库）

- `README-1Panel移植适配手册.md` —— 面板交叉编译与安装包
- `README-商店应用移植矩阵.md` —— 268 应用 A/B/C/D/VAR 分层矩阵（w48 后增量以波次 memory 为准）
- `README-商店应用移植报告-mega216.md` —— 216 应用 B 层评估与 46 入库详录
- `README-网卡驱动修复报告.md` / `README-2K3000-Docker安装手册.md` / `README-远程桌面方案.md` —— 平台层
- `README-覆盖缺口分析-20261111.md` —— 缺口分级方法论（gap_analysis.py 可重跑）
