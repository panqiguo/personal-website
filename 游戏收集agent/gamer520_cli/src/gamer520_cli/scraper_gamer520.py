"""
Gamer520.com-specific scraping logic.

Edit this file when gamer520.com page structure changes.
Registered in scraper.py for domains matching 'gamer520.com'.

Page structure (as of 2026-06):
  List page — each game entry is an <article class="post post-grid post-NNNNN ...">
    - Title/URL: <h2 class="entry-title"><a href="...NNNNN.html" title="游戏名">
    - Date:      <time datetime="YYYY-MM-DDTHH:MM:SS+08:00"> (machine-readable, no parsing of relative text needed)

  Detail page — structured info block in the post body:
    - Release date: text pattern "发行日期: YYYY 年 M 月 D 日"
    - Genres:       text pattern "游戏类型: ..."
    - Description:  paragraphs in the content area (class containing "entry-content" etc.)
"""
import re
from datetime import date, datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_TIMEOUT = 15
_TZ_CST = timezone(timedelta(hours=8))

_SKIP_IN_DESC = re.compile(
    r"发行日期|游戏类型|文件大小|官方网站|语言|截图|下载|安装|"
    r"系统需求|处理器|内存|显卡|存储|DirectX|解压|链接",
    re.IGNORECASE,
)

_BOILERPLATE_START = re.compile(
    r"用\s*PC\s*的用户|用手机的用户|获取地址|立即获取|"
    r"本页面顶部|本页面下面|小站为非商业性|资源信息均转载自互联网|"
    r"小站没有充值|没有售卖会员|没有购买[,，、\s]*打赏[,，、\s]*捐赠",
    re.IGNORECASE,
)

# Site editorial/utility categories that can be pinned into game listing pages
# but are not standalone games and must never become scan candidates.
_NON_GAME_ARTICLE_CLASSES = {"category-shen"}


def parse_site_title(raw_title: str) -> str:
    """Return the game title before Gamer520's pipe-delimited package metadata."""
    title = raw_title.split("|", 1)[0]
    return re.sub(r"\s+", " ", title).strip()


def _fetch(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=_TIMEOUT)
    resp.raise_for_status()
    return BeautifulSoup(resp.content, "html.parser")


def scrape_list(url: str) -> list[dict]:
    """
    Return [{title, url, date, date_text}, ...] from a gamer520 game list page.

    Iterates <article class="post post-grid ..."> elements — one per game entry.
    The <time datetime="..."> attribute provides an absolute ISO 8601 timestamp;
    we parse it to YYYY-MM-DD without relying on relative Chinese text.

    Returns field 'date' as 'YYYY-MM-DD' string (None if unparseable).
    Returns field 'date_text' as raw displayed text (e.g. '2天前') for reference.
    """
    soup = _fetch(url)
    results: list[dict] = []

    for article in soup.find_all("article", class_=re.compile(r"\bpost\b")):
        article_classes = set(article.get("class") or [])
        if article_classes & _NON_GAME_ARTICLE_CLASSES:
            continue

        # Title + URL from <h2 class="entry-title"><a ...>
        h2 = article.find("h2", class_="entry-title")
        if not h2:
            continue
        a = h2.find("a", href=True)
        if not a:
            continue

        href = str(a["href"]).strip()
        raw_title = (a.get("title") or a.get_text(separator=" ", strip=True)).strip()
        title = parse_site_title(raw_title)
        if not title or not re.search(r"/\d{4,}\.html$", href):
            continue

        # Date from <time datetime="YYYY-MM-DDTHH:MM:SS+08:00">
        parsed_date: str | None = None
        date_text = ""
        time_el = article.find("time", datetime=True)
        if time_el:
            raw_dt = str(time_el["datetime"])
            date_text = time_el.get_text(strip=True)
            # Strip leading icon text (e.g. " 1小时前" has a leading fa-icon)
            date_text = re.sub(r"^\s*\S+\s*", "", date_text).strip() or date_text.strip()
            try:
                dt = datetime.fromisoformat(raw_dt)
                parsed_date = dt.date().isoformat()
            except ValueError:
                pass

        results.append({
            "title": title,
            "raw_title": raw_title,
            "url": href,
            "date": parsed_date,
            "date_text": date_text,
        })

    return results


