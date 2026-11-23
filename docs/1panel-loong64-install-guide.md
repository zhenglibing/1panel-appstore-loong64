# 1Panel 龙芯（LoongArch64）安装部署手册

> 适用对象：任何 loongarch64 Linux 设备（龙芯 2K3000 / 3A5000 / 3C5000 等；本文在
> **零刻 ME Pro + 龙芯 2K3000 + Loongnix 25.1（内核 6.6.52-loong64）** 上全流程实测）。
> 目标：从裸系统到「1Panel 面板 + 应用商店可装 loong64 应用」完整可用。
>
> - 构建过程与移植原理的完整记录见 [1panel-port-manual-v2.4.2-loong64.md](1panel-port-manual-v2.4.2-loong64.md)
> - 应用镜像如何构建见仓库根 [README.md](../README.md)（pipeline.py + recipes/）
>
> 本文档为公开脱敏版：凭据、入口路径等以 `<占位符>` 表示，请替换为你自己的值。

---

## 0. 五分钟速览（已经装好 Docker 的设备）

```bash
# ① 面板：直接下载现成安装包（Releases · panel-v2.4.2-loong64，含 sha256，见 §3 路线 B），
#    或用 fork 源码交叉编译（PC 上 ~10 分钟，见 §3 路线 A）后在设备上免交互安装（见 §4）
# ② 镜像供给：零配置 —— fork 的 agent 内建「映射层 + ACR 二级回源」，
#    安装应用时自动改写 compose 并从公共 ACR 匿名拉取 loong64 镜像
# ③ 商店：面板默认连官方商店源即可用（见 §7 路线一）
# ④ 验证：商店装一个 Redis，容器起来就是端到端通了（见 §8）
```

三条部署路线对比（可组合）：

| 路线 | 依赖 | 适用 | 离线可装 |
|---|---|---|---|
| **一 · 官方商店直连**（推荐起点） | 网络 + ACR 公共镜像源 | 快速上手，装「已移植清单」内应用 | ✗（在线） |
| **二 · 本地 registry** | 自建/回填镜像到设备 | 内网、离线装机、自建应用 | ✓ |
| **三 · 自建商店镜像站** | 路线二 + 镜像站构建 | 全量 268 应用离线可装、规范化修复 | ✓✓ |

---

## 1. 环境要求与检查

| 项 | 要求 | 实测环境 |
|---|---|---|
| 架构 | loongarch64（`uname -m`） | loongarch64 |
| 系统 | Loongnix 25.x（Debian 系 apt；其他 loongarch64 发行版需自行对应包名） | Loongnix 25.1 |
| 内核 | ≥ 6.6 | 6.6.52-loong64 |
| 内存 | ≥ 4G（编译在 PC 侧做，设备只跑面板+容器） | 32G |
| 磁盘 | 系统盘 ≥ 20G；镜像/数据盘建议大容量 NVMe/SATA | NVMe 953.9G + SATA 465.8G |
| 网络 | 能访问 lcr.loongnix.cn（国内直连）；能访问官方商店 CDN（apps-assets.fit2cloud.com，国内直连）；需要 ACR 公共镜像源（阿里云国内直连） | 同 |
| 权限 | root 或 sudo；装 Docker 后把用户加入 docker 组免 sudo | lingke + sudo |

检查命令：

```bash
uname -m                                   # 期望 loongarch64
cat /etc/os-release | head -2              # Loongnix
free -h ; df -h / /var/lib/docker 2>/dev/null
```

> ⚠️ Loongnix 25.1 的 **firewalld 默认启用**（nftables 后端；iptables INPUT 全 ACCEPT 是假象）。
> 面板安装器会自动放行面板端口，但**后续在面板外自开的服务端口要手动放行**：
> `firewall-cmd --permanent --add-port=端口/tcp && firewall-cmd --reload`

---

## 2. 安装 Docker（Loongnix 官方源）

download.docker.com 没有 loong64 包；Loongnix 源版本足够新（26.1.5）：

```bash
sudo apt update
sudo apt install -y docker.io docker-compose        # 26.1.5 + compose v2 插件
sudo systemctl enable --now docker
sudo usermod -aG docker $USER                        # 免 sudo（重新登录生效）
```

