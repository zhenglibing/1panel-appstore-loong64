# 龙芯 2K3000（Loongnix 25）移植 1Panel 完整手册

适用：零刻 ME Pro-龙芯（2K3000 / loongarch64）　|　目标版本：1Panel v2.4.2（2026-10-30 发布，当前最新稳定版）
移植方式：Windows 交叉编译 → 本地 loong64 安装包 → 设备部署 + 应用商店镜像映射层
本手册 2026-11-06 于真机实测产出，照做可复现。

---

## 0. 结果速览

| 项目 | 状态 |
|---|---|
| 1Panel core + agent（loong64 静态二进制） | ✅ 编译部署成功，**源码零修改** |
| 面板服务（systemd 双服务开机自启） | ✅ active，Windows HTTP 200 |
| 面板地址 | `http://<设备IP>:10086/（入口已隐去）`（lingke / （密码已隐去））。设备 IP 随网络变化：公司有线 `192.168.0.59`、家里无线 `192.168.3.35`（（WiFi-SSID已隐去））——换了网络以路由器后台或 `ip a` 为准 |
| 应用商店（官方源，268 个应用） | ✅ CDN 同步正常（无需 GitHub） |
| 商店装应用（Redis/MySQL/PostgreSQL/nginx…） | ✅ 镜像映射层实测闭环：商店装 Redis 8.10.3 → 自动改写 lcr redis:7.4.1 → 容器运行可访问（2026-11-06 用户验收） |
| 网站/建站模块（OpenResty） | ✅ **已打通**：自建 loong64 镜像（17 轮迭代，含 WAF/brotli/lsqlite3）→ 本地 registry → 商店安装 → WAF 2.0 加载 → 静态站建站闭环（2026-11-06 用户验收，见 §8） |
| 本地镜像仓库 | ✅ `127.0.0.1:5000`（registry:3.1.1 容器，自建镜像统一命名 `loong/<app>`，见 §8.4） |
| 兼容矩阵 | ✅ 268 应用四层盘点落盘《README-商店应用移植矩阵.md》；不可移植应用安装时给明确中文提示（D 层拦截） |
| 重启持久化 | ✅ 2026-11-06 实测：重启后 6 服务全部自启，dc-Redis 自动拉起，面板 HTTP 200 |
| 待办 | 上游 PR（§12）；阶段二 B 层应用滚动构建（§12 末） |

## 1. 背景：1Panel 架构与龙芯适配的难点

1Panel v2 是 **core + agent 双 Go 二进制**架构（core 管 web UI/认证，agent 管本机操作，gRPC 互联），前端 Vue3 构建产物通过 `go:embed` 打进 core 二进制。龙芯适配的四个难点与结论：

