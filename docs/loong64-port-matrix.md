# 1Panel 应用商店 loong64 移植矩阵（268 应用全量盘点）

生成日期：2026-11-06　|　商店版本：v2.4.2 dev 通道（268 应用）　|　比对基准：lcr.loongnix.cn 公开目录 270 仓库（44 命名空间）
盘点工具：`1panel_port/patches/inventory_all_apps.py`（扫描）+ `compare_inventory.py`（分层）→ 原始数据 `patches/_inventory/`

> 更新 2026-11-06：**OpenResty 移植完成**（A 层 29→30）——自建 loong64 镜像（WAF/brotli/lsqlite3 全组件）入库本地 registry，商店安装+建站闭环用户验收通过，详见《README-1Panel移植适配手册.md》§8。

## 总览

> **更新 2026-11-07：mega216 全量评估 + 波次二/三**——216 个 B 层应用已逐一评估（上游 manifest 探测 + 逐应用判定），**61 个已构建入库并冒烟验证**（波次二 dockge；波次三 8 个；波次四 6 个；波次五 forgejo-runner；clickhouse 因 lcr 旧版段错误改判 D，其中 7 个经商店端到端安装验证）、61 个判定暂缓（F：构建链过重/闭源/依赖阻塞，含逐应用原因；waline 镜像可构建但 thinkjs API 层挂起，记 F 详注；nezha 缺 swagger 生成+双前端仓库组装；dbhub 已转 TypeScript 项目）、18 个判定不可移植（D）。完整清单与逐应用移植报告见 **《README-商店应用移植报告-mega216.md》**；本地 registry 现有 72 仓库，映射层 agent v13 已部署（99 条映射规则 + 19 应用 D 层拦截表，真机单测 PASS；mssql 拦截/dockge/memos/opengist 商店端到端安装验证）。
>
> **更新 2026-11-08：波次六**——komari（双仓库 web 组装 + 设备 CGO，商店端到端 ✅）、openldap（debian sid slapd + bitnami 环境接口仿真，商店端到端 ✅）、casdoor（yarn→npm + modernc sqlite 升级 v1.34.5 + web/build 烤入，镜像入库，商店流程需外部 DB 故未装）、couchdb/obsidian-livesync 判 F（Debian 无 couchdb deb 且 sid 仅 mozjs 140，couchdb 3.5 需 mozjs 91 链）。自建镜像 61→**64**，registry 72→**76 仓**，规则 99→**101 条**，agent **v14** 已部署；面板 Running 应用达 **11 个**（redis/openresty/ddns-go/uptime-kuma/freshrss/it-tools/dockge/memos/opengist/komari/openldap）；36 个带 v 镜像已补无 v 别名（商店 tag 无 v 前缀）。
>
> **更新 2026-11-08：波次七**——**casdoor 商店端到端闭环 ✅**（补齐商店版 v4.25.0 镜像 + 入口脚本把 PANEL_DB_* env 落到 conf/app.conf——casdoor 只认配置文件不认 env；postgresql 商店安装走 A 层映射 lcr postgres:15.7-sid，healthy）；**nezha v2.6.1 攻坚入库 + 商店端到端 ✅**（swag init 生成 swagger docs + admin/user 双前端 dist 组装 + gozstd 无 loong64 预编译 blob → replace+loong64 shim 链系统 libzstd + 设备 CGO）。自建镜像 64→**65**，registry 76→**77 仓**，规则 101→**103 条**，agent **v16**；面板 Running 达 **14 个**（+postgresql/casdoor/nezha），商店可用 **103/265（≈39%）**。补丁 v10（649 行）apply-check PASS。
>
> **更新 2026-11-08：波次八**——**cloudreve 4.19.1 / woodpecker v3.20.1（server+agent 双镜像）/ focalboard 7.11.4 全部入库并商店端到端 ✅**；siyuan 判 F（需源码构建 onnxruntime，链路过重）。自建镜像 65→**68**，registry 77→**81 仓**，规则 103→**107 条**，agent **v17**；面板 Running 达 **17 个**（+cloudreve/woodpecker/focalboard），商店可用 **107/265（≈40%）**。新坑：build tags 门控的 Go 文件遇 Windows CRLF 会静默失效（`//go:build sqlite3\r` 不匹配）→ 打包期 LF 归一化；mattn v2.0.3 老 binding 在 musl 缺 pread64/off64_t → CGO_CFLAGS -D_LARGEFILE64_SOURCE；woodpecker 要 go≥1.27 → GOTOOLCHAIN=auto 经 goproxy 自动拉新工具链。补丁 v11（660 行）apply-check PASS。
>
> **更新 2026-11-08：波次九**——**vaultwarden 1.37.5 商店端到端 ✅**（rust 二进制早已编成，缺的是官方预编译 web-vault——bw_web_builds release 解包叠层即通；USER vw→root + ROCKET_ADDRESS=0.0.0.0 两处镜像修正）。回收尝试：certimate 判 F 详注（devEngines/子模块 SSH→HTTPS 转换后可编译，但运行期 pocketbase/modernc DB 层栈溢出——loong64 依赖链问题）、bililive-go 判 F 详注（react-scripts 构建栈在 node22/24 均崩溃 `reading 'date'`）、excalidraw 暂缓（PC yarn 环境损坏）。自建镜像 68→**69**（+vaultwarden web-vault 叠层），registry 81→**82 仓**（bitwarden 双 tag 别名），规则 107→**108 条**，agent **v18**；面板 Running **18 个**（+bitwarden），商店可用 **108/265（≈41%）**。补丁 v12（662 行）apply-check PASS。
>
> **更新 2026-11-08：波次十**——**excalidraw latest / easytier v2.7.0 入库并商店端到端 ✅**（excalidraw=设备容器内 yarn 构建+esbuild resolution 钉新版破 loong64 崩溃+本地 nginx:1.28.0 运行层；easytier=主机 rustup 1.90 编译+debian:sid 运行时+ENTRYPOINT 补齐）；rustdesk-server 判 F 详注（上游 rustdesk-org 重写多个 git 依赖仓库，1.1.16 源码构建已腐化）；dosgame 判 F（上游仓库 404）。自建镜像 69→**71**，registry 82→**85 仓**，规则 108→**111 条**，agent **v19**；面板 Running **20 个**（+excalidraw/easytier），商店可用 **111/265（≈42%）**。补丁 v13（671 行）apply-check PASS。
>
> **更新 2026-11-08：波次十一**——**评论双雄全部端到端闭环 ✅**：twikoo（真凶=artifact 误装客户端包 `twikoo`，服务端实为独立 npm 包 **`tkserver`**——按官方 Dockerfile 重装即通）；**waline 撤销 F 转正 ✅**（strace 破案：挂起=镜像内 better-sqlite3 原生模块缺失→require 无限重试循环，**非 thinkjs/loong64 架构问题**；修复=容器内 node-gyp 现场编译（npmmirror 缺 node26 SHASUMS → 手动预置 ~/.cache/node-gyp 头文件）+ waline 官方 waline.sqlite.sql 建表 SQL 做启动初始化层——上游本不自动建表）。规则 111→**113 条**，agent **v21**；面板 Running **22 个**（+twikoo/waline），商店可用 **113/265（≈43%）**。补丁 v14（678 行）apply-check PASS。
>
> **更新 2026-11-08：波次十二**——**wikijs 3.1.0 重工程攻坚端到端闭环 ✅**（F 清单清完后首个大项）：官方 release tarball **v3 直跑 TypeScript**（node26 原生 type-stripping，零构建）；**Temporal 全局缺失**（lcr node26 无此 API，26 个文件深度使用、--harmony-temporal 也不开）→ `temporal-polyfill` 经 `--require` 预载根治；sharp/puppeteer/pandoc 三个可选扩展全部优雅降级。**PG17 门槛遇上 lcr 全网宕机** → plan-B：**deb.debian.org sid main 自带 loong64 的 postgresql-18.6**（debian-ports 反而无 loong64！）→ 自建 PG18 影子 tag `lcr.../postgres:17-sid`（本地已有镜像 docker 免拉取）；两个新坑：docker commit 继承临时容器 config 需显式重声明 ENTRYPOINT、官方 postgres 镜像监听 0.0.0.0 是构建期 sed 进 conf.sample 的换大版本必须重打。商店 service 联动首次打通：PANEL_DB_HOST 直传容器名（面板无 database 记录时原样透传）、DB_PORT 空值被 wiki `$(VAR:def)` 的 `||` 回退兜住、API 装数据库应用需手动 CREATE USER/DATABASE（casdoor 同款）。自建镜像 +postgres PG18（wikijs 重建覆盖旧坏 tag），registry 现载 **85 仓**，规则 113→**114 条**，agent **v22**；面板 Running **24 个**（+postgresql17/wikijs），商店可用 **114/265（≈43%）**。补丁 **v15**（683 行）apply-check PASS。
>
> **更新 2026-11-08：波次十三**——**audiobookshelf 2.37.2 端到端闭环 ✅（F 清单最后一个大项，至此 B 层大项全部归零）**：client=**Nuxt2 webpack4 + tailwind v4（原生 oxide 无 loong64 预编译且 npm 包不含 Rust 源码）→ 客户端搬 PC 构建**（产物架构无关，唯一特判 webpack4 需 `NODE_OPTIONS=--openssl-legacy-provider`）；server=tsc 编译 + sqlite3 5.1.7 源码构建（**sid python3.14 移除 distutils → 老版 node-gyp 8.4.1 全挂，apt python3-setuptools 的 vendored shim 即修**）；运行层 node20-debian + **sid ffmpeg 9.0.2 loong64**（apt 直装可用）；libnusqlite3（unicode 搜索扩展，官方仅 musl x64/arm64 预编译、源码构建需现拉 bitbucket）走条件加载优雅降级。发现：**API 直装端口绑定 127.0.0.1 回环是面板全舰队统一默认**（UI"外部访问"开关才 0.0.0.0）；upstream 默认 base path `/audiobookshelf`。自建镜像 +1（2.67GB），registry **86 仓**，规则 114→**115 条**，agent **v23**；面板 Running **25 个**全绿，商店可用 **115/265（≈43%）**。补丁 **v16**（688 行）apply-check PASS。
>
> **更新 2026-11-08：波次十四**——**全舰队映射体检（质量保障波）**：以商店 265 应用当前版本为基准全量解析映射（115 规则→111 映射检查：81 本地 registry manifest 级 + 28 lcr 引用），**抓出 17 个版本漂移 404**（商店上游发新版后 keep-tag 模式下新 tag 无镜像：adguardhome/adminer/beszel/ezbookkeeping/frpc/frps/memos/navidrome/opengist/prometheus/roundcube/screego/sftpgo/watchtower 等）→ **14 项补 tag 别名修复**（4 项纯后缀差完全等价、10 项同谱系滞后标注）；**1 个 F 遗留死规则清除**（rustdesk-server：wave-10 判 F 但规则未删、镜像从未入库 → 转拦截表）；**2 项标记需重建**（gitea 1.25.4→27.3.11 跨代、zabbix-agent alpine-7.4.5→ubuntu-7.0.27 变体错配）。复测 **78/81 全绿**（余 3 项均为已记录待办）；lcr 仍宕机，28 个 lcr 引用中 4 个本地缓存可验全绿、24 个挂"待 lcr 恢复"。规则 115→**114 条**（rustdesk 删除）、拦截表 19→**20**，agent **v24**；面板 Running **25 个**全绿。补丁 **v17**（692 行）apply-check PASS。**体检机制沉淀：商店版本漂移是常态，建议每次商店同步后复跑 audit14 系列（parse→gen→device 三段脚本已入库）。**
>
> **更新 2026-11-08：波次十五**——**重建待办池清空（10/10）✅**：波次十四体检产出的全部重建项一次批量落地。**替代构建**（store tag ↔ 上游 tag 错位，pipeline 新增 `git_tag` 字段=克隆真上游 tag、镜像打 store tag，文档标注替代关系）：gitea 27.3.11←**CE v1.27.3**（EE 分支版本号上游不存在）、memos 26.11.0←**上游 v0.31.0**（上游根本没有该版本号，store 走了独立版本线）、zabbix-agent ubuntu-7.0.27←sid apt 7.4.x（agent 与旧 LTS server 兼容）。**直对重建**：adguardhome v0.107.80 / beszel v0.21.1 / navidrome v0.64.2 / opengist v1.15.3 / prometheus v3.15.1 / screego v1.12.6 / ezbookkeeping v2.1.1。其中 navidrome 与 ezbookkeeping 因新版引用 mattn sqlite3 Backup/Error 完整 API → **必须设备端 CGO 构建**（PC 交叉编译的 sqlite3 stub 不够）：navidrome 需 `-tags "netgo sqlite_fts5"`（⑩哨兵变体）、ezbookkeeping 需 dist→public + templates + data/log/storage 四件套。复跑体检 **80/81 = 98.8% 全绿**（唯一 404 为已转拦截的 rustdesk 检查残留）；面板 25 应用全绿。规则/补丁不变（114 规则+20 拦截 / v17）。
>
> **更新 2026-11-08：波次十六**——**VAR 层打通：PHP 运行环境端到端闭环 ✅（建站生态最后一块拼图）**。三处上游死结逐一化解：① 商店 `php8` 被 `deprecated: 2.0` 在**同步期**过滤（`getApps` 短路，store 里根本不存在）→ agent v25 放行 php8 单键（php5/7 仍屏蔽）；② 运行时 compose `${IMAGE_NAME}` 由用户填写 → **本地预建 `1panel-php-fpm:8.4.27`**（sid apt php8.4.27-1 **与商店 8.4.27 精确同版**，520MB 含 84 模块/redis/imagick/apcu/memcached/xdebug/yaml/Composer 2.11，www-data uid 1000，复刻官方 php 挂载布局），compose up 命中本地镜像零拉取；③ `install-ext` 官方脚本依赖 pear/phpize → **自写 apt 版 install-ext**（63 项映射 + 不支持的优雅跳过），运行时"扩展安装 → docker exec → docker commit"链路实测通过（odbc 非预装 → 安装后 PDO_ODBC/odbc 双模块加载）。网站闭环：`POST /api/v2/websites type=runtime + runtimeID` → openresty fastcgi_pass 127.0.0.1:9010 → 默认 index.php 动态渲染 **PHP 8.4.27 + 扩展清单**；**上游遗留 bug**：UI 传 resource=remote 而 website 服务比对 appstore → 已把运行时记录修正为 appstore。lcr 全程宕机不受影响（底座 debian:sid 缓存 + tuna http 源；**https 源在老容器验签失败，apt 必须用 http**）。VAR 其余项处置见下表（node/go/java/python/dotnet 卡在显式 pull，待 agent 守卫改造）。agent **v25**（114 规则+20 拦截不变），补丁 **v18**（716 行）apply-check PASS。