推荐 `/etc/docker/daemon.json`（NAS 场景：日志封顶 + live-restore）：

```json
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "50m", "max-file": "3" },
  "live-restore": true
}
```

`sudo systemctl restart docker` 后验证：

```bash
docker version                                       # 26.x
docker run --rm lcr.loongnix.cn/library/alpine:3.24 uname -m
# 期望输出 loongarch64 —— 这是龙芯官方容器仓库，国内直连快
```

> **镜像仓库铁律**：Docker Hub 基本没有 loong64 manifest 且国内不可直连；
> 龙芯镜像优先级 = 本地 registry > ACR 公共源 > lcr.loongnix.cn。别指望 Hub。

---

## 3. 1Panel loong64 的两条获取路线

上游官方只发 amd64/arm64 包。loong64 面板来自本项目的 fork（对上游 v2.4.2 零侵入增量，
`runtime.GOARCH` 门控，其他架构零影响）：

- fork：`https://github.com/zhenglibing/1Panel`，分支 **`loong64-support`**
  （= 上游 v2.4.2 + 27 个移植提交：商店镜像映射层、php8 同步豁免、商店源覆盖、ACR 二级回源）

### 路线 A：交叉编译（推荐，约 10 分钟）

**构建端**（Windows/Linux x86 均可）：

```bash
# ① Go ≥ 1.27.3（对齐 go.mod；国内镜像下载免安装）
curl -L -o go1.27.3.windows-amd64.zip https://mirrors.aliyun.com/golang/go1.27.3.windows-amd64.zip
# 解压后用绝对路径引用；export GOTOOLCHAIN=local GOPROXY=https://goproxy.cn,direct

# ② 前端（Node ≥ 22.12，Vite 8 要求；npmmirror）
git clone --depth 1 -b loong64-support https://github.com/zhenglibing/1Panel.git
cd 1Panel/frontend
npm install --registry=https://registry.npmmirror.com --no-audit --no-fund
npm run build:pro
# vite outDir 直写 ../core/cmd/server/web，go:embed 直接吃掉，无需手工拷贝

# ③ 交叉编译两个二进制（源码零修改一次通过；sonic 自动回退 encoding/json）
export PATH="/path/to/go/bin:$PATH" GOTOOLCHAIN=local GOPROXY=https://goproxy.cn,direct
cd ../core
CGO_ENABLED=0 GOOS=linux GOARCH=loong64 go build -trimpath -ldflags '-s -w' -o ../build/1panel-core ./cmd/server
cd ../agent
CGO_ENABLED=0 GOOS=linux GOARCH=loong64 go build -trimpath -ldflags '-s -w' -o ../build/1panel-agent ./cmd/server

# ④ 验证架构：ELF 头 e_machine=258 (EM_LOONGARCH)
readelf -h ../build/1panel-core | grep Machine
```

### 路线 B：组装安装包（官方 amd64 包做模板，只换二进制）