def scrape_detail(url: str) -> dict:
    """
    Return {title, release_date, genres, description} from a gamer520 game detail page.

    The detail page contains a structured info block with:
      发行日期: YYYY 年 M 月 D 日
      游戏类型: tag1 tag2 ...
    followed by description paragraphs in the content area.
    """
    soup = _fetch(url)
    full_text = soup.get_text(separator="\n")

    raw_title = _extract_title(soup)
    description = _extract_description(soup)
    return {
        "title": parse_site_title(raw_title),
        "raw_title": raw_title,
        "game_release_date": _extract_release_date(full_text),
        "genres": _extract_genres(full_text),
        "description": description,
        "description_quality": _description_quality(description),
    }


def _extract_title(soup: BeautifulSoup) -> str:
    if h1 := soup.find("h1"):
        return h1.get_text(strip=True)
    if h2 := soup.find("h2"):
        return h2.get_text(strip=True)
    if og := soup.find("meta", {"property": "og:title"}):
        return (og.get("content") or "").strip()
    return ""


def _extract_release_date(text: str) -> str:
    # e.g. "发行日期: 2026 年 5 月 19 日" or "发行日期：2026年5月19日"
    m = re.search(
        r"发行[日时]?期\s*[：:]\s*(\d{4})\s*年\s*(\d{1,2})\s*月(?:\s*(\d{1,2})\s*日)?",
        text,
    )
    if m:
        y, mo, d = m.group(1), m.group(2).zfill(2), (m.group(3) or "01").zfill(2)
        return f"{y}-{mo}-{d}"
    m = re.search(r"发行[日时]?期\s*[：:]\s*(\d{4})", text)
    return m.group(1) if m else ""


def _extract_genres(text: str) -> str:
    for pattern in [r"游戏类型\s*[：:]\s*(.+)", r"类型\s*[：:]\s*(.+)"]:
        m = re.search(pattern, text)
        if m:
            return m.group(1).strip().split("\n")[0].strip()
    return ""


def _extract_description(soup: BeautifulSoup) -> str:
    content = (
        soup.find("div", class_=re.compile(r"entry.content|post.content|article.content|single.content", re.I))
        or soup.find("div", class_=re.compile(r"the.content|post.body|content.body", re.I))
        or soup.find("article")
    )
    if content:
        chunks: list[str] = []
        total_chars = 0
        seen: set[str] = set()
        for el in content.find_all(["p", "li"]):
            t = _clean_description_text(el.get_text(separator=" ", strip=True))
            if _is_meaningful_description(t) and t not in seen:
                chunks.append(t)
                seen.add(t)
                total_chars += len(t)
            if total_chars >= 1500 or len(chunks) >= 12:
                break
        if chunks:
            return " ".join(chunks)

    for attrs in (
        {"property": "og:description"},
        {"name": "description"},
    ):
        if meta := soup.find("meta", attrs):
            text = _clean_description_text(str(meta.get("content") or ""))
            if _is_meaningful_description(text):
                return text

    # Fallback: meaningful lines from full text
    lines = [
        _clean_description_text(line)
        for line in soup.get_text(separator="\n").split("\n")
    ]
    good = [line for line in lines if _is_meaningful_description(line)]
    return " ".join(good[:4])


def _clean_description_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if match := _BOILERPLATE_START.search(text):
        text = text[:match.start()].strip(" |。，,;|")
    return text


def _is_meaningful_description(text: str) -> bool:
    return len(text) > 15 and not _SKIP_IN_DESC.search(text) and not _BOILERPLATE_START.search(text)


def _description_quality(description: str) -> str:
    if not description:
        return "missing"
    if len(description) < 80:
        return "limited"
    return "sufficient"