> **更新 2026-11-08：波次十七**——**VAR 层五连击：go/node/python/java 运行时全部闭环 ✅（零 agent 改动）**。波次十六的"显式 pull 必挂"结论被推翻——读 `pullComposeImages` 实现发现**本地已有镜像即跳过 pull 的守卫本来就在**（`ImageExists → continue`），VAR 解锁纯粹是镜像供给问题。供应四件套：`golang:1.26`（lcr alpine 底座 apk 补 bash/git 重打，alpine 无 bash 会让 `bash /run.sh` 直接挂）、`1panel/node:26.13.0/22.23.4/20.20.2`（lcr node 三档 tag 别名，debian 底座）、`python:3.14.8`（sid apt python3.14.10 自建 + venv/pip + python symlink）、`1panel/java:21`（sid apt openjdk-21-jdk-headless 自建）。四类型逐项验证：go demo `go run main.go`→go1.26.8 ✅、node demo→v26.13.0 ✅、python demo→3.14.10 ✅、java 单文件源码启动→21.0.13 ✅（18300-18303 四端口 HTTP 实证，面板五运行时 API 全 Running 截图留证）。dotnet 判 F（mcr 无 loong64）。商店可用 **120/265（≈45%）**；agent/补丁不变（v25 / v18）。

> **更新 2026-11-09：波次十八**——**WordPress 全栈金丝雀 ✅（PHP 运行时 + 建站 + 数据库三链条真枪实弹）**。lcr 仍宕机，全程离线：①商店装 MySQL——缓存镜像别名 trick（`docker tag` 把缓存的 lcr mysql:8.4.3 打成商店要的 8.4.13，compose up 本地命中零拉取），1Panel-mysql 容器 mysqld 8.4.3 loong64 正常服务；②建 wp16 网站绑 php8427 运行时 + 加 IP:8081 域名（PC hosts 无权限且 DNS 被 TUN 劫持，IP 域名绕开）；③WordPress latest-zh_CN 上传到站点目录（.user.ini 有不可变属性 chown 需排除）；④浏览器走完安装向导：**PHP 容器经容器名直连 MySQL 容器**（1panel-network DNS）、`wp-config.php` 自动写入（uid1000 可写）、**wp-admin 仪表盘完整渲染**、前台主题/文章全出（siteurl 丢端口需手动 UPDATE wp_options 补 :8081）。这验证的是波次十六/十七的运行时机器能承载**真实生产级 PHP 应用**，非 demo 级。商店可用计数不变 120/265（WordPress 是文件部署非商店 app）。

