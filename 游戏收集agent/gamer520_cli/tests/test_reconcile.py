import json
from datetime import date
from pathlib import Path

from typer.testing import CliRunner

from gamer520_cli.cli import app
from gamer520_cli.csv_store import read_csv
from gamer520_cli.reconcile import reconcile_items

FIXTURE_CSV = Path(__file__).parent / "fixtures" / "games.csv"
runner = CliRunner()


def test_reconcile_uses_title_then_url_then_similar_candidates():
    rows = read_csv(FIXTURE_CSV)
    items = [
        {
            "title": "Game Alpha",
            "raw_title": "Game Alpha|豪华中文|Build.123|",
            "url": "https://www.gamer520.com/999001.html",
            "date": "2026-06-06",
        },
        {
            "title": "Completely Renamed Game",
            "url": "https://www.gamer520.com/100002.html",
            "date": "2026-06-06",
        },
        {
            "title": "Game Alfa",
            "url": "https://www.gamer520.com/999003.html",
            "date": "2026-06-06",
        },
        {
            "title": "Brand New Title",
            "url": "https://www.gamer520.com/999004.html",
            "date": "2026-06-06",
        },
        {
            "title": "Old List Item",
            "url": "https://www.gamer520.com/999005.html",
            "date": "2026-06-05",
        },
    ]

    result = reconcile_items(
        rows,
        items,
        platform="PC",
        latest_date=date(2026, 6, 6),
    )

    assert result["match_order"] == ["title_exact", "url_exact", "title_similar"]
    assert result["existing"][0]["reason"] == "title_exact"
    assert result["platform_merges"][0]["reason"] == "url_exact"
    assert result["ambiguous"][0]["reason"] == "title_similar"
    assert result["ambiguous"][0]["candidates"][0]["title"] == "Game Alpha"
    assert result["new"][0]["source"]["title"] == "Brand New Title"
    assert result["summary"] == {
        "input": 5,
        "candidates": 4,
        "existing": 1,
        "platform_merges": 1,
        "ambiguous": 1,
        "new": 1,
        "before_boundary": 1,
    }


def test_reconcile_command_reads_scrape_list_json_from_stdin():
    payload = json.dumps(
        [
            {
                "title": "Game Alpha",
                "raw_title": "Game Alpha|官方中文|Build.123|",
                "url": "https://www.gamer520.com/999001.html",
                "date": "2026-06-06",
                "date_text": "1小时前",
            }
        ]
    )
    result = runner.invoke(
        app,
        [
            "reconcile",
            "--stdin",
            "--platform",
            "PC",
            "--latest-date",
            "2026-06-06",
            "--csv",
            str(FIXTURE_CSV),
        ],
        input=payload,
    )
    assert result.exit_code == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["summary"]["existing"] == 1
    assert output["existing"][0]["source"]["raw_title"].endswith("Build.123|")


def test_reconcile_surfaces_title_and_url_conflicts():
    rows = read_csv(FIXTURE_CSV)
    result = reconcile_items(
        rows,
        [
            {
                "title": "Game Alpha",
                "url": "https://www.gamer520.com/100002.html",
                "date": "2026-06-06",
            }
        ],
        platform="PC",
        latest_date=date(2026, 6, 6),
    )
    assert result["summary"]["ambiguous"] == 1
    assert result["ambiguous"][0]["reason"] == "title_url_conflict"
    assert {candidate["title"] for candidate in result["ambiguous"][0]["candidates"]} == {
        "Game Alpha",
        "Game Beta",
    }
