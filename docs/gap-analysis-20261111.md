# 1Panel 商店应用覆盖缺口分析（2026-11-11）

上游商店 269 应用，遍历镜像树 compose 逐应用核对：

| 状态 | 数量 | 说明 |
|---|---|---|
| B层完成（registry-backed） | 108 | compose 已改写 127.0.0.1:5000/loong/*，本地 registry 全量可装 |
| A层（lcr 直映） | 28 | compose 全部引用 lcr.loongnix.cn，装时按需 pull |
| D层（不可移植） | 20 | 映射层拦截表命中 |
| 缺口（GAP/WAIT/NOIMG/VAR） | 113 | 见下方清单 |

## 缺口清单

| 应用 | 分类 | 说明 |
|---|---|---|
| act-runner | NOIMG | compose 无 image（需人工看 build 段） |
| affine | GAP:MED | affine |
| ai-gateway | GAP:UNK | ai-gateway |
| ai-portal | GAP:UNK | ai-portal |
| arcadia | GAP:UNK | arcadia |
| archivebox | GAP:MED | archivebox |
| astrbot | GAP:MED | astrbot |
| bililive-go | WAIT | 等前端栈 loong64 |
| blinko | GAP:MED | blinko |
| browserless | GAP:HARD | chrome |
| calibre-web | GAP:MED | calibre-web |
| certd | GAP:MED | certd |
| certimate | WAIT | 等 pocketbase/modernc loong64 |
| changedetectionio | GAP:HARD | changedetection.io |
| clawswarm | GAP:UNK | clawswarm |
| clickhouse | WAIT | 等 lcr 补 tag |
| cloudbeaver | GAP:EASY | cloudbeaver |
| convertx | GAP:MED | convertx |
| copaw | GAP:UNK | qwenpaw |
| cordys-crm | GAP:UNK | cordys-crm |
| dbx | GAP:UNK | dbx |
| deepseek-harness | GAP:HARD | deepseek-harness |
| discourse | GAP:HARD | discourse |
| domain-admin | GAP:MED | domain-admin |
| dosgame | GAP:EASY | dosgame-web-docker |
| dotnet | VAR | image 含 ${VAR}，需人工 |
| drawio | GAP:MED | drawio |
| filecodebox | GAP:MED | filecodebox |
| forgejo | VAR | image 含 ${VAR}，需人工 |
| ghost | GAP:MED | ghost |
| greatsql | GAP:HARD | greatsql |
| gsmanager | GAP:UNK | gameservermanager |
| hermes-agent | GAP:UNK | hermes-agent |
| home-assistant | GAP:HARD | home-assistant |
| huginn | GAP:HARD | huginn |
| jsonhero | GAP:UNK | jsonhero-web |
| jumpserver | GAP:UNK | jms_all |
| jupyter-notebook | GAP:UNK | scipy-notebook |
| keydb | VAR | image 含 ${VAR}，需人工 |
| kirara-agent | GAP:UNK | kirara-agent-framework |
| kkfileview | GAP:UNK | kkfileview |
| koishi | GAP:UNK | koishi |
| koodo-reader | GAP:UNK | koodo-reader |
| kubepi | GAP:UNK | kubepi |
| langbot | GAP:UNK | langbot |
| langflow | GAP:UNK | langflow |
| laya-server | GAP:UNK | laya-server |
| linkding | GAP:UNK | linkding |
| lobe-chat | GAP:UNK | lobe-chat |
| logto | GAP:UNK | logto |
| lsky-pro | GAP:UNK | lsky-pro-docker |
| magpie | GAP:UNK | magpie |
| mailserver | GAP:UNK | docker-mailserver |
| manticoresearch | GAP:UNK | manticore |
| mattermost | GAP:UNK | mattermost-team-edition |
| maxkb | GAP:UNK | maxkb |
| mblog | GAP:UNK | mblog |
| mcsmanager-daemon | GAP:UNK | mcsmanager-daemon |
| mcsmanager-web | GAP:UNK | mcsmanager-web |
| meilisearch | GAP:UNK | meilisearch |
| metersphere | GAP:UNK | metersphere-ce-allinone |
| mkdocs-material | GAP:UNK | mkdocs-material |
| mliev-dwz | GAP:UNK | dwz-server |
| music-tag-web | GAP:UNK | music_tag_web |
| mysql-cluster | GAP:UNK | mysql |
| n8n | GAP:UNK | n8n |
| neko | VAR | image 含 ${VAR}，需人工 |
| netdata | GAP:UNK | netdata |
| newsnow | GAP:UNK | newsnow |
| nexus | GAP:UNK | nexus3 |
| nocobase | GAP:UNK | nocobase |
| nocodb | GAP:UNK | nocodb |
| obsidian-livesync | NOIMG | compose 无 image（需人工看 build 段） |
| oceanbase | GAP:UNK | oceanbase-ce |
| octop | GAP:UNK | octop |
| odoo | GAP:MED | odoo |
| onlyoffice | GAP:HARD | documentserver |
| openclaw | GAP:UNK | openclaw |
| openlitespeed | GAP:HARD | openlitespeed |
| pgadmin4 | GAP:MED | pgadmin4 |
| photoprism | GAP:HARD | photoprism |
| php | VAR | image 含 ${VAR}，需人工 |
| php5 | VAR | image 含 ${VAR}，需人工 |
| php7 | VAR | image 含 ${VAR}，需人工 |
| php8 | VAR | image 含 ${VAR}，需人工 |
| postgresql-cluster | GAP:EASY | postgresql |
| qiandao | GAP:MED | qd qiandao |
| qinglong | GAP:MED | qinglong |
| redis-cluster | GAP:EASY | redis |
| redpanda-console | GAP:EASY | console |
| rsshub | GAP:MED | rsshub |
| rustfs | GAP:HARD | rustfs |
| silo | GAP:UNK | silo |
| siyuan | WAIT | 等 onnxruntime loong64 |
| sonarqube | GAP:EASY | sonarqube |
| sqlbot | GAP:EASY | sqlbot |
| stalwart-mail | GAP:HARD | stalwart |
| starrocks | GAP:HARD | allin1-ubuntu |
| synapse | GAP:HARD | synapse |
| tdengine | GAP:HARD | tsdb |
| teable | GAP:MED | teable |
| trendradar | GAP:MED | trendradar |
| twenty | GAP:MED | twenty |
| typesense | GAP:HARD | typesense |
| umami | VAR | image 含 ${VAR}，需人工 |
| upage | GAP:UNK | upage |
| vane | GAP:UNK | vane |
| vector | GAP:UNK | vector |
| vllm | VAR | image 含 ${VAR}，需人工 |
| xiaomusic | GAP:MED | xiaomusic |
| zabbix-proxy | GAP:HARD | zabbix-proxy-mysql |
| zabbix-server | GAP:HARD | zabbix-java-gateway zabbix-server-mysql zabbix-web-nginx-mysql |
| zitadel | GAP:EASY | zitadel |

## 可移植性分级（缺口 139 项）

| 分级 | 数量 | 判据 |
|---|---|---|
| EASY（流水线现成路线） | 0 | Go交叉编译 / PHP底座 / Java(temurin) / 静态站 / 官方loong64(C层) / lcr别名 |
| MED（Node/Python单体） | 0 | 需 node/php 底座 + 依赖验证，工作量中 |
| HARD（不建议/高成本） | 0 | Ruby/C++重栈/浏览器内嵌/推理GPU/闭源x86 |
| UNK（待评估） | 0 | 小众应用，按上游仓库定栈 |
| WAIT/NOIMG/VAR | 16 | 外部条件/无image/变量引用 |

**EASY 全清单（建议下批波次候选）**：

```
  cloudbeaver  cloudbeaver
  dosgame  dosgame-web-docker
  postgresql-cluster  postgresql
  redis-cluster  redis
  redpanda-console  console
  sonarqube  sonarqube
  sqlbot  sqlbot
  zitadel  zitadel
  openlist  （零成本翻绿：官方loong64/lcr别名/dev底座）
  go  （零成本翻绿：官方loong64/lcr别名/dev底座）
  python  （零成本翻绿：官方loong64/lcr别名/dev底座）
  java  （零成本翻绿：官方loong64/lcr别名/dev底座）
  postgresql-cluster  （零成本翻绿：官方loong64/lcr别名/dev底座）
  redis-cluster  （零成本翻绿：官方loong64/lcr别名/dev底座）
```

## 分类口径

- **GAP**：compose 引用 docker.io/ghcr 镜像且无映射——按语言栈评估可构建性（分级见上表）
- **WAIT**：F 清单扩展项，等外部条件（lcr 补 tag / 上游依赖 loong64 化 / 可自建底座）
- **NOIMG**：compose 无 image 引用（build 段应用），需人工评估
- **VAR**：image 含 ${VAR} 变量引用，需人工看模板

## 数据来源

- 镜像树：`1panel_port/phase2/mega216/store_loong_mirror/dev/1panel/`（2026-11-10 上游快照已采纳）
- blocked 表：`patches/1panel-v2.4.2-loong64-support.patch` loong64BlockedRepos（21 条）
- 可移植性分级：`gap_analysis.py` BUILD_CLASS（按上游技术栈知识，2026-11-11）
- 生成：`gap_analysis.py`（可重跑刷新）