> **更新 2026-11-09：波次二十**——**离线可装性体检定论（audit20）+ 资产保护备份**。新工具 `audit20_offline.py`（入库 mega216/）：按 audit14 checks 基线逐项判定离线可装性——**87/111（78%）可离线装**（83 registry 支撑 + 4 lcr 精确缓存命中：mysql/postgres/redis/registry），**24 个 lcr 项仅在线可装**（2fauth/consul/elasticsearch/emqx/flarum/gitlab/grafana/influxdb/jaeger/jenkins/kibana/logstash/mariadb/memcached/mongodb/nats/neo4j/pgvector/phpmyadmin/portainer-ce/postgis/rabbitmq/wordpress/yourls），**别名可救 0 个**（缓存的 lcr 镜像 tag 与映射要求无一差补丁级可对齐）。lcr 仍宕机、商店无漂移。**glance 根治**：镜像 WORKDIR=/app/config 重打并 push（与商店包挂载约定对齐，容器重建 200 验证）。**keydb 正式定论：不构建**（valkey——Redis 兼容 fork——已在库并覆盖同生态位，eqalpha/keydb 的 `${ARCH}` 枚举无 loong64）→ VAR 层 14 项全部闭环、无待评估剩余。**资产保护**：设备全量移植资产 tar.gz（docker volumes 14G + panel db/www/runtime/apps/resource/log ~0.75G）回传 PC `E:/backup_2k3000/`——registry 架构的可重建性 + 数据卷备份双保险。
>
> **更新 2026-11-10：波次二十一全波完成（PC 侧 + 设备半场经外网映射 （公网运维隧道·地址端口已隐去））**——**自建商店源上线并端到端验证**。11-09 PC 侧：**A fork 分支 `loong64-support`**（v2.4.2 基线 3 commits：映射层/php8 豁免/商店源覆盖，已 push `zhenglibing/1Panel`）+ **agent v26**（新增 `base.app_repo_url` 商店源覆盖，77.6MB d2001b74…）+ **补丁 v19**（7 文件 665+，apply-check PASS）；**B 镜像树**：`store_loong_build.py` 规则表直解析 `app_loong64.go`（110 repo+4 base+20 blocked），CDN 全量下载 268 应用 → **tar.gz 内 compose + 散装 compose 双路改写**。11-10 设备半场：真机门禁 PASS → v26 上位 → nginx 容器 8082 托管 → 外置 `app.yaml` 切源（agent 日志证实从 8082 拉索引，268 应用同步）→ **E2E 真装 memcached 1.6.22 成功**（包内改写生效、镜像拉 lcr 目标、容器 Up、stats 验证；已装应用无损）。**排障新知【52】**：上游包 1018/1021 带 0 字节占位文件条目 × v2.4.2 SDK 严格解压器 → 装不上；镜像侧全量规范化（删占位+补目录条目，`w21_fix_tars.py`）修复，**权威总包 `store_loong_mirror.tgz` 378.9MB a8b7d143…**（取代 9c68546e…）。商店源切换后应用更新不再依赖 agent 重编译，映射层退化为兜底。**memcached 由"仅在线可装"转"在线即装"**（lcr 在线时直拉；规范化包 + 商店源切换同时验证了 A 层在线路径的全链路）。矩阵应用行不变；详见手册 §12 与报告 §九。

> **更新 2026-11-10：波次二十二**——**lcr 复苏红利：24 项在线限定批量转离线可装，离线可装率 87/111 → 111/111（100%）**。lcr 复苏（宕机约 11-04~11-10，memcached 真拉证实）→ audit20 的 24 个 ONLINE-ONLY 项按映射目标 tag 批量 `docker pull` 入本地缓存，**24/24 零 404 零漂移**（波次十四 tag 别名全部有效）；复跑 audit20 全绿——**lcr 再宕机时全量商店离线可装**（registry 83 自建 ∪ lcr 缓存 28 命中双保险）。postgres:17-sid 验真：lcr 确有真 tag，本地 PG18.6 影子刻意保留（现存数据卷 PG18 集群格式，真 PG17 会炸库；新装走缓存命中行为一致）。**watchtower 经新镜像源 B 层 E2E ✅**（image=127.0.0.1:5000/loong/watchtower → registry 命中 → Running；商店包写死 DOCKER_API_VERSION=1.52 × 设备 daemon 1.45 上限 → 镜像侧改写解决）——自建商店源双目标路径（lcr 直连 + registry 本地）全部真机验证。**三层缓存新知**：镜像源内容补丁必须包内改写 + 散装改写 + per-version lastModified 提升三件套（版本号提升只清包缓存，DB compose 缓存靠 per-detail 比较清）。权威总包定稿 **ed563554…**。F 项复查：clickhouse 的 lcr 仍只有旧 tag，保持 F。矩阵应用行不变（A 层 37 项全部真镜像在位）；详见手册波次二十二与报告 §十。

> **更新 2026-11-10：波次二十三**——**备份补打：商店源自持切换 + 24 镜像入缓存后的资产固化**。增量判定：卷树 mtime 全深度扫描证明 14G docker 卷（13G = loong-registry 自建镜像）与 11-09 全量母本 `backup_port_20261109.tar.gz`（13.7GB）逐位一致 → 不重拉；新增资产仅三处（/opt/1panel 414M、mega216 脚本、loong-store 快照哈希）→ 三包 + manifest（bk_panel 240MB / bk_db 一致性快照 735KB / bk_scripts 737KB / w23_manifest.txt 含 38 项 lcr 镜像摘要）落 PC `E:\backup_2k3000\w23_20261110\`，哈希全对上。矩阵应用行不变；详见手册波次二十三与报告 §十一。

> **更新 2026-11-10：波次二十四**——**滚动维护首次实战：上游 11-10 全局重发布检测与决策**。267 应用 lastModified 全刷但严格 diff 仅 18 项真实变化；5 项 B 层应用 6 个新 tag（gitea 27.3.12/glance v0.8.8/verdaccio 7.1.0/wallos 5.11.1/wikijs 3.2.0+3.3.0）镜像全 MISS → **决策保持 20261109 基线不采纳**（所见即可装优先），6 新 tag 入重建待办池。双体检复跑全绿；**体检口径修正**：剔除 rustdesk 拦截残留假阳性 → **audit20 新口径 110/110**（波次22 的 111/111 为含残留历史值）。矩阵应用行不变；详见手册波次二十四与报告 §十二。

> **更新 2026-11-10：波次二十五**——**6-tag 重建 + 采纳闭环：滚动维护完整走通一轮**。6 新 tag 全部入库（glance v0.8.8 真源码重建、verdaccio 7.1.0 E504 重试、wallos 5.11.1 真构建 + gitea 27.3.12/wikijs 3.2.0/3.3.0 同谱系别名）→ builder 升级（增量重建 + watchtower 环境适配内建化）→ STORE_VERSION 20261111 → delta 9.9MB overlay → 重同步 → **E2E 真装 glance 0.8.8 全绿**（Running + HTTP 200）。**【58】clone 缓存陷阱实战抓出**（换 tag 重建拿旧源码错标，红旗=耗时与旧版同速；已加 sha 校验）。商店基线升为 **20261111（1043 版本，上游 22 新版本全采纳）**；矩阵应用行不变；详见手册波次二十五与报告 §十三。

> **更新 2026-11-10：波次二十六**——**体检重定基 20261111 + 抓出采纳回漂移**。`audit26_parse.py` 从镜像树取改写目标直查存在性 → 109 检查（81 本地 + 28 lcr）→ 立刻抓出 **7 个本地 404**（caddy 2.11.9/casdoor v4.26.0/keycloak 26.8.2/kodbox 1.71.02/maddy 0.9.7/prometheus v3.16.0/sub2api 0.2.20，均为 11-09 快照时代潜入、offline 统计与版本 diff 双盲区）+ grafana 13.0.2-alpine 未缓存 → **7 同谱系别名 + grafana lcr 真拉**后全绿（79×200 + 28 命中，audit20 109/109）；7-tag 真构建入待办池（lag）。一键巡检 `roll_maint.py` 落地；备份补打#2（三包 + registry 86 仓 158 tag 权威登记）落 `E:\backup_2k3000\w26_20261111\`。详见手册波次二十六与报告 §十四。

> **更新 2026-11-10：波次二十七**——**lag 批次 7 项升级真构建 + digest 终审定案**。caddy 2.11.9/casdoor v4.26.0/keycloak 26.8.2/kodbox 1.71.02（源 1.71.03 顶）/maddy 0.9.7/prometheus v3.16.0（UI 迁 mantine-ui 改 fe 入口）/sub2api 0.2.20（前后端分离 `-tags embed`）全部 digest ≠ 前驱 + 设备本地缓存刷新；**【60】真构建终审判据 = digest 差异**（首轮 kodbox/sub2api smoke 全绿实为旧源码错标，靠 digest 揪出）。**流水线三缺陷修复**：smoke 假绿（PIPESTATUS）/ssh_put 115s×WAN（1800s+重试+device_extract）/clone 校验 fail-open（非 git 目录强制重取）。wikijs 3.2.0/3.3.0 + gitea 27.3.12 保持别名定案（无对应源 tag）。终态体检全绿（79×200+28 命中+0 miss，audit20 109/109）。详见手册波次二十七与报告 §十五。

> **更新 2026-11-09：波次十九**——**A 层离线可装性定论 + registry 离线装机 3/3 ✅**。三例 lcr 引用应用（memcached/nats/consul）面板 API 安装全部 InstallErr——**A 层"纯映射零构建"仅在线成立：镜像不在本地缓存时 lcr 宕机即不可装**（离线可装 = registry 支撑的 80 项 + lcr 缓存命中的 mysql/postgres 系）。改用 registry 支撑项实测离线商店安装：gotify 3.1.1 / glance 0.8.7 / adguardhome（商店现版本 0.107.79，compose 镜像 tag 漂移到 v0.107.80 仍在库）**3/3 Running** + HTTP 冒烟（gotify 200 / glance 200 / adguard 302 引导页）；面板安装总数 **29/29 全 Running**。附带修掉 glance 商店包挂载 bug（包挂 /app/config/glance.yml 而 glance 只读 $WD/glance.yml → 补 /app/glance.yml 绑定）。**推论：lcr 长期宕机下 B 层 registry 架构是唯一稳态；高价值 lcr 映射可逐步转本地 registry 镜像（批量 tag 别名/搬运）以获得离线可装性。（波次二十二已兑现：24 项批量转离线，111/111）**

> **更新 2026-11-16/17：波次四十四至五十六**——十三波连打（ghost/libvips 打通 sharp、n8n/certd/nocodb、jsonhero/mblog、certimate+gap120 分级、bililive/siyuan、mliev-dwz/redpanda-console、logto/umami、kkfileview/nexus、sonarqube（**lcr temurin=Zero VM 无 JIT 定论 → Loongnix 官方 JDK21 底座正解**）、清尾款（TestGzipTemplate CRLF 坑修复 + no_rule 99 应用全量分诊：34 拦截/40 候选/mysql-cluster 补映射）、kubepi+mattermost（Go 批）、**meilisearch（Rust 批首试）**）→ 体检 **161/161 全绿**，映射规则 159→**160 条**，拦截表 **58 条**，agent **v56**，STORE_VERSION **20261124**。**Rust 批首试配方（meilisearch 1.56.2，549MB 镜像）**：Windows host 跑不了 loongnix Linux 交叉 gcc → 设备 native 编译（lcr rust:1.100 完整版；rust-toolchain.toml 锁 1.98.1 由 rustup loong64 官方分发通道自动补齐；crates.io 直连卡死 → cargo config 走 rsproxy，800 crates/1.3G；ring 0.17 无 loong asm 但 generic C 路径可编可跑；产物 339MB 含 charabia 全语种分词字典，glibc 三依赖 → debian:sid 底座）。**镜像元数据三坑**：compose `command: sh -c` 覆盖 CMD → ENTRYPOINT 必须 `["/bin/tini","--"]`（对齐官方）；商店 config.toml 钉 `http_addr="localhost:7700"` → 镜像必须带 MEILI_HTTP_ADDR=0.0.0.0:7700 等 ENV 覆盖（官方 Dockerfile 同款）；docker commit --change 的 JSON 数组不能带 `\"`（否则被解析成 shell form）。另排查面板版本号机制（viper.go 硬编码 v2.0.0 为 dev 模式回落值 → app.yaml 补 version=v2.5.1 防误点官方 amd64 升级覆盖）。

