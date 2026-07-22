from datetime import date
from typing import Literal

from pydantic import AnyUrl, BaseModel, field_validator


class GameRow(BaseModel):
    release_date: date
    platform: Literal["PC", "Switch", "PC/Switch"]
    title: str
    tags: str
    one_line_description: str
    score: int
    reasoning: str
    url: AnyUrl
    user_note: str = ""

    @field_validator("score")
    @classmethod
    def score_range(cls, v: int) -> int:
        if v < 1 or v > 5:
            raise ValueError(f"score must be 1-5, got {v}")
        return v


CSV_FIELDS = [
    "帖子发布日期",
    "平台",
    "标题",
    "标签",
    "一句话描述",
    "推荐度",
    "判断理由",
    "链接",
    "用户备注",
]

MODEL_FIELD_MAP: dict[str, str] = {
    "帖子发布日期": "release_date",
    "平台": "platform",
    "标题": "title",
    "标签": "tags",
    "一句话描述": "one_line_description",
    "推荐度": "score",
    "判断理由": "reasoning",
    "链接": "url",
    "用户备注": "user_note",
}


def row_to_csv_dict(row: GameRow) -> dict[str, str]:
    return {
        "帖子发布日期": row.release_date.isoformat(),
        "平台": row.platform,
        "标题": row.title,
        "标签": row.tags,
        "一句话描述": row.one_line_description,
        "推荐度": str(row.score),
        "判断理由": row.reasoning,
        "链接": str(row.url),
        "用户备注": row.user_note,
    }


def csv_dict_to_row(data: dict[str, str]) -> GameRow:
    raw: dict[str, str | int] = {}
    for csv_field, model_field in MODEL_FIELD_MAP.items():
        val = data.get(csv_field, "").strip()
        if model_field == "score":
            raw[model_field] = int(val) if val else 0
        else:
            raw[model_field] = val
    return GameRow.model_validate(raw)
