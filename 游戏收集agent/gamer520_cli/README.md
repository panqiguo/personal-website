# gamer520-cli

管理 Gamer520 游戏收藏 CSV 数据库的命令行工具。所有 CSV 读写操作通过本工具完成，不直接编辑 CSV 文件。

## 调用方式

```bash
# 从仓库根目录（推荐）
uv run --project 游戏收集agent/gamer520_cli gamer520 <command>

# 在 CLI 子目录内
cd 游戏收集agent/gamer520_cli && uv run gamer520 <command>
```

**关键路径**

| 名称 | 路径 |
|------|------|
| 数据库 | `游戏收集agent/gamer520-games.csv` |
| 口味文件 | `游戏收集agent/taste.txt` |
| Doctor 复核账本 | `游戏收集agent/gamer520-doctor-reviews.json` |

## 命令一览

| 命令 | 用途 | 关键参数 |
|------|------|---------|
| `latest` | 返回最新帖子发布日期和最大 link_id | `--platform PC\|Switch`、`--json` |
| `search` | 全字段子串匹配；`--field` 限定单列 | `--field 字段名`、`--json`、`--limit`、`--full` |
| `reconcile` | 批量对账列表页与数据库 | `--stdin`、`--platform`、`--latest-date` |
| `scan-updates` | 按平台自动分页抓取并对账 | `--platform`、`--max-pages`、`--debug` |
| `validate` | 校验 CSV 完整性和数据健康 | `--json` |
| `doctor` | 检查完全重复并报告高相似标题候选 | `--json`、`--similarity-threshold` |
| `doctor-review` | 持久化相似标题的复核结论 | `--title`、`--decision`、`--reason`、`--dry-run`、`--yes` |
| `sort` | 按帖子发布日期降序、同日期按 link_id 降序排列 | `--dry-run` |
| `add` | 从 stdin 追加新条目 | `--stdin`、`--dry-run`、`--json` |
| `remove` | 按标题精确删除 | `--title`、`--dry-run`、`--yes` |
| `update` | 修改已有条目的字段 | `--title`、`--set KEY=VALUE`、`--dry-run`、`--yes` |
| `export` | 按条件导出子集 | `--days`、`--date`、`--latest`、`--query`、`--platform`、`--format`、`--full` |
| `scrape-list` | 抓取列表页，同时返回展示标题和原始标题 | `<url>` |
| `scrape-detail` | 抓取并清洗详情页内容 | `<url>` |

## 命令详情

### `latest`

返回 CSV 中最新帖子发布日期（即 gamer520 论坛帖子日期，非游戏官方发行日期）和相关统计。

```bash
uv run gamer520 latest
uv run gamer520 latest --platform PC
uv run gamer520 latest --platform Switch --json
```

输出：

```
latest_date: 2026-06-14
rows_on_latest_date: 3
latest_link_id: 115709
total_rows: 306
```

用途：每日更新前确定扫描边界，PC 和 Switch 各自独立查询。

### `search`

全字段子串匹配（不区分大小写）。

```bash
uv run gamer520 search "灰烬王国"
uv run gamer520 search "115709"              # 链接 ID 子串
uv run gamer520 search "5" --field 推荐度
uv run gamer520 search "叙事" --json --limit 10
uv run gamer520 search "宝石少女" --full
```

默认匹配所有 10 个字段。`--field 字段名` 限定到单列（任意中文字段名均可）。

### `reconcile`

将 `scrape-list` 的 JSON 数组与数据库批量对账。边界日期默认从数据库对应平台的最新记录推导。

```bash
uv run gamer520 scrape-list https://www.gamer520.com/pcplay \
  | uv run gamer520 reconcile --stdin --platform PC
```

匹配顺序是固定的：

1. 规范标题完全一致
2. 规范 URL 完全一致
3. 标题相似度候选

前两种可确定归入 `existing` 或 `platform_merges`。相似标题只进入 `ambiguous`，不会自动判定为同一游戏。若标题和 URL 分别指向不同的数据库记录，也会以 `title_url_conflict` 进入 `ambiguous`。无匹配的条目进入 `new`，早于边界的条目进入 `before_boundary`。

### `scan-updates`

自动执行“抓取列表页 → reconcile → 翻页”，直到某页所有条目都早于对应平台的数据库边界。