> **更新 2026-11-19：波次五十七**——**Rust 批 #2 三应用全部闭环 ✅（rustfs 1.0.5 + stalwart-mail v1.1.0-alpine + vector 0.61.0-debian）**，E2E 真装三应用 15 秒级全绿（rustfs Running+S3 healthz 200 / vector Running+GraphQL 200 / stalwart Running+healthz 200），体检 **137/137 local 全 200 + 29 lcr 缓存命中 0 miss**（live-tree 口径另测 112/112）。**①R_LARCH_B26 重定位溢出攻坚（本波最大技术收获）**：rustfs 终产物巨大（datafusion+aws-lc 全家桶，.text 超大），aws-lc-sys 的 bcm.o 手写汇编在链接序末端、距 .plt 超 B26 ±128MB → 链接期 `relocation truncated to fit: R_LARCH_B26 against memcpy/__assert_fail/abort` 结构性死亡（此前多日被误判为容器被杀，实为切换 LTO-off 后的真实链接错误，追加式 history log 留尸定案）；修复=`CFLAGS="-fno-plt"`（C 侧外呼改 GOT 间接、64 位重定位无距离上限）+ 脚本内 `cargo clean -p aws-lc-sys` 强制 build.rs 重跑吃新 CFLAGS；11-19 20:03 二进制落地（506MB）且运行验证 S3 healthz 200。若再遇 Rust 侧对象溢出，升级方案 `RUSTFLAGS="-C link-arg=-fuse-ld=lld"`（未启用）。**②rustfs console 内嵌机制**：console UI 是编译期 RustEmbed（`rustfs/static/`，官方 build-rustfs.sh 的 download_console_assets 步骤从 release 下载 console.zip）——空目录构建 = "asset-less console"（`/rustfs/console/*` 404，但 S3 API 正常）；把官方 console.zip 解入 `static/` 重编即修复（index.html+version 双 200）。**③`links` 键连带重编**：`cargo clean -p aws-lc-sys` 因 aws-lc-sys 带 `links` 键会强制整条下游链重编（~840 crates 中尾段全量 + rustfs lib 单体 ~60-90 分钟静默期），并非只重编一包——每轮容器重启即触发一轮 ~70 分钟全链重编。**④跨会话冲突零击杀收场**：两 ZCode 窗口同设备并发（一方 SSH 清扫循环杀"日志冻结"容器 vs 另一方心跳+keepalive 铁桶阵），11-19 停战后改纯协议协作：追加式构建日志（RUN 头+心跳行+RC 尾）+ marker 文件（w57_done_rustfs/sw/vec）+ 冒烟门（新二进制 mtime + 新镜像 created + console 200 三门槛）→ 本窗 push 5 tags 后写 marker，对方 pack_all 循环见三 marker 齐自然退出打印 W57_PACK_ALL_DONE，全程无一次容器击杀。**⑤bash 运行中改脚本无效**：进程启动时已解析函数体（pack_all 内存中旧版 smoke URL curl `/` 永远 403 → console 门死循环），文件修正必须重启进程才生效。**入库清单**：rustfs 5 tags（1.0.0/1.0.1/1.0.3/1.0.4/1.0.5；debian:sid + TUNA apt + jq/curl + entrypoint 凭证归一/buckets.json 校验 + console 内嵌）+ stalwart-mail 2 tags（v1.0.3/v1.1.0-alpine；ENV CONFIG_PATH=/opt/stalwart 单卷布局、首启 bootstrap 向导 8080）+ vector 4 tags（0.58.0-0.61.0-debian；api 8686）→ 映射规则 160→**163 条**（wave57 三应用 keep-tag），repo 补丁 **e44e2b3**（wave29-57 映射规则+单测）+ **c0689a3**（vector 配方四坑注释）已 push `zhenglibing/1Panel@loong64-support`。**体检基线教训**：audit14 冻结 checks 清单不随商店入库自动更新（rustfs/stalwart/vector 均不在基线内，旧 126/126 口径实则未覆盖 wave57）→ **商店入库新应用后必须重生成 checks**，本波补齐 11 tag 后实测 137/137。

| 层 | 数量 | 定义 | 处理方式 |
|---|---|---|---|
| **A** | 37 | lcr 已有对应镜像（含 8 个自建入库） | 纯映射表扩充，零构建（映射层 v2 自动改写） |
| **B** | 216 | 无现成镜像，需源码构建或维持原样（**已自建 57 个：批次一~三 7 个 + mega216 50 个**，含 casdoor 镜像入库待商店依赖适配） | 滚动流水线：lcr 工具链底座自建 → 本地 registry → 入表；未处理前安装会报架构不匹配 |
| **C** | 1 | 上游官方自带 loong64 | 直接可用（openlist 镜像由参数注入，openlistteam/openlist 官方含 loong64 manifest） |
| **D** | 1 | 确认不可移植 | 映射层拦截并给明确提示 |
| **VAR** | 14 | 语言运行时类（php8/go/java/node…），镜像由参数驱动 | 属 1Panel runtime 生态（1Panel-dev/runtime），另册处理 |

