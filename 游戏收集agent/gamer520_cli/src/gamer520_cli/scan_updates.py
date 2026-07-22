from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from .normalize import normalize_title_key, normalize_url
from .reconcile import reconcile_items

PLATFORM_LIST_URLS = {
    "PC": "https://www.gamer520.com/pcplay",
    "Switch": "https://www.gamer520.com/gameswitch",
}


def scan_updates(
    rows: list[dict[str, str]],
    *,
    platform: str,
    latest_date: date,
    scrape_page: Callable[[str], list[dict[str, Any]]],
    max_pages: int = 10,
    candidate_limit: int = 3,
) -> dict[str, Any]:
    if platform not in PLATFORM_LIST_URLS:
        raise ValueError("platform must be PC or Switch")

    groups: dict[str, list[dict[str, Any]]] = {
        "existing": [],
        "platform_merges": [],
        "ambiguous": [],
        "new": [],
        "before_boundary": [],
    }
    pages: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    complete = False
    stop_reason = "max_pages_reached"

    for page_number in range(1, max_pages + 1):
        url = _page_url(PLATFORM_LIST_URLS[platform], page_number)
        raw_items = scrape_page(url)
        if not raw_items:
            pages.append({"page": page_number, "url": url, "input": 0})
            complete = True
            stop_reason = "empty_page"
            break

        unique_items: list[dict[str, Any]] = []
        for item in raw_items:
            normalized_url = normalize_url(str(item.get("url") or ""))
            if normalized_url and normalized_url in seen_urls:
                continue
            if normalized_url:
                seen_urls.add(normalized_url)
            unique_items.append(item)

        result = reconcile_items(
            rows,
            unique_items,
            platform=platform,
            latest_date=latest_date,
            candidate_limit=candidate_limit,
        )
        for group in groups:
            groups[group].extend(result[group])
        pages.append(
            {
                "page": page_number,
                "url": url,
                "raw_input": len(raw_items),
                "unique_input": len(unique_items),
                **result["summary"],
            }
        )

        page_dates = [_item_date(item) for item in raw_items]
        if all(item_date < latest_date for item_date in page_dates):
            complete = True
            stop_reason = "before_boundary"
            break

    scanned_item_count = sum(
        len(groups[group])
        for group in ("existing", "platform_merges", "ambiguous", "new")
    )
    actionable_count = sum(
        len(groups[group]) for group in ("platform_merges", "ambiguous", "new")
    )
    return {
        "platform": platform,
        "latest_date": latest_date.isoformat(),
        "complete": complete,
        "stop_reason": stop_reason,
        "pages_scanned": len(pages),
        "pages": pages,
        "summary": {
            "scanned_items": scanned_item_count,
            "candidates": actionable_count,
            "actionable_candidates": actionable_count,
            "existing": len(groups["existing"]),
            "platform_merges": len(groups["platform_merges"]),
            "ambiguous": len(groups["ambiguous"]),
            "new": len(groups["new"]),
            "before_boundary": len(groups["before_boundary"]),
        },
        **groups,
    }


def compact_scan_result(result: dict[str, Any]) -> dict[str, Any]:
    """Return only the scan state and groups that require Agent action."""
    return {
        "platform": result["platform"],
        "latest_date": result["latest_date"],
        "complete": result["complete"],
        "stop_reason": result["stop_reason"],
        "pages_scanned": result["pages_scanned"],
        "summary": result["summary"],
        "new": result["new"],
        "ambiguous": result["ambiguous"],
        "platform_merges": result["platform_merges"],
    }


def combine_platform_scans(
    results: dict[str, dict[str, Any]],
    *,
    debug: bool = False,
) -> dict[str, Any]:
    if set(results) != {"PC", "Switch"}:
        raise ValueError("combined scan requires PC and Switch results")

    cross_platform_candidates = _cross_platform_candidates(
        results["PC"], results["Switch"]
    )
    summary_keys = (
        "scanned_items",
        "actionable_candidates",
        "existing",
        "platform_merges",
        "ambiguous",
        "new",
        "before_boundary",
    )
    complete = all(result["complete"] for result in results.values())
    summary = {
        key: sum(result["summary"][key] for result in results.values())
        for key in summary_keys
    }
    unique_actionable_count = (
        summary["actionable_candidates"] - len(cross_platform_candidates)
    )
    return {
        "platform": "all",
        "complete": complete,
        "stop_reason": "complete" if complete else "platform_incomplete",
        "summary": summary
        | {
            "candidates": unique_actionable_count,
            "unique_actionable_candidates": unique_actionable_count,
            "cross_platform_candidates": len(cross_platform_candidates),
        },
        "platforms": {
            platform: result if debug else compact_scan_result(result)
            for platform, result in results.items()
        },
        "cross_platform_candidates": cross_platform_candidates,
    }


def _cross_platform_candidates(
    pc_result: dict[str, Any],
    switch_result: dict[str, Any],
) -> list[dict[str, Any]]:
    pc_items = _actionable_sources(pc_result)
    switch_items = _actionable_sources(switch_result)
    candidates: list[dict[str, Any]] = []
    for pc_source in pc_items:
        pc_title = normalize_title_key(pc_source.get("title", ""))
        pc_url = normalize_url(pc_source.get("url", ""))
        for switch_source in switch_items:
            switch_title = normalize_title_key(switch_source.get("title", ""))
            switch_url = normalize_url(switch_source.get("url", ""))
            if pc_title and pc_title == switch_title:
                reason = "title_exact"
            elif pc_url and pc_url == switch_url:
                reason = "url_exact"
            else:
                continue
            candidates.append(
                {
                    "reason": reason,
                    "pc": pc_source,
                    "switch": switch_source,
                }
            )
    return candidates


def _actionable_sources(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item["source"]
        for group in ("new", "ambiguous")
        for item in result[group]
    ]


def _page_url(base_url: str, page_number: int) -> str:
    if page_number == 1:
        return base_url
    return f"{base_url}/page/{page_number}"


def _item_date(item: dict[str, Any]) -> date:
    raw_date = str(item.get("date") or "").strip()
    try:
        return date.fromisoformat(raw_date)
    except ValueError as exc:
        title = str(item.get("title") or "")
        raise ValueError(f"scan item '{title}' has invalid date '{raw_date}'") from exc