命令负责数据库边界推导、分页抓取和确定性候选分类，不做语义裁决。已存在项直接跳过；`new`、`ambiguous`、`platform_merges` 交给 Agent 调查、判断并调用通用写入命令处理。

```bash
uv run gamer520 scan-updates --platform all
uv run gamer520 scan-updates --platform PC
uv run gamer520 scan-updates --platform Switch --max-pages 15
```

`--platform all` 分别推导 PC/Switch 边界并一次完成两次扫描，同时用规范标题优先、URL 其次生成 `cross_platform_candidates`。它们只是代码可确定的跨平台候选，最终是否合并仍由 Agent 判断。汇总中的 `scanned_items` 包含已有记录；`actionable_candidates` 是平台间去重前的待处理条目；`unique_actionable_candidates`（同时也是组合结果的 `candidates`）才是跨平台去重后的真实候选数。

输出 `complete: true` 才代表扫描完整。默认只输出状态、计数和需要处理的 `new`、`ambiguous`、`platform_merges`；排查问题时加 `--debug` 查看逐页、已存在和边界前数据。达到 `--max-pages` 仍未越过边界时命令返回非零。

### `validate`

校验 CSV 数据健康。

```bash
uv run gamer520 validate
uv run gamer520 validate --json
```

检查项：表头完整性、日期格式、平台合法性、推荐度范围、URL 格式、链接重复、标题重复、空标题。

### `doctor`

对数据库做通用体检：检查完全重复的规范标题和 URL，并报告高相似标题候选。

```bash
uv run gamer520 doctor
uv run gamer520 doctor --json
uv run gamer520 doctor --similarity-threshold 0.9
```

- 完全重复标题或 URL：`valid: false`，退出码 `1`。
- 高相似标题：`review_required: true`，但退出码 `0`。
- `doctor` 只检查和报告，不修改数据；修正使用通用的 `update`、`remove`、`add`。

### `doctor-review`

记录两个标题是同一游戏还是不同游戏。标题可以来自尚未入库的扫描候选，不要求已存在于 CSV。结论保存在 `游戏收集agent/gamer520-doctor-reviews.json`。

```bash
uv run gamer520 doctor-review \
  --title "深空梦里人 Citizen Sleeper" \
  --title "深空梦里人2 Citizen Sleeper 2" \
  --decision distinct \
  --reason "系列一代与二代" \
  --dry-run
```

- `distinct`：后续 `doctor` 不再将该组列为未决候选。
- `same`：保留为待处理项，直到用 `update/remove` 修复数据。
- 重复执行会更新原结论，可用于纠正之前的判断。

### `sort`

按帖子发布日期降序、同日期按链接 ID 降序排列。

```bash
uv run gamer520 sort
uv run gamer520 sort --dry-run
```

### `add`

追加新条目。写入前自动组装字段并校验格式、重复链接和重复标题。推荐使用 `source + assessment`：来源字段直接复制扫描和详情结果，Agent 只生成语义评估。

```bash
# heredoc stdin（推荐，避免中文 shell 转义问题）
uv run gamer520 add --stdin --dry-run << 'ENDOFDATA'
[{"source":{"date":"2026-06-14","platform":"PC","title":"游戏名","url":"https://www.gamer520.com/NNNNN.html"},"assessment":{"tags":["叙事","探索"],"description":"...","score":3,"reason":"..."}}]
ENDOFDATA

uv run gamer520 add --stdin << 'ENDOFDATA'
[{...}]
ENDOFDATA

```

### `remove`

按标题删除条目（规范化后精确匹配，忽略空格/标点/大小写）。

```bash
uv run gamer520 remove --title "精确标题" --dry-run
uv run gamer520 remove --title "精确标题" --yes
```

### `update`

修改已有条目的一个或多个字段。

```bash
uv run gamer520 update --title "舒适森林 Cozy Grove" --set "用户备注=玩过" --dry-run
uv run gamer520 update --title "舒适森林 Cozy Grove" --set "用户备注=玩过" --yes
uv run gamer520 update --title "游戏名" --set "推荐度=4" --yes
```

### `export`

按条件导出子集，供 AI 上下文或人工审阅使用。

```bash
uv run gamer520 export --days 7           # 最近 7 天
uv run gamer520 export --date 2026-06-14  # 指定日期
uv run gamer520 export --latest           # 最新一批
uv run gamer520 export --query "王国"
uv run gamer520 export --platform Switch
uv run gamer520 export --days 30 --format md --full
```