**说明**：商店 dev 通道当前**没有 minio 应用**（已下架/改名）；lcr 有 minio 镜像可用，若商店恢复可直接映射。同名的 `linuxserver/*`、`bitnami/*` 变体镜像因 env/路径布局不同**不做同名替换**，归入 B 层需专门适配。

## A 层：直接映射清单（37 个，含本地 registry 自建 8 个）

| 应用键 | 名称 | 类型 | 商店镜像引用 | 映射目标 |
|---|---|---|---|---|
| 2fauth | 2FAuth | website | 2fauth/2fauth:9.0.1 | lcr library/2fauth |
| consul | Consul | website | hashicorp/consul:2.1.0 | lcr library/consul |
| docker-registry | Docker Registry | tool | registry:3.1.2 | lcr library/registry |
| elasticsearch | Elasticsearch | tool | elasticsearch:9.5.5 | lcr library/elasticsearch |
| emqx | EMQX | website | emqx/emqx:6.3.2 | lcr library/emqx |
| flarum | Flarum | website | crazymax/flarum:2.0.2 | lcr library/flarum |
| gitlab | GitLab | website | gitlab/gitlab-ce:19.5.3-ce.0 | lcr gitlab/gitlab-ce:17.6.2（tag 修正，官方 19.5.3 无龙芯） |
| grafana | Grafana | website | grafana/grafana:13.3.0 | lcr grafana/grafana:13.0.2-alpine |
| influxdb | InfluxDB | website | influxdb:3.12.2-core | lcr library/influxdb |
| jaeger | Jaeger | website | jaegertracing/all-in-one:1.76.0 | lcr jaegertracing/all-in-one:1.6.0 |
| jenkins | Jenkins | website | jenkins/jenkins:2.580.2-lts | lcr jenkins/jenkins:2.583-jdk21 |
| kibana | Kibana | website | kibana:9.5.5 | lcr library/kibana |
| logstash | Logstash | tool | logstash:9.5.5 | lcr library/logstash |
| mariadb | MariaDB | runtime | mariadb:11.8.9 | lcr library/mariadb |
| memcached | Memcached | tool | memcached:1.6.22-alpine3.18 | lcr library/memcached |
| mongodb | MongoDB | runtime | mongo:8.3.13 | lcr library/mongo |
| mysql | MySQL | runtime | mysql:8.4.13 | lcr library/mysql |
| n8n | n8n | website | n8nio/n8n:2.47.2 | lcr library/n8n |
| nats | NATS | tool | nats:2.15.2 | lcr library/nats |
| openresty | OpenResty | runtime | 1panel/openresty:1.31.8.1-2-1-noble | **本地 registry** `127.0.0.1:5000/loong/openresty:同tag`（自建 17 轮，✅ 已验收） |
| caddy | Caddy | website | caddy:2.11.8 | **本地 registry** `loong/caddy:2.11.8`（自建批次一，✅ 2026-11-06） |
| filebrowser | File Browser | tool | filebrowser/filebrowser:v2.63.23 | **本地 registry** `loong/filebrowser:v2.63.23`（自建批次一，✅ 2026-11-06） |
| ddns-go | ddns-go | 实用工具 | jeessy/ddns-go:v6.17.7 | **本地 registry** `loong/ddns-go:v6.17.7`（自建批次一，✅ 商店安装闭环 2026-11-06） |
| typecho | Typecho | 建站 | joyqi/typecho:1.3.0-php8.2-apache | **本地 registry** `loong/typecho:1.3.0-php8.2-apache`（自建批次二，复刻 typecho/Dockerfile 配方 + lcr php:8.2-apache-sid 底座，✅ 2026-11-06） |
| uptime-kuma | Uptime Kuma | 实用工具 | louislam/uptime-kuma:2.5.9 | **本地 registry** `loong/uptime-kuma:2.5.9`（自建批次二，原生 @louislam/sqlite3 设备编译，✅ 商店安装闭环 2026-11-06；旧版 1.23.17 目录未构建） |
| halo | Halo | 建站 | halohub/halo-pro:2.27.2 | **本地 registry** `loong/halo-pro:2.27.2`（自建批次三：社区版 jar 挂 pro tag，官方配方 + lcr temurin 21 底座；安装需先装 MySQL/PostgreSQL，✅ 镜像冒烟 2026-11-06） |
| freshrss | FreshRSS | 实用工具 | linuxserver/freshrss:1.30.4 | **本地 registry** `loong/freshrss:1.30.4`（自建批次三：官方 FreshRSS 配方复刻 + FRESHRSS_DATA_PATH 重定位到 /config 兼容商店挂载，✅ 商店安装闭环 2026-11-06） |
| neo4j | Neo4j | tool | neo4j:5.26.32 | lcr library/neo4j |
| pgvector | pgvector | runtime | pgvector/pgvector:0.8.7-pg18 | lcr library/pgvector |
| phpmyadmin | phpMyAdmin | website | phpmyadmin:5.2.3 | lcr library/phpmyadmin |
| portainer-ce | Portainer-CE | website | portainer/portainer-ce:2.45.3-alpine | lcr library/portainer-ce |
| postgis | PostGIS | tool | postgis/postgis:18-3.6-alpine | lcr postgis/postgis:16-3.4 |
| postgresql | PostgreSQL | runtime | postgres:18.6-alpine | lcr library/postgres |
| rabbitmq | RabbitMQ | website | rabbitmq:4.4.0-management-alpine | lcr library/rabbitmq |
| redis | Redis | runtime | redis:8.10.3 | lcr library/redis |
| wordpress | WordPress | website | wordpress:7.1.4 | lcr library/wordpress |
| yourls | YOURLS | website | yourls:1.10.6 | lcr library/yourls |

> 映射进 `app_loong64.go` v2 表时，tag 策略：保留商店请求 tag，若 lcr 无该 tag 则回退到各镜像的兜底 tag（入表时逐个经 Quay API tags/list 核实）。

## C 层：官方自带 loong64（1 个）

| 应用键 | 名称 | 商店镜像引用 |
|---|---|---|
| openlist | OpenList | ${OPENLIST_IMAGE}（默认 openlistteam/openlist，官方 manifest 含 loong64） |

## D 层：确认不可移植（59 个，映射层 loong64BlockedRepos 拦截，安装时给明确中文提示）

> 波次 53/54 完成全量 gap 分诊（audit14 no_rule 110 项 → 99 个唯一应用）：34 个新增拦截 + 20 个此前已拦 + 5 个更早批次已拦；另有 40 个"可移植候选"留待后续波次（见下表），1 个漏映射补规则（mysql-cluster → bitnamilegacy/mysql → lcr mysql）。

| 应用键 | 原因 | 落表批次 |
|---|---|---|
| jellyfin | .NET 无 loong64 | 初版 |
| bettafish / code-server / comfyui / harness / llama.cpp / localai / nginx-proxy-manager / ollama / open-webui / openvpn-as / palworld / sglang / teamspeak / tiny-rdm / vexdb / windows(dockurr) / zfile / rustdesk-server-s6 / mssql / keydb / dotnet-aspnet / dosgame / convertx(Bun) | 早期分诊批次（GPU/闭源/重型构建链/无 loong64 运行时） | mega216~w43 |
| langbot / langflow / astrbot / kirara-agent / copaw(qwenpaw) / hermes-agent / clawswarm / ai-gateway / ai-portal / deepseek-harness / maxkb / sqlbot / octop / openclaw | LLM/AI 栈（python 原生依赖无 loong64 wheel；1Panel 官方镜像仅 amd64/arm64） | w54 |
| clickhouse / oceanbase-ce / starrocks / manticoresearch / typesense | C++ 引擎无 loong64 构建，且内存需求远超 8G 设备 | w54 |
| zabbix-proxy / zabbix-server（含信创版） | C server+php 栈，无 loong64 镜像 | w54 |
| home-assistant / jupyter-scipy / archivebox / changedetection.io / browserless | python 原生 wheel 链断裂或核心依赖 chromium（无 loong64） | w54 |
| discourse / huginn / jumpserver / metersphere / gameservermanager / onlyoffice / openlitespeed / magpie | 构建/资源不可行（Ruby 巨栈、10GB all-in-one、wine+steamcmd、C++ 大构建链、桌面 GUI） | w54 |

### 可移植候选（40 个，未落表、面板可见但暂不可装，按性价比排序）