> **现成安装包（推荐，跳过本节）**：[Releases · panel-v2.4.2-loong64](https://github.com/zhenglibing/1panel-appstore-loong64/releases/tag/panel-v2.4.2-loong64)
> —— 从 fork `loong64-support` @ `c8becdc` 交叉编译的完整包（含全部映射规则 + ACR 二级回源），
> sha256 随附；安装步骤直接看 §4。

```bash
# 官方包结构：1panel-core / 1panel-agent / 1pctl / GeoIP.mmdb / install.sh / lang/ / initscript/ / *.service
curl -LOk https://resource.fit2cloud.com/1panel/package/v2/stable/v2.4.2/release/1panel-v2.4.2-linux-amd64.tar.gz
tar xzf 1panel-v2.4.2-linux-amd64.tar.gz -C template/
# 复制目录结构为 1panel-v2.4.2-linux-loong64/，把两个二进制换成路线 A 的产物
tar czf 1panel-v2.4.2-linux-loong64.tar.gz -C staging 1panel-v2.4.2-linux-loong64
```

> 官方 `install.sh` 内部**无架构检查**（架构门槛只在 CDN 的 quick_start.sh 引导脚本），
> 包内脚本一行不用改；本地部署直接跳过引导脚本、手动装即可。
> （若你有现成的 `1panel-v2.4.2-linux-loong64.tar.gz`，本节整段跳过。）

---

## 4. 设备安装 1Panel

```bash
# 传包到设备后：
sha256sum 1panel-v2.4.2-linux-loong64.tar.gz          # 与构建端核对
tar xzf 1panel-v2.4.2-linux-loong64.tar.gz -C /tmp/ && cd /tmp/1panel-v2.4.2-linux-loong64

sudo bash install.sh --non-interactive --lang zh \
    --port 10086 --entrance <入口> --username <管理用户> \
    --password '<强密码>' --install-docker n
```

- `--install-docker n`：已装 Docker 就不要让安装器再装一遍（双保险，安装器本身检测到 ≥20 也会跳过）
- 入口/用户名规则 `^[a-zA-Z0-9_]{3,30}$`，密码 `^[a-zA-Z0-9_!@#$%*,.?]{8,30}$`
- 安装器自动完成：二进制 → `/usr/local/bin`、`1pctl` 模板化、systemd 双服务
  （`1panel-core.service` / `1panel-agent.service`）enable+start、**firewalld 放行面板端口**
- 忘了凭据：`sudo 1pctl user-info` 随时可查

安装完成：浏览器访问 `http://<设备IP>:10086/<入口>`。

实测资源占用：core RSS ~39M + agent RSS ~75M，SQLite（纯 Go 驱动）WAL 正常。

---

## 5. 镜像供给：映射层与三个来源

这是龙芯上能装应用的核心机制，**全部内建在 fork 的 agent 里，零配置生效**：

1. **映射层**（`agent/app/service/app_loong64.go`）：安装/升级渲染 compose 时，
   仅当 `runtime.GOARCH == "loong64"` 才按规则表改写 image 引用：
   - 基座类直映 lcr（redis→7.4.1、mysql→5.7.29-an23/8.4.3、postgres→13/15/17 系、mariadb、
     mongo、minio、memcached、rabbitmq、emqx、grafana、phpmyadmin、wordpress 等，
     主版本路由 + 兜底 tag）；
   - 自建应用映射到本地 registry（`127.0.0.1:5000/loong/<key>:<tag>`，保 tag）；
   - 不可移植应用（jellyfin 等，58 条）安装时直接返回明确中文提示；
   - 带 `build:` 段的模板照常改写（规则白名单精确匹配，不会误伤真源码构建应用）。
2. **ACR 二级回源**：改写后的本地 ref 先探测（HEAD，3s 超时），miss 或本地 registry 停机
   即自动换 **ACR 公共镜像源** ref 匿名拉取——所以**新设备不需要本地 registry 也能在线装**。

三个镜像来源（按优先级自动协同）：

| 来源 | 地址 | 说明 |
|---|---|---|
| **ACR 公共镜像源** | `crpi-a02ej0ppuvq7b0mw.cn-hangzhou.personal.cr.aliyuncs.com/1panel-loong64/<key>:<ver>` | 本项目构建的全量应用镜像（约 370 tag），逐仓库公开，**匿名可拉**；回源自动用，也可手动 pull |
| **本地 registry** | `127.0.0.1:5000/loong/<key>:<tag>` | 自建镜像的内网分发层（registry:3.1.1 容器，卷 `loong-registry-data`）；离线/内网场景必备 |
| **lcr.loongnix.cn** | `lcr.loongnix.cn/library/<repo>:<tag>` | 龙芯官方容器仓库，基座类直映目标；国内直连 |

手动验证 ACR 匿名拉取（可选）：

```bash
docker pull crpi-a02ej0ppuvq7b0mw.cn-hangzhou.personal.cr.aliyuncs.com/1panel-loong64/redis:7.4.1
docker inspect --format '{{.Architecture}}' <上面镜像ID>   # 期望 loong64
```

自建本地 registry（路线二）：

```bash
docker run -d --name loong-registry --restart always \
  -p 127.0.0.1:5000:5000 -v loong-registry-data:/var/lib/registry \
  lcr.loongnix.cn/library/registry:3.1.1
# 回填镜像：从 ACR/lcr 拉回后 docker tag + docker push 127.0.0.1:5000/loong/<key>:<tag>
# 或在 PC 构建后直接 push（见仓库根 README「快速开始」）
```

---

## 6. 面板与 agent 的升级

fork 增量以「rebase 上游 → 真机门禁 → 交叉编译 → 换装」循环维护：

```bash
# PC：门禁（agent 含 Linux-only syscall，Windows 宿主 go test 必败，必须交叉编译测试二进制到设备跑）
cd 1Panel/agent
GOOS=linux GOARCH=loong64 go test -c -o /tmp/app_loong64_test ./app/service
# 传设备执行，全 PASS 再出新二进制

# 设备：换装 agent（Text file busy，必须 stop→cp→start）
sudo systemctl stop 1panel-agent
sudo cp /tmp/1panel-agent /usr/local/bin/1panel-agent
sudo systemctl start 1panel-agent
# 验证：md5sum 对上 + strings 里能 grep 到新规则串 + 装一个新应用实测改写
```

> ⚠️ 面板版本升级后（尤其商店索引相关改动），注意 §7.3 的「商店三层缓存」。

---

## 7. 应用商店配置（三选一或组合）

### 7.1 路线一：官方商店直连（默认，零配置）

fork 的 agent 对商店源无特殊要求：面板装好后商店默认指向官方 CDN
（`apps-assets.fit2cloud.com`，国内直连）。同步应用索引后即可安装——
映射层 + ACR 回源在安装链里自动完成改写与拉取。

适合：快速上手、安装「已移植清单」内的应用。局限见 §11（个别上游包的解压兼容问题）。

### 7.2 路线三：自建商店镜像站（离线可装 + 包规范化，进阶）

自建镜像站解决两件事：**268 应用全量离线可装** + **上游包占位文件规范化**（见 §11 FAQ-1）。
构建器（改写 tar 包内 compose + 删占位条目 + 补目录条目 + 版本戳）在本项目作者环境
`1panel_port/appstore_build/store_loong_build.py`，核心逻辑：

1. 按 agent 规则表对每个应用的版本 tar 包做**双路改写**——安装走整包
   `{key}-{ver}.tar.gz`，必须改写 tar **内部** compose（散装 yml 只是兜底路径）；
2. 规范化包结构（上游 1018/1021 个包带 0 字节占位文件条目且无目录条目）；
3. 产物 = `1panel.json.zip` 索引 + 应用目录树，用 nginx 容器只读托管：

```bash
docker run -d --name loong-store --restart always \
  -p 8082:8082 -v /opt/loong-store:/usr/share/nginx/html:ro \
  lcr.loongnix.cn/library/nginx:1.28.0
```

4. 面板切源：agent 配置是 go:embed 嵌入的，外置文件整体覆盖
   `/opt/1panel/conf/app.yaml`（文件名必须 `.yaml`，须带完整 base+log 段），
   加一行 `base.app_repo_url: http://<镜像站IP>:8082` 后
   `sudo systemctl restart 1panel-agent`。agent 日志可证实索引从镜像站拉取。

### 7.3 商店同步与刷新（三层缓存，重要）

商店「检测到更新但装上还是旧 compose」之类的问题几乎都出在缓存层：

| 层 | 刷新方式 |
|---|---|
| 索引/包缓存 | version.txt 版本戳提升（**必须 `printf '%s'` 无换行写入**——带换行会让面板解析崩） |
| agent.db 的 `app_details.docker_compose` | 版本号不变时**不会**随 tar 改写刷新 → 需 sqlite UPDATE（表 `app_details` 字段 `docker_compose`）+ 重启 agent |
| 安装渲染 | 以 agent.db 的 compose 为准（不是 resource 目录的 tar 内容） |

手动强刷索引：面板 `POST /api/v2/apps/sync/remote`；镜像站内容更新后**必须重启
1panel-agent**（内置定时同步 ~240h 太慢）。

---

## 8. 安装后验证清单

```bash
# ① 双服务运行
systemctl status 1panel-core 1panel-agent --no-pager | grep Active

# ② 映射层在位（任选其一）
strings /usr/local/bin/1panel-agent | grep -m1 "lcr.loongnix.cn/library/redis"
grep -m3 "\[loong64\]" /opt/1panel/log/1Panel.log

# ③ 端到端：商店搜索 redis → 安装 → 容器 Up
docker ps --filter name=1Panel-redis
# 镜像应为 lcr.loongnix.cn/library/redis:7.4.1（映射直供）或
# crpi-...aliyuncs.com/1panel-loong64/...（ACR 回源）—— 都算通

# ④ 落盘 compose 的 image 行已被改写（映射触发的权威证据）
cat /opt/1panel/apps/redis/<安装名>/docker-compose.yml | grep image
```

FAQ 排障三板斧：①`strings agent 二进制 | grep 规则串`（部署的二进制含不含修复）→
②`/opt/1panel/log/1Panel.log` 的 `[loong64]` 行（改写是否触发）→
③落盘 compose 的 image 行（最终结果）。三方比对，一眼定位断在哪层。

---

## 9. 安装应用实战注意

- **伴生数据库类应用**（WordPress/Ghost/n8n/odoo 等，compose 带 PANEL_DB_* 服务）：
  - 伴生容器与应用容器同在 `1panel-network`，容器名互通（Docker DNS）；
  - **DB 用户要显式建**：面板装的 MySQL/PG 只建库不建业务用户，
    装应用前先 `docker exec <db容器> ... CREATE USER/GRANT`，否则应用 Access denied 重启循环；
  - 应用首启慢（迁移+初始化）：龙芯上 Spring 类冷启动可达 20+ 分钟，
    面板显示 Running ≠ 应用就绪，以应用日志/HTTP 探针为准。
- **容器命名**：面板容器名 = `1Panel-<应用key>-<随机4位>`，与安装名无关；
  脚本化检测用 key 前缀 grep，别用安装名。
- **运行时类**（php/node/java/python/go 运行环境）：走 `/api/v2/runtimes` 流，
  安装时 `CONTAINER_NAME` 必传、代码目录必须预先存在；镜像引用 `${VAR}` 的，
  用「本地预置同名镜像 + 本地命中零拉取」机制代位。
- **删除重装**：删除是异步清理，立刻重装会报「应用名称已存在」；等 20 秒或换安装名。
- **安装失败取证**：面板安装失败的真实原因在 agent.db `app_installs.message`
  （404=pull 失败、解压错误、密码策略等都在这），不在 agent 日志。

---

## 10. 备份与恢复

**真正不可再生的资产 = Docker 数据卷 + 面板双库**；镜像可重建、商店包可重下。

```bash
# 面板库一致性快照（sqlite3 在线 backup，比直接 cp 可靠）
sudo python3 -c "import sqlite3; [sqlite3.connect('/opt/1panel/db/'+d+'.db').\
execute('VACUUM INTO \"/tmp/bk_'+d+'.db\"') for d in ('core','agent')]"

# 数据卷与面板目录
sudo tar czf bk_volumes.tar.gz -C /var/lib/docker volumes/
sudo tar czf bk_panel.tar.gz -C / opt/1panel/

# 本地 registry 卷（有自建镜像时）
sudo tar czf bk_registry.tar.gz -C /var/lib/docker volumes/loong-registry-data/
```

恢复顺序：系统 → Docker → 恢复卷 → 恢复 /opt/1panel（含商店源 app.yaml）→ 覆盖双库 →
起服务。registry 卷建议每次大变更后直接 tar 落盘异地（**不要**依赖「可由构建上下文重建」）。

> ⚠️ `docker image prune -a` 会删除所有未被运行容器引用的镜像（含 lcr 缓存）且
> dangling 层不可恢复——registry 有 tag 的可全量 pull 回来（localhost 仅分钟级），没 tag 的永久丢失。

---

## 11. 故障排查 FAQ

| # | 症状 | 原因与对策 |
|---|---|---|
| 1 | 安装报 `archive file path is a directory` | 上游商店包带 0 字节占位文件条目 × v2.4.2 严格解压器。对策：自建镜像站做包规范化（§7.2）；或换装该应用其他版本 |
| 2 | 安装报 `no matching manifest for linux/loong64` | 改写没触发。三板斧（§8）：agent 二进制有无规则（strings）→ 日志 `[loong64]` 行 → 落盘 compose image 行。老二进制就升级 agent（§6） |
| 3 | 映射改写成功但拉取超时 | 本地 registry 没起/镜像缺失，且 ACR 回源网络不通。`docker pull` ACR 地址手动验证网络 |
| 4 | 面板提示「该应用暂无 LoongArch64（龙芯）版本镜像…」 | 正常拦截（D 层 58 条：.NET/GPU/闭源/上游死亡等）。这是设计行为，不是故障 |
| 5 | 登录一次失败就要求验证码 | 防爆破机制（内存态）。重启 `1panel-core` 清除 |
| 6 | 外部访问面板/应用端口不通 | firewalld 没放行（nftables 后端）。`firewall-cmd --permanent --add-port=端口/tcp && firewall-cmd --reload` |
| 7 | 应用安装报数据库认证失败 | 伴生 DB 只建库没建业务用户（§9）。显式 CREATE USER + GRANT 后重启应用 |
| 8 | 商店「已是最新」但改写没生效 | 三层缓存（§7.3）：version.txt 戳 → agent.db compose UPDATE → 重启 agent |
| 9 | 面板容器名和安装名对不上 | 容器名 = `1Panel-<key>-<随机>`，面板忽略安装名参数。按 key 前缀 grep |
| 10 | Node 类自建镜像启动 CPU 100% 不响应 | libuv io_uring 在 loong64 + 6.6 内核自旋挂死。镜像里烘 `UV_USE_IO_URING=0` |
| 11 | `docker commit` 后镜像行为怪异 | commit 会继承容器的 entrypoint/CMD/WORKDIR 运行时状态；`--change` 显式覆盖，空数组 `ENTRYPOINT []` 会被静默忽略 |
| 12 | lcr.loongnix.cn 偶发拉不动 | 官方仓库偶发抖动/维护。兜底：ACR 公共源（全量已移植应用镜像都在）+ 本地缓存 |
| 13 | 磁盘看 du 很大但 df 没降 | du 向上取整 + root 属主目录 rmtree 静默失败。以 df 为准；先 `sudo chown -R` 再删 |

---

## 12. 已知限制

- **面板版本基线 v2.4.2**：fork 以 rebase 方式跟随上游；商店机制若上游大改需重适配。
- **应用覆盖**：上游 268 个商店应用中已移植 148 个（镜像在 ACR 匿名可拉）+ 基座类 27 项
  lcr 直映 + 7 类运行时（php/node/java/python/go 等）代位；58 个不可移植项安装时明确拦截。
  全量 268 应用无「装不上的灰区」（未移植且未拦截的中间态为零，NONLOCAL=0 口径）。
- **版本漂移**：上游商店发新版后，ACR 里没有对应 tag 的会安装失败——属预期，
  等本仓库按配方跟进构建（见仓库根 README「体检与维护」）。
- **官方 CDN 包解压兼容**：见 FAQ-1（占位文件问题自建镜像站已规范化规避）。
- **验证深度**：「已移植」指安装可完成 + 服务健康探针通过；个别应用的部分高级功能
  （如依赖专有原生库的可选特性）存在文档标注的降级。

---

## 13. 参考

- fork（面板 loong64 适配）：`https://github.com/zhenglibing/1Panel`（分支 `loong64-support`）
- 本仓库（商店镜像构建管线 + 配方 + 文档）：`https://github.com/zhenglibing/1panel-appstore-loong64`
- ACR 公共镜像源：`crpi-a02ej0ppuvq7b0mw.cn-hangzhou.personal.cr.aliyuncs.com/1panel-loong64/`（匿名拉取）
- 龙芯官方容器仓库：`https://lcr.loongnix.cn`
- 移植全记录：[1panel-port-manual-v2.4.2-loong64.md](1panel-port-manual-v2.4.2-loong64.md)
- 移植总报告（wave29-79）：[loong64-port-report-20261123.md](loong64-port-report-20261123.md)
- 上游项目：`https://github.com/1Panel-dev/1Panel` · 许可：GPL-3.0（随上游）