格式：`jsonl`（默认）、`csv`、`md`。默认不含 `判断理由`，加 `--full` 输出全字段。

### `scrape-list`

抓取 gamer520 列表页，返回紧凑 JSON。

```bash
uv run gamer520 scrape-list https://www.gamer520.com/pcplay
uv run gamer520 scrape-list https://www.gamer520.com/gameswitch
```

返回：`[{"title": "游戏展示名", "raw_title": "游戏展示名|官方中文|Build...|", "url": "...", "date": "2026-06-14", "date_text": "3小时前"}]`

`title` 已在 scraper 中去掉第一个 `|` 之后的语言、版本和包信息；`raw_title` 保留站点原文便于追溯。

`date` 从页面 `<time datetime="...">` 属性解析，是 gamer520 帖子发布日期，非游戏官方发行日期。

### `scrape-detail`

抓取 gamer520 详情页，返回游戏信息。

```bash
uv run gamer520 scrape-detail https://www.gamer520.com/NNNNN.html
```

返回：`{"title": "...", "raw_title": "...|Build...|", "game_release_date": "2026-04-03", "genres": "...", "description": "...", "description_quality": "sufficient"}`

注意：`game_release_date` 是游戏官方发行日期，与 `帖子发布日期` 是两个不同概念。

`description` 会过滤获取地址、下载安装说明和站点广告。`description_quality` 可为 `sufficient`、`limited` 或 `missing`；后两种情况应谨慎评估或补充信息。

## 操作规范

- 写入前必须先 `--dry-run` 确认
- `add` 推荐用 heredoc 传 `--stdin`，避免中文 shell 转义问题
- 写入后运行 `sort` 和 `validate`
- 需要局部数据时用 `search` 或 `export`，不直接读取整份 CSV

## CSV Schema

默认路径：`游戏收集agent/gamer520-games.csv`，编码 UTF-8 with BOM，字段顺序固定。

| 字段 | 类型 | 说明 |
|------|------|------|
| 帖子发布日期 | `YYYY-MM-DD` | gamer520 论坛帖子发布日期（非游戏官方发行日期），从 `scrape-list` 的 `date` 字段取得 |
| 平台 | `PC` / `Switch` / `PC/Switch` | |
| 标题 | string | 去掉版本/build 修饰，必要时补充英文名 |
| 标签 | string | 中文分号 `；` 分隔 |
| 一句话描述 | string | 基于详情页内容 |
| 推荐度 | `1`–`5` | 唯一推荐事实源；展示时映射为 `非常不推荐 / 不推荐 / 可试 / 推荐 / 优先推荐` |
| 判断理由 | string | 结合口味解释评分 |
| 链接 | URL | gamer520 条目页 |
| 用户备注 | string | 新增默认留空 |

## 退出码

| 退出码 | 含义 |
|--------|------|
| 0 | 成功 |
| 1 | 数据校验失败或写入被拒绝 |
| 2 | 命令参数错误 |
| 3 | 文件路径或编码错误 |

## 开发与测试

```bash
cd 游戏收集agent/gamer520_cli
uv run pytest
```

测试使用独立 fixture（`tests/fixtures/games.csv`），不影响真实数据。

**测试覆盖**：`test_normalize.py`（URL/标题规范化）、`test_csv_store.py`（BOM 读写、字段顺序）、`test_operations.py`（每个命令的集成测试）。

**源码结构**：

| 文件 | 职责 |
|------|------|
| `cli.py` | Typer 命令入口 |
| `csv_store.py` | UTF-8 with BOM 读写 |
| `models.py` | GameRow 模型，CSV 字段映射 |
| `normalize.py` | URL/标题规范化，link_id 提取 |
| `reconcile.py` | 标题优先的批量对账与候选匹配 |
| `scan_updates.py` | 自动分页抓取、边界停止与对账汇总 |
| `doctor_reviews.py` | Doctor 复核结论的读写与原子替换 |
| `scraper.py` | 抓取器注册表（新站点在此注册） |
| `scraper_gamer520.py` | gamer520.com 专用 HTML 解析（页面结构变化时改此文件） |
| `config.py` | 默认 CSV 路径 |