| 批次方向 | 应用 |
|---|---|
| Go 交叉编译批 | zitadel |
| ~~Rust 批~~ ✅ **已全部闭环（波次五十七）** | ~~rustfs、vector、stalwart-mail~~ 三应用均已入库+体检+E2E 全绿（R_LARCH_B26 -fno-plt 攻坚与 console RustEmbed 内嵌详见总览波次五十七） |
| Java 底座批（temurin/JDK 换芯） | cloudbeaver、rocketmq-dashboard、cordys-crm、upage |
| Node 批（logto/umami 套路） | blinko、nocobase、teable、twenty、mcsmanager-daemon/web |
| Python 批（pip 链可解） | pgadmin4、linkding、mkdocs-material、qinglong、filecodebox、domain-admin、music-tag-web、xiaomusic、trendradar、vane、laya-server、arcadia、dbx、calibre-web、qiandao |
| 中等工程 | affine（Node+Rust native）、synapse（pyo3）、netdata、photoprism（libvips 链现成） |
| 待查官方支持 | greatsql、tdengine（国产库可能已有 loong64 官方包）、silo |

## VAR 层：语言运行时（14 个，波次十六起逐项处置）

> 这些属于 1Panel「运行时环境」生态（镜像由 1Panel-dev/runtime 构建体系产出，用户在面板里选版本）。机制真相（波次十六/十七逆向结论）：**五类运行时共用同一骨架**（挂 CODE_DIR:/app + run.sh 读 .env 执行 EXEC_SCRIPT）；`pullComposeImages` **本来就带"本地已有则跳过 pull"守卫**（`ImageExists → continue`，波次十六的"显式 pull 必挂"是函数名误读，波次十七读实现后推翻）→ **无需任何 agent 改动，本地对齐镜像 tag 即可离线解锁全部运行时**。

| 应用键 | 处置 | 说明 |
|---|---|---|
| **php8** | ✅ **已闭环（波次十六）** | agent v25 放行 deprecated 过滤；本地镜像 `1panel-php-fpm:8.4.27`（sid php8.4.27-1 与商店精确同版）+ 别名 `php:8.4.27`/`8.4.6`；扩展走自写 apt 版 install-ext（63 项映射，不支持项优雅跳过）；PHP 网站 fastcgi 闭环验证。**可用版本：8.4.27 / 8.4.6**（其余 8.0~8.3、8.5 无对应底座，选了会在启动时报镜像拉取失败） |
| **go** | ✅ **已闭环（波次十七）** | 本地 `golang:1.26`（lcr golang:1.26.8-alpine + apk bash/git 重打）；验证：go.mod demo `go run main.go` HTTP 服务 ✅。**可用版本：1.26**（1.21~1.25 无底座；alpine 底座无 bash，`bash /run.sh` 会挂——重打时必须补 bash） |
| **node** | ✅ **已闭环（波次十七）** | 三档别名：`1panel/node:26.13.0`（精确）/`22.23.4`（≈22.23.2）/`20.20.2`（≈20.19.3），debian 底座自带 bash/npm；验证：node server.js HTTP ✅。**可用版本：26.13.0 / 22.23.4 / 20.20.2**（12~18/21/24/25 无底座；创建时 source 留空会让 run.sh `npm config set registry ''` 打一条无害报错） |
| **python** | ✅ **已闭环（波次十七）** | 本地 `python:3.14.8`（debian sid apt python3=3.14.10 自建，`/usr/local/bin/python` symlink + venv/pip；补丁级近似 3.14.10）；验证：http.server HTTP ✅。**可用版本：3.14.8**（3.10~3.13/3.15 无底座） |
| **java** | ✅ **已闭环（波次十七）** | 本地 `1panel/java:21`（debian sid apt openjdk-21-jdk-headless 自建）；验证：单文件源码启动 `java Main.java` 内建 HttpServer ✅。**可用版本：21**（1.8/11/17/22/25 无底座） |
| dotnet | ❌ F | mcr.microsoft.com 无 loong64 manifest，Loongson dotnet 移植版不可达；如未来需要可用 loongnix 源自建底座 |
| php | ❌ 不采用 | v2 时代 supervisor 版（compose 自带 build 段 FROM `1panel/php:${PHP_VERSION}-fpm`），官方 install-ext 依赖 pear/phpize/install-php-extensions 重型 dev 底座；php8 路线已通，不再复刻 |
| php5 / php7 | 屏蔽保留 | deprecated 过滤保留（版本过老，无适配价值） |
| forgejo / neko / openlist | 参数型 app，无需面板适配 | 镜像引用为 `${IMAGE}`/`${OPENLIST_IMAGE}` 用户自填，映射层天然跳过 `${}`；官方无 loong64 → 自建镜像后**在安装参数里填本地 tag** 即可（openlist 官方 manifest 含 loong64 但 Hub 直连不可达，仍需本地中转） |
| keydb | ❌ 不构建（波次二十定论） | `eqalpha/keydb:${ARCH}_v6.3.4` 的 `${ARCH}` 枚举无 loong64；生态位已被 **valkey**（Redis 兼容 fork，mega216 已入库 9.0.7）覆盖，不再重复造轮子 |
| vllm | D 层候选 | GPU 推理框架，2K3000 无 GPU，建议转拦截表 |

## B 层：待构建/待评估（216 个）

完整清单（应用键 | 名称 | 类型 | 当前镜像引用）：

