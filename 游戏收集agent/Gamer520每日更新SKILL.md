---
name: gamer520-daily-update
description: 抓取 Gamer520 PC/Switch 最新游戏列表，与口味基准对比，将新游戏写入数据库并向用户推荐
allowed-tools: Bash, Read, Agent, WebSearch, WebFetch
triggers:
  - "更新一下"
  - "daily update"
  - "今天有更新吗"
  - "今日更新"
---

# Gamer520 每日更新 Skill

触发后直接执行，不询问是否开始。CLI 参考见 `游戏收集agent/gamer520_cli/README.md`。

## 职责与约束

- CLI 负责确定性操作；本 Skill 负责编排；Agent 负责“是否同一游戏”和推荐度等语义判断。
- 通过 CLI 获取数据库状态，不直接读取整份 `gamer520-games.csv`。口味只读 `游戏收集agent/taste.txt`。
- 命令输出直接在 Agent 上下文中处理，不创建中转目录或临时 CSV/JSON，不将输出落盘后再读取或过滤。
- scraper 返回的 `title` 已规范化，不再自行截断标题，也不删除 `+`、数字或版本词。
- 非游戏内容不得进入数据库。列表抓取器应直接排除公告、置顶通知、工具/资源页等站点内容；若详情阶段仍发现候选不是独立游戏，必须标记为跳过，不评分、不生成 `add` 输入。
- `complete: false`、数据库校验失败或任一 dry-run 失败时，禁止写入。

## 流程

### 1. 预检与扫描

读取一次 `taste.txt`，然后运行：

```bash
uv run --project 游戏收集agent/gamer520_cli gamer520 validate
uv run --project 游戏收集agent/gamer520_cli gamer520 doctor --json
uv run --project 游戏收集agent/gamer520_cli gamer520 scan-updates --platform all
```

`scan-updates` 自动推导两个平台的边界、分页抓取并分类。结果必须 `complete: true`；否则提高 `--max-pages` 重跑。仅排障时使用 `--debug`。

候选处理规则：

| 输出 | 处理 |
|---|---|
| `platforms.*.summary.existing/before_boundary` | CLI 已跳过，默认不返回具体条目 |
| `platforms.*.platform_merges` | Agent 确认后将已有记录更新为 `PC/Switch` |
| `platforms.*.new` | 抓详情、评估并准备新增 |
| `platforms.*.ambiguous` | Agent 判断同一或不同游戏，再决定跳过、更新或新增 |
| `cross_platform_candidates` | CLI 用标题/URL 确定性归组；Agent确认后生成一条 `PC/Switch` 记录 |
| Doctor `unresolved_candidates` | Agent 复核并记录结论 |

同一新游戏只生成一条 `PC/Switch` 记录。`summary.scanned_items` 是边界内扫描总量，包含已有条目；不得称为候选数。真实待处理数使用 `summary.unique_actionable_candidates`（单平台时使用 `summary.actionable_candidates`）。只有真实待处理数超过 50 时，才先告知用户再继续。

### 2. 语义裁决

对 `ambiguous` 和 Doctor 未决组使用同一判断阶梯：

1. 比较规范标题、英文名、系列编号、平台、描述和链接。
2. 仍不确定时，对相关链接运行 `scrape-detail`。
3. 仍不确定时联网查 Steam、官网或发行商等一手来源。
4. 确认不同：`doctor-review --decision distinct`；确认相同：`doctor-review --decision same`，并准备通用 `update/remove` 操作。
5. 仍无法判断才交给用户；不得写复核结论或修改相关数据。

明确的续作或不同系列编号通常是 `distinct`。合并数据时保留有效标题、平台、评分理由和用户备注；平台组合统一为 `PC/Switch`。所有 `doctor-review` 也要先 `--dry-run`。

### 3. 详情与评估

对每款确定的新游戏并行启动子代理。子代理只运行：

```bash
uv run --project 游戏收集agent/gamer520_cli gamer520 scrape-detail <URL>
```

主代理向子代理提供候选 URL 和完整 `taste.txt`。子代理只返回详情标题和语义评估：