| 难点 | 结论（均已实测验证） |
|---|---|
| 官方不发布 loong64 包 | 官方 stable 通道有 amd64/arm64/armv7/ppc64le/s390x/**riscv64**（无 loong64）→ 自行编译。上游曾有 loong64 构建修复 PR #8260（已合并）证明源码可编译 |
| Go 工具链 | 1Panel v2.4.2 的 go.mod 要求 **go 1.27.3**（正好当前最新）；loong64 是 Go 官方支持架构（1.19+） |
| CGO | **全栈 CGO-free**（sqlite 用 glebarez/modernc 纯 Go 驱动），`CGO_ENABLED=0` 可干净交叉编译 |
| 应用商店镜像 | 商店引用的 Docker Hub 镜像几乎都没有 loong64 manifest → 见 §7 镜像映射层 + §8 自建镜像 |

**应用商店机制**（v2.4.2 实测）：不是 git clone，而是从飞致云 CDN 拉取——
- 应用索引：`https://apps-assets.fit2cloud.com/{mode}/1panel.json.zip`（社区版 mode=`dev`）
- 应用包：`.../dev/1panel/{key}/{version}/{key}-{version}.tar.gz`（含 docker-compose.yml 模板）
- 安装时按模板渲染 compose 并 `docker compose up` → **镜像架构是唯一的坎**，CDN/网络本身无障碍（国内直连，无需代理）

## 2. 前置条件

**设备端**（本机均已就绪）：
- Loongnix 25.1，内核 6.6.52-loong64，root/ sudo 权限
- Docker ≥ 20（本机 26.1.5 + compose v2 插件，见《README-2K3000-Docker安装手册.md》）
- firewalld 运行中（安装脚本会自动放行面板端口，无需手动）
- 磁盘：/opt（系统盘 141G 空闲）放面板；镜像落 /var/lib/docker（NVMe 600G）

**构建端（Windows）**：
- Go：版本必须 ≥ go.mod 要求（v2.4.2 = 1.27.3）。国内镜像下载 zip 免安装：
  ```bash
  curl -L -o go1.27.3.windows-amd64.zip https://mirrors.aliyun.com/golang/go1.27.3.windows-amd64.zip
  # go.dev 直连超时用阿里镜像；解压到 1panel_port/toolchain/，用绝对路径引用
  ```
- Node ≥ 22.12（Vite 8 要求；本机 24.13）
- git、curl、python（打包辅助）

## 3. 源码获取与前端构建

```bash
cd 1panel_port/repo
git clone --depth 1 -b v2.4.2 https://github.com/1Panel-dev/1Panel.git
cd 1Panel/frontend
npm install --registry=https://registry.npmmirror.com --no-audit --no-fund
npm run build:pro
# vite outDir 直接指向 ../core/cmd/server/web（assets 子目录与 go:embed 声明吻合），
# 构建即放置，无需手工拷贝；产物约 30M
```

> 注：`Makefile` 里 `prepare_vm_helper` 引用的 `agent/utils/vm/helper/prepare.sh` 实际不存在（空目录），linux 构建目标也不调用它——VM 功能与本机无关，忽略。

## 4. loong64 交叉编译

```bash
export PATH="/…/1panel_port/toolchain/go/bin:$PATH" GOTOOLCHAIN=local GOPROXY=https://goproxy.cn,direct
cd 1panel_port/repo/1Panel/core
CGO_ENABLED=0 GOOS=linux GOARCH=loong64 go build -trimpath -ldflags '-s -w' -o ../../build/1panel-core ./cmd/server
cd ../agent
CGO_ENABLED=0 GOOS=linux GOARCH=loong64 go build -trimpath -ldflags '-s -w' -o ../../build/1panel-agent ./cmd/server
```

- 实测：**两个二进制一次编译通过，源码零修改**（bytedance/sonic 在 loong64 自动回退 encoding/json，无功能影响）
- 验证架构：ELF 头 `e_machine=258`（EM_LOONGARCH）
- 若在设备上原生编译亦可（apt 装 golang），但 5.8G 内存 + 龙芯 CPU 明显慢，推荐交叉编译

## 5. 制作 loong64 安装包

官方包结构（以 amd64 包为模板）：

```
1panel-v2.4.2-linux-loong64/
├── 1panel-core            ← 换成自己编译的
├── 1panel-agent           ← 换成自己编译的
├── 1pctl                 # CLI（安装时被 sed 模板化端口/账号/入口）
├── GeoIP.mmdb            # 19.5M IP 库，照抄
├── install.sh            # 真正的安装器，内部无架构检查，照抄
├── lang/                 # 安装器 i18n
├── initscript/           # systemd/sysv/openrc/procd 服务文件
├── 1panel-core.service / 1panel-agent.service
└── (可选) appstore.tar.gz   # 离线应用商店，自动落到 resource/offline/
```

制作脚本（对齐官方包结构，仅换二进制）：

```bash
# 解包官方 amd64 包作模板
curl -LOk https://resource.fit2cloud.com/1panel/package/v2/stable/v2.4.2/release/1panel-v2.4.2-linux-amd64.tar.gz
tar xzf 1panel-v2.4.2-linux-amd64.tar.gz -C template/
# 复制目录结构 → dist/staging/1panel-v2.4.2-linux-loong64，替换两个二进制
tar czf dist/1panel-v2.4.2-linux-loong64.tar.gz -C dist/staging 1panel-v2.4.2-linux-loong64
```

> 官方安装器 `install.sh` 内部**不做架构检查**（架构门槛只在 CDN 的 quick_start.sh 引导层），
> 所以包内脚本一行都不用改。本工作区 `patches/quick_start_v2_loong64.sh` 是给官方引导脚本
> 加了 `loongarch64→loong64` 分支的补丁版（留作上游 PR 素材），本地部署直接跳过引导脚本。

## 6. 设备部署

```bash
# Windows → 设备 传包（有线 2.5G 链路 58M 约 9 秒）
python ssh_exec.py --host 192.168.0.59 --put dist/1panel-v2.4.2-linux-loong64.tar.gz /home/lingke/

# 设备上：校验 → 解包 → 免交互安装
sha256sum 1panel-v2.4.2-linux-loong64.tar.gz   # 对照本地记录
tar xzf 1panel-v2.4.2-linux-loong64.tar.gz -C /tmp/ && cd /tmp/1panel-v2.4.2-linux-loong64
PANEL_PASSWORD='你的密码' sudo bash install.sh --non-interactive --lang zh \
    --port 10086 --entrance （入口已隐去） --username lingke \
    --password '你的密码' --install-docker n
```

安装器自动完成：binaries→`/usr/local/bin`、`1pctl` 模板化、systemd 双服务 enable+start、**firewalld 放行端口**（Set_Firewall 函数原生支持 firewalld/ufw）、检测已有 Docker ≥20 跳过安装（`--install-docker n` 双保险）。

参数校验规则：入口/用户名 `^[a-zA-Z0-9_]{3,30}$`，密码 `^[a-zA-Z0-9_!@#$%*,.?]{8,30}$`。

安装完成后：`http://<设备IP>:10086/<入口>` 即面板；`1pctl user-info` 随时可查凭据。

**实测结果**：core RSS 39M + agent RSS 75M，SQLite（纯 Go 驱动）WAL 落盘正常，Windows curl 面板 HTTP 200。

## 7. 应用商店 loong64 镜像映射层（核心适配工程，v2）

商店模板里的镜像（`redis:8.10.3`、`mysql:8.4.13`、`1panel/openresty:*`…）都没有 loong64 manifest，直接装必然失败。解法：在 agent 里加**运行时架构门控的镜像映射层**——只在 `runtime.GOARCH == "loong64"` 时改写，其他架构零影响（对上游无侵入，可合并）。

**新增文件** `agent/app/service/app_loong64.go`（+ 同名 `_test.go`，40 用例）：
- 解析 compose 的 services，逐个按规则表改写 `image`
- **改写只认精确规则白名单**（repo 全路径匹配），命中才改、不命中原样保留；digest 固定 / 已是龙芯仓库 / 带 `${}` 变量的引用自动跳过
- **D 层拦截**：`loong64BlockedRepos` 中的不可移植应用（jellyfin 等）安装时直接返回明确中文错误，替代晦涩的 manifest 报错
- 服务同时带 `build:` 段与发布 `image:` 时**照常改写**（OpenResty 模板就是这种形态；规则白名单保证不会误伤真源码构建应用——这是实测踩过的坑：早期"带 build 就跳过"的守卫让 OpenResty 改写静默失效）

**映射规则三类**（完整表以代码为准，`loong64RepoRules` / `loong64BaseRules` / `loong64BlockedRepos`）：

| 类型 | 规则 | 示例 |
|---|---|---|
| lcr 直映 | 商店 repo → `lcr.loongnix.cn/{namespace}/{repo}`，主版本路由 + 兜底标签 | `redis:8.10.3` → `lcr.loongnix.cn/library/redis:7.4.1`；`mysql:5.x/8.x` → 5.7.29-an23 / 8.4.3；`postgres:13-18` → 13.19-alpine3.21 / 15.7-sid / 17-sid |
| 本地 registry 自建 | `1panel/openresty:*` → `127.0.0.1:5000/loong/openresty:*`（保 tag） | OpenResty 见 §8 |
| D 层拦截 | `jellyfin/jellyfin` → 返回中文错误"该应用暂无 LoongArch64（龙芯）版本镜像…" | .NET 无官方 loong64 移植 |

覆盖 redis/mysql/mariadb/postgres/mongo/memcached/rabbitmq/emqx/nats/elasticsearch/kibana/logstash/influxdb/phpmyadmin/wordpress/yourls/flarum/postgis/pgvector/registry/jenkins/gitlab-ce/grafana/jaeger/consul/portainer-ce/neo4j/2fauth + 基础镜像 alpine/busybox/python/node。**各版本标签 2026-11-06 逐一在 lcr.loongnix.cn 核实存在**。

**接线 3 处调用点**（安装 / 更新重装 / 升级渲染 compose 反序列化之后，各 +3 行）：
1. `app.go → installWithHooks()`：`mapImagesForLoong64(composeMap)`
2. `app_install.go → Update()`（高级编辑重装）：同上
3. `app_utils.go → getUpgradeCompose()`：同上

**真机测试**：`GOOS=linux GOARCH=loong64 go test -c` 交叉编译测试二进制 → 上传设备执行 → 40 用例全 PASS，含两个回归用例：① 复刻 OpenResty 商店模板（带 build 段）断言改写生效；② compose 级 D 层拦截返回中文错误（Windows 宿主无法直接跑：agent 含 Linux 专有 syscall，目标机跑正好 100% 真实）。注意测试台架需在 `TestMain` 给 `global.LOG` 挂静默 logger，否则映射成功路径打日志时空指针段错误。

**排障两板斧**（改写"没生效"时）：
```bash
grep -n image /opt/1panel/apps/<key>/<name>/docker-compose.yml   # 落盘 compose 是否已改写
grep loong64 /opt/1panel/log/1Panel.log                          # 有无 [loong64] 改写日志
```

**镜像预热**（安装秒完成）：
```bash
for img in redis:7.4.1 mysql:8.4.3 postgres:15.7-sid nginx:1.28.0; do
  docker pull lcr.loongnix.cn/library/$img; done
```

## 8. OpenResty loong64 自建镜像 + 本地 registry（建站模块解锁）

建站/反代/WAF 全依赖 OpenResty 应用，商店引用 `1panel/openresty:1.31.8.1-2-1-noble`（amd64）。lcr 有 openresty 但最高 1.25.3.2，不满足建站模块要求 → **按官方构建配方自建 loong64 镜像**。

### 8.1 官方配方与改造

官方配方在 `1Panel-dev/appstore` 仓库：`apps/openresty/1.31.8.1-2-1-noble/build/Dockerfile`（FROM ubuntu:noble 全源码编译 OpenSSL 3.5.9 / PCRE2 10.49 / LuaJIT / LuaRocks + brotli 等动态模块 + 1pwaf WAF）。loong64 版改造（成品 `1panel_port/openresty_build/Dockerfile.loong64`，与设备 `/home/lingke/openresty_build/` 为重建套件）：

1. **底座**：`lcr.loongnix.cn/library/debian:sid-20250615`（apt 兼容，改动最小）。坑：lcr 底座自带 debian-ports 源对 loong64 已 404（loong64 包已迁入 debian 正式仓库）→ 整体重写 `/etc/apt/sources.list.d/debian.sources` 指向 tuna `/debian` sid；基础镜像无 ca-certificates，用 http 源
2. **LuaJIT 替换**：OpenResty bundle 的 LuaJIT 不支持 loongarch64 → 换 `loongson/LuaJIT`（v2.1-loongarch64 分支）源码并入 bundle 目录再 configure
3. **消除 bootstrap**：官方 Dockerfile 从上一版官方镜像 COPY 预编译产物（amd64 blob）→ 全部改为同构建内源码编译：ngx_brotli（含 vendored google/brotli 的 c/ 子目录）、libmaxminddb、libinjection（`libinjection_sqli.c` 单文件）、lsqlite3（要 `-DluaL_reg=luaL_Reg` 兼容宏）、lfs
4. **1pwaf lua 部分**（脚本无架构性）：从官方 amd64 镜像 `docker create` + `docker cp` 抽出（国内经 docker.1ms.run 拉镜像 + `--platform=linux/amd64`）
5. **table.nkeys shim**（关键，17 轮迭代的最大发现）：`table.nkeys/.clone/.isarray/.isempty` 是 **OpenResty 自家 LuaJIT2 fork 的内建**（`lj_lib_prereg` 注册，不落盘），loongson/LuaJIT 没有 → 1pwaf 的 ipmatcher 和 lualib 的 lua-resty-openssl 启动即崩（容器 Exit 1）。修复：镜像内烘焙纯 Lua shim 到 `/usr/local/openresty/lualib/table/nkeys.lua`：
   ```lua
   return function(t) local n = 0 for _ in pairs(t) do n = n + 1 end return n end
   ```
   验证内置在构建里：`/usr/local/openresty/bin/resty -e 'assert(require("table.nkeys")({1,2,3,a="x"}) == 4)'`。注意 resty 完整路径 + 须在 `ENV PATH` 生效前的层里用全路径调用（踩过 exit 127）
6. 逐模块拆 `RUN` + `set -x`（buildkit 2MiB 日志上限会截断大步骤的报错；分层缓存也加速迭代）；Windows 拷贝进构建上下文的 sh 脚本/lua 文件须转 LF（git autocrlf 的 CRLF 会毁掉 nginx 模块 config 脚本）

### 8.2 构建与入库

```bash
# 设备上（约 25 分钟，8 核；失败重来缓存会加速）
cd ~/openresty_build
docker build -f Dockerfile.loong64 -t 127.0.0.1:5000/loong/openresty:1.31.8.1-2-1-noble .
docker push 127.0.0.1:5000/loong/openresty:1.31.8.1-2-1-noble
```
冒烟验收：`openresty -V`；brotli 两个 .so 在位；`resty -e 'require("lsqlite3"); require("lfs")'`；WAF 库 `libmaxminddb.so*` 链接链完整 + `libinjection.so`；容器日志出现 `Load 1Panel WAF Version:2.0`。

### 8.3 商店安装与建站闭环（2026-11-06 用户验收 ✅）

商店装 OpenResty（默认参数）→ 映射层改写为本地 registry 镜像秒拉 → 容器运行 WAF 加载 → 网站模块创建静态站 test01 → `curl -H 'Host: test01' http://127.0.0.1/` 返回 200 默认页。**注意**：浏览器访问用真实域名或 hosts 解析（`192.168.0.59 test01`）；直接用 IP 访问 Host 不匹配会落 nginx 默认 404，属虚拟主机正常行为。

### 8.4 本地 registry

```bash
docker run -d --name loong-registry --restart always -p 127.0.0.1:5000:5000 \
  -v loong-registry-data:/var/lib/registry lcr.loongnix.cn/library/registry:3.1.1
```
仅绑 127.0.0.1（本机免 TLS）；数据落 NVMe volume；面板/映射层引用统一 `127.0.0.1:5000/loong/<app>:<tag>`。后续阶段二构建的应用同入口入库（B 层流水线）。

## 9. 部署后配置加固

- **DNS 兜底**（路由器 DNS 开机瞬时抖动会导致面板日志报解析失败）。**每接入一个新网络（换 WiFi/插网线）给对应连接配一次**；⚠️ `nmcli con up` 会重启该连接，SSH 若走同一连接会瞬断（等它自动重连或重启设备即可，配置已保存）：
  ```bash
  # 公司有线 / 家里无线分别执行（连接名用 nmcli con show 查）
  sudo nmcli con mod '有线连接 1'    +ipv4.dns '223.5.5.5 119.29.29.29' ipv4.ignore-auto-dns no
  sudo nmcli con mod 'WONGOING_3-5G' +ipv4.dns '223.5.5.5 119.29.29.29' ipv4.ignore-auto-dns no
  sudo nmcli con mod '（WiFi-SSID已隐去）' +ipv4.dns '223.5.5.5 119.29.29.29' ipv4.ignore-auto-dns no   # 2026-11-06 家里已配
  ```
- 商店同步无需任何配置：社区版自动走 `apps-assets.fit2cloud.com`（国内 CDN，实测直连）

## 10. 日常运维

```bash
1pctl user-info      # 查面板地址/账号
1pctl version        # 版本（当前 v2.4.2, mode=dev）
systemctl status 1panel-core 1panel-agent
journalctl -u 1panel-core -f          # 日志
tail /opt/1panel/log/1Panel-Agent.log # agent 业务日志
```

**升级新版本**（官方发新版后）：重复 §3-§6（clone 新 tag → 编译 → 换包内二进制 → `install.sh` 会检测已安装并询问迁移，或直接替换两个二进制 + restart）。loong64 映射层文件在新 tag 上按 git patch 重放即可（改 3 个调用点 + 拷 2 个新文件）。

**卸载**：
```bash
sudo systemctl disable --now 1panel-core 1panel-agent
sudo rm -f /etc/systemd/system/1panel-{core,agent}.service
sudo rm -f /usr/local/bin/1panel-core /usr/local/bin/1panel-agent /usr/local/bin/1pctl /usr/bin/1panel
sudo rm -rf /opt/1panel
sudo firewall-cmd --permanent --remove-port=10086/tcp && sudo firewall-cmd --reload
```

**故障排查**：
| 现象 | 处理 |
|---|---|
| 浏览器打不开（超时） | `firewall-cmd --list-ports` 查 10086；`ss -tln \| grep 10086` 查监听 |
| 装应用报 no matching manifest | 该应用镜像不在映射表（§7 第二列清单）→ 用本地 compose + lcr 镜像替代 |
| 日志 DNS 报错 | 见 §9 DNS 兜底 |
| 升级 1Panel 后商店又装不上 | 新版本重放了映射层吗？对照 §10 升级流程 |
| MCP Docker runtime 警告 | 无碍，未启用 MCP 功能 |

## 11. 已知限制

1. ~~网站/建站模块不可用~~ → **已解决**（§8 自建 OpenResty 镜像 + 映射层 + 本地 registry，2026-11-06 建站闭环验收通过）
2. D 层不可移植应用（jellyfin 等 .NET/闭源系）：安装时映射层拦截并给明确中文提示，属预期行为；完整清单见《README-商店应用移植矩阵.md》
3. sonic JSON 库在 loong64 走 encoding/json 回退（大 JSON 场景略慢，无功能影响）
4. 面板"虚拟机"功能（v2.4 新增）依赖 QEMU 镜像体系，本机 5.8G 内存也不适合，未适配未启用
5. B 层应用（源码可构建但无现成镜像，如部分 Go/Node/Java 应用）尚未逐一构建——机制已就绪（§8.4 registry + §7 映射表追加），滚动批次推进

## 12. 上游回馈与自维护路线（波次二十一定型）

**上游结论**：PR [#14328](https://github.com/1Panel-dev/1Panel/pull/14328) 已提交并被维护者关闭（未合并，2026-11-07）——官方理由：应用包体系未为运行时镜像替换做逐应用兼容性验证、自建镜像仓长期维护成本高。**根因是 PR 形状而非质量**：架构专属映射表 = 上游背着无法 CI 验证的数据（GitHub 无官方 loong64 runner）+ `127.0.0.1:5000` 设备私有基础设施指向，这种"机制+数据混装"形状不可能被收。

**四路线决策（2026-11-09 定型）**：

| 路线 | 内容 | 状态 |
|---|---|---|
| **A fork 分支（主线）** | `loong64-support` 分支（基线 = v2.4.2 tag 832d367）3 commits：映射层 / php8 弃用豁免 / 商店源覆盖；push 至 fork `zhenglibing/1Panel`；升级流程 = rebase 新 tag → 真机门禁 → 交叉编译 → 部署；可发 release 二进制形成事实发行版 | ✅ 已落地 |
| **B 自建商店源** | agent conf `base.app_repo_url` 指向设备本机 nginx 容器（127.0.0.1:8082，只读挂载 /opt/loong-store）托管的镜像树（compose/tar.gz 内 image 已按映射表预改写）——应用更新不再依赖 agent 重编译，映射层退化为兜底 | 工具链就绪，设备侧待执行 |
| **C 机制版再提一次（收手即止）** | ①机制 PR：`app_loong64.go` 只留加载器，规则外置 JSON（上游收机制不收数据）；②数据 PR：appstore 仓库 build 目录提 OpenResty loong64 配方；③issue 先行 + 主动提出挂 2K3000 self-hosted runner（社区方案：kubernetes-loong64 示例 / loong64 组织 runner 二进制） | 择机，最多一轮 |
| **D 龙芯生态回馈** | B 层自建镜像构建配方贡献 Loongnix 社区（lcr/或社区仓库）——价值不依赖 1Panel 决策 | 择机 |

**分支与产物**：`1panel_port/repo/1Panel` 本地仓库（origin=1Panel-dev，fork=zhenglibing/1Panel）；分支 `feat/loong64-appstore-mapping`（PR #14328 历史分支，基于较新 upstream，保留不动）+ `loong64-support`（自维护主线）。补丁随分支重生成：v19 = `git diff 832d367 loong64-support`（7 文件 665+，对 pristine apply-check PASS）。

**阶段二 B 层滚动构建流水线（批次一、二、三完成 2026-11-06）**：流程定型——Windows 交叉编译（`CGO_ENABLED=0 GOOS=linux GOARCH=loong64`，Go 单二进制应用最快）→ 按**官方镜像布局**写精简 Dockerfile（底座 lcr alpine/busybox/node/php/temurin；Windows 打包需补 `RUN chmod +x`，tar 丢执行位）→ 设备 `docker build` → push `127.0.0.1:5000/loong/<app>:<同商店tag>` → `app_loong64.go` 规则表追加 + 单测 → agent 重新部署。**批次一（caddy / filebrowser / ddns-go，ddns-go 商店闭环）**；**批次二（typecho 复刻 [typecho/Dockerfile](https://github.com/typecho/Dockerfile)；uptime-kuma 原生 sqlite 设备编译，商店闭环）**；**批次三（halo-pro=社区 jar 挂 pro tag + lcr temurin 21；freshrss 复刻官方配方 + `FRESHRSS_DATA_PATH=/config/www/FreshRSS/data` 兼容商店挂载，商店闭环）**。踩坑：lcr node tag 带 `v` 前缀；npm 11 删 `disturl` → `ENV npm_config_disturl`；FreshRSS release 无 zip 改用 tag 克隆。出局：code-server、nginx-proxy-manager（构建过重，专项评估）、gitea（商店已换 commitgo/gitea-ee 商业分支）。构建上下文存 `1panel_port/phase2/`。下一批候选：按用户需求点单。

**mega216 全量批次（2026-11-07，B 层 216 应用逐一评估 + 46 个构建入库）**：评估三层证据——上游 manifest 架构探测（Docker Hub/ghcr/forgejo 匿名 API，结论：**216 个无一原生 loong64**）+ 逐应用语言/路线判定表（`phase2/mega216/curated.py`）+ lcr/apt 资产核实（debian sid loong64 有 qbittorrent-nox/valkey/zabbix 7.0 LTS/chromium 等）。构建走通用流水线 `phase2/mega216/pipeline.py`（clone→PC 交叉编译/前端构建→上载→设备 docker build→push→容器冒烟，断点续跑），按语言分波：Go 交叉编译 17 个；Java 发行包 8 个（temurin 底座，keycloak/nacos/rocketmq/sentinel/komga/kafka(KRaft 单节点适配层)/metabase/tomcat(bitnami shim)）；静态站 5 个；PHP 9 个（debian sid + php8.4-apache 模式——**lcr php 底座无 docker-php-ext-install，别用**）；Node 4 个（npm 全局包直装：verdaccio@7 需 Node24→sid nodejs；node-red@5 同）；apt-sid 3 个（qbittorrent/valkey/zabbix-agent）。**关键攻坚**：alist/sftpgo 的 sqlite 走 CGO → alist 换 glebarez 纯 Go 驱动、sftpgo 烘 bolt provider + env `SFTPGO_DATA_PROVIDER__DRIVER=bolt`；komga 自编 libsqlitejdbc.so（javac -h 生成 JNI 头 + `-DSQLITE_ENABLE_FTS5`）；gitea act_runner 从 gitea.com 直克隆。**判 D**（18）：mssql/teamspeak/windows(QEMU x86)/ollama 等 GPU AI 栈/palworld(x86 游戏)/openvpn-as/zfile(闭源)/harness 等。**判 F 暂缓**（62）：逐应用原因见报告。**流水线大坑**：Windows 上 `shutil.which('bash')` 会解析到 System32 的 WSL bash（Windows 路径全废）→ 显式钉死 Git Bash 路径；codeload tarball 兜底 git clone 抽风（但 tarball 不含 git submodule——certimate/rustdesk 栽在这）；docker build 轮询重试前必须 `docker rmi` 旧 tag（否则误判已建成）；同 tag 并发构建互踩。映射层 agent v8：+46 规则烤入 + **D 层拦截表扩充至 19 条**（18 个 mega216 拒绝应用 + jellyfin），真机单测 PASS，**mssql 商店安装 UI 级拦截验证通过**（红色中文提示 + 落盘前拦截，复验 jellyfin 行为一致）。逐应用全表：**《README-商店应用移植报告-mega216.md》**。

**波次二（2026-11-07）：dockge 1.5.0 入库闭环。**
**波次三（2026-11-07）：P 级补齐 8 个入库（memos/gatus/gitea-CE/beszel/prometheus/navidrome/gotify/sun-panel）——自建累计 55 个镜像，registry 67 仓库，商店可用 93/265（≈35%），映射规则 95 条（agent v10 真机单测 PASS + memos 商店端到端验证三证）**。
**波次四（2026-11-07）：P 级再补 6 个入库（opengist/screego/ezbookkeeping/adguardhome/memos/gatus）——自建累计 61 个镜像，registry 72 仓库，商店可用 99/265（≈37%），映射规则 99 条（agent v11 真机单测 PASS + opengist 商店端到端验证三证）**。
**波次五（2026-11-07）：forgejo-runner v13.2.1 入库（纯 Go，code.forgejo.org，--version 验证）+ clickhouse 判 D**——lcr 唯一 tag 23.8.16.40-lts 在 2K3000 上启动即 SIGSEGV 崩溃循环（39 次重启，非 OOM），降级映射不可用 → 移除规则改判 D（无可用 loong64 版本），应用记录/容器/镜像三清。自建累计 61 个镜像，registry 72 仓库，商店可用 99/265（≈37%），映射规则 99 条（agent v13 真机单测 PASS）。新坑：⑯cobra serve 类（screego）必须注入 `SCREEGO_EXTERNAL_IP` 否则启动即退出；⑰ezbookkeeping 官方布局需 public(dist)/conf/templates 三目录 + data/log/storage 运行目录；⑱交叉编译 go-sqlite3 是 stub——凡 mattn sqlite3 必须设备端 CGO 编译（gotify/navidrome/sun-panel 同）；⑲yarn 1 的 ERESOLVE/EBUSY：npm --legacy-peer-deps 或独立 --cache-folder。关键坑沉淀：⑧cobra 应用（beszel/gitea 系）需显式 serve 子命令与参数，否则打印 help 退出；⑨gitea 拒绝 root 运行 → su-exec 降权入口脚本（USER_UID/GID 兼容商店 compose 挂载）；⑩navidrome/gitea 的"强制构建标签哨兵"（conf/buildtags 等 go:build 守卫变量）——缺 `-tags netgo,sqlite_fts5` 就编译报 undefined；⑪gotify/sun-panel 的 docs 与 assets 为编译必需的生成包——打包上下文勿排除；⑫gitea webpack 需 `--disable-interpret`（node24 原生 TS 加载）；⑬prometheus react-app 需 CRLF→LF（prettier 检查拦截 Windows checkout）；⑭**docker commit 快照容器 CMD/ENTRYPOINT**——勿基于 sleep 容器提交（会顶掉原入口）；⑮商店安装可走页面同源 API（POST /api/v2/apps/install，X-CSRF-Token = pcsrftoken cookie），与按钮点击等价且更稳。关键新知：①**lcr 已有 node 22/24/26 全系 tag**（library/node，如 22.23.2、26.13.0-debian；记忆中"最高 v20"过时）——dockge 官方底座 node:22 直接对齐，node-pty 0.11.14 的 NAN 代码只在 node 22 可编译（node 24 V8 13 删 API，编译必挂）；②**npm ≥11.6/12 默认拦截依赖 install 脚本**（`npm warn install-scripts ... not covered by allowScripts`）→ 需在 package.json 加 `allowScripts: {包名: true}` 白名单，否则 node-pty/sqlite3 静默不编译；③**node-gyp 头文件必须走 npmmirror disturl**（`npm_config_disturl=https://npmmirror.com/mirrors/node/`，nodejs.org 直连不通）；④**Debian apt 的 node-gyp 会链 Debian node 的 libnode.so.<ABI>**，运行时用 lcr 官方 node 静态二进制时 dlopen 必挂 `libnode.so.137`——必须用 npm 版 node-gyp + 对应版本头文件；⑤**libuv io_uring 在 loong64+kernel 6.6.52 上会自旋挂死**（worker 100% CPU 空转、请求不响应）——统一烘 `UV_USE_IO_URING=0`（dockge 官方注释早有预警）；⑥esbuild loong64 二进制在容器内构建偶发 `service was stopped` → 前端产物改在 PC 构建（产物架构无关）；⑦商店安装按钮的坑：抽屉二次确认为 el-message-box 需 CUA 点其按钮**中心**（rect 左上角不触发），且抽屉残留实例会让 rect 超出视口（x=1870>1280）→ 刷新页面重来最省事。工程流程上 dockge 的前端走 PC 构建（vite 产物与架构无关）、设备端只 npm ci 出 loong64 原生模块，是 node 类应用的定型流水线。**waline 1.43.6 记 F 详注**：镜像可构建（@waline/core 需 PC pnpm 构建——rolldown 无 loong64 绑定；better-sqlite3 需 node-gyp 显式源码编译），但 thinkjs 4 API 层请求挂起（静态 200 / API 挂起，io_uring 修复后依旧，node 22/26 同现），待上游层面排查。上游 PR #14328 已被官方关闭（未合并，理由=应用包体系未配套验证+自建镜像仓长期维护成本），本地补丁持续重放。

**波次六（2026-11-08）：komari + openldap 商店端到端闭环，casdoor 镜像入库，couchdb 判 F——自建累计 64 个镜像，registry 76 仓库，商店可用 101/265（≈38%），映射规则 101 条（agent v14 真机单测 PASS；面板 Running 应用达 11 个）。**
- **komari 1.6.1 ✅**：komari/komari-web 双仓库组装——web/public/defaultTheme 需 dist.tar.zst + komari-theme.json 才能满足 go:embed；CGO 设备编译（lcr golang:1.26.8-alpine），apk 默认 dl-cdn 镜像在设备上会卡死、两阶段构建都要 sed 换 aliyun。商店安装端到端验证（HTTP 307 首装引导页）。
- **openldap 2.6.10 ✅（apt-sid + bitnami 接口仿真）**：debian sid slapd 2.6.14 + 入口脚本按 LDAP_ROOT/LDAP_ADMIN_PASSWORD 运行时 `dpkg-reconfigure` 生成配置（先配置→拷入卷→再换 /bitnami/openldap 软链的顺序不能反，否则首启即删库）；商店安装端到端验证（admin bind + ldapsearch 成功）。**两个 slapd 容器坑**：⑳LMDB 按 RLIMIT_NOFILE 分配 reader 表——Docker 默认 nofile 100 万 → 开机 calloc 72GiB 断言崩溃，入口 `ulimit -n 1024` 解决；㉑debconf 生成的配置引用 /run/slapd/slapd.pid，容器无 systemd tmpfiles，需 `mkdir -p /run/slapd`。
- **casdoor 4.6.0 ✅镜像入库（商店流程未装）**：web 强制 yarn 的 preinstall 摘除后改走 npm（**EBUSY 根因 = Windows Defender 实时扫描锁 yarn 缓存目录**；npm 缓存在用户目录不受影响，54s 装完 734 包）；modernc.org/sqlite v1.18.2 的 libc 不认识 loong64 → 升级 v1.34.5；go:embed 前端必须 COPY web/build；运行配置只认 conf/app.conf（driverName=sqlite 验证通过，env 覆盖不生效）；商店 compose 绑外部 DB，待面板装 DB 应用后可端到端。
- **couchdb/obsidian-livesync 判 F**：Debian 仓库无 couchdb deb（loong64 端口未带）、sid 只有 erlang-base 29 与 mozjs 140，couchdb 3.5 需 mozjs 91 链——源码路线要自编 SpiderMonkey（rust+autoconf2.13），成本过高延后。
- **流水线级新知**：㉒**商店 tag 无 v 前缀**（商店版本串 1.6.1 形态 vs 自建惯例 v1.6.1 → manifest unknown）——已批量补 36 个无 v 别名，新镜像直接双 tag；**/tmp 路径陷阱**——Git Bash /tmp 是 MSYS 映射，Python 解析为当前盘 E:\tmp，构建产物用项目内绝对路径，否则部署旧二进制；**商店端到端新姿势**——浏览器同源 fetch（页面登录态 + document.cookie 的 pcsrftoken 作 X-CSRF-Token；/api/v2/core/auth/login 密码为 RSA 包 AES 混合加密不必复刻），面板安装记录 `installed/op operate=rebuild` 可重试失败安装。补丁已重生成 v9（642 行，apply-check PASS）。