| 应用键 | 名称 | 类型 | 商店镜像引用 |
|---|---|---|---|
| act-runner | Act Runner | tool | gitea/act_runner:0.6.1（lcr library/act_runner 无任何标签，暂无龙芯版） |
| adguardhome | AdGuardHome | website | adguard/adguardhome:v0.107.80 |
| adminer | Adminer | website | adminer:6.3.0-standalone |
| affine | AFFiNE | website | ghcr.io/toeverything/affine:0.27.4 |
| ai-gateway | 1Panel AI 网关 | website | 1panel/ai-gateway:v1.5.1 |
| ai-portal | 1Panel AI 门户 | website | 1panel/ai-portal:v1.0.10 |
| alist | AList | website | xhofe/alist:v3.66.0 |
| answer | Answer | website | apache/answer:2.0.3 |
| arcadia | Arcadia | website | supermanito/arcadia:1.2.0 |
| archivebox | ArchiveBox | website | archivebox/archivebox:0.9.77 |
| artalk | Artalk | website | artalk/artalk-go:2.10 |
| astrbot | AstrBot | website | soulter/astrbot:v4.29.4 |
| audiobookshelf | Audiobookshelf | website | advplyr/audiobookshelf:2.37.2 |
| beszel | Beszel | website | henrygd/beszel:0.21.1 |
| bettafish | BettaFish | website | ghcr.io/666ghj/bettafish:v3.0.0 |
| bililive-go | Bililive-go | website | chigusa/bililive-go:v0.8.3 |
| bitwarden | Bitwarden | website | vaultwarden/server:1.37.5-alpine |
| blinko | Blinko | tool | blinkospace/blinko:1.8.9 |
| browserless | Browserless | tool | ghcr.io/browserless/chrome:v2.59.0 |
| bytebase | Bytebase | website | bytebase/bytebase:3.24.1 |
| calibre-web | Calibre-Web | website | linuxserver/calibre-web:0.6.27 |
| casdoor | Casdoor | website | casbin/casdoor:v4.25.0 |
| certd | Certd | website | greper/certd:1.46.0 |
| certimate | Certimate | website | certimate/certimate:v0.4.36 |
| changedetectionio | Changedetection.io | website | dgtlmoon/changedetection.io:0.70.1 |
| chatgpt-next-web | ChatGPT-Next-Web | website | yidadaa/chatgpt-next-web:v2.16.1 |
| clawswarm | ClawSwarm | website | 1panel/clawswarm:v1.0.5 |
| clickhouse | ClickHouse | tool | clickhouse/clickhouse-server:26.10.3-alpine |
| cloudbeaver | CloudBeaver | website | dbeaver/cloudbeaver:26.2.4 |
| cloudflared | cloudflared | tool | cloudflare/cloudflared:2026.10.7 |
| cloudreve | Cloudreve | website | cloudreve/cloudreve:4.19.1 |
| code-server | code-server | website | linuxserver/code-server:4.145.0 |
| comfyui | ComfyUI | website | 1panel/comfyui:v0.33.1 |
| convertx | ConvertX | website | c4illin/convertx:v0.20.0 |
| copaw | QwenPaw | website | agentscope/qwenpaw:v2.2.2 |
| cordys-crm | Cordys CRM | website | 1panel/cordys-crm:v1.9.6 |
| cyberchef | CyberChef | website | ghcr.io/gchq/cyberchef:11.5.0 |
| dashy | Dashy | website | lissy93/dashy:4.9.15 |
| dataease | DataEase | website | registry.cn-qingdao.aliyuncs.com/dataease/dataease:v3.1.0 |
| dbhub | DBHub | tool | bytebase/dbhub:1.5.1 |
| dbx | DBX | tool | t8y2/dbx:0.6.66 |
| deepseek-harness | DeepSeek Harness | website | 1panel/deepseek-harness:0.2.1-rc.5 |
| discourse | Discourse | website | bitnamilegacy/discourse:3.5.0 |
| discuz | Discuz! | website | tencentci/discuz:v3.4 |
| dockge | Dockge | website | louislam/dockge:1.5.0 |
| docmost | Docmost | website | docmost/docmost:0.97.0 |
| domain-admin | Domain Admin | website | mouday/domain-admin:v1.6.79 |
| dosgame | 中文 DOS 游戏 | website | firezmc/dosgame-web-docker:v3.9.6 |
| drawio | Draw.io | website | jgraph/drawio:32.6.10 |
| dvwa | DVWA | website | ghcr.io/digininja/dvwa:latest |
| easyimage2 | EasyImage2.0 | website | ddsderek/easyimage:v2.8.7 |
| easytier | EasyTier | tool | easytier/easytier:v2.7.0 |
| emlog | emlog | website | emlog/emlog:pro-latest-php8.2-nginx |
| excalidraw | excalidraw | website | excalidraw/excalidraw:latest |
| ezbookkeeping | ezBookkeeping | website | mayswind/ezbookkeeping:2.1.1 |
| filecodebox | FileCodeBox | website | lanol/filecodebox:2.8.5 |
| firefly-iii | Firefly III | website | fireflyiii/core:version-6.4.2 |
| focalboard | Focalboard | website | mattermost/focalboard:7.11.4 |
| forgejo-runner | Forgejo Actions Runner | tool | code.forgejo.org/forgejo/runner:13.2.1、docker:29.9.3 |
| frpc | frp 客户端 | website | snowdreamtech/frpc:0.71.1-alpine |
| frps | frp 服务端 | website | snowdreamtech/frps:0.71.1-alpine |
| gatus | Gatus | website | twinproduction/gatus:v5.38.0 |
| ghost | Ghost | website | ghost:6.75.0 |
| gitea | Gitea | website | commitgo/gitea-ee:27.3.11 |
| glance | Glance | website | glanceapp/glance:v0.8.7 |
| gotify | Gotify | website | gotify/server:3.1.1 |
| greatsql | GreatSQL | tool | greatsql/greatsql:8.0.32-27 |
| gsmanager | GSManager | website | xiaozhu674/gameservermanager:3.14.2 |
| harness | Harness | tool | harness/harness:3.3.0 |
| heimdall | Heimdall | website | linuxserver/heimdall:2.8.4 |
| hermes-agent | Hermes Agent | website | 1panel/hermes-agent:2026.9.24 |
| home-assistant | Home Assistant | website | homeassistant/home-assistant:2026.11.0 |
| homepage | Homepage | website | ghcr.io/gethomepage/homepage:v2.7.0 |
| huginn | Huginn | website | ghcr.io/huginn/huginn:latest |
| it-tools | IT-Tools | website | corentinth/it-tools:2024.10.22-7ca5933 |
| jsonhero | JSON Hero | website | henryclw/jsonhero-web:latest |
| jumpserver | JumpServer | website | jumpserver/jms_all:v5.1.1 |
| jupyter-notebook | Jupyter Notebook | tool | jupyter/scipy-notebook:latest |
| kafka | Kafka | tool | bitnamilegacy/kafka:4.0.0 |
| keycloak | Keycloak | website | keycloak/keycloak:26.8.1 |
| kirara-agent | Kirara AI | tool | lss233/kirara-agent-framework:v3.2.0 |
| kkfileview | kkFileView | website | keking/kkfileview:4.1.0 |
| kodbox | Kodbox | website | kodcloud/kodbox:1.70.03 |
| koishi | Koishi | website | koishijs/koishi:v1.16.0 |
| komari | Komari | website | ghcr.io/komari-monitor/komari:1.6.1 |
| komga | Komga | website | gotson/komga:1.30.0 |
| koodo-reader | Koodo Reader | website | ghcr.io/koodo-reader/koodo-reader:master |
| kubepi | KubePi | website | 1panel/kubepi:v2.0.3 |
| langbot | LangBot | aiwebsite | rockchin/langbot:v4.11.4 |
| langflow | Langflow | tool | langflowai/langflow:1.13.1 |
| laya-server | Laya Server | website | 1panel/laya-server:v0.1.2 |
| linkding | linkding | website | sissbruecker/linkding:1.47.0-plus |
| linux-command | Linux Command | website | wcjiang/linux-command:1.22.0 |
| llama-cpp | llama.cpp | tool | ghcr.io/ggml-org/llama.cpp:server |
| lobe-chat | LobeChat | website | lobehub/lobe-chat:1.143.3 |
| localai | LocalAI | website | localai/localai:v3.12.1-aio-cpu |
| logto | Logto | website | svhd/logto:1.46.0 |
| lsky-pro | Lsky-pro | website | halcyonazure/lsky-pro-docker:latest |
| maddy-mail | Maddy Mail Server | website | foxcpp/maddy:0.9.6 |
| mailserver | Mailserver | website | ghcr.io/docker-mailserver/docker-mailserver:16.0.1 |
| manticoresearch | Manticore Search | tool | manticoresearch/manticore:29.9.0 |
| mattermost | Mattermost | website | mattermost/mattermost-team-edition:12.0.2 |
| maxkb | MaxKB | website | 1panel/maxkb:v2.10.8-lts |
| mblog | mBlog | website | kingwrcy/mblog:1.1.0 |
| mcsmanager-daemon | MCSManager | tool | githubyumao/mcsmanager-daemon:latest |
| mcsmanager-web | MCSManager | website | githubyumao/mcsmanager-web:latest |
| meilisearch | MeiliSearch | website | getmeili/meilisearch:v1.56.1 |
| memos | Memos | website | neosmemo/memos:26.11.0 |
| metabase | Metabase | website | metabase/metabase:v0.65.3 |
| metersphere | MeterSphere | website | metersphere/metersphere-ce-allinone:v3.6.10-lts |
| miniflux | Miniflux | website | miniflux/miniflux:2.3.5 |
| mkdocs-material | Material for MkDocs | website | squidfunk/mkdocs-material:9.8.0 |
| mliev-dwz | 木雷短网址 | website | docker.cnb.cool/mliev/dwz/dwz-server:v2.24.1 |
| mongo-express | mongo-express | website | mongo-express:1.0.2-20 |
| mssql | Microsoft SQL Server | runtime | mcr.microsoft.com/mssql/server:2025-latest |
| music-tag-web | Music Tag Web | tool | xhongc/music_tag_web:2.8.1 |
| mysql-cluster | MySQL-Cluster | runtime | bitnamilegacy/mysql:8.4 |
| nacos | Nacos | website | nacos/nacos-server:v3.3.0 |
| navidrome | Navidrome | website | deluan/navidrome:0.64.2 |
| netdata | Netdata | website | netdata/netdata:v2.12.3 |
| new-api | New API | website | calciumion/new-api:v0.13.2 |
| newsnow | NewsNow | website | ghcr.io/ourongxing/newsnow:v0.0.41 |
| nextcloud | Nextcloud | website | linuxserver/nextcloud:35.0.2 |
| nexus | Nexus Repository | website | sonatype/nexus3:3.98.0 |
| nezha | 哪吒监控 | tool | ghcr.io/nezhahq/nezha:v2.6.1 |
| nginx-proxy-manager | Nginx Proxy Manager | website | jc21/nginx-proxy-manager:2.16.0 |
| nocobase | NocoBase | website | nocobase/nocobase:2.2.40 |
| nocodb | NocoDB | website | nocodb/nocodb:0.301.5 |
| node-exporter | Node Exporter | tool | prom/node-exporter:v1.12.1 |
| node-red | Node-RED | website | nodered/node-red:5.0.9 |
| nodebb | NodeBB | website | ghcr.io/nodebb/nodebb:4.16.7 |
| npc | NPC | tool | yisier1/npc:v0.26.35 |
| nps | NPS | tool | yisier1/nps:v0.26.35 |
| ntfy | ntfy | website | binwiederhier/ntfy:v2.37.2 |
| obsidian-livesync | Obsidian LiveSync | website | couchdb:3.5.3 |
| oceanbase | OceanBase | tool | oceanbase/oceanbase-ce:4.4.2-lts |
| octop | Octop | website | ghcr.io/tencentcloud/octop:1.0.2 |
| odoo | Odoo | website | odoo:19.0 |
| ollama | Ollama | website | ollama/ollama:0.40.14 |
| ollama-webui | OpenWebUI | website | ghcr.io/open-webui/open-webui:v0.13.0 |
| onedev | OneDev | tool | 1dev/server:17.1.0 |
| onlyoffice | ONLYOFFICE Docs | website | onlyoffice/documentserver:10.0.0.1 |
| openclaw | OpenClaw | website | 1panel/openclaw:2026.10.10 |
| opengist | Opengist | website | ghcr.io/thomiceli/opengist:1.15.3 |
| openldap | OpenLDAP | website | bitnamilegacy/openldap:2.6.10 |
| openlitespeed | OpenLiteSpeed | website | litespeedtech/openlitespeed:1.8.4-lsphp81 |
| openvpn | OpenVPN | website | openvpn/openvpn-as:latest |
| outline | Outline | website | outlinewiki/outline:1.12.0 |
| palworld | Palworld Server | website | thijsvanloef/palworld-server-docker:v2.8.1 |
| palworld-server-tool | Palworld Server Tool | website | jokerwho/palworld-server-tool:0.12.2 |
| pgadmin4 | PGAdmin4 | website | dpage/pgadmin4:9.19 |
| photoprism | PhotoPrism | website | photoprism/photoprism:251130-ce |
| planka | Planka | website | ghcr.io/plankanban/planka:2.3.0 |
| postgresql-cluster | PostgreSQL-Cluster | runtime | bitnamilegacy/postgresql:17 |
| prometheus | Prometheus | website | prom/prometheus:v3.15.1 |
| qbittorrent | qBittorrent | website | linuxserver/qbittorrent:5.3.0 |
| qiandao | QD | website | a76yyyy/qiandao:20250803 |
| qinglong | 青龙 | website | whyour/qinglong:2.24.0-debian |
| redis-cluster | Redis-Cluster | runtime | bitnamilegacy/redis:8.0 |
| redis-commander | Redis-Commander | website | rediscommander/redis-commander:latest |
| redpanda-console | Redpanda Console | website | redpandadata/console:v3.13.1 |
| rocketmq | RocketMQ | website | apache/rocketmq:5.5.0、apacherocketmq/rocketmq-dashboard:2.1.0 |
| roundcube | Roundcube | website | roundcube/roundcubemail:1.7.5-apache |
| rsshub | RSSHub | website | diygod/rsshub:chromium-bundled-2026-04-19 |
| rustdesk | RustDesk | tool | rustdesk/rustdesk-server-s6:1.1.16 |
| rustfs | RustFS | website | rustfs/rustfs:1.0.4 |
| screego | screego | website | ghcr.io/screego/server:1.12.6 |
| sentinel-dashboard | Sentinel Dashboard | website | bladex/sentinel-dashboard:1.8.10 |
| sftpgo | SFTPGo | website | drakkan/sftpgo:v2.7.6-alpine |
| sglang | SGLang | tool | lmsysorg/sglang:v0.5.23 |
| showdoc | ShowDoc | website | star7th/showdoc:v3.9.6 |
| silo | Silo | website | pgsty/silo:RELEASE.2026-10-15T00-00-00Z |
| siyuan | 思源笔记 | website | b3log/siyuan:v3.8.9 |
| sonarqube | SonarQube | website | sonarqube:26.10.0.133078-community |
| sqlbot | SQLBot | website | dataease/sqlbot:v1.10.3 |
| stalwart-mail | Stalwart Mail Server | website | stalwartlabs/stalwart:v1.0.3-alpine |
| starrocks | StarRocks | tool | starrocks/allin1-ubuntu:4.1.7 |
| stirling-pdf | Stirling-PDF | website | frooodle/s-pdf:3.3.0 |
| sub2api | Sub2API | website | weishaw/sub2api:0.2.19 |
| sun-panel | Sun-Panel | website | hslr/sun-panel:1.8.1 |
| synapse | Synapse | website | matrixdotorg/synapse:v1.164.2 |
| tailchat | Tailchat | website | moonrailgun/tailchat:1.11.18 |
| tdengine | TDengine | website | tdengine/tsdb:3.4.3.9 |
| teable | Teable | website | ghcr.io/teableio/teable:latest |
| teamspeak | TeamSpeak Server | website | teamspeak:3.13.8 |
| tinyrdm | Tiny RDM | website | ghcr.io/tiny-craft/tiny-rdm:1.2.7 |
| tomcat | Apache Tomcat | website | bitnamilegacy/tomcat:10.1.43 |
| trendradar | TrendRadar | tool | wantcat/trendradar:6.11.0 |
| trilium | Trilium | website | triliumnext/trilium:v0.106.1 |
| twenty | Twenty | website | twentycrm/twenty:v2.55.0 |
| twikoo | Twikoo | website | imaegoo/twikoo:2.0.17 |
| typesense | Typesense | tool | typesense/typesense:30.2 |
| umami | Umami | website | ghcr.io/umami-software/umami:3.4.1 |
| upage | UPage | website | halohub/upage:2.0.0 |
| valkey | Valkey | tool | valkey/valkey:9.0.7 |
| vane | Vane | website | itzcrazykns1337/vane:v1.12.2 |
| vector | Vector | tool | timberio/vector:0.61.0-debian |
| verdaccio | Verdaccio | website | verdaccio/verdaccio:7.0.2 |
| vexdb | VexDB | tool | shuzhiyinhang/vexdb:3.0.0.28146 |
| waline | Waline | website | lizheming/waline:1.43.6 |
| wallos | Wallos | website | bellamy/wallos:5.10.4 |
| watchtower | watchtower | tool | containrrr/watchtower:latest |
| web-check | Web-Check | website | lissy93/web-check:2.3.12 |
| wechatmarkdowneditor | WeChat Markdown Editor | website | doocs/md:2.1.0 |
| wikijs | Wiki.js | website | requarks/wiki:3.1.0 |
| windows | Windows | tool | dockurr/windows:6.06 |
| woodpecker | Woodpecker CI | website | woodpeckerci/woodpecker-agent:v3.20.1-alpine、woodpeckerci/woodpecker-server:v3.20.1-alpine |
| xiaomusic | XiaoMusic | tool | hanxi/xiaomusic:v0.6.1 |
| yesplaymusic | YesPlayMusic | website | fogforest/yesplaymusic:0.4.9 |
| zabbix-agent | Zabbix Agent | tool | zabbix/zabbix-agent:alpine-7.4.5 |
| zabbix-proxy | Zabbix Proxy | tool | zabbix/zabbix-proxy-mysql:alpine-7.4.5 |
| zabbix-server | Zabbix Server | website | zabbix/zabbix-java-gateway:alpine-latest、zabbix/zabbix-server-mysql:alpine-7.4.5、zabbix/zabbix-web-nginx-mysql:alpine-latest |
| zabbix-xinchuang-edition | Zabbix 信创版 | tool | zabbix/zabbix-agent:ubuntu-7.0.27、zabbix/zabbix-proxy-mysql:ubuntu-7.0.27、zabbix/zabbix-server-mysql:ubuntu-7.0.27、zabbix/zabbix-web-nginx-mysql:ubuntu-7.0.27 |
| zentao | 禅道 | website | hub.zentao.net/app/zentao:22.7 |
| zfile | ZFile | website | zhaojun1998/zfile:5.1.0 |
| zitadel | ZITADEL | website | ghcr.io/zitadel/zitadel:v4.19.4 |