```json
{"title":"<scrape-detail title>","assessment":{"tags":["标签1","标签2"],"description":"基于详情的介绍","score":3,"reason":"结合口味的理由"}}
```

详情返回后先做内容类型门禁：只有能够确认是独立游戏作品的候选才进入评分。公告、置顶通知、下载说明、修改器/补丁/固件/插件、资源合集、站务文章等统一跳过；不得为了满足 1–5 分字段而给非游戏内容打 1 分。最终核对时，所有扫描候选都必须明确归入 `已有 / 合并 / 新增 / 非游戏跳过 / 未决` 之一，避免裁决后漏项。`ambiguous` 判为 `distinct` 后必须转入新增详情评估，不能只写 `doctor-review`。写入前必须核对数量守恒：`唯一待处理数 = 合并 + 新增 + 非游戏跳过 + 未决`；等式不成立时禁止写入。

主代理将扫描结果中的 `date/platform/url`、返回的详情标题和 `assessment` 组合为 `add` 输入：

```json
{"source":{"date":"<列表页 date>","platform":"<PC|Switch|PC/Switch>","title":"<详情标题>","url":"<URL>"},"assessment":{...}}
```

评估规则：

- 只生成评分 1–5；推荐文字按分数派生为 `非常不推荐 / 不推荐 / 可试 / 推荐 / 优先推荐`，不单独存储。
- 先判断主循环，再看辅助元素；明确贴合模拟、经营、修理、具体工作或创新体验时，不因辅助性 Roguelite、时间压力或重复结构直接降为低分。
- 1–2 分必须有“主要体验不匹配”的证据。信息不足不是低分理由；有明确贴合点时至少给 3 分。
- `description_quality` 为 `limited/missing` 时补充调查并注明不确定性。帖子日期必须使用列表页 `date`，不是游戏发行日期。

### 4. 统一写入

先整理本轮全部 `doctor-review/update/remove/add` 操作，对每项执行 dry-run。全部成功后才正式执行：`doctor-review/update/remove` 将 `--dry-run` 替换为 `--yes`，`add` 移除 `--dry-run`。不得边预检边写入。

```bash
uv run --project 游戏收集agent/gamer520_cli gamer520 update --title "游戏标题" --set "平台=PC/Switch" --dry-run
uv run --project 游戏收集agent/gamer520_cli gamer520 remove --title "重复记录" --dry-run
uv run --project 游戏收集agent/gamer520_cli gamer520 add --stdin --dry-run << 'ENDOFDATA'
[{...}]
ENDOFDATA
```

正式写入后运行：

```bash
uv run --project 游戏收集agent/gamer520_cli gamer520 sort
uv run --project 游戏收集agent/gamer520_cli gamer520 validate
uv run --project 游戏收集agent/gamer520_cli gamer520 doctor --json
```

最终必须 validate 通过，Doctor 无完全重复和未处理的相似候选。

### 5. 汇报

首行写：`今天新增 X 款（PC Y / Switch Z）`；有跨平台更新时补充数量。

随后只汇报所有 3 分及以上游戏；不高于 3 分但特色鲜明的游戏也可列出。汇报顺序必须按评分从高到低排列；同评分时保持扫描结果中的稳定顺序。每款必须单独一行，并严格包含以下四项：

`游戏名称｜推荐语｜评分：X/5｜链接`

其中：

- `游戏名称` 使用详情抓取返回的规范标题。
- `推荐语` 根据评估 `reason` 改写为面向用户的简短推荐说明，不能只写标签或重复评分。
- `评分` 必须明确写成 `X/5`，使用 1–5 分评估结果。
- `链接` 必须是对应 Gamer520 详情页的完整 Markdown 链接，格式为 `[游戏名称](URL)`。

示例：

`太阳港 Sun Haven｜农场经营、生活模拟、城镇关系和探索都高度贴合口味，优先推荐。｜评分：5/5｜[详情](https://www.gamer520.com/57477.html)`

无值得关注项时写“今天都不太推荐”。不写操作日志、过程说明或客套结束语。