**波次七（2026-11-08）：casdoor + nezha 商店端到端闭环，postgresql 上线——自建累计 65 个镜像，registry 77 仓库，商店可用 103/265（≈39%），映射规则 103 条（agent v16 真机单测 PASS；面板 Running 应用达 14 个，零异常记录）。**
- **casdoor v4.25.0 商店版 ✅ 端到端**：商店要求的 v4.25.0 比先前自建的 v4.6.0 还新——按商店 tag 重建（yarn preinstall 摘除 + modernc sqlite v1.34.5 的组合在 fresh clone 上重放）。**核心发明：入口脚本 env→conf 落地**——casdoor 只认 conf/app.conf、完全不读 env，而商店 compose 传 driverName/dataSourceName env → 自建镜像加 /app/entrypoint.sh：`cd /app`（保住相对路径 web/build 静态资源，第一版 `cd /` 导致 / 404）+ sed 把 env 写进配置 + `-config=/conf/app.conf` 指向商店挂载。API 直装跳过了面板 UI 的自动建库 → 手动 `CREATE DATABASE casdoor` 后 rebuild 即通（/ 200、/api/health 200 casbin allow、postgres 绑定链路全通）。postgresql 商店安装走 A 层映射（16.15-alpine 请求 → ByMajor 16 → lcr 15.7-sid），healthy。
- **nezha v2.6.1 攻坚 ✅ 端到端**：官方 release workflow 即配方——①`script/fetch-frontends.sh` 的逻辑手工化：admin-frontend v2.3.6 + nezha-dash-v2 v2.4.2 两个 dist.zip 解进 `cmd/dashboard/{admin,user}-dist`（`//go:embed *-dist` 占位空目录编译即挂）；②`swag init --pd -d cmd/dashboard -g main.go -o cmd/dashboard/docs` 生成 swagger（swag v1.16.6 PC 装即可）+ go mod tidy；③mattn sqlite3 → 设备 CGO。**新坑 ㉓：valyala/gozstd（经 VictoriaMetrics tsdb 依赖引入）按文件名选预编译 libzstd blob，没有 loong64 变体 → undefined ZSTD_* 链接错误**——解法：`replace github.com/valyala/gozstd => ./third_party/gozstd` 本地副本 + 加 `libzstd_linux_loong64.go` shim 链系统库；alpine loong64 的 zstd-dev **不带静态 .a**（`-l:libzstd.a` 找不到）→ 改 `-lzstd` 动态链接，运行层 apk 加 `zstd`（loong64 端口无 libzstd 包名）。**坑 ㉔：git checkout 的 entrypoint.sh 带 CRLF → `exec /entrypoint.sh: no such file or directory`**（内核把 `/bin/sh\r` 当解释器）——镜像里 `sed -i "s/\r$//"` 清洗。
- 补丁 v10（649 行，对 pristine 832d367 apply-check PASS）。**排障新知**：`git diff > file 2>&1 | grep` 的重定向顺序会把 stderr 警告写进补丁文件导致 corrupt——一律 `2>/dev/null > file`；docker build 的 `| tail -6` 会吞掉真实编译错误行，调试期必须落全量日志再 grep。

