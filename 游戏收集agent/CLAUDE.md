# 游戏收集 Agent

这个目录维护一个 gamer520.com 游戏收藏数据库，通过 CLI 工具管理数据，通过 AI Skill 执行每日更新流程。

## 项目结构

| 层 | 位置 | 说明 |
|----|------|------|
| 数据 | `gamer520-games.csv`、`taste.txt` | 主数据库和口味基准，不直接编辑 |
| 工具 | `gamer520_cli/` | CLI 工具，所有数据库操作通过它完成 |
| 工作流 | `Gamer520每日更新SKILL.md` | 每日更新的 5 阶段执行流程 |
| 临时 | `scratch/` | 个人札记、历史产物，不属于生产流程 |

## 关键指引

- **CLI 完整参考**（命令、CSV schema、示例）→ `gamer520_cli/README.md`
- **每日更新流程** → `Gamer520每日更新SKILL.md`
- **不要直接读取整份 CSV**，用 `search` 或 `export` 获取局部数据
- **不要创建流程中转文件**，CLI 输出由 Agent 直接处理；持久化业务状态只写数据库和 Doctor 复核账本

## 常用调用

```bash
uv run --project 游戏收集agent/gamer520_cli gamer520 <command>
```

常用起点：

```bash
# 查看最新收录边界（PC / Switch 分别查）
uv run --project 游戏收集agent/gamer520_cli gamer520 latest --platform PC --json
uv run --project 游戏收集agent/gamer520_cli gamer520 latest --platform Switch --json

# 搜索
uv run --project 游戏收集agent/gamer520_cli gamer520 search "关键词" --json

# 自动分页扫描与对账
uv run --project 游戏收集agent/gamer520_cli gamer520 scan-updates --platform all

# 数据库通用体检
uv run --project 游戏收集agent/gamer520_cli gamer520 doctor --json

# 记录已复核的相似标题结论（先 --dry-run，再 --yes）
uv run --project 游戏收集agent/gamer520_cli gamer520 doctor-review \
  --title "标题 A" --title "标题 B" \
  --decision distinct --reason "不同游戏" --dry-run

# 导出最近 N 天
uv run --project 游戏收集agent/gamer520_cli gamer520 export --days 7 --json

# 健康检查
uv run --project 游戏收集agent/gamer520_cli gamer520 validate
```
