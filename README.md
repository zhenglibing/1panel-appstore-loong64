# 1Panel 应用商店 LoongArch64（龙芯）构建方案

为 [1Panel](https://github.com/1Panel-dev/1Panel) 应用商店的 LoongArch64（龙芯 2K3000 等）移植提供**完整可复现的构建方案**：构建流水线 + 23 份波次构建配方（spec）+ OpenResty 全源码构建配方 + 7 个代表性应用的镜像构建配方。

- 配套上游 PR：[1Panel-dev/appstore](https://github.com/1Panel-dev/appstore) loong64 build 配方（openresty + 7 应用）
- 实测环境：零刻 ME Pro（龙芯 2K3000，8×LA364E），Loongnix 25，Docker 26.1.5
- 实测成果：268 个商店应用四层盘点，**86 个自建镜像 / 158 个 tag**，体检 **109/109 离线可装**，OpenResty 建站闭环（静态站/反代/WAF）

## 背景与思路

Docker Hub 上游镜像无一提供 loong64 manifest，龙芯设备安装商店应用必然拉取失败。方案是**不动 1Panel 本体代码**，在应用包数据层解决：

| 层 | 处理 | 规模 |
|---|---|---|
| A 层 | lcr.loongnix.cn 已有镜像 → 商店 compose 改写指向 | 30 应用 |
| B 层 | 源码构建（Go/PHP/Node/Java）→ 推本地 registry | 223 应用中已完成 79+ |
| C 层 | 官方 loong64 或天然跨架构 | 1 |
| D 层 | 不可移植（.NET/GPU/闭源），映射层拦截并明示 | 1 |
| VAR | compose 多镜像变体处理 | 14 |

镜像分发用设备本地 registry（`127.0.0.1:5000`，localhost 免 TLS），商店 compose 全部改写为 `127.0.0.1:5000/loong/<key>:<ver>`。

## 目录结构

```
pipeline.py            构建流水线（go_only / go_fe / artifact / static 四路线）
specs/                 23 份波次构建配方（应用名/版本/构建命令/Dockerfile/烟囱测试）
recipes/
  openresty/           OpenResty 1.31.8.1 loong64 全源码构建（含 loongarch64 LuaJIT 移植、
                       ngx_brotli 动态模块、1pwaf 原生库源码编译，vendor/ 与 1pwaf/ 为构建上下文）
  apps/<key>-<ver>/    7 个代表性应用配方（BUILD.md + Dockerfile）
```

## 快速开始（龙芯设备）

```bash
# 1. 本地 registry（镜像分发）
docker run -d --name loong-registry --restart always -p 127.0.0.1:5000:5000 \
  -v loong-registry-data:/var/lib/registry lcr.loongnix.cn/library/registry:3.1.1

# 2. 纯 Go 应用：x86 PC 交叉编译 or 设备原生构建
GOARCH=loong64 GOOS=linux go build -o maddy ./cmd/maddy   # PC 侧（CGO=0）
# 然后按 recipes/apps/<key>-<ver>/Dockerfile 组装镜像并推 127.0.0.1:5000/loong/<key>:<ver>

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

- `audit14`（manifest 级探测）+ `audit20`（离线可装性）双体检：79×200 + 28 命中 + 0 miss，109/109 offline-ok
- 上游漂移检测：CDN 索引 vs 本地快照严格 diff（键用 `apps[].id`），全绿则零动作
- 备份惯例：registry 卷直接 tar 落盘（13G 约 17 分钟），不要依赖"可重建"

## 许可与致谢

- 本仓库遵循 GPL-3.0（与上游 1Panel-dev/appstore 一致）
- OpenResty 配方基于 [1Panel-dev/appstore](https://github.com/1Panel-dev/appstore) 官方 Dockerfile 移植，diff 均有标注
- 镜像底座来自 [龙芯社区 registry](https://lcr.loongnix.cn)，LuaJIT loongarch64 移植来自龙芯社区
- 感谢 1Panel 团队对本项目作为"独立社区方案探索"的建议
