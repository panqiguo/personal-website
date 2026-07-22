import os
import tempfile

from gamer520_cli.csv_store import CSV_FIELDS, check_header, read_csv, write_csv


def _make_csv(content: str) -> str:
    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="", suffix=".csv", delete=False
    )
    tmp.write(content)
    tmp.close()
    return tmp.name


def test_read_csv_utf8_bom():
    header = "帖子发布日期,平台,标题,标签,一句话描述,推荐度,判断理由,链接,用户备注\n"
    data = '2026-06-06,PC,Test Game,action,Desc.,3,Reason,https://www.gamer520.com/1.html,\n'
    content = header + data
    path = _make_csv(content)
    with open(path, "rb") as f:
        raw = f.read()
    with open(path, "wb") as f:
        f.write(b"\xef\xbb\xbf" + raw)
    try:
        rows = read_csv(path)
        assert len(rows) == 1
        assert rows[0]["标题"] == "Test Game"
    finally:
        os.unlink(path)


def test_write_csv_preserves_bom():
    rows_data = [
        {
            "帖子发布日期": "2026-06-06",
            "平台": "PC",
            "标题": "Test",
            "标签": "action",
            "一句话描述": "Desc",
            "推荐度": "3",
            "判断理由": "Reason",
            "链接": "https://www.gamer520.com/1.html",
            "用户备注": "",
        }
    ]
    tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
    tmp.close()
    try:
        write_csv(tmp.name, rows_data)
        with open(tmp.name, "rb") as f:
            raw = f.read()
        assert raw[:3] == b"\xef\xbb\xbf"
        assert b"Test" in raw
    finally:
        os.unlink(tmp.name)


def test_field_order_preserved():
    rows_data = [
        {
            "帖子发布日期": "2026-06-06",
            "平台": "PC",
            "标题": "Test",
            "标签": "action",
            "一句话描述": "Desc",
            "推荐度": "3",
            "判断理由": "Reason",
            "链接": "https://www.gamer520.com/1.html",
            "用户备注": "note",
        }
    ]
    tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
    tmp.close()
    try:
        write_csv(tmp.name, rows_data)
        rows = read_csv(tmp.name)
        assert list(rows[0].keys()) == CSV_FIELDS
        assert rows[0]["用户备注"] == "note"
    finally:
        os.unlink(tmp.name)


def test_check_header_valid():
    check_header(CSV_FIELDS)


def test_check_header_missing():
    import pytest

    with pytest.raises(ValueError, match="CSV header mismatch"):
        check_header(["帖子发布日期", "平台"])