### B 层推进策略

1. **可源码自建**（Go/PHP/Node/Java/Python 应用，lcr 有对应工具链底座 golang/php/node/eclipse-temurin/python）：滚动流水线，每批 5-10 个
2. **首批建议**（建站与运维生态优先）：~~openresty~~（✅）~~caddy/filebrowser/ddns-go~~（✅ 批次一，2026-11-06：Windows 交叉编译→lcr alpine/busybox 底座→本地 registry→映射表，ddns-go 商店安装闭环验收）→ ~~uptime-kuma/typecho~~（✅ 批次二 2026-11-06：uptime-kuma 商店闭环；code-server 出局——linuxserver 变体+VS Code 构建过重；gitea 已变更为 commitgo/gitea-ee 商业分支，移入专项评估）→ ~~freshrss~~（✅ 批次三 2026-11-06：官方配方复刻 + 数据路径重定位，商店闭环）→ nginx-proxy-manager（jc21 源码构建过重，专项评估）、webtop 类工具、halo 安装需先装 MySQL/PostgreSQL（镜像已就绪）
3. **需专门评估**：闭源/商业版（gitea-ee→CE 替代、commitgo 镜像）、重量级（gitlab、jumpserver、dataease、odoo、onlyoffice——依赖复杂但多为 Java/Python，理论可建）、GPU/AI 类（ollama/vllm/comfyui——依赖 CUDA/ROCm，龙芯无 GPU 栈，标 D 处理）
4. **AI/GPU 类**（ollama、vllm、sglang、localai、comfyui、xinference 等）：2K3000 无 CUDA，纯 CPU 模式理论可跑但无实际价值，统一标 D（明确提示）

## 维护

- 商店更新后重跑 `inventory_all_apps.py` + `compare_inventory.py` 刷新本矩阵
- 每完成一批 B 层构建，把对应行移入 A 层并在手册记录构建配方
