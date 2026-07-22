import json
import os
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from gamer520_cli.cli import app
from gamer520_cli.csv_store import write_csv

runner = CliRunner()


def _row(title: str, link_id: int) -> dict[str, str]:
    return {
        "帖子发布日期": "2026-07-10",
        "平台": "PC",
        "标题": title,
        "标签": "",
        "一句话描述": "",
        "推荐度": "3",
        "判断理由": "",
        "链接": f"https://www.gamer520.com/{link_id}.html",
        "用户备注": "",
    }


def _temp_paths() -> tuple[str, str]:
    csv_file = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
    csv_file.close()
    reviews_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    reviews_file.close()
    os.unlink(reviews_file.name)
    write_csv(
        csv_file.name,
        [
            _row("深空梦里人 Citizen Sleeper", 100001),
            _row("深空梦里人2 Citizen Sleeper 2", 100002),
        ],
    )
    return csv_file.name, reviews_file.name


def test_doctor_review_distinct_suppresses_resolved_candidate():
    csv_path, reviews_path = _temp_paths()
    try:
        before = runner.invoke(
            app,
            ["doctor", "--json", "--reviews", reviews_path, "--csv", csv_path],
        )
        assert before.exit_code == 0
        assert len(json.loads(before.stdout)["unresolved_candidates"]) == 1

        dry_run = runner.invoke(
            app,
            [
                "doctor-review",
                "--title",
                "深空梦里人 Citizen Sleeper",
                "--title",
                "深空梦里人2 Citizen Sleeper 2",
                "--decision",
                "distinct",
                "--reason",
                "Series entries 1 and 2",
                "--dry-run",
                "--reviews",
                reviews_path,
            ],
        )
        assert dry_run.exit_code == 0
        assert not Path(reviews_path).exists()

        recorded = runner.invoke(
            app,
            [
                "doctor-review",
                "--title",
                "深空梦里人 Citizen Sleeper",
                "--title",
                "深空梦里人2 Citizen Sleeper 2",
                "--decision",
                "distinct",
                "--reason",
                "Series entries 1 and 2",
                "--yes",
                "--reviews",
                reviews_path,
            ],
        )
        assert recorded.exit_code == 0, recorded.stderr

        after = runner.invoke(
            app,
            ["doctor", "--json", "--reviews", reviews_path, "--csv", csv_path],
        )
        data = json.loads(after.stdout)
        assert data["review_required"] is False
        assert data["unresolved_candidates"] == []
        assert len(data["reviewed_distinct"]) == 1
    finally:
        if os.path.exists(csv_path):
            os.unlink(csv_path)
        if os.path.exists(reviews_path):
            os.unlink(reviews_path)


def test_doctor_review_same_remains_actionable_until_data_is_fixed():
    csv_path, reviews_path = _temp_paths()
    try:
        result = runner.invoke(
            app,
            [
                "doctor-review",
                "--title",
                "深空梦里人 Citizen Sleeper",
                "--title",
                "深空梦里人2 Citizen Sleeper 2",
                "--decision",
                "same",
                "--reason",
                "Confirmed duplicate",
                "--yes",
                "--reviews",
                reviews_path,
            ],
        )
        assert result.exit_code == 0, result.stderr

        doctor_result = runner.invoke(
            app,
            ["doctor", "--json", "--reviews", reviews_path, "--csv", csv_path],
        )
        data = json.loads(doctor_result.stdout)
        assert data["review_required"] is True
        assert len(data["confirmed_same_candidates"]) == 1
        assert data["confirmed_same_candidates"][0]["review"]["decision"] == "same"
    finally:
        if os.path.exists(csv_path):
            os.unlink(csv_path)
        if os.path.exists(reviews_path):
            os.unlink(reviews_path)


def test_doctor_review_accepts_title_not_yet_in_database():
    csv_path, reviews_path = _temp_paths()
    try:
        result = runner.invoke(
            app,
            [
                "doctor-review",
                "--title",
                "尚未入库的新游戏",
                "--title",
                "数据库中的相似游戏",
                "--decision",
                "distinct",
                "--reason",
                "扫描候选是独立作品",
                "--dry-run",
                "--reviews",
                reviews_path,
            ],
        )

        assert result.exit_code == 0, result.stderr
        assert not Path(reviews_path).exists()
        assert json.loads(result.stdout)["would_record"]["titles"][0] == "尚未入库的新游戏"
    finally:
        if os.path.exists(csv_path):
            os.unlink(csv_path)
        if os.path.exists(reviews_path):
            os.unlink(reviews_path)
