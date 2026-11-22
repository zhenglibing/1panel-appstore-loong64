# 1Panel 应用商店 LoongArch64（龙芯）构建方案

为 [1Panel](https://github.com/1Panel-dev/1Panel) 应用商店的 LoongArch64（龙芯 2K3000 等）移植提供**完整可复现的构建方案**：构建流水线 + 23 份波次构建配方（spec）+ OpenResty 全源码构建配方 + 7 个代表性应用的镜像构建配方。

- 配套上游 PR：[1Panel-dev/appstore](https://github.com/1Panel-dev/appstore) loong64 build 配方（openresty + 7 应用）
- 实测环境：零刻 ME Pro（龙芯 2K3000，8×LA364E），Loongnix 25，Docker 26.1.5
- 实测成果：268 个商店应用四层盘点，**182 个自建仓库 / 322 个 tag**（已全量镜像至公共 ACR 源并逐 tag 校验 digest），体检 **158/158 离线可装、NONLOCAL 清零**（全部应用 manifest 级零 miss），OpenResty 建站闭环（静态站/反代/WAF）

## 背景与思路

Docker Hub 上游镜像无一提供 loong64 manifest，龙芯设备安装商店应用必然拉取失败。方案是**不动 1Panel 本体代码**，在应用包数据层解决：

| 层 | 处理 | 规模 |
|---|---|---|
| A 层 | lcr.loongnix.cn 已有镜像 → 商店 compose 改写指向 | 30 应用 |
| B 层 | 源码构建（Go/PHP/Node/Java）→ 推本地 registry | 223 应用中已完成 79+ |
| C 层 | 官方 loong64 或天然跨架构 | 1 |
| D 层 | 不可移植（.NET/GPU/闭源），映射层拦截并明示 | 1 |
| VAR | compose 多镜像变体处理 | 14 |

镜像分发双层：设备本地 registry（`127.0.0.1:5000`，localhost 免 TLS，构建产物的内网层）+ 阿里云 ACR 公共镜像源（`crpi-a02ej0ppuvq7b0mw.cn-hangzhou.personal.cr.aliyuncs.com/1panel-loong64/<key>:<ver>`，面向所有龙芯设备的公开层）；自建商店源 compose 改写为本地 ref，agent 二级回源在本地缺失时自动回落 ACR。

## 目录结构

```
pipeline.py            构建流水线（go_only / go_fe / artifact / static 四路线）
specs/                 23 份波次构建配方（应用名/版本/构建命令/Dockerfile/烟囱测试）
recipes/
  openresty/           OpenResty 1.31.8.1 loong64 全源码构建（含 loongarch64 LuaJIT 移植、
                       ngx_brotli 动态模块、1pwaf 原生库源码编译，vendor/ 与 1pwaf/ 为构建上下文）
  apps/<key>-<ver>/    7 个代表性应用配方（BUILD.md + Dockerfile）
```

## 公共镜像源（免构建直用，2026-11-21）

全部自建镜像已同步到阿里云 ACR 公共实例并逐 tag 校验（**171 仓库 / 309 tag，digest 全量比对与源 registry 一致**）。任何龙芯设备（含其他人的 1Panel）都可以直接在线拉取，无需自行构建、也无需连任何人的局域网：

```bash
# 拉取示例（命名空间公开后匿名可用）
docker pull crpi-a02ej0ppuvq7b0mw.cn-hangzhou.personal.cr.aliyuncs.com/1panel-loong64/openresty:1.31.8.1-2-2-noble
docker pull crpi-a02ej0ppuvq7b0mw.cn-hangzhou.personal.cr.aliyuncs.com/1panel-loong64/gatus:v5.38.0
```

- 命名空间 `1panel-loong64` 与本地 registry `127.0.0.1:5000/loong/...` 一一对应：`loong/<key>:<tag>` ↔ `1panel-loong64/<key>:<tag>`
- 配套的 1Panel agent（[1Panel fork loong64-support 分支](https://github.com/zhenglibing/1Panel/tree/loong64-support)）已内置**二级回源**：安装/升级渲染 compose 时探测本地 registry，`loong/<key>:<tag>` 不在本地即自动改写为上述 ACR 地址——新版本商店条目先于本地 registry 也能在线安装
- 云端盘点用 `docker buildx imagetools inspect <ref>`（ACR 个人版不开放 `/v2/_catalog` API）；命名空间可见性在 ACR 控制台设置

## 快速开始（龙芯设备）

```bash
# 0. 直接使用公共镜像源（推荐起点，见上节）
docker pull crpi-a02ej0ppuvq7b0mw.cn-hangzhou.personal.cr.aliyuncs.com/1panel-loong64/<key>:<ver>

# 1. 自建时：本地 registry（构建产物的内网分发层）
docker run -d --name loong-registry --restart always -p 127.0.0.1:5000:5000 \
  -v loong-registry-data:/var/lib/registry lcr.loongnix.cn/library/registry:3.1.1

# 2. 纯 Go 应用：x86 PC 交叉编译 or 设备原生构建
GOARCH=loong64 GOOS=linux go build -o maddy ./cmd/maddy   # PC 侧（CGO=0）
# 然后按 recipes/apps/<key>-<ver>/Dockerfile 组装镜像并推 127.0.0.1:5000/loong/<key>:<ver>
# （构建完成后同步到公共 ACR 源，供其他设备匿名拉取）

# 3. 复杂应用（Go+前端 / Java release / PHP 站点）：用 pipeline.py + specs/ 配方
python -I pipeline.py --spec specs/spec_w27.json --key prometheus
```

## OpenResty（建站模块解锁）

官方配方基于 `FROM 1panel/openresty` bootstrap（amd64 blob），loong64 必须全源码自建。要点：

1. 底座 `lcr.loongnix.cn/library/debian:sid`（apt 兼容；loong64 包已入官方 sid archive，apt 源改写见 Dockerfile 注释）
2. **LuaJIT 换 loongarch64 移植版**（loongson/LuaJIT v2.1，vendor/LuaJIT）——上游捆绑 LuaJIT 不支持 loongarch，且 1pwaf 依赖的 `table.new/.clear` 只有 LuaJIT 有
3. brotli/libmaxminddb/libinjection/lsqlite3/lfs 全部并入同次构建（vendor/）
4. 1pwaf lua 引擎为架构无关数据，直接复用官方提取件（1pwaf/）
5. 与官方 Dockerfile 的 diff 全部注释说明，见 `recipes/openresty/Dockerfile.loong64`

构建耗时：龙芯 2K3000 8 核实测约 30-60 分钟（OpenSSL 3.5.9 + OpenResty 全模块）。

## 体检与维护

- `audit14`（manifest 级探测）+ `audit20`（离线可装性）双体检：153/153 零 miss（2026-11-22，wave69 增补 odoo 19.0 ERP / zabbix-server 7.4.5 监控栈 / dbx 0.6.68；wave70 增补 netdata v2.12.3 全源码监控 agent 与 docker-mailserver 16.0.1 全栈邮件服务器；wave71 增补 GreatSQL 8.0.32-27 国产 MySQL 分支全源码设备编译；wave72 增补 zabbix-xinchuang-edition 信创版 7.0.27 四镜像全栈（server/proxy/agent C 源码编 + web 纯 PHP ui，官方 zabbix-docker entrypoints 照抄支持 init_db_only 模式）；wave73 增补 TDengine 3.4.3.9 时序数据库全源码（taosd + taos CLI + taosadapter CGO，官方 entrypoint 照抄；keeper/explorer 为内部组件按设计降级）与 Arcadia 1.2.0 脚本运维平台（Node 全栈重写，Prisma 7 driver-adapter 纯 TS 客户端，PC 预生成 + seed sqlite 首启注入）；wave74 增补 LobeChat 1.143.3（Next 15 standalone，Windows 构建三坑：junction shim 破 symlink 特权墙 + changelog 路由动态化 + 懒加载长尾补链）与 UPage 2.0.0（Prisma 6.16 换 engineType=client 纯 TS 客户端补丁 + better-sqlite3 设备源编 + PC migrate 种子库），并对存量 10 应用终审：5 个拦截（palworld/photoprism/music-tag-web/laya-server/vane，含上游闭源化与 torch/playwright/onnxruntime 无 loong64）；wave75 增补 AFFiNE 0.27.4（amd64 层抽取 + Prisma 6.16 纯 TS 客户端 + 自家 Rust napi（y-octo/sqlx 全家桶）设备 rustc 1.97.1 源编 + @node-rs argon2/crc32 loong64 cdylib + SQL 迁移器复刻 prisma migrate deploy 语义 + pgvector 伴生）与 Teable latest（**Prisma 史上最深移植**：bundle 内联的 queryCompiler 客户端与 6.2.1 实例式 adapter 协议错位，以 /app/loong 运行时岛屿 + connect 点桥接（用 6.16 PrismaPg 在其 pool 上重建原生工厂）闭环；sharp/css-inline/bcrypt 三 native 源编；@napi-rs/canvas 缺失以 DOM stub 预载兜底 pdf-parse）—— **NONLOCAL 清零，158/158 全量离线可装**）
- 公共 ACR 源校验：逐 tag 比对本地 registry 与 ACR 的 manifest digest，302 tag 全量 bit-exact
- 上游漂移检测：CDN 索引 vs 本地快照严格 diff（键用 `apps[].id`），全绿则零动作
- 备份惯例：registry 卷直接 tar 落盘，不要依赖"可重建"

## 许可与致谢

- 本仓库遵循 GPL-3.0（与上游 1Panel-dev/appstore 一致）
- OpenResty 配方基于 [1Panel-dev/appstore](https://github.com/1Panel-dev/appstore) 官方 Dockerfile 移植，diff 均有标注
- 镜像底座来自 [龙芯社区 registry](https://lcr.loongnix.cn)，LuaJIT loongarch64 移植来自龙芯社区
- 感谢 1Panel 团队对本项目作为"独立社区方案探索"的建议
