import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import DEFAULT_CSV_PATH, DEFAULT_DOCTOR_REVIEWS_PATH
from .csv_store import read_csv, write_csv
from .models import CSV_FIELDS, MODEL_FIELD_MAP
from .normalize import (
    extract_link_id,
    is_url_valid,
    normalize_title_key,
    normalize_url,
)

app = typer.Typer(
    name="gamer520",
    help="CLI for managing Gamer520 game CSV data",
    no_args_is_help=True,
)

err_console = Console(stderr=True)

CSV_OPT = typer.Option(
    None,
    "--csv",
    help="Path to CSV file (default: ../gamer520-games.csv)",
)


def _resolve_csv(csv_opt: Optional[str]) -> Path:
    if csv_opt:
        return Path(csv_opt)
    return DEFAULT_CSV_PATH



def _search_rows(
    rows: list[dict[str, str]],
    query: str,
    field: Optional[str] = None,
) -> list[dict[str, str]]:
    q = query.lower()
    fields = [field] if field else CSV_FIELDS
    return [
        row for row in rows
        if any(q in row.get(f, "").lower() for f in fields)
    ]


def _latest_info(rows: list[dict[str, str]]) -> tuple[date, int, int]:
    latest: date | None = None
    for row in rows:
        try:
            d = date.fromisoformat(row["帖子发布日期"])
        except ValueError:
            continue
        if latest is None or d > latest:
            latest = d
    if latest is None:
        msg = "No valid dates found in CSV"
        raise typer.BadParameter(msg)
    rows_on_date = [r for r in rows if r["帖子发布日期"] == latest.isoformat()]
    max_id = 0
    for r in rows_on_date:
        rid = extract_link_id(r.get("链接", ""))
        if rid and rid > max_id:
            max_id = rid
    return latest, len(rows_on_date), max_id


def _check_duplicates(
    rows: list[dict[str, str]],
) -> dict[str, list[tuple[int, str, str]]]:
    link_groups: dict[str, list[tuple[int, str, str]]] = {}
    title_groups: dict[str, list[tuple[int, str, str]]] = {}
    for i, row in enumerate(rows, start=2):
        url = normalize_url(row.get("链接", ""))
        link_groups.setdefault(url, []).append((i, row["标题"], url))
        norm = normalize_title_key(row.get("标题", ""))
        if norm:
            title_groups.setdefault(norm, []).append((i, row["标题"], url))
    dups: dict[str, list[tuple[int, str, str]]] = {}
    link_dups = {k: v for k, v in link_groups.items() if len(v) > 1}
    title_dups = {k: v for k, v in title_groups.items() if len(v) > 1}
    dups["links"] = list(link_dups.values())
    dups["titles"] = list(title_dups.values())
    return dups


def _validate_rows(
    rows: list[dict[str, str]],
    strict: bool = False,
) -> list[str]:
    errors: list[str] = []
    for i, row in enumerate(rows, start=2):
        raw_date = row.get("帖子发布日期", "").strip()
        platform = row.get("平台", "").strip()
        score = row.get("推荐度", "").strip()
        url = row.get("链接", "").strip()
        try:
            date.fromisoformat(raw_date)
        except ValueError:
            errors.append(f"Row {i}: invalid date '{raw_date}'")
        if platform not in ("PC", "Switch", "PC/Switch"):
            errors.append(f"Row {i}: invalid platform '{platform}'")
        if score not in ("1", "2", "3", "4", "5"):
            errors.append(f"Row {i}: invalid score '{score}'")
        if not url:
            errors.append(f"Row {i}: empty link")
        elif not is_url_valid(url):
            errors.append(f"Row {i}: invalid URL '{url[:60]}'")
        if not row.get("标题", "").strip():
            errors.append(f"Row {i}: empty title")
    dups = _check_duplicates(rows)
    for group in dups["links"]:
        lines = ", ".join(str(x[0]) for x in group)
        errors.append(f"Duplicate link (rows {lines}): {group[0][2]}")
    for group in dups["titles"]:
        lines = ", ".join(str(x[0]) for x in group)
        errors.append(f"Duplicate title (rows {lines}): {group[0][1]}")
    return errors


def _export_rows(
    rows: list[dict[str, str]],
    *,
    full: bool = False,
    format: str = "jsonl",
) -> str:
    fields = CSV_FIELDS
    if not full:
        fields = [f for f in CSV_FIELDS if f != "判断理由"]
    if format == "jsonl":
        lines: list[str] = []
        for row in rows:
            obj = {k: row.get(k, "") for k in fields}
            lines.append(json.dumps(obj, ensure_ascii=False))
        return "\n".join(lines)
    elif format == "csv":
        import csv
        import io

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fields})
        return buf.getvalue()
    elif format == "md":
        lines_out: list[str] = []
        lines_out.append("| " + " | ".join(fields) + " |")
        lines_out.append("| " + " | ".join("---" for _ in fields) + " |")
        for row in rows:
            vals = [row.get(k, "").replace("|", "\\|") for k in fields]
            lines_out.append("| " + " | ".join(vals) + " |")
        return "\n".join(lines_out)
    else:
        msg = f"Unknown format: {format}"
        raise typer.BadParameter(msg)


