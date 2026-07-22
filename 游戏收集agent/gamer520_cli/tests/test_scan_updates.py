from datetime import date
from pathlib import Path

from gamer520_cli.csv_store import read_csv
from gamer520_cli.scan_updates import (
    combine_platform_scans,
    compact_scan_result,
    scan_updates,
)

FIXTURE_CSV = Path(__file__).parent / "fixtures" / "games.csv"


def _item(title: str, link_id: int, item_date: str) -> dict[str, str]:
    return {
        "title": title,
        "raw_title": title,
        "url": f"https://www.gamer520.com/{link_id}.html",
        "date": item_date,
        "date_text": "",
    }


def test_scan_updates_paginates_until_page_is_before_boundary():
    rows = read_csv(FIXTURE_CSV)
    requested_urls: list[str] = []
    pages = {
        "https://www.gamer520.com/pcplay": [
            _item("Game Alpha", 100001, "2026-06-07"),
            _item("Brand New", 200001, "2026-06-07"),
        ],
        "https://www.gamer520.com/pcplay/page/2": [
            _item("Old One", 200002, "2026-06-05"),
            _item("Old Two", 200003, "2026-06-04"),
        ],
    }

    def scrape_page(url: str) -> list[dict[str, str]]:
        requested_urls.append(url)
        return pages[url]

    result = scan_updates(
        rows,
        platform="PC",
        latest_date=date(2026, 6, 6),
        scrape_page=scrape_page,
    )

    assert result["complete"] is True
    assert result["stop_reason"] == "before_boundary"
    assert result["pages_scanned"] == 2
    assert result["summary"]["existing"] == 1
    assert result["summary"]["new"] == 1
    assert result["summary"]["before_boundary"] == 2
    assert result["summary"]["scanned_items"] == 2
    assert result["summary"]["candidates"] == 1
    assert result["summary"]["actionable_candidates"] == 1
    assert requested_urls == list(pages)


def test_scan_updates_reports_incomplete_when_max_pages_is_reached():
    rows = read_csv(FIXTURE_CSV)

    def scrape_page(url: str) -> list[dict[str, str]]:
        page_number = 1 if "/page/" not in url else int(url.rsplit("/", 1)[1])
        return [_item(f"New {page_number}", 300000 + page_number, "2026-06-06")]

    result = scan_updates(
        rows,
        platform="PC",
        latest_date=date(2026, 6, 6),
        scrape_page=scrape_page,
        max_pages=2,
    )

    assert result["complete"] is False
    assert result["stop_reason"] == "max_pages_reached"
    assert result["pages_scanned"] == 2
    assert result["summary"]["new"] == 2


def test_compact_scan_result_only_contains_actionable_groups():
    full = {
        "platform": "PC",
        "latest_date": "2026-06-06",
        "complete": True,
        "stop_reason": "before_boundary",
        "pages_scanned": 2,
        "pages": [{"page": 1}],
        "summary": {"new": 1, "ambiguous": 0, "platform_merges": 0},
        "new": [{"source": {"title": "New"}}],
        "ambiguous": [],
        "platform_merges": [],
        "existing": [{"source": {"title": "Existing"}}],
        "before_boundary": [{"source": {"title": "Old"}}],
    }

    compact = compact_scan_result(full)

    assert compact["new"] == full["new"]
    assert "pages" not in compact
    assert "existing" not in compact
    assert "before_boundary" not in compact


def test_combine_platform_scans_reports_exact_cross_platform_candidates():
    def result(platform: str, title: str, url: str) -> dict[str, object]:
        source = _item(title, 400001 if platform == "PC" else 400002, "2026-06-07")
        source["url"] = url
        return {
            "platform": platform,
            "latest_date": "2026-06-06",
            "complete": True,
            "stop_reason": "before_boundary",
            "pages_scanned": 1,
            "pages": [],
            "summary": {
                "scanned_items": 1,
                "candidates": 1,
                "actionable_candidates": 1,
                "existing": 0,
                "platform_merges": 0,
                "ambiguous": 0,
                "new": 1,
                "before_boundary": 0,
            },
            "new": [{"source": source}],
            "ambiguous": [],
            "platform_merges": [],
            "existing": [],
            "before_boundary": [],
        }

    combined = combine_platform_scans(
        {
            "PC": result("PC", "Shared Game", "https://example.com/pc"),
            "Switch": result("Switch", "Shared Game", "https://example.com/switch"),
        }
    )

    assert combined["complete"] is True
    assert combined["summary"]["cross_platform_candidates"] == 1
    assert combined["summary"]["scanned_items"] == 2
    assert combined["summary"]["actionable_candidates"] == 2
    assert combined["summary"]["candidates"] == 1
    assert combined["summary"]["unique_actionable_candidates"] == 1
    assert combined["cross_platform_candidates"][0]["reason"] == "title_exact"
    assert "pages" not in combined["platforms"]["PC"]
