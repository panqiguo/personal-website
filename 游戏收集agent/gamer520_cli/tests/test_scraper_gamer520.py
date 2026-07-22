from bs4 import BeautifulSoup

from gamer520_cli.scraper_gamer520 import (
    _description_quality,
    _extract_description,
    parse_site_title,
    scrape_list,
)


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_parse_site_title_removes_pipe_metadata():
    raw = "银白钢铁伊克斯1+2双重收藏辑 Gunvolt Chronicles|官方中文|NSZ|"
    assert parse_site_title(raw) == "银白钢铁伊克斯1+2双重收藏辑 Gunvolt Chronicles"


def test_extract_description_truncates_download_boilerplate():
    soup = _soup(
        """
        <article>
          <p>在山城里驾驶送货，边接单边探索居民与小镇隐藏的故事。
             用PC的用户=获取地址 在本页面顶部 右边可看见 [立即获取]</p>
        </article>
        """
    )
    description = _extract_description(soup)
    assert description == "在山城里驾驶送货，边接单边探索居民与小镇隐藏的故事"
    assert "获取地址" not in description


def test_extract_description_uses_meta_when_article_is_only_advertising():
    soup = _soup(
        """
        <html>
          <head>
            <meta name="description" content="管理一支电竞战队，通过选手招募、训练、排兵布阵和赛事经营争夺联赛冠军。">
          </head>
          <body><article><p>小站为非商业性盈利网站，资源信息均转载自互联网。</p></article></body>
        </html>
        """
    )
    assert _extract_description(soup).startswith("管理一支电竞战队")


def test_description_quality_marks_short_or_missing_content():
    assert _description_quality("") == "missing"
    assert _description_quality("一段很短的介绍。") == "limited"
    assert _description_quality("这是一段足够长的游戏介绍。" * 10) == "sufficient"


def test_scrape_list_skips_non_game_editorial_posts(monkeypatch):
    soup = _soup(
        """
        <article class="post post-grid category-shen category-pcplay category-gameswitch">
          <h2 class="entry-title"><a href="https://www.gamer520.com/117792.html"
            title="您有2条未读消息 不看一下吗? 嘿嘿~[顶置2天]">公告</a></h2>
          <time datetime="2026-07-11T11:00:44+08:00">1天前</time>
        </article>
        <article class="post post-grid category-pcplay">
          <h2 class="entry-title"><a href="https://www.gamer520.com/117850.html"
            title="瑞奇与叮当 时空跳转|豪华中文|">游戏</a></h2>
          <time datetime="2026-07-12T09:00:00+08:00">3小时前</time>
        </article>
        """
    )
    monkeypatch.setattr(
        "gamer520_cli.scraper_gamer520._fetch", lambda _url: soup
    )

    result = scrape_list("https://www.gamer520.com/pcplay")

    assert [item["title"] for item in result] == ["瑞奇与叮当 时空跳转"]