@app.command()
def latest(
    csv_opt: Optional[str] = CSV_OPT,
    platform: Optional[str] = typer.Option(
        None, "--platform", help="Filter by platform: PC, Switch, or PC/Switch",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    rows = read_csv(_resolve_csv(csv_opt))
    if platform:
        if platform in ("PC", "Switch"):
            rows = [r for r in rows if platform in r.get("平台", "").split("/")]
        else:
            rows = [r for r in rows if r.get("平台", "") == platform]
        if not rows:
            err_console.print(f"No rows found for platform '{platform}'", style="red")
            raise typer.Exit(code=1)
    d, count_on_date, max_id = _latest_info(rows)
    total = len(rows)
    if json_output:
        obj = {
            "latest_date": d.isoformat(),
            "rows_on_latest_date": count_on_date,
            "latest_link_id": max_id,
            "total_rows": total,
        }
        if platform:
            obj["platform"] = platform
        print(json.dumps(obj, ensure_ascii=False))
    else:
        if platform:
            print(f"platform: {platform}")
        print(f"latest_date: {d.isoformat()}")
        print(f"rows_on_latest_date: {count_on_date}")
        print(f"latest_link_id: {max_id}")
        print(f"total_rows: {total}")
    raise typer.Exit()


@app.command()
def search(
    query: str = typer.Argument(
        ...,
        help="Case-insensitive substring query across CSV fields",
    ),
    field: Optional[str] = typer.Option(
        None,
        "--field", "-f",
        help=f"Restrict to one field: {', '.join(CSV_FIELDS)}",
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
    full: bool = typer.Option(False, "--full", help="Show all fields"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    csv_opt: Optional[str] = CSV_OPT,
):
    if field and field not in CSV_FIELDS:
        err_console.print(
            f"Error: unknown field '{field}'. Valid: {', '.join(CSV_FIELDS)}", style="red"
        )
        raise typer.Exit(code=2)
    rows = read_csv(_resolve_csv(csv_opt))
    results = _search_rows(rows, query, field=field)
    results = results[:limit]
    if json_output:
        if full:
            out_fields = CSV_FIELDS
        else:
            out_fields = ("帖子发布日期", "平台", "标题", "推荐度", "链接", "用户备注")
        out = json.dumps(
            [{k: r.get(k, "") for k in out_fields} for r in results],
            ensure_ascii=False,
            indent=2,
        )
        print(out)
    else:
        if not results:
            print("No matches found.")
            raise typer.Exit()
        for r in results:
            if full:
                print(
                    f"{r['帖子发布日期']} [{r['平台']}] {r['标题']} | {r.get('标签','')} | {r.get('一句话描述','')} | score: {r['推荐度']} | {r['链接']} | {r.get('用户备注','')}"
                )
            else:
                print(
                    f"{r['帖子发布日期']} [{r['平台']}] {r['标题']} (score: {r['推荐度']}) {r['链接']}"
                )


@app.command()
def reconcile(
    platform: str = typer.Option(..., "--platform", help="Source platform: PC or Switch"),
    stdin: bool = typer.Option(False, "--stdin", help="Read scrape-list JSON array from stdin"),
    latest_date: Optional[str] = typer.Option(
        None,
        "--latest-date",
        help="Override the database-derived boundary date (YYYY-MM-DD)",
    ),
    candidate_limit: int = typer.Option(
        3,
        "--candidate-limit",
        min=1,
        help="Maximum similar-title candidates per ambiguous item",
    ),
    csv_opt: Optional[str] = CSV_OPT,
):
    """Classify scraped list items as existing, platform merge, ambiguous, or new."""
    if platform not in ("PC", "Switch"):
        err_console.print("Error: --platform must be PC or Switch", style="red")
        raise typer.Exit(code=2)
    if not stdin:
        err_console.print("Error: provide --stdin", style="red")
        raise typer.Exit(code=2)

    try:
        items = json.loads(sys.stdin.read())
    except json.JSONDecodeError as e:
        err_console.print(f"Error reading reconcile input: {e}", style="red")
        raise typer.Exit(code=2)
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        err_console.print("Error: reconcile input must be a JSON array of objects", style="red")
        raise typer.Exit(code=2)

    rows = read_csv(_resolve_csv(csv_opt))
    if latest_date:
        try:
            boundary = date.fromisoformat(latest_date)
        except ValueError:
            err_console.print(
                f"Error: invalid --latest-date '{latest_date}', expected YYYY-MM-DD",
                style="red",
            )
            raise typer.Exit(code=2)
    else:
        platform_rows = [
            row for row in rows if platform in row.get("平台", "").split("/")
        ]
        if not platform_rows:
            err_console.print(
                f"Error: no database rows found for platform '{platform}'",
                style="red",
            )
            raise typer.Exit(code=1)
        boundary, _, _ = _latest_info(platform_rows)

    from .reconcile import reconcile_items

    try:
        result = reconcile_items(
            rows,
            items,
            platform=platform,
            latest_date=boundary,
            candidate_limit=candidate_limit,
        )
    except ValueError as e:
        err_console.print(f"Error: {e}", style="red")
        raise typer.Exit(code=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))


@app.command("scan-updates")
def scan_updates_cmd(
    platform: str = typer.Option(
        ..., "--platform", help="Source platform: PC, Switch, or all"
    ),
    max_pages: int = typer.Option(
        10,
        "--max-pages",
        min=1,
        help="Safety limit for list pagination",
    ),
    candidate_limit: int = typer.Option(
        3,
        "--candidate-limit",
        min=1,
        help="Maximum similar-title candidates per ambiguous item",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Include per-page, existing, and before-boundary details",
    ),
    csv_opt: Optional[str] = CSV_OPT,
):
    """Scrape and reconcile list pages until every item is before the boundary."""
    if platform not in ("PC", "Switch", "all"):
        err_console.print("Error: --platform must be PC, Switch, or all", style="red")
        raise typer.Exit(code=2)

    rows = read_csv(_resolve_csv(csv_opt))
    validation_errors = _validate_rows(rows)
    if validation_errors:
        for error in validation_errors:
            err_console.print(f"Validation error: {error}", style="red")
        raise typer.Exit(code=1)
    from .scan_updates import combine_platform_scans, compact_scan_result, scan_updates
    from .scraper import scrape_list

    platforms = ("PC", "Switch") if platform == "all" else (platform,)
    results: dict[str, dict[str, object]] = {}
    try:
        for source_platform in platforms:
            platform_rows = [
                row
                for row in rows
                if source_platform in row.get("平台", "").split("/")
            ]
            if not platform_rows:
                raise ValueError(
                    f"no database rows found for platform '{source_platform}'"
                )
            boundary, _, _ = _latest_info(platform_rows)
            results[source_platform] = scan_updates(
                rows,
                platform=source_platform,
                latest_date=boundary,
                scrape_page=scrape_list,
                max_pages=max_pages,
                candidate_limit=candidate_limit,
            )
    except (ValueError, OSError) as e:
        err_console.print(f"Scan failed: {e}", style="red")
        raise typer.Exit(code=1)
    except Exception as e:
        err_console.print(f"Scan failed: {e}", style="red")
        raise typer.Exit(code=1)

    if platform == "all":
        output = combine_platform_scans(results, debug=debug)
        complete = output["complete"]
    else:
        result = results[platform]
        output = result if debug else compact_scan_result(result)
        complete = result["complete"]
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if not complete:
        err_console.print(
            "Scan incomplete for at least one platform; increase --max-pages",
            style="red",
        )
        raise typer.Exit(code=1)


@app.command()
def validate(
    csv_opt: Optional[str] = CSV_OPT,
    strict: bool = typer.Option(False, "--strict", help="(reserved for future strict checks)"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    csv_path = _resolve_csv(csv_opt)
    try:
        rows = read_csv(csv_path)
    except ValueError as e:
        err_console.print(f"CSV read error: {e}", style="red")
        raise typer.Exit(code=1)
    errors = _validate_rows(rows, strict=strict)
    if json_output:
        obj = {
            "valid": len(errors) == 0,
            "total_rows": len(rows),
            "errors": errors,
        }
        print(json.dumps(obj, ensure_ascii=False))
    else:
        if errors:
            for e in errors:
                err_console.print(f"  {e}", style="red")
            err_console.print(f"\nTotal: {len(rows)} rows, {len(errors)} errors", style="red")
            raise typer.Exit(code=1)
        else:
            print(f"All valid: {len(rows)} rows, no errors.")


@app.command("doctor")
def doctor(
    csv_opt: Optional[str] = CSV_OPT,
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    reviews_path: Optional[str] = typer.Option(
        None,
        "--reviews",
        help="Doctor review ledger path",
    ),
    similarity_threshold: float = typer.Option(
        0.82,
        "--similarity-threshold",
        min=0.5,
        max=1.0,
        help="Minimum score for similar-title review candidates",
    ),
):
    """Check exact duplicates and report similar-title candidates for review."""
    csv_path = _resolve_csv(csv_opt)
    try:
        rows = read_csv(csv_path)
    except ValueError as e:
        err_console.print(f"CSV read error: {e}", style="red")
        raise typer.Exit(code=1)

    link_groups: dict[str, list[dict[str, str | int]]] = {}
    title_groups: dict[str, list[dict[str, str | int]]] = {}
    indexed_items: list[tuple[dict[str, str], dict[str, str | int]]] = []

    for i, row in enumerate(rows, start=2):
        raw_url = row.get("链接", "").strip()
        url = normalize_url(raw_url)
        item = {
            "row": i,
            "date": row.get("帖子发布日期", "").strip(),
            "platform": row.get("平台", "").strip(),
            "title": row.get("标题", "").strip(),
            "score": row.get("推荐度", "").strip(),
            "url": raw_url,
        }
        if url:
            link_groups.setdefault(url, []).append(item)

        norm_title = normalize_title_key(row.get("标题", ""))
        if norm_title:
            title_groups.setdefault(norm_title, []).append(item)
        indexed_items.append((row, item))

    link_dups = {k: v for k, v in link_groups.items() if len(v) > 1}
    title_dups = {k: v for k, v in title_groups.items() if len(v) > 1}
    from .doctor_reviews import read_reviews, review_key
    from .reconcile import title_similarity

    resolved_reviews_path = Path(reviews_path) if reviews_path else DEFAULT_DOCTOR_REVIEWS_PATH
    try:
        reviews = read_reviews(resolved_reviews_path)
    except ValueError as e:
        err_console.print(f"Doctor review error: {e}", style="red")
        raise typer.Exit(code=1)

    similar_title_candidates: list[dict[str, object]] = []
    reviewed_distinct: list[dict[str, object]] = []
    for left_index, (left_row, left_item) in enumerate(indexed_items):
        left_title_key = normalize_title_key(left_row.get("标题", ""))
        left_url = normalize_url(left_row.get("链接", ""))
        for right_row, right_item in indexed_items[left_index + 1:]:
            right_title_key = normalize_title_key(right_row.get("标题", ""))
            right_url = normalize_url(right_row.get("链接", ""))
            if left_title_key == right_title_key or left_url == right_url:
                continue
            score = title_similarity(
                left_row.get("标题", ""), right_row.get("标题", "")
            )
            if score >= similarity_threshold:
                candidate: dict[str, object] = {
                    "score": round(score, 3),
                    "items": [left_item, right_item],
                }
                review = reviews.get(
                    review_key(
                        left_row.get("标题", ""), right_row.get("标题", "")
                    )
                )
                if review:
                    candidate["review"] = review
                if review and review["decision"] == "distinct":
                    reviewed_distinct.append(candidate)
                else:
                    similar_title_candidates.append(candidate)
    similar_title_candidates.sort(
        key=lambda candidate: float(candidate["score"]), reverse=True
    )
    confirmed_same_candidates = [
        candidate
        for candidate in similar_title_candidates
        if isinstance(candidate.get("review"), dict)
        and candidate["review"].get("decision") == "same"
    ]
    unresolved_candidates = [
        candidate
        for candidate in similar_title_candidates
        if not isinstance(candidate.get("review"), dict)
    ]

    if json_output:
        output_data = {
            "valid": not bool(link_dups or title_dups),
            "review_required": bool(similar_title_candidates),
            "link_repeats": [
                {"normalized_url": url, "items": items}
                for url, items in link_dups.items()
            ],
            "title_repeats": [
                {"normalized_title": norm_title, "items": items}
                for norm_title, items in title_dups.items()
            ],
            "similar_title_candidates": similar_title_candidates,
            "confirmed_same_candidates": confirmed_same_candidates,
            "unresolved_candidates": unresolved_candidates,
            "reviewed_distinct": reviewed_distinct,
            "reviews_path": str(resolved_reviews_path),
            "similarity_threshold": similarity_threshold,
        }
        print(json.dumps(output_data, ensure_ascii=False, indent=2))
        if link_dups or title_dups:
            raise typer.Exit(code=1)
        raise typer.Exit(code=0)

    console = Console()
    if not link_dups and not title_dups and not similar_title_candidates:
        console.print("[bold green]Database is healthy; no duplicate or similar titles found.[/bold green]")
        raise typer.Exit(code=0)

    if link_dups:
        console.print(f"[bold yellow]Found {len(link_dups)} duplicate link group(s):[/bold yellow]\n")
        for url, items in link_dups.items():
            console.print(f"[bold cyan]Normalized URL: {url}[/bold cyan]")
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Row", style="dim", width=6)
            table.add_column("Date", width=12)
            table.add_column("Platform", width=10)
            table.add_column("Title", style="bold")
            table.add_column("Score", justify="right", width=6)
            table.add_column("URL")
            for item in items:
                table.add_row(
                    str(item["row"]),
                    str(item["date"]),
                    str(item["platform"]),
                    str(item["title"]),
                    str(item["score"]),
                    str(item["url"]),
                )
            console.print(table)
            console.print()

    if title_dups:
        console.print(f"[bold yellow]Found {len(title_dups)} duplicate title group(s):[/bold yellow]\n")
        for norm_title, items in title_dups.items():
            console.print(f"[bold cyan]Normalized Title Key: '{norm_title}'[/bold cyan]")
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Row", style="dim", width=6)
            table.add_column("Date", width=12)
            table.add_column("Platform", width=10)
            table.add_column("Title", style="bold")
            table.add_column("Score", justify="right", width=6)
            table.add_column("URL")
            for item in items:
                table.add_row(
                    str(item["row"]),
                    str(item["date"]),
                    str(item["platform"]),
                    str(item["title"]),
                    str(item["score"]),
                    str(item["url"]),
                )
            console.print(table)
            console.print()

    if similar_title_candidates:
        console.print(
            f"[bold yellow]Found {len(similar_title_candidates)} similar-title candidate(s) for review:[/bold yellow]\n"
        )
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Score", justify="right", width=7)
        table.add_column("Decision", width=10)
        table.add_column("First title")
        table.add_column("Second title")
        for candidate in similar_title_candidates:
            items = candidate["items"]
            review = candidate.get("review")
            decision = review.get("decision", "unresolved") if isinstance(review, dict) else "unresolved"
            table.add_row(
                str(candidate["score"]),
                str(decision),
                str(items[0]["title"]),
                str(items[1]["title"]),
            )
        console.print(table)

    raise typer.Exit(code=1 if link_dups or title_dups else 0)


@app.command("doctor-review")
def doctor_review(
    titles: list[str] = typer.Option(
        [],
        "--title",
        help="Title in the reviewed pair; provide exactly twice",
    ),
    decision: str = typer.Option(..., "--decision", help="same or distinct"),
    reason: str = typer.Option(..., "--reason", help="Reason for the review decision"),
    reviews_path: Optional[str] = typer.Option(
        None,
        "--reviews",
        help="Doctor review ledger path",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview review, do not write"),
    yes: bool = typer.Option(False, "--yes", help="Confirm review"),
):
    """Record a model or user decision for a similar-title pair."""
    if len(titles) != 2:
        err_console.print("Error: provide exactly two --title values", style="red")
        raise typer.Exit(code=2)
    if decision not in ("same", "distinct"):
        err_console.print("Error: --decision must be same or distinct", style="red")
        raise typer.Exit(code=2)

    from .doctor_reviews import review_key

    try:
        review_key(titles[0], titles[1])
    except ValueError as e:
        err_console.print(f"Error: {e}", style="red")
        raise typer.Exit(code=2)

    target = Path(reviews_path) if reviews_path else DEFAULT_DOCTOR_REVIEWS_PATH
    preview = {
        "titles": titles,
        "decision": decision,
        "reason": reason.strip(),
        "reviews_path": str(target),
    }
    if dry_run:
        print(json.dumps({"would_record": preview}, ensure_ascii=False, indent=2))
        raise typer.Exit()
    if not yes:
        err_console.print(
            "Use --yes to confirm review (preview with --dry-run first)", style="red"
        )
        raise typer.Exit(code=1)

    from .doctor_reviews import write_review

    try:
        review = write_review(
            target,
            title_a=titles[0],
            title_b=titles[1],
            decision=decision,
            reason=reason,
        )
    except (OSError, ValueError) as e:
        err_console.print(f"Error writing doctor review: {e}", style="red")
        raise typer.Exit(code=1)
    print(
        json.dumps(
            {"recorded": {**preview, "reviewed_at": review["reviewed_at"]}},
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command("sort")
def sort_csv(
    csv_opt: Optional[str] = CSV_OPT,
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview sort, do not write"),
):
    csv_path = _resolve_csv(csv_opt)
    rows = read_csv(csv_path)

    def sort_key(row: dict[str, str]) -> tuple[str, int]:
        try:
            d = date.fromisoformat(row["帖子发布日期"])
        except ValueError:
            d = date.min
        rid = extract_link_id(row.get("链接", "")) or 0
        return (-d.toordinal(), -rid)

    sorted_rows = sorted(rows, key=sort_key)
    if dry_run:
        print(f"Would sort {len(sorted_rows)} rows (no write)")
        for r in sorted_rows[:5]:
            print(f"  {r['帖子发布日期']} id={extract_link_id(r.get('链接',''))} {r['标题']}")
        if len(sorted_rows) > 5:
            print(f"  ... and {len(sorted_rows) - 5} more")
    else:
        write_csv(csv_path, sorted_rows)
        print(f"Sorted and wrote {len(sorted_rows)} rows to {csv_path}")


@app.command()
def add(
    stdin: bool = typer.Option(False, "--stdin", help="Read JSON array from stdin (preferred for AI)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes, do not write"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    csv_opt: Optional[str] = CSV_OPT,
):
    """Add one or more entries from JSON.

    Examples:
      gamer520 add --stdin --dry-run
    """
    if not stdin:
        err_console.print("Error: provide --stdin", style="red")
        raise typer.Exit(code=2)
    csv_path = _resolve_csv(csv_opt)
    existing = read_csv(csv_path)
    try:
        entries = json.loads(sys.stdin.read())
        if not isinstance(entries, list):
            err_console.print("Error: input must be a JSON array", style="red")
            raise typer.Exit(code=2)
    except json.JSONDecodeError as e:
        err_console.print(f"Error parsing JSON: {e}", style="red")
        raise typer.Exit(code=2)

    new_rows: list[dict[str, str]] = []
    errors: list[str] = []
    rejected_count = 0
    for i, entry in enumerate(entries):
        try:
            row = _add_entry_to_row(entry)
        except ValueError as exc:
            errors.append(f"Entry {i + 1}: {exc}")
            rejected_count += 1
            continue
        errors_in_row = _validate_entry(row, i + 1, existing + new_rows)
        if errors_in_row:
            errors.extend(errors_in_row)
            rejected_count += 1
            continue
        new_rows.append(row)

    if errors:
        for e in errors:
            err_console.print(e, style="red")
        if json_output:
            print(
                json.dumps(
                    {
                        "accepted_entries": len(new_rows),
                        "rejected_entries": rejected_count,
                        "error_count": len(errors),
                        "errors": errors,
                    },
                    ensure_ascii=False,
                )
            )
        raise typer.Exit(code=1)

    all_rows = existing + new_rows
    validation_errors = _validate_rows(all_rows)
    if validation_errors:
        for e in validation_errors:
            err_console.print(f"Validation error: {e}", style="red")
        if json_output and dry_run:
            print(
                json.dumps(
                    {
                        "would_add": len(new_rows),
                        "validation_errors": validation_errors,
                    },
                    ensure_ascii=False,
                )
            )
        raise typer.Exit(code=1)

    if dry_run:
        msg = f"Would add {len(new_rows)} entries (no duplicates, no errors)"
        print(msg)
        for r in new_rows:
            print(f"  + {r['帖子发布日期']} [{r['平台']}] {r['标题']} ({r['链接']})")
    else:
        write_csv(csv_path, all_rows)
        if json_output:
            print(
                json.dumps(
                    {"added": len(new_rows), "total": len(all_rows)},
                    ensure_ascii=False,
                )
            )
        else:
            print(f"Added {len(new_rows)} entries. Total: {len(all_rows)} rows.")


def _add_entry_to_row(entry: object) -> dict[str, str]:
    if not isinstance(entry, dict):
        raise ValueError("entry must be an object")

    if "source" not in entry and "assessment" not in entry:
        return {
            field: str(entry.get(field) or "").strip()
            for field in CSV_FIELDS
        }

    source = entry.get("source")
    assessment = entry.get("assessment")
    if not isinstance(source, dict) or not isinstance(assessment, dict):
        raise ValueError("structured entry requires source and assessment objects")

    tags = assessment.get("tags") or ""
    if isinstance(tags, list):
        tags = "；".join(str(tag).strip() for tag in tags if str(tag).strip())
    return {
        "帖子发布日期": str(source.get("date") or "").strip(),
        "平台": str(source.get("platform") or "").strip(),
        "标题": str(source.get("title") or "").strip(),
        "标签": str(tags).strip(),
        "一句话描述": str(assessment.get("description") or "").strip(),
        "推荐度": str(assessment.get("score") or "").strip(),
        "判断理由": str(assessment.get("reason") or "").strip(),
        "链接": str(source.get("url") or "").strip(),
        "用户备注": str(assessment.get("user_note") or "").strip(),
    }


def _validate_entry(
    row: dict[str, str],
    num: int,
    all_rows: list[dict[str, str]],
) -> list[str]:
    errs: list[str] = []
    try:
        date.fromisoformat(row["帖子发布日期"])
    except (ValueError, KeyError):
        errs.append(f"Entry #{num}: invalid date '{row.get('帖子发布日期', '')}'")
    if row.get("平台") not in ("PC", "Switch", "PC/Switch"):
        errs.append(f"Entry #{num}: invalid platform '{row.get('平台', '')}'")
    score = row.get("推荐度", "")
    if score not in ("1", "2", "3", "4", "5"):
        errs.append(f"Entry #{num}: invalid score '{score}'")
    if not row.get("标题", "").strip():
        errs.append(f"Entry #{num}: empty title")
    if not row.get("链接", "").strip():
        errs.append(f"Entry #{num}: empty link")
    else:
        normalized = normalize_url(row["链接"])
        if not is_url_valid(normalized):
            errs.append(f"Entry #{num}: invalid URL '{row['链接'][:60]}'")
        dup = _find_duplicate_link(normalized, all_rows)
        if dup:
            errs.append(
                f"Entry #{num}: duplicate link '{normalized}' matches row {dup[0]}: {dup[1]}"
            )
    norm = normalize_title_key(row.get("标题", ""))
    if norm:
        dup = _find_duplicate_title(norm, all_rows)
        if dup:
            errs.append(
                f"Entry #{num}: duplicate title '{row.get('标题', '')}' matches row {dup[0]}: {dup[1]}"
            )
    return errs


def _find_duplicate_link(
    url: str, rows: list[dict[str, str]],
) -> tuple[int, str] | None:
    for i, r in enumerate(rows, start=2):
        if normalize_url(r.get("链接", "")) == url:
            return (i, r.get("标题", ""))
    return None


def _find_duplicate_title(
    norm_title: str, rows: list[dict[str, str]],
) -> tuple[int, str] | None:
    for i, r in enumerate(rows, start=2):
        if normalize_title_key(r.get("标题", "")) == norm_title:
            return (i, r.get("标题", ""))
    return None


@app.command()
def remove(
    title: str = typer.Option(..., "--title", help="Exact title to remove (after normalization)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview removal, do not write"),
    yes: bool = typer.Option(False, "--yes", help="Confirm removal"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    csv_opt: Optional[str] = CSV_OPT,
):
    csv_path = _resolve_csv(csv_opt)
    rows = read_csv(csv_path)
    norm_query = normalize_title_key(title)
    matches: list[tuple[int, dict[str, str]]] = []
    for i, r in enumerate(rows, start=2):
        if normalize_title_key(r.get("标题", "")) == norm_query:
            matches.append((i, r))
    if len(matches) == 0:
        err_console.print(f"No match for title '{title}' (normalized: '{norm_query}')", style="red")
        raise typer.Exit(code=1)
    if len(matches) > 1:
        err_console.print(
            f"Multiple matches ({len(matches)}) for title. Data integrity issue.", style="red"
        )
        for line, r in matches:
            err_console.print(f"  Row {line}: {r['标题']} ({r['链接']})")
        raise typer.Exit(code=1)
    line, match_row = matches[0]
    if dry_run:
        if json_output:
            print(json.dumps({"would_remove": match_row}, ensure_ascii=False))
        else:
            print(
                f"Would remove row {line}: {match_row['帖子发布日期']} [{match_row['平台']}] {match_row['标题']}"
            )
        raise typer.Exit()
    if not yes:
        err_console.print(
            "Use --yes to confirm removal (preview with --dry-run first)", style="red"
        )
        raise typer.Exit(code=1)
    remaining = [r for i, r in enumerate(rows, start=2) if i != line]
    validation_errors = _validate_rows(remaining)
    if validation_errors:
        for e in validation_errors:
            err_console.print(f"Post-removal validation error: {e}", style="red")
        raise typer.Exit(code=1)
    write_csv(csv_path, remaining)
    if json_output:
        print(
            json.dumps({"removed": match_row["标题"], "remaining": len(remaining)}, ensure_ascii=False)
        )
    else:
        print(f"Removed row {line}: {match_row['标题']}. {len(remaining)} rows remaining.")


@app.command()
def update(
    title: str = typer.Option(
        ..., "--title", help="Exact title to update (after normalization)"
    ),
    set_fields: list[str] = typer.Option(
        [],
        "--set",
        help='field=value pairs to update (e.g. --set "推荐度=4" --set "用户备注=已玩")',
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes, do not write"),
    yes: bool = typer.Option(False, "--yes", help="Confirm update"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    csv_opt: Optional[str] = CSV_OPT,
):
    """Update one or more fields of an existing entry by title.

    Examples:
      gamer520 update --title "舒适森林 Cozy Grove" --set "用户备注=玩过" --dry-run
      gamer520 update --title "游戏名" --set "推荐度=4" --yes
    """
    if not set_fields:
        err_console.print("Error: provide at least one --set field=value", style="red")
        raise typer.Exit(code=2)

    csv_path = _resolve_csv(csv_opt)
    rows = read_csv(csv_path)
    norm_query = normalize_title_key(title)

    matches: list[tuple[int, dict[str, str]]] = []
    for i, r in enumerate(rows, start=2):
        if normalize_title_key(r.get("标题", "")) == norm_query:
            matches.append((i, r))

    if len(matches) == 0:
        err_console.print(f"No match for title '{title}' (normalized: '{norm_query}')", style="red")
        raise typer.Exit(code=1)
    if len(matches) > 1:
        err_console.print(f"Multiple matches ({len(matches)}) for title. Data integrity issue.", style="red")
        for line, r in matches:
            err_console.print(f"  Row {line}: {r['标题']} ({r['链接']})")
        raise typer.Exit(code=1)

    line, match_row = matches[0]

    changes: dict[str, str] = {}
    for kv in set_fields:
        if "=" not in kv:
            err_console.print(f"Error: --set must be field=value, got '{kv}'", style="red")
            raise typer.Exit(code=2)
        field, _, value = kv.partition("=")
        field = field.strip()
        if field not in CSV_FIELDS:
            err_console.print(
                f"Error: unknown field '{field}'. Valid fields: {', '.join(CSV_FIELDS)}",
                style="red",
            )
            raise typer.Exit(code=2)
        changes[field] = value.strip()

    updated = dict(match_row)
    for field, value in changes.items():
        updated[field] = value

    errs: list[str] = []
    if "帖子发布日期" in changes:
        try:
            date.fromisoformat(changes["帖子发布日期"])
        except ValueError:
            errs.append(f"Invalid date '{changes['帖子发布日期']}'")
    if "平台" in changes:
        if changes["平台"] not in ("PC", "Switch", "PC/Switch"):
            errs.append(f"Invalid platform '{changes['平台']}'")
    if "推荐度" in changes:
        if changes["推荐度"] not in ("1", "2", "3", "4", "5"):
            errs.append(f"Invalid score '{changes['推荐度']}'")
    if "标题" in changes and not changes["标题"].strip():
        errs.append("Title cannot be empty")
    if "链接" in changes:
        if not changes["链接"].strip():
            errs.append("Link cannot be empty")
        elif not is_url_valid(changes["链接"]):
            errs.append(f"Invalid URL '{changes['链接'][:60]}'")

    if errs:
        for e in errs:
            err_console.print(f"Error: {e}", style="red")
        raise typer.Exit(code=1)

    remaining = [r for i, r in enumerate(rows, start=2) if i != line]
    final_rows = remaining + [updated]
    validation_errors = _validate_rows(final_rows)
    if validation_errors:
        for e in validation_errors:
            err_console.print(f"Validation error after update: {e}", style="red")
        raise typer.Exit(code=1)

    if dry_run:
        if json_output:
            print(
                json.dumps(
                    {"would_update": match_row["标题"], "changes": changes},
                    ensure_ascii=False,
                )
            )
        else:
            print(f"Would update row {line}: {match_row['标题']}")
            for field, value in changes.items():
                old_val = match_row.get(field, "")
                print(f"  {field}: '{old_val}' -> '{value}'")
        raise typer.Exit()

    if not yes:
        err_console.print(
            "Use --yes to confirm update (preview with --dry-run first)", style="red"
        )
        raise typer.Exit(code=1)

    write_csv(csv_path, final_rows)
    if json_output:
        print(
            json.dumps(
                {
                    "updated": match_row["标题"],
                    "changes": changes,
                    "total": len(final_rows),
                },
                ensure_ascii=False,
            )
        )
    else:
        print(f"Updated row {line}: {match_row['标题']}. Total: {len(final_rows)} rows.")


@app.command()
def export(
    date_filter: Optional[str] = typer.Option(None, "--date", help="Export entries for a specific date"),
    days: Optional[int] = typer.Option(None, "--days", help="Export entries from last N days"),
    query: Optional[str] = typer.Option(None, "--query", help="Export entries matching query"),
    platform: Optional[str] = typer.Option(None, "--platform", help="Filter by platform (PC/Switch/PC/Switch)"),
    latest_only: bool = typer.Option(False, "--latest", help="Export only latest date entries"),
    format: str = typer.Option("jsonl", "--format", help="Output format: jsonl, csv, md"),
    full: bool = typer.Option(False, "--full", help="Include 判断理由 field"),
    csv_opt: Optional[str] = CSV_OPT,
):
    rows = read_csv(_resolve_csv(csv_opt))
    if date_filter:
        rows = [r for r in rows if r.get("帖子发布日期", "") == date_filter]
    if days is not None:
        cutoff = date.today() - timedelta(days=days)
        rows = [
            r
            for r in rows
            if r.get("帖子发布日期", "")
            and date.fromisoformat(r["帖子发布日期"]) >= cutoff
        ]
    if query:
        q = query.lower()
        rows = [
            r
            for r in rows
            if q in r.get("标题", "").lower()
            or q in r.get("标签", "").lower()
            or q in r.get("用户备注", "").lower()
        ]
    if platform:
        rows = [r for r in rows if r.get("平台", "") == platform]
    if latest_only:
        d_info, _, _ = _latest_info(rows)
        rows = [r for r in rows if r.get("帖子发布日期", "") == d_info.isoformat()]
    output = _export_rows(rows, full=full, format=format)
    print(output)


@app.command("scrape-list")
def scrape_list_cmd(
    url: str = typer.Argument(..., help="Game list page URL to scrape"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Output as JSON (default: true)"),
):
    """Scrape a game list page; return clean and raw titles, URL, and dates.

    Example:
      gamer520 scrape-list https://www.gamer520.com/pcplay
      gamer520 scrape-list https://www.gamer520.com/pcplay/page/2
    """
    try:
        from .scraper import scrape_list
    except ImportError as e:
        err_console.print(f"Missing dependency: {e}", style="red")
        raise typer.Exit(code=1)

    try:
        results = scrape_list(url)
    except ValueError as e:
        err_console.print(str(e), style="red")
        raise typer.Exit(code=1)
    except Exception as e:
        err_console.print(f"Scrape failed: {e}", style="red")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for item in results:
            date_col = (item["date_text"] or "")[:20].ljust(20)
            print(f"{date_col} {item['title']} ({item['url']})")


@app.command("scrape-detail")
def scrape_detail_cmd(
    url: str = typer.Argument(..., help="Game detail page URL to scrape"),
    json_output: bool = typer.Option(True, "--json/--no-json", help="Output as JSON (default: true)"),
):
    """Scrape a game detail page; return cleaned title and description metadata.

    Example:
      gamer520 scrape-detail https://www.gamer520.com/113322.html
    """
    try:
        from .scraper import scrape_detail
    except ImportError as e:
        err_console.print(f"Missing dependency: {e}", style="red")
        raise typer.Exit(code=1)

    try:
        result = scrape_detail(url)
    except ValueError as e:
        err_console.print(str(e), style="red")
        raise typer.Exit(code=1)
    except Exception as e:
        err_console.print(f"Scrape failed: {e}", style="red")
        raise typer.Exit(code=1)

    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for k, v in result.items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    app()