**波次八（2026-11-08）：cloudreve / woodpecker / focalboard 三应用商店端到端闭环，siyuan 判 F——自建累计 68 个镜像，registry 81 仓库，商店可用 107/265（≈40%），映射规则 107 条（agent v17 真机单测 PASS；面板 Running 应用达 17 个，零异常）。**
- **cloudreve 4.19.1 ✅ 端到端**：v4 前端是独立仓库 cloudreve/frontend（vite outDir=build + 构建期自动生成 version.json）→ PC npm build 后按 `assets/build/**` 结构打 assets.zip 放进 `application/statics/`（`//go:embed assets.zip`）；BackendVersion 是 ldflags 注入的陈旧默认值 → `-X ...constants.BackendVersion=4.19.1` 对齐；modernc sqlite 纯 Go 交叉直通。商店 compose 强制 postgres+redis 绑定（CR_CONF_* env）→ 重装时把 PANEL_DB_HOST 指向 postgresql 安装、PANEL_REDIS_HOST 指向 dc-redis。**大坑 ㉕：compose env 值里的 `#` 会被当注释截断**（Pg#2026Root → "Pg" → postgres 认证失败）——DB 密码避开 `#` 字符。
- **woodpecker v3.20.1 ✅ 端到端（双镜像）**：web/ 是 pnpm Vue 项目（`//go:embed all:dist/*`），`vite build --base=/BASE_PATH` 的占位符是运行时 web.go 按根路径替换的——直接原样构建即可；**go.mod 要 go≥1.27 而 lcr 只有 1.26.8 → `GOTOOLCHAIN=auto` 经 goproxy 自动拉 1.27 工具链**（⑳系列新知）；server mattn sqlite 设备 CGO，agent 纯 Go；agent 镜像=FROM server 镜像换 ENTRYPOINT（商店 compose 给 agent 传 `command: agent` 双保险）；server 必须配 forge（商店默认 GITHUB env 即可启动）。
- **focalboard 7.11.4 ✅ 端到端**：webapp `npm run pack` → webapp/pack；server 需 **`-tags "json1 sqlite3"`**（sqlite 驱动 import 被构建标签门控）；**坑 ㉖：Windows git clone 的 CRLF 让 `//go:build sqlite3` 变成 `sqlite3\r` 不匹配 → 驱动被静默剔除**（⑬ 坑的 Go 约束变体）——**根治 = 打包期 LF 归一化**（tar 打包时对文本文件统一 strip CR，不在容器里 sed）；**坑 ㉗：mattn v2.0.3 老 binding 在 musl 缺 `pread64/off64_t`**（musl 无 LFS 兼容层）→ `CGO_CFLAGS=-D_LARGEFILE64_SOURCE`。
- **siyuan v3.8.9 判 F**：官方 Dockerfile 需从源码构建 microsoft/onnxruntime（OCR 内核依赖），loong64 链路过重，延后。
- 教训沉淀：**同一脚本历经 python 转义/Windows 文本模式换行/脚本级 CR 清洗多轮处理后，`s/\r$//` 会退化成 no-op 或真 CR 分行**——多进程流水线里一切 CR 处理应在单一环节（打包期）用字节级代码完成。补丁 v11（660 行）apply-check PASS。

**波次九（2026-11-08）：vaultwarden 商店端到端闭环 + 三个回收项深挖定论——自建累计 69 个镜像，registry 82 仓库，商店可用 108/265（≈41%），映射规则 108 条（agent v18 真机单测 PASS；面板 Running 应用达 18 个，零异常）。**
- **vaultwarden 1.37.5 ✅ 端到端**：波次 mega216 时代 rust 二进制早已编译入库，卡的是 **web-vault 缺失**（"install it, please follow the steps"）——解法零编译：官方 [bw_web_builds](https://github.com/dani-garcia/bw_web_builds) release 预编译包（静态资产与架构无关）解包叠层 `COPY web-vault /web-vault` 即通。另两处镜像修正：**USER vw→root**（1Panel 商店挂载 ./data 是 root 属主，vw(1000) 写不进）+ **ROCKET_ADDRESS=0.0.0.0**（Rocket prod 模式默认只绑 127.0.0.1）。商店端到端：8095 → 200 Bitwarden UI 出页。
- **certimate 判 F 详注**：三重障碍逐一破除后倒在最后一环——①devEngines/packageManager 钉死 npm 版本（摘除即可）②pkg/sdk3rd-forked 是子模块且 URL 是 **git@ SSH**（codeload tarball 不含子模块=坑②；改 HTTPS `git config submodule.<path>.url` 后拉取成功）③编译通过但**运行期 pocketbase/modernc DB 层栈溢出**（migration 后 infinite recursion，loong64 依赖链问题）——需 upstream 升级依赖才能解。
- **bililive-go 判 F 详注**：webapp 是 react-scripts 5 栈——node24 崩（schema-utils/ajv 路径错乱）、设备 node22 容器构建也崩（`Cannot read properties of undefined (reading 'date')`，GENERATE_SOURCEMAP=false 等三连 env 无效）；另发现 **lcr debian node 底座默认 `omit=dev`**（npm ci 不装 devDependencies → cross-env missing）——需 `npm config set omit empty` + `--include=dev`。待前端栈迁移后回收。
- **excalidraw 暂缓**：PC 端 yarn 环境损坏（npm -g 安装 ECONNRESET），网络稳定后重试。
- 补丁 v12（662 行）apply-check PASS。

**波次十（2026-11-08）：excalidraw + easytier 商店端到端闭环，rustdesk-server 判 F——自建累计 71 个镜像，registry 85 仓库，商店可用 111/265（≈42%），映射规则 111 条（agent v19 真机单测 PASS；面板 Running 应用达 20 个）。**
- **excalidraw latest ✅ 端到端**：回收到波次九的暂缓项——PC yarn 被 Defender 锁缓存的顽疾（换缓存盘也逃不掉，monorepo 包量大必触发）→ **整链路搬进设备容器**（lcr debian node:22.23.2 自带 yarn，`npm install -g yarn` 反而 EEXIST）；**根因=esbuild loong64 二进制崩溃（⑯ 号坑）→ 根 package.json 加 `resolutions: {esbuild: ^0.25}` 钉新版**（新版 esbuild 的 loong64 构建健壮）；运行层用本地缓存 `lcr nginx:1.28.0`（stable-alpine tag 不存在；lcr 网络抖动时先查 `docker images` 本地缓存底座）。商店端到端 8083 → 200。
- **easytier v2.7.0 ✅ 端到端**：apt rustc 1.85 不够新（依赖要 1.88/1.89）→ **rustup 装 1.90 minimal profile**（sh.rustup.rs 直连可用）；cargo 换 rsproxy.cn sparse index；主机编译 + debian:sid 运行时（主机 glibc 旧于 sid → 向后兼容 ✓）；**镜像必须补 ENTRYPOINT**——商店 compose 传 `command: -c /root/config.toml`，无 ENTRYPOINT 时 command 被当裸可执行文件，容器停在 Created。商店端到端：容器 Up + wg/ws/wss 监听器全起。
- **rustdesk-server 1.1.16 判 F 详注**：编译卡在**上游 git 依赖腐化**——hbb_common 子模块可救（同 certimate 的 SSH→HTTPS 转换），但 confy/sysinfo 等钉在 rustdesk-org 的 git rev/分支被上游重写删除，逐个补丁不经济 → 待 upstream 更新版本管理后回收。教训：**老版本 rust 项目的 git 依赖（rev/branch 钉定）会随上游 force-push 腐化**，评估"源码构建"类应用时要看 Cargo.toml 里 git 依赖的数量与钉定方式。
- **dosgame 判 F**：上游仓库 firezmc/dosgame-web-docker 已 404。
- 补丁 v13（671 行）apply-check PASS。

**波次十一（2026-11-08）：评论双雄 twikoo + waline 全部商店端到端闭环——商店可用 113/265（≈43%），映射规则 113 条（agent v21 真机单测 PASS；面板 Running 应用达 22 个，零异常）。**
- **twikoo 2.0.17 ✅ 端到端**：当年 artifact 路线误装了 npm `twikoo` 包——那是**客户端 SDK**（dist 是浏览器 bundle，node 一跑就 `document is not defined`）；服务端是**独立 npm 包 `tkserver`**（版本号与 twikoo 严格对齐）——按官方 Dockerfile `npm install --omit=dev tkserver@2.0.17` 重做镜像，冒烟直接返回云函数 JSON。商店端到端 8084 → errno:0。
- **waline 1.43.6 撤销 F 转正 ✅ 端到端**：波次二的"thinkjs 4 API 层挂起"判定**系误诊**——设备 strace 追 worker 进程，真凶是镜像内 **better-sqlite3 原生模块缺失**：API 请求触发 require 死循环重试 statx 找 better_sqlite3.node。修复三步：①容器内 node-gyp 现场编译（**npmmirror 镜像缺 lcr 自构 node v26.13.0 的 SHASUMS256.txt → gyp 回滚**——手动预置 `~/.cache/node-gyp/<ver>/`（headers 包 200 可下，解包+touch installVersion 绕过校验））；②发现 **waline 官方对 sqlite 本就不自动建表**——仓库 assets/waline.sqlite.sql 是官方手动建表脚本，做进镜像启动初始化层（表存在检查 + IF NOT EXISTS 幂等）；③商店镜像源是 **lizheming/waline**（非 walinejs），规则补上后**卸载重装**才触发新改写（rebuild 用装时落盘的 compose，不会重跑改写）。商店端到端 8085 → errno:0 正常查询。
- **排障方法论沉淀**：node 服务"请求挂起"先 `strace -f -p <worker>` 看系统调用（statx/ENOENT 死循环=原生模块缺失；read/epoll 停滞=真挂起）——一个 strace 就能区分"构建缺陷"与"架构不兼容"，避免误判 F。
- 补丁 v14（678 行）apply-check PASS。

**波次十二（2026-11-08）：wikijs 3.1.0 重工程攻坚端到端闭环（含 PG18 plan-B 应对 lcr 宕机）——商店可用 114/265（≈43%），映射规则 114 条（agent v22 真机单测 PASS；面板 Running 应用达 24 个）。**
- **wikijs v3 官方 tarball 直跑 TypeScript**：v3 release 资产 `wiki-js.tar.gz`（65MB）内含 node_modules，backend 全 TS——**node ≥26 原生 type-stripping 直接 `node backend`，零构建步骤**；注意 `--no-experimental-webstorage` 启动旗标（lib0/yjs 探测 localStorage 会刷警告）。config.yml 用官方 dev/build 版（`$(DB_HOST)` 等环境替换语法，`parseConfigValue` 用 `env||default`——**空串环境变量自动回退默认值**，配合商店 compose 未注入的 `DB_PORT` 正好落 5432）。
- **Temporal 全局缺失（㊱号新坑）**：v3 有 26 个文件深度使用 Temporal API（`Temporal.Now.instant()` 等），lcr node26 无此全局、`--harmony-temporal` 也开不出 → 官方镜像实为依赖上游 node26 自带 Temporal。**根治：`npm i temporal-polyfill`（npmmirror）+ `--require` 预载脚本挂 `globalThis.Temporal`**——比 sed 改 26 处调用可靠。
- **可选扩展优雅降级**：sharp（optionalDependencies，代码显式支持"未装"分支）、puppeteer（编辑器渲染在客户端，服务端渲染只是可选扩展）、pandoc——删除 x64 的 `@img/sharp-*` 后三者启动日志全部 SKIPPED，功能不受影响。
- **PG17 门槛 + lcr 全网宕机 → plan-B 自建 PG18（㊲号新坑）**：wiki v3 运行期硬性校验 PG≥17；恰逢 lcr.loongnix.cn 宕机（主机/设备均不可达，DNS 正常）无法拉 `library/postgres:17-sid`。**关键发现：debian-ports 无 loong64，而 deb.debian.org sid main 自 trixie 起自带 loong64（postgresql-18.6 在列）**——从本地 `postgres:15.7-sid` 底座起容器，换源 `mirrors.tuna.tsinghua.edu.cn/debian sid main`，apt 装 postgresql-18 + commit，**影子 tag `lcr.loongnix.cn/library/postgres:17-sid`**（docker 本地已有镜像免拉取，商店映射零改动）。PG18.6 原生 loong64 编译（gcc 16.2）boot 全绿。
- **docker commit 陷阱复现（㊱ 与 waline 波同源）**：从 sleep 临时容器 commit 会**继承其 config**（`ENTRYPOINT ["/bin/sh"]`+`CMD sleep 3600` 覆盖官方 `docker-entrypoint.sh`）——commit 必须 `--change 'ENTRYPOINT ["docker-entrypoint.sh"]' --change 'CMD ["postgres"]'` 显式重声明；且 `--change` 的 JSON 引号经多层转义易损坏，**放设备端脚本文件里执行**（干净单层引号）。
- **postgres 官方镜像监听机制（㊲ 配套）**：`listen_addresses='*'` 不是 initdb 默认而是**官方 Dockerfile 构建期 sed 进 `postgresql.conf.sample`** 的——换大版本二进制必须对新版本的 sample 重打 sed，否则只监听 localhost 容器网络不可达。
- **商店 service 联动首次打通**：`GET /api/v2/apps/services/<appKey>` 返回 `{label,value,config}`（value=serviceName）；compose 的 `PANEL_DB_HOST` 在安装时若面板 **databaseRepo 无同名记录则原样透传**（本例直传容器名 `1Panel-postgresql-MsJH`，docker DNS 解析）——API 装的数据库应用**不会自动注册 database 记录、不自动建 DB/用户**（casdoor 同款坑），手动 `CREATE USER wikijs; CREATE DATABASE wiki OWNER wikijs;` 补齐，wiki 的 drizzle 迁移将 `wiki.*` 全表（apiKeys/authentication/blocks/comments…）建齐。
- **顺手修**：bitwarden（vaultwarden）镜像 healthcheck 指向不存在的 `extra/healthcheck` 导致 docker 层 unhealthy（面板不受影响）→ registry 镜像 `--change 'HEALTHCHECK NONE'` 修复，存量容器待下次重装生效；清除昨天评估残留的 gatus 杂散容器。
- 补丁 **v15**（683 行）apply-check PASS。

**波次十三（2026-11-08）：audiobookshelf 2.37.2 端到端闭环（F 清单最后一个大项，B 层大项归零）——商店可用 115/265（≈43%），映射规则 115 条（agent v23 真机单测 PASS；面板 Running 应用达 25 个）。**
- **前端/后端分离构建（重应用定型管线）**：client 是 Nuxt2（webpack4）+ **tailwind v4 CSS-first**（`@import 'tailwindcss'`）——`@tailwindcss/postcss` 依赖原生 **oxide** 模块，loong64 无预编译且 npm 包不含 Rust 源码（无法 rebuild-from-source）→ **客户端搬 PC 构建**（波次三"前端产物架构无关"管线的重应用延伸；Windows 上 oxide 有现成预编译）。PC 侧唯一特判：webpack4 的 md4 hash 在 node≥17 需要 `NODE_OPTIONS=--openssl-legacy-provider`。产物 dist/（4.9MB 压缩）上传设备塞进镜像。
- **server 侧**（设备容器）：`npm ci --include=dev --ignore-scripts` → `tsc` 出 dist-server → `npm ci --omit=dev` 装 sqlite3 5.1.7（**prebuild-install 无 loong64 → 自动回落 node-gyp 源码编译**）。**㊴号新坑：sid 的 python3.14 移除 distutils，sqlite3 自带的 node-gyp 8.4.1 直接 `ModuleNotFoundError: No module named 'distutils'`** → `apt install python3-setuptools`（其 vendored distutils shim 恢复 import）一次修复。sqlite3 在 loong64 上编译+加载全绿。另：设备其实能直连 unofficial-builds.nodejs.org（node-gyp 拉头文件 200）——旧"nodejs.org 不通"结论仅限主站。
- **运行层**：node20-debian + **sid 的 ffmpeg 9.0.2 loong64 apt 直装可用**（tzdata/ffmpeg/tini）；ENTRYPOINT `tini --` + `CMD node dist-server/index.js`（commit 显式重声明——波次十二 ㊳ 教训照抄）。libnusqlite3（unicode 折叠搜索扩展）官方仅 musl x64/arm64 预编译、源码构建需现拉 bitbucket → 走**条件加载降级**（不设 NUSQLITE3_PATH 即跳过，只损失 unaccent 搜索增强）。
- **㊵号新发现：API 直装的应用端口绑定 `127.0.0.1` 回环是面板全舰队统一默认**（25 个应用全部如此）——UI 安装勾选"外部访问"才绑 0.0.0.0；商店安装契约验证（改写/启动/迁移/HTTP 200）设备侧 curl 完整覆盖，外部访问按需在 UI 编辑里开。upstream 默认 base path `/audiobookshelf`（官方行为，`:40096/audiobookshelf/login` 301 正常）。
- 商店端到端：安装 id=31 → 映射触发（`loong/audiobookshelf:2.37.2`）→ DB 迁移+触发器全套 → `Listening on port :80` → `:40096 → 200`，面板 Running/2.37.2。
- 补丁 **v16**（688 行）apply-check PASS。

**波次十四（2026-11-08）：全舰队映射体检（质量保障波，无新镜像）——商店可用 115/265（≈43%），映射规则 114 条（rustdesk-server F 遗留死规则清除转拦截；agent v24 真机单测 PASS；面板 Running 应用 25 个全绿）。**
- **体检方法（三段脚本已入库 `phase2/mega216/audit14_*.py|.sh`）**：①parse——解析 app_loong64.go 映射表（Target/ByMajor/Fallback）+ 遍历商店缓存全部应用的**当前版本** compose 提取镜像引用，逐条走映射逻辑得"期望镜像引用"；②gen——生成本地 registry manifest 级存在性检查 + lcr 本地缓存检查脚本；③device——registry API `GET /v2/<repo>/manifests/<tag>` 逐条验证。本次结果：**115 规则 → 111 映射检查，81 本地引用初测 17 个 404，lcr 28 引用因宕机仅 4 个本地缓存可验（全绿）**。
- **版本漂移（㊱波新知）**：商店上游发新版后 keep-tag 模式下新 tag 在本地 registry 无镜像 → 安装报 manifest unknown。**14 项补 tag 别名**（`docker tag 旧构建 + push`：adminer 6.3.0→6.3.0-standalone、roundcube/sftpgo/frpc/frps 同版本后缀差 4 项完全等价；adguardhome/beszel/memos/ezbookkeeping/navidrome/opengist/prometheus/screego/watchtower 10 项同谱系滞后，**装到的是旧构建**，矩阵已标注 lag 待按需重建）。处置原则：**同谱系小版本漂移→别名+滞后标注；跨代/变体错配（gitea 1.25→27.x、zabbix alpine→ubuntu 变体）→不别名，标记重建**。
- **死规则清除**：rustdesk-server（wave-10 判 F 但映射规则遗留、镜像从未 push 成功）→ 从规则表删除、加入拦截表（安装给明确中文提示）——**体检抓到"判 F 未清规则"的流程漏洞**，今后判 F 时同步清规则。
- 复测 **78/81 全绿**（余 3 项均为已记录重建待办：gitea 27.x、zabbix ubuntu 变体、rustdesk 已转拦截）。重建待办池按优先级：gitea 27.3.11（跨代）> zabbix-agent ubuntu 变体 > 10 项 lag 版本滚动更新。
- 补丁 **v17**（692 行）apply-check PASS。

**波次十五（2026-11-08）：重建待办池清空（10/10）——商店可用 115/265（≈43%），规则/补丁不变（114 规则+20 拦截 / v17 692 行），agent v24；面板 Running 25 个全绿。**
- **批量重建管线复用**：mega216 的 pipeline.py 支持 spec 驱动批量（`python -I pipeline.py spec_w15.json`），旧 spec 条目改 tag 即可复用；**新增 `git_tag` 字段**——克隆真上游 tag、镜像打 store tag，解决"store 版本号与上游错位"的替代构建。注意 pipeline 会按 status.json 跳过 "built" 状态，重跑前需清对应键。
- **替代构建三例（㊷）**：gitea 27.3.11←**CE v1.27.3**（store 是 EE 分支版本号，上游不存在 27.3.11；CE 版功能覆盖常规自建需求）；memos 26.11.0←**上游 v0.31.0**（上游无该版本号，store 的 26.x 走了独立版本线）；zabbix-agent ubuntu-7.0.27←sid apt 7.4.x（zabbix 官方 agent 跨版本向后兼容 LTS server）。三者均在矩阵标注替代关系。
- **CGO 设备构建两例（新版触碰 sqlite3 完整 API）**：navidrome v0.64.2 新增 db/backup.go（sqlite3 Backup/Error）——PC 交叉编译的 mattn stub 缺方法 → 设备 CGO；**⑩哨兵变体**：v0.64.2 的 buildtags 移到 conf/buildtags 包且不提供无 tag 缺省实现，`main.go` 显式引用——必须 `-tags "netgo sqlite_fts5"`（Makefile GO_BUILD_TAGS）。ezbookkeeping v2.1.1 同因 sqlite3 stub → 设备 CGO；**⑰强化**：除 public/conf/templates 三目录外还需 data/log/storage 运行目录（storage 路径缺失启动即退）。
- **多阶段构建遮蔽坑（㊸）**：stage2 的 `COPY <ctx 路径>` 若与 stage1 产物同名同路径，会把**构建上下文里的旧文件覆盖 stage1 编译产物**（本例：ctx 里残留 pipeline 的 PC 交叉编译 stub 二进制，COPY 后覆盖了 CGO 真产物）——build 产物输出到独立路径（`/out/`）并 `COPY --from=build`。
- **lcr 宕机期离线构建**：BuildKit 总会 HEAD registry 解析元数据（本地有镜像也报 EOF）→ `DOCKER_BUILDKIT=0` 经典构建器直接用本地镜像；GOTOOLCHAIN=auto + goproxy 在 golang:1.26.8-alpine 内自动拉 go1.27 工具链（navidrome/ezbookkeeping 均要求 go≥1.27）。
- **存量复验**：体检复跑 **80/81 = 98.8%**（唯一 404 为已转拦截的 rustdesk 检查残留）；gitea/memos/zabbix 等十个重建项全部入 registry 并冒烟通过（gitea/ezbookkeeping/navidrome HTTP 200/302、zabbix process、其余 pipeline 内建 http smoke）。

**波次十六（2026-11-08）：VAR 层打通——PHP 运行环境端到端闭环——商店可用 116/265（≈44%），规则/拦截不变（114+20 / v18 716 行），agent v25；面板 Running 25 个 + PHP 运行时 php8427 Running。**

- **上游三重死结逐一化解**：① 商店 `php8` 带 `deprecated: 2.0`，v2.4.2 **同步期**（`getApps`）直接跳过——store 里根本没有这个应用，任何安装都无从谈起 → agent v25 放行 php8 单键（`config.Key != "php8"` 才 continue；php5/7 保留屏蔽）。② 运行时 compose 的 `${IMAGE_NAME}` 是用户自填镜像名 → **设备本地预建 `1panel-php-fpm:8.4.27`**（debian sid apt php8.4-fpm，候选版本 8.4.27-1 与商店 8.4.27 **精确同版**）并补 `php:8.4.27`/`8.4.6` 别名（对齐 UI 默认镜像名 `服务名:版本`）；`docker compose up` 默认 pull_policy=missing → 本地命中零拉取，Hub 不可达/lcr 宕机均无影响。③ 官方 `install-ext` 依赖 pear/phpize/docker-php-ext-enable → **自写 apt 版 install-ext**（63 项扩展映射：php8.4-* 直装 + php-redis/php-imagick 等 pecl 包 + 不支持项打印跳过并恒 exit 0，绝不让运行时报错）。
- **PHP 底座镜像配方**：FROM 缓存的 `lcr debian:sid-20250615` → 整写 apt 源（底座内置源是 **debian-ports，无 loong64**）→ 装 php8.4-fpm/cli/common/opcache + 常用扩展 + composer + pecl 系包 → www-data usermod uid/gid 1000（面板 chown 1000 的目录才可写）→ **复刻官方 php 镜像挂载布局**：`/usr/local/etc/php/php.ini`、`/usr/local/etc/php-fpm.conf`（含 `include php-fpm.d/*.conf`）、`/usr/local/etc/php-fpm.d/www.conf`（pool listen 9000）；debian 的 fpm 二进制 config-file-path 烧死在 `/etc/php/8.4/fpm` → 用 **symlink** 把 `/etc/php/8.4/fpm/{php.ini,php-fpm.conf}` 指回 /usr/local/etc 挂载点；CMD `php-fpm8.4 -F`。
- **运行时链路逆向结论**：php8 流 = 创建时下载商店包 → 渲染 install compose → `docker compose build`（无 build 段=no-op）→ up（本地镜像）→ 有扩展时 `docker exec <c> install-ext <逗号串>` → `docker commit` 到 runtime.Image；node/java/go/python/dotnet 流 = 创建前 **`pullRuntimeComposeImages` 显式 `docker pull`**——离线设备即使本地有同名镜像也必失败，这就是 VAR 其余五项的卡点（待做"本地已有则跳过 pull"守卫）。
- **上游遗留 bug（㊺）**：UI 创建 PHP 运行时传 `resource: remote/custom`，而 website 服务的部署分支比对 `constant.ResourceAppstore`（"appstore"）→ resource 不同的 runtime 建站时 proxy 分支走空、nginx `fastcgi_pass` 空参数 emerg。处置：运行时记录 resource 修正为 `appstore`（sqlite 一行），网站创建 `type=runtime + runtimeID` → proxy 自动 `127.0.0.1:<fpm端口>`。
- **商店强刷机制（㊹）**：`apps/sync/remote` 先比对 agent DB 设置 `AppStoreLastModified` 与 CDN `1panel.json.version.txt`，相同则"已是最新"**短路**——改了同步过滤逻辑后必须把该设置置 0 再触发同步（getApps 才真正执行）。dev 通道索引在 `apps-assets.fit2cloud.com/dev/1panel.json.zip`（268 应用）。
- **apt 源两坑（㊻）**：lcr debian 底座内置 debian-ports 源（无 loong64，apt update 直接 E: 不存在 Release）；tuna **https** 源在 2025-06 快照的老 ca-certificates 下验签失败（SSL certificate verify failed）→ **apt 源必须用 http://mirrors.tuna.tsinghua.edu.cn/debian sid main**（GPG 验包不依赖 TLS）。
- **扩展安装实测**：运行时更新带 `PHP_EXTENSIONS=[odbc,swoole,opcache,bcmath]` → odbc 非预装 → 容器内 apt 装 php8.4-odbc → commit 后 `PDO_ODBC`+`odbc` 双模块加载；swoole（sid 无包）优雅跳过、流程不中断；网站默认 index.php 动态渲染 PHP 8.4.27 + 全扩展清单（fastcgi 闭环铁证）。
- **交叉编译部署流程坑（㊼）**：Bash 工具 shell cwd 会被自动复位，`go build -o ../../相对路径` 会旁落到 `repo/phase2/...` 造成**部署了陈旧产物**（服务 active、测试 PASS 但行为不变）——构建输出一律用**绝对路径**，并用二进制内**新增字符串字面量**（`strings | grep "loong64 php8 kept"`）验证部署内容，哈希比对双保险。

**波次十七（2026-11-08）：VAR 层五连击——go/node/python/java 运行时闭环（零 agent 改动）——商店可用 120/265（≈45%），agent v25 / 补丁 v18 不变；面板 5 个运行时全 Running（php8427/godemo/nodedemo/pydemo/jdemo）。**

- **㊽ 函数名陷阱（推翻波次十六结论）**：波次十六看到 `pullRuntimeImagesBeforeStart`（显式 pull）就断言"离线必挂、需加守卫"——波次十七读 `utils/compose` 实现发现 `pullComposeImages` **本来就带"本地已有则跳过"守卫**（`ImageExists → continue`，forcePull=false；连 pull 失败后本地存在也放行）→ **VAR 解锁从来不需要改 agent，纯粹是本地镜像供给问题**。教训：下"必挂"结论前必须读实现，函数名会撒谎。
- **运行时骨架**：五类运行时 compose 同构——挂 `${CODE_DIR}:/app` + `./run.sh` + `./.env`，`command: bash /run.sh` → `source /.env` → `eval $EXEC_SCRIPT`（node 多 npm/yarn/pnpm 分支与 RUN_INSTALL/CUSTOM_SCRIPT 开关；go 多 ./mod:/go/pkg/mod 模块缓存卷）。UI 表单字段是前端硬编码（EXEC_SCRIPT/PACKAGE_MANAGER/RUN_INSTALL），经 params 落入 .env。
- **底座供应四件套**：`golang:1.26` = lcr golang:1.26.8-alpine 经 `FROM + apk add bash git` 重打（**alpine 无 bash，`bash /run.sh` 会直接挂**；apk 源 sed aliyun 防 dl-cdn 卡死；用 FROM 构建而非 docker commit 可自动继承 ENTRYPOINT/CMD，绕开波次十二的 commit 配置坑）；`1panel/node:26.13.0/22.23.4/20.20.2` = lcr node 三档 tag 别名（26.13.0 精确，22.23.4/20.20.2 为补丁级近似 22.23.2/20.19.3，文档标注）；`python:3.14.8` = sid apt python3（3.14.10）+ python3-venv/pip + `/usr/local/bin/python` symlink（debian 只有 python3 命令）；`1panel/java:21` = sid apt openjdk-21-jdk-headless（openjdk-21 在 sid 仍在，候选探测后择一）。镜像全部裸 tag 留本地（compose 引用裸名，daemon 本地命中；无需进本地 registry）。
- **四类型端到端验证**（每类型一个 demo 代码目录 + API 创建）：go `go run main.go`（带 go.mod，纯 stdlib 免模块下载）→ `go-runtime-ok|go1.26.8|loong64`；node `node server.js`（CUSTOM_SCRIPT=1 + RUN_INSTALL=0）→ `node-runtime-ok|v26.13.0`；python `python app.py` → `3.14.10`；java **单文件源码启动** `java Main.java`（JDK 11+ 特性，免 javac）→ `21.0.13`。四端口 18300-18303 HTTP 实证，`runtimes/search` API 五运行时全 Running。
- **API 载荷要点**：非 php 类型不需要 image（compose 以版本号推导）；`exposedPorts: [{hostPort, containerPort, hostIP, protocol}]` 生成 `HOST_PORT_0/CONTAINER_PORT_0` env 键；node 的 `source` 参数留空会让 run.sh `npm config set registry ''` 打一条无害 npm error——传真实源或忽略。
- **dotnet 判 F**：mcr.microsoft.com/dotnet 无 loong64 manifest，Loongson dotnet 移植版不可达；VAR 层至此 **13/14 项处置完毕**（php8+go+node+python+java 五项闭环，dotnet/php F，php5/7 屏蔽，forgejo/neko/openlist 参数自填无需适配，keydb 待评估，vllm D 候选）。

**波次十八（2026-11-09）：WordPress 全栈金丝雀——PHP 运行时/建站/数据库三链条真枪实弹验证——agent/补丁不变（v25 / v18），商店可用计数不变 120/265（WordPress 为文件部署非商店 app）。**

- **离线商店装数据库（缓存别名 trick，㊾）**：商店 mysql 应用当前版本 8.4.13 → 映射目标 lcr mysql:8.4.13（lcr 宕机拉不了）→ 设备缓存有 lcr mysql:8.4.3 → **`docker tag` 给缓存镜像打上商店要的 tag**，compose up pull_policy=missing 本地命中零拉取，1Panel-mysql 容器 mysqld 8.4.3 loong64 正常服务（面板 API `POST /apps/install` 全自动）。此 trick 适用于"商店版本号与本地缓存版本号同谱系差补丁"的场景——比升级缓存镜像省事得多。API 装的 MySQL 不自动建库（波次十二已知），`docker exec <mysql容器> mysql -uroot -p... -e "CREATE DATABASE ..."` 手动建。
- **无域名访问建站（㊿）**：PC hosts 无权限写入且 DNS 被 TUN 劫持（wp16.site 解析到 198.18.x 假 IP）→ 给网站**加 `192.168.3.35:8081` 域名**（`POST /websites/domains {websiteID, domains:[{domain,port,ssl}]}`），openresty 多监听一块，firewall-cmd 放行 8081 → 浏览器直接 `http://IP:8081/` 访问。WordPress 安装向导把 siteurl 写成了丢端口的 `http://192.168.3.35`——手动 `UPDATE wp_options SET option_value='http://IP:8081' WHERE option_name IN ('siteurl','home')` 修正。
- **全栈链路实证**：wp16 网站（type=runtime 绑 php8427）→ WordPress latest-zh_CN 解压进站点目录（**`.user.ini` 带 chattr +i 不可变属性，chown -R 会失败——排除后单独处理**）→ 浏览器安装向导四步（语言→DB 表单→wp-config 自动写入（站点目录 uid1000 可写，向导自己能建配置文件）→站点信息）→ **PHP 容器经容器名直连 MySQL 容器**（1panel-network DNS，root/密码面板参数注入）→ 前台主题/首篇文章完整渲染、**wp-admin 仪表盘完整加载**（WordPress 7.1.4 最新版）。表单 JS 提交注意：input[name=submit] 会遮蔽 form.submit()，用 `HTMLFormElement.prototype.submit.call(form)`。
- **金丝雀意义**：波次十六/十七验证的是运行时机器本身（demo 级），本波次证明同一套机器能承载**生产级真实 PHP 应用**（WordPress = PHP+MySQL+重写+session+上传全特性）——龙芯设备上 1Panel 建站生态从"能装"升级到"能用"。

**波次十九（2026-11-09）：A 层离线可装性定论 + registry 离线装机 3/3——面板安装 29/29 全 Running，agent/补丁不变（v25 / v18）。**

- **A 层离线可装性定论（㊽补充）**：lcr 引用的映射（memcached/nats/consul 三例）面板安装全部 `InstallErr`（`docker compose up` 对缺失镜像发起 lcr pull → 宕机超时）——**"纯映射零构建"只在线成立**。离线可装 = ①registry 支撑（80 项 B 层自建入库）②lcr 缓存命中（mysql/postgres 系）。**推论：lcr 长期宕机时 registry 架构是唯一稳态；高价值 lcr 映射可逐步搬运进本地 registry 换取离线可装性**（tag 别名搬运即可，无需重建）。
- **registry 离线装机三连**：gotify 3.1.1 / glance 0.8.7 / adguardhome（商店现版本 0.107.79，其 compose 镜像 tag 漂移 v0.107.80，registry 两 tag 都在）——全部面板 API 安装、容器 Up、HTTP 冒烟（200/200/302 引导页）。端口冲突时报错很友好（"8080 端口已被应用 FreshRSS 占用"，换端口重装即可）。
- **glance 商店包挂载 bug**：商店 compose 把 `./data/glance.yml` 挂到 `/app/config/glance.yml`，但 glance 二进制只读 `$PWD/glance.yml`（镜像 WORKDIR=/app）→ 启动即循环崩溃。修复：安装的 compose 补一条 `- ./data/glance.yml:/app/glance.yml` 再 `docker compose -p <project> up -d --force-recreate`（project 名取容器 label `com.docker.compose.project`，小写）。**后续重建 glance 镜像时把 WORKDIR 设为 /app/config 即可根治**（对齐商店包约定）。
- **API 陷阱备忘**：`GET /apps/detail/{appId}/{version}/install` 第一段是 **appId 不是 detailId**（传错报 record not found）；`POST /apps/search` 列表的 `versions[]` 为空——版本枚举要用 `GET /apps/{key}`；卸载是 `POST /apps/installed/op {installId, operate:'delete', forceDelete, deleteBackup, deleteDB}`；安装名称冲突/端口冲突都会明确报错。

**波次二十（2026-11-09）：离线可装性体检定论 + glance 根治 + keydb 定论 + 资产保护备份——agent/补丁不变（v25 / v18）。**

- **audit20_offline.py（新体检工具，入库 mega216/）**：按 audit14 checks 基线（111 项 = 83 registry + 28 lcr）判定离线可装性，**repo 级缓存比对**（不只精确 tag——缓存差补丁级 tag 的可用 `docker tag` 别名救活）→ **87/111（78%）可离线装**（83 registry + 4 lcr 精确缓存：mysql/postgres/redis/registry），别名可救 0，**24 项仅在线可装**（elasticsearch/gitlab/jenkins/kibana/logstash/mariadb/mongodb/phpmyadmin/portainer-ce/rabbitmq/wordpress 等）。结论：**lcr 长宕下 registry 架构是唯一稳态**；24 项在线限定项在 lcr 恢复后可批量 `docker pull` 进本地缓存（或直接 tag 别名搬运入 registry）转离线可装。
- **glance 镜像根治**：pipeline go_only 生成的运行层镜像丢了上游 Dockerfile 的 `--config /app/config/glance.yml` 参数（ENTRYPOINT 只有裸二进制）→ 商店包挂 /app/config/glance.yml 与镜像 WD=/app 错位。**修复 = 2 行 Dockerfile 改 WORKDIR**（`FROM 现镜像` + `WORKDIR /app/config`，经典构建器秒级）+ push 同 tag + 容器重建。教训：**自建镜像的路径约定要对齐商店包的挂载约定**（挂载点写死在 compose 里，镜像侧 WD/ENTRYPOINT 得配合）。
- **keydb 定论（VAR 最后一项待评估关闭）**：不构建——生态位已被 valkey 覆盖（Redis 兼容 fork，mega216 已入库 9.0.7），eqalpha/keydb 的 `${ARCH}` 枚举无 loong64。**VAR 层 14 项全部处置完毕**：5 闭环（php8/go/node/python/java）+ dotnet/php F + php5/7 屏蔽 + forgejo/neko/openlist 参数自填 + keydb 不构建（valkey 覆盖）+ vllm D 候选。
- **资产保护备份（新流程）**：`tar -C / -czf backup_port_<date>.tar.gz var/lib/docker/volumes opt/1panel/{db,www,runtime,apps,resource,log}`（设备端 nohup 后台）→ SFTP 拉回 PC。覆盖：全部数据卷（14G，含 MySQL/PG/wikijs/wp16 用户数据）+ 面板库 + 站点目录 + 运行时配置 + 商店包缓存。**定位：registry 镜像本身可由 PC 侧 pipeline/构建上下文全量重建，真正的不可再生资产 = 数据卷 + 面板库**。lcr 长宕期 + 单机 NVMe 环境，异地备份是最后的保险。

**波次二十一（2026-11-09~10，PC 侧 + 设备半场——设备经外网映射 （公网运维隧道·地址端口已隐去） 远程执行）：上游拒收后的自维护体系落地。**

- **路线 A ✅**：`loong64-support` 分支 3 commits（基线 v2.4.2 tag 832d367）——①`feat(appstore): add loong64 image mapping layer`（1594243，映射层 114 规则+20 拦截+3 调用点）②`feat(appstore): keep php8 runtime syncable on loong64`（53b685c）③`feat(appstore): allow overriding app-store source URL via config`（aaff79f，`base.app_repo_url` 覆盖 `AppRepoURL()` 版本写死值）。**已 push fork**（公司网络 GitHub 可达；家里网络此前 TLS 抽风）。agent **v26** 交叉编译（77.6MB，sha256 d2001b74…；字面量验证：`app_repo_url` 新增 + php8 两字面量继承）。补丁 **v19** = git diff 生成（7 文件 665+），pristine apply-check PASS。
- **路线 B 工具链 ✅（PC 侧）**：`phase2/mega216/store_loong_build.py`——规则表**直接解析自 `app_loong64.go`**（单一事实源：110 repo + 4 base + 20 blocked），CDN（带浏览器 UA，403=UA 过滤）全量下载 268 应用 → **双路改写**：tar.gz 包内 `*.yml` image + 散装 `docker-compose.yml`（`{IMAGE_RE}` 行级重写，与 Go 端 mapLoong64Image 1:1 移植）→ 重打 tar.gz（保留原条目 `{key}/` 前缀布局）→ 自描述 `1panel.json.zip`（顶层 lastModified=20261109 触发一次重同步）+ `1panel.json.version.txt`。产物 `store_loong_mirror/`。
- **关键机制发现（决定自建源形态）**：**安装路径拉的是整包 tar.gz**（`{base}/{mode}/1panel/{key}/{ver}/{key}-{ver}.tar.gz`，同步期仅记录 DownloadUrl、安装期下载解压到 appResourceDir）——散装 compose 只是 `getRemoteCompose` 兜底路径；**自建源必须改写 tar.gz 内部的 compose**，只改散装 yml 是无效功。1panel.json 结构：应用键在 `apps[].id`（无 appProperty 键）、icon 是绝对 CDN URL（图标仍走 CDN，缓存后离线无碍）、无 extra 键（最低版本门禁天然跳过）。
- **设备半场 ✅（2026-11-10，外网 SSH （公网运维隧道·地址端口已隐去））**：门禁单测 PASS → agent v26 上位 active → nginx 容器（lcr nginx:1.28.0，127.0.0.1:8082 只读挂载 /opt/loong-store）托管，`curl /dev/1panel.json.version.txt`=20261109 → **外置 `/opt/1panel/conf/app.yaml`**（见下）启用 `app_repo_url: http://127.0.0.1:8082` → agent 日志证实 `download file from http://127.0.0.1:8082/dev/1panel.json.zip`、268 应用 detail 同步完成 → **E2E 真装 memcached 1.6.22**：面板 API 提交 → 镜像站访问日志见 docker-compose.yml + memcached-1.6.22.tar.gz 拉取 → 改写 compose 生效 → **镜像 `lcr.loongnix.cn/library/memcached:1.6.21-alpine` 拉取成功 → 容器 Up、`stats` 功能验证通过**（install 状态 Running）；已装应用（openresty/ddns-go/registry/演示容器）全部无损。
- **【51】新机制：agent 配置是嵌入式的**——agent 把 `agent/cmd/server/conf/app.yaml` **go:embed 进二进制**（mode=dev），仅当外部 `/opt/1panel/conf/app.yaml` 存在时才读外置文件且**整体替换**（文件名必须是 `app.yaml` 不是 `app.yml`；外置文件必须带完整 base+log 段，install_dir/port 由 initBaseInfo 从节点信息覆写）。此前 runbook 写的 `/opt/1panel/conf/app.yml` 是想当然——v2.4.2 agent 设备上根本没有该文件。
- **【52】新坑：上游包占位文件 × SDK 严格解压器**——上游 CDN 包 **1018/1021** 带版本路径 **0 字节占位文件条目**（如 `memcached/1.6.22`，真文件在其下），且无目录条目；v2.4.2 `extractArchiveWithSDK` 严格校验（文件条目遇已存在目录→拒、文件阻塞自身父目录→拒）→ 装不上（干净状态也一样炸，属上游现行包形态与 v2.4.2 解压器的组合缺陷）。**镜像侧修复**：`w21_fix_tars.py` 全量规范化（删占位文件条目 + 补显式目录条目），builder 重打包逻辑同步内置；规范化后**旧源残留目录自愈**（`ensureArchiveDirectory` 对已存在目录放行、文件条目覆盖走 os.Remove），无需手工清缓存。权威总包重打：`store_loong_mirror.tgz` 378.9MB **a8b7d143…**（取代 9c68546e…）。
- **【53】新机制：安装 URL 由 baseRemoteUrl 重建**——同步代码 `processOneApp` 用 `{AppRepoURL}/{mode}/1panel/{key}/{ver}/{key}-{ver}.tar.gz` **重建** DownloadUrl 入库，1panel.json 里的 fit2cloud 绝对 downloadUrl **不被采用** → 商店源覆盖 3 行改动即可全链路生效，无需改写索引 URL。
- **【54】面板 API 自动化登录链（curl 可复用）**——真实 API 不带入口前缀：`POST /api/v2/core/auth/login`；需 **`EntranceCode: base64(入口名)`** 头；密码须**混合加密格式** `base64(RSA-PKCS1v15(AES密钥)):base64(IV):base64(AES-CBC(明文))`（公钥在 core.db `PASSWORD_PUBLIC_KEY`；设备端 `openssl pkeyutl` + `openssl enc` 可构造，存储密码可用 `EncryptKey` AES-128-CBC 解出核对）；agent 路由同路径透传（`/api/v2/apps/...`），需会话 cookie + **`X-CSRF-Token` 头 = `pcsrftoken` cookie 值**；登录失败 1 次即触发验证码（IPTracker 内存态，**重启 1panel-core 清除**）。安装接口：`POST /api/v2/apps/install {appDetailId,name,params}`，detail id 可从 agent.db `app_details` 直查。

**波次二十二（2026-11-10）：lcr 复苏红利 —— 24 项在线限定批量转离线可装，离线可装率 87/111 → 111/111（100%）。**

- **lcr 复苏确认**：波次二十一 E2E 装 memcached 时直接从 `lcr.loongnix.cn` 拉取成功 → `/v2/_catalog` 200 → 复苏实锤（宕机自波次十二前后起，约 11-04~11-10）。设备本地 lcr 镜像 15 → 39。
- **24/24 批量拉取零失败**：audit20 的 24 个 ONLINE-ONLY 项（2fauth/consul/elasticsearch/emqx/flarum/gitlab/grafana/influxdb/jaeger/jenkins/kibana/logstash/mariadb/memcached/mongo/nats/neo4j/pgvector/phpmyadmin/portainer-ce/postgis/rabbitmq/wordpress/yourls）按映射规则目标 tag 逐个 `docker pull` 入本地缓存（`w22_pull.sh` 设备后台 nohup；gitlab-ce 17.6.2 最大 ~7G 用时 21 分钟）→ **零 404 零漂移**（波次十四补的 tag 别名全部有效）。复跑 `audit20_offline.py`：**total=111 offline-ok=111 online-only=0**。**lcr 再宕机时全量商店离线可装**（registry 支撑 + lcr 缓存命中双保险）。
- **postgres:17-sid 验真（非破坏性）**：lcr 目录确有真 `17-sid` tag；本地 17-sid 无 digest（= 波次十二 PG18.6 影子，15.7-sid 有 digest 是真拉的）。**刻意不 `docker pull` 替换**——现存 postgresql17 实例的数据卷是 PG18.6 集群格式，真 PG17 二进制无法读取（大版本降级不支持），替换 tag 会在容器重建时炸库；且 `pull_policy=missing` 缓存命中使新旧安装行为一致（都拿到影子 PG18.6，满足 wikijs 的 PG≥17 门槛）。将来要真 PG17：独立 tag 另拉 + 新集群。
- **watchtower B 层 E2E（经新镜像源）✅**：`POST /apps/install` detailId=571 → 镜像站整包下发（改写后 image=`127.0.0.1:5000/loong/watchtower`）→ registry 命中 → Running。与波次二十一 memcached（lcr 直连路径）合起来，**自建商店源双目标路径全部真机验证**。商店包写死 `DOCKER_API_VERSION=1.52`（上游 docker 27/28）而设备 daemon 上限 1.45 → 镜像侧改写为 1.45（散装 compose + 包内 compose 双改，`w22_patch_watchtower.py`）后即正常。
- **【55】新坑：商店源三层缓存，只升版本号只清一层**——`AppStoreLastModified`/version.txt 提升只强制**重下包**（marker 失配 + detail.Update=true）；**DB 里缓存的 `detail.DockerCompose` 清空条件是 per-detail 比较**（`detail.LastModified != v.LastModified || detail.DownloadUrl != downloadURL || Params 变`），版本号提升时这些都不变 → 安装渲染仍用旧 compose。**镜像源内容补丁必须同时改 per-version `lastModified`**（JSON 内），下一次商店同步才会清 DB compose 并从镜像重取。排障链：安装目录 compose `grep DOCKER_API_VERSION` → DB `app_details.docker_compose` → 镜像站 `curl` 实发内容，三层逐层对。
- **F 项外部条件复查**：clickhouse 的 lcr 仍只有 `23.8.16.40-lts` 旧 tag（商店要新版）→ 保持 F。其余 F 项条件均与 lcr 无关（onnxruntime/pocketbase/前端栈/上游依赖）。
- **经验教训**：①nohup 后台脚本经 paramiko exec_command 启动必须 `< /dev/null`（stdin 不关会让 SSH 通道挂死）；②SFTP put 不建目录，先 `mkdir -p`；③`cp A B dir/` 保留原名——改名落盘要用显式目标名（本轮 watchtower 散装 compose 顶名失败多绕两轮）。
- **权威制品定稿**：`store_loong_mirror.tgz` 378,907,366 字节 **sha256 ed563554…**（含波次二十一规范化 + 波次二十二 watchtower API 适配/per-version lastModified 提升；取代 a8b7d143… 与 9c68546e…）。`audit20_offline_report.json` 已重生成（111/111）。

**波次二十三（2026-11-10）：备份补打 —— 商店源自持切换 + 24 镜像批量入缓存之后的资产固化。**

- **增量判定先行（省 13G 传输的关键）**：先全深度扫 `find /var/lib/docker/volumes -newermt '2026-11-09 12:00'`——变更文件仅 metadata.db/backingFsBlockDev 两个占位（实际 **0 个真实文件**），证明 14G 卷（其中 13G = loong-registry-data 自建镜像）与 11-09 全量母本 `backup_port_20261109.tar.gz`（13.7GB，sha256 6fe5fc24…）**逐位一致**，不重拉。波次 21/22 拉的 39 个 lcr 镜像全在 overlay2 不在卷里，可从 lcr 重拉，仅入清单登记。**真正新增资产只有三处**：`/opt/1panel`（414M，含商店源自持 `conf/app.yaml`、双库的 memcached/watchtower 记录）、mega216 顶层脚本/日志、loong-store 设备侧快照哈希。
- **三包 + 清单**（设备端 `w23_backup.sh`，**必须 sudo 跑**——首跑 lingke 身份下 db/log/volumes 全被权限挡，panel 包静默缺库；产出均落 `/home/lingke/mega216/`）：
  - `bk_panel_20261110.tar.gz`（240MB）：`/opt/1panel` 全目录 live tar（`--warning=no-file-changed` 容忍日志滚动）
  - `bk_db_20261110.tar.gz`（735KB）：core.db + agent.db 用 python3 `sqlite3.backup()` 做**一致性快照**（不中断服务，避免 live tar 抓到半写事务）——**权威恢复点**
  - `bk_scripts_20261110.tar.gz`（737KB）：mega216 顶层 `*.sh *.log *.txt *.json` + w22_delta（9.5G 构建 scratch 不收，PC 均有母本）
  - `w23_manifest.txt`：三包 sha256 + `/opt/loong-store/dev/` 快照哈希（对应母本 ed563554…）+ 38 项 lcr 镜像 sha256 摘要清单 + 运行容器表 + 卷不变性证据
- **落盘**：`E:\backup_2k3000\w23_20261110\`，哈希全部对上 manifest。恢复顺序：重装系统底座 → 还原 11-09 全量包（卷+面板）→ 叠加 w23 panel 包（新面板状态）→ `bk_db` 快照覆盖库 → 商店源即恢复自持。
- **【56】备份脚本坑**：①paramiko exec + nohup 脱机跑 sudo 脚本，脚本内 `sqlite3`/`tar`/`find` 都以 root 视角访问 `/opt/1panel/db`、`/var/lib/docker/volumes`，**忘加 sudo 会产出"看起来成功实则缺库"的包**——校验要查 log 里的权限报错而非只看包存在；②Git Bash 传 `--put /remote/path` 会被 MSYS 转成 Windows 路径致 ENOENT，加 `MSYS_NO_PATHCONV=1`；③manifest 里顺带登记 lcr 镜像 `--digests` 清单，postgres:17-sid digest `<none>` 恰好可复核影子 tag 身份。

**波次二十四（2026-11-10）：滚动维护首次实战演练 —— 上游 11-10 全局重发布的检测、评估与决策。**

- **检测**（新工具 `w24_upstream_check.py`）：上游 CDN `version.txt` 20261109 → **1794221851**（时间戳式），267 应用 per-app `lastModified` **全部刷新**（~17940587xx → ~17942217xx，上游 11-10 全局重发布），但**零新增/零移除应用**。**【57】滚动维护判据**：全局时间戳刷新 ≠ 重建触发器；**真实判据 = 版本串 + params 的严格 diff**——实测仅 **18 项真实变化**（certd/certimate/cordys-crm/dashy/dbx/domain-admin/gitea/glance/mkdocs-material/n8n/nocobase/ollama-webui/openclaw/trilium/verdaccio/vllm/wallos/wikijs），其余 249 项纯元数据。`w24_assess.py`（复用 `store_loong_build` 的规则表+改写函数）对 18 项新版本拉上游散装 compose → 提 image → 映射 → 设备端双探测。
- **评估**：18 项中 **13 项无映射规则**（未移植层，新版本装不上与旧版本一样，无回归）；**5 项 B 层 registry 支撑应用带新版本**：gitea 27.3.12 / glance v0.8.8 / verdaccio 7.1.0 / wallos 5.11.1 / wikijs 3.2.0+3.3.0，共 6 个新 tag，`docker manifest inspect` **全部 MISS**（registry 现存 gitea 27.3.11 / glance 0.8.7 / verdaccio 7.0.2 / wallos 5.10.4 / wikijs 3.1.0）。
- **决策：镜像树保持 20261109 基线不采纳**——采纳会把 5 个"商店里可见但拉不到镜像"的新版本带进设备商店，违背"所见即可装"原则。**采纳门槛 = 目标镜像可用性（registry 命中或 lcr 可拉），MISS 一律 hold 入重建待办池**。6 个新 tag 已入池（gitea 的 CE 源 tag 映射、wikijs 3.x 谱系构建时核实）。
- **双体检复跑**：`audit14` 设备复跑——80 个本地 manifest **全部 200** + 28 个 lcr 项**全部 CACHE-HIT（0 miss）**（对比波次14 基线 78 绿 + lcr 在线级，如今全部离线级）；`audit20` 复跑 **110/110 全绿**。
- **体检口径修正**：波次14 遗留的 rustdesk-server 残留检查（波次10 判 F、波次14 规则已删转拦截表，但检查清单未同步）从 `audit14_checks.json` 剔除——audit20 此前把它**无条件计为 offline-ok 是假阳性**。修正后口径 **110/110**（82 条本地检查含 2 组重复引用去重 80 唯一 ref + 28 lcr）；波次22 报告的 111/111 为历史数值（含 1 项残留），无行为差异（拦截发生在 pull 之前）。
- **排障小坑**：ssh_exec 复合命令里不加引号的 `echo (xxx)` 会让整条 `bash -c` 语法报错**压根不执行**（result 文件都不生成），别误判成脚本问题。

**波次二十五（2026-11-10）：6-tag 重建批次 + 采纳闭环 —— 滚动维护三步法首次完整走通（检测→评估→构建→采纳→E2E）。**

- **6 新 tag 全部入库**：三真构建——glance v0.8.8（go_only，82s，**v0.8.8 真源码 53aec7f**）、verdaccio 7.1.0（artifact npm 装，npmmirror E504 一次后重试成功，容器内 `version: 7.1.0` + HTTP 200）、wallos 5.11.1（static，git_tag=v5.11.1 释出提交 50e92d7，85s smoke 200）；三别名（同谱系重标签）——gitea 27.3.12←27.3.11（上游无 v1.27.4，已跳 v28.x）、wikijs 3.2.0/3.3.0←3.1.0（v3 alpha 线重标签）。gitea 版本映射定论：上游已切 v28.x 版本线，store 的 EE 式 27.3.x 对应 CE v1.27.3 即最新。
- **【58】构建流水线缓存陷阱（本波实战抓出）**：`pipeline.py clone()` 对已存在源码目录直接 `"cached"` 返回——**换 tag 重建时会拿旧源码打新标**。glance v0.8.8 首建 72s 完成（红旗：与 v0.8.7 原 67s 几乎同速），核查 `git rev-parse` = v0.8.7 commit，实为**错标镜像**；删缓存重clone 后才拿到真 v0.8.8。已在 clone() 加校验（ls-remote 目标 sha ≠ 本地 HEAD → 强制重取），并实测 wallos 场景用"抢跑植入"（pipeline 到达前手工把正确源码放进缓存目录）。**判错标红旗：换 tag 重建耗时与旧版几乎相同 = 大概率没换源码**。
- **builder 升级（增量重建内建化）**：①tar 取包改存在即复用（增量模式，1021 包不重下）；②重打包只对**新取包或内容补丁包**执行；③`CONTENT_PATCHES` 内容补丁表（watchtower `DOCKER_API_VERSION=1.52→1.45`）——波次22 的手工环境适配正式内建为 PC 母本权威，全量重建不再丢修复；④`STORE_VERSION → 20261111`。重建实测：1043 版本（上游新增 22 个版本目录全部入树，13 处改写，0 错误，仅数分钟）。
- **采纳执行**：delta tgz 9.9MB（索引两件 + 22 新版本目录，显式清单法——builder 第5步全量拷贝搅动 mtime，不能按时间筛）→ 设备 overlay `/opt/loong-store`（nginx 免重启）→ `systemctl restart 1panel-agent` 触发重同步 → 新版本 detail 生成（glance 0.8.8 = detail 1030）→ **E2E 真装 glance 0.8.8 全绿**：API 安装（install id 45）→ 首轮轮询即 Running → 容器 Up → `curl 127.0.0.1:18099 → 200`（compose 挂载 `./data/glance.yml:/app/config/glance.yml` 与 WD=/app/config 修复严丝合缝）。
- **"268 vs 267"之谜**：MCSManager 在上游索引中有两个同名应用（不同 id），检测脚本用 key-or-name 做 dict 去重成 267——**非新增应用**；用 id 做键不去重。
- **探针口径**：`docker manifest inspect` 对本地 registry 的同名 tag 探针行为怪异（tag 明明已 push 仍报 FAIL）——**registry API curl（`/v2/<repo>/manifests/<tag>` 带 Accept 头）才是真探针**，audit14 设备脚本即此法。
- **体检清单时效**：audit14/audit20 检查集仍基于 11-08 商店版本快照；20261111 采纳的新版本可用性以 registry API 200 + E2E 实装为准（本轮 6/6 全绿）。
- **设备终态**：12 容器全 Up（新增 1Panel-glance-bklY）、面板安装 5/5 Running（openresty/ddns-go/memcached/watchtower/glance 0.8.8）、磁盘 17G/163G。

**波次二十六（2026-11-10）：体检对齐 20261111 基线 + 一键巡检 + 备份补打#2 —— 抓出并修复采纳回漂移。**

- **体检工具升级（`audit26_parse.py`）**：基线体检不再依赖上游 apps checkout（11-08 已过时），改从**镜像树**取每个应用的最新版本改写 compose，**直接以改写后目标为检查对象**（本地 registry manifest / lcr 缓存）——映射正确性已由波次14/21 背书，体检聚焦"目标是否存在"。下游 `audit14_gen.py`/`audit20_offline.py` schema 兼容不动。新基线：**109 检查（81 本地 + 28 lcr），unmapped 145**。
- **【59】采纳回漂移（本波最重要的发现）**：新基线体检立刻抓出 **7 个本地 404**（caddy 2.11.9 / casdoor v4.26.0 / keycloak 26.8.2 / kodbox 1.71.02 / maddy-mail 0.9.7 / prometheus v3.16.0 / sub2api 0.2.20）+ grafana 13.0.2-alpine lcr 未缓存。这批版本是 **11-09 快照时代就已潜入商店的**——波次24 只 diff 了 11-09 vs 11-10（它们不在"新变化"里），audit20 的 local 项又**无条件判 offline-ok**（不查 manifest）→ 唯有 manifest 级设备体检能抓。**教训：每次商店基线切换后必须跑一次 manifest 级体检，不能只信 offline 统计**。处置：7 项同谱系**别名**（前驱 tag 全在位，`pull→tag→push` 批量）+ grafana **lcr 真拉**（13.0.2-alpine lcr 确有此 tag）→ 复跑 **79×200 + 28 命中全绿**，audit20 **109/109**。真构建批次入待办池（lag 标注）。
- **一键巡检（`roll_maint.py`）**：检测（严格 diff）→ 重基线（audit26_parse→gen→设备 manifest 体检）→ offline 统计 → **结论输出**（采纳/入池/全绿）。实测一轮：上游零漂移 + 全绿。今后每次"继续"可从它起步。
- **备份补打#2**：`w26_backup.sh`（波次23 同配方）→ 三包 `bk_panel_20261111.tar.gz`（240MB，含 glance 安装记录与 20261111 商店缓存）/ `bk_db_20261111.tar.gz`（734KB 一致性快照）/ `bk_scripts_20261111.tar.gz`（704KB）+ `w26_manifest.txt`（三包哈希 + loong-store 快照 + **registry 权威登记 86 仓 158 tag**（python 重生成——shell 管道拼 JSON 易花）+ lcr 缓存清单 + 容器表）。registry 卷自 11-09 母本已变化（+10 tag），按惯例不重拉 13G（可由 PC 构建上下文 + 别名重建），落盘 `E:\backup_2k3000\w26_20261111\`。
- **小坑**：ssh 复合命令嵌套引号里用 sed/awk 拼验证 URL 极易错（本轮 7 个"假 404"实为 URL 拼错）——**复验一律用体检脚本本身**，不手搓一次性管道。

**波次二十七（2026-11-10）：7 项 lag 别名升级真构建 —— 流水线三缺陷实战修复，digest 终审定案。**

- **7/7 真构建落地**（全部 digest ≠ 前驱，设备本地缓存已刷新）：caddy 2.11.9（手工树更新 v2.11.9→PC 交叉编译→img-caddy 布局，`caddy version` 输出 v2.11.9 commit）、casdoor v4.26.0（go_fe，329s）、keycloak 26.8.2（**手工**：zip 设备端解包拍平→`COPY keycloak /opt/keycloak`→smoke HTTP_OK）、kodbox 1.71.02（源 1.71.03 顶标，258s）、maddy-mail 0.9.7（bins pkg 修正 `./cmd/maddy`，109s）、prometheus v3.16.0（**UI 已迁 mantine-ui**：fe 入口改 `pnpm run build:mantine-ui`，react-app 目录是废弃残留；702s）、sub2api 0.2.20（**前后端分离重构**：fe_dir=frontend + go `-tags embed` + ldflags 版本注入，298s，smoke 自报 `Sub2API 0.2.20`）。
- **【60】真构建终审判据：registry digest ≠ 前驱 tag digest**。"构建 OK"≠"真构建"——kodbox/sub2api 首轮 smoke 全绿、digest 却与 1.70.03/0.2.19 相同（旧源码错标），靠 digest 对比揪出。配套快速红旗：换 tag 重建耗时 ≈ 旧版。
- **流水线三缺陷实战修复**（`pipeline.py`）：①smoke cmd 假绿——`EXIT=$?` 取的是管道末端 `tail` 的退出码（恒 0，`exec format error` 都判过）→ 改 `${PIPESTATUS[0]}`；②`ssh_put` 115s × WAN——大上下文必死（keycloak 700MB ctx、sub2api 断连 10054）→ 1800s + 3 次重试，keycloak 改 `device_extract`（只传 174MB zip 设备端解压）；③**clone 校验 fail-open 漏洞**——codeload 时代缓存目录无 `.git`，`rev-parse` 取不到 HEAD → "无法验证则放行缓存"分支放行了旧源码（kodbox/sub2api 中招）→ 非 git 目录一律强制重取。
- **上游架构迁移的两类适配**：①prometheus v3.16.0 UI 迁 mantine-ui——fe 入口换 `build:mantine-ui`（workspace 只含 mantine-ui+module，react-app 死代码）；②sub2api 前后端分离——fe 在 frontend/、go module 在 backend/（bins 支持 `cwd`）、`-tags embed`、vite outDir 直写 backend/internal/web/dist（`go_fe` 路由原样覆盖）。**pnpm 12 严格模式**拒绝未批准构建脚本（esbuild/vue-demi）→ 本地构建树加 `pnpm-workspace.yaml` `allowBuilds` 白名单（不动锁文件）。
- **小坑**：store 版本无源 tag 用相近 tag 顶（kodbox store 1.71.02 ← 源 1.71.03）；`git ls-remote` 可替代 GitHub API 验 tag（无限流）；pipeline 并发运行会互踩 status.json（末次写覆盖）。
- **lag 批次结账**：10 项中 7 项升级真构建；wikijs 3.2.0/3.3.0 + gitea 27.3.12 **保持别名定案**（v3 alpha 线无对应源 tag / 上游已切 v28.x 版本线）。终态体检：79×200 + 28 命中 + 0 miss，audit20 109/109。

## 13. 文件清单

**Windows 工作区** `02loongson2k3000\1panel_port\`：
| 路径 | 内容 |
|---|---|
| `toolchain/` | Go 1.27.3 zip 免安装版 |
| `repo/1Panel/` | 源码（v2.4.2 tag）+ 前端产物 + 映射层新文件 |
| `repo/build/` | 1panel-core / 1panel-agent（loong64）+ 测试二进制 |
| `patches/1panel-v2.4.2-loong64-support.patch` | **上游 PR 补丁（635 行，v8-final：99 映射规则 + 19 拦截表）** |
| `patches/quick_start_v2_loong64.sh` | 引导脚本 loongarch64 分支补丁版 |
| `patches/fetch_app_images.py` 等 | 商店镜像扫描 / 盘点比对 / 矩阵生成脚本 |
| `openresty_build/Dockerfile.loong64`(+nginx.conf/vendor/1pwaf) | **OpenResty loong64 构建配方**（§8，与设备 `~/openresty_build/` 同步） |
| `phase2/`(img-caddy/img-ddns-go/img-filebrowser + 源码) | **批次一自建镜像上下文**（caddy/filebrowser/ddns-go，与设备 `~/img-*` 同步） |
| `dist/1panel-v2.4.2-linux-loong64.tar.gz`(+.sha256) | **成品安装包（58M）** |
| `dist/template/`, `dist/staging/` | 官方 amd64 模板 / loong64 打包目录 |

**设备端**：
| 路径 | 内容 |
|---|---|
| `/usr/local/bin/1panel-core|agent`、`1pctl` | 面板二进制与 CLI |
| `/etc/systemd/system/1panel-{core,agent}.service` | 开机自启服务 |
| `/opt/1panel/`（db/apps/backup/log/resource/…） | 面板数据（/opt 在系统盘；备份可指向 /mnt/hdd） |
| `~/openresty_build/` | OpenResty loong64 重建套件（§8 配方 + vendor，~90M，保留以备重构建） |
| `loong-registry` 容器 + `loong-registry-data` volume | 本地镜像仓库（127.0.0.1:5000，restart=always） |
| firewalld public zone | 10086/tcp（安装器自动放行）、3389/tcp（远程桌面） |

## 14. 参考

- 1Panel 源码：https://github.com/1Panel-dev/1Panel （v2.4.2）
- 官方 v2 在线安装引导：https://resource.fit2cloud.com/1panel/package/v2/quick_start.sh
- v2 安装包 CDN：`https://resource.fit2cloud.com/1panel/package/v2/stable/{版本}/release/`
- 应用商店索引：`https://apps-assets.fit2cloud.com/dev/1panel.json.zip`
- 龙芯容器仓库：https://lcr.loongnix.cn （Harbor API：`/v2/library/<img>/tags/list` 可匿名查标签）
- 上游 loong64 先例：PR #8260（构建修复，已合并）、PR #4932（CI 支持，未合并）
