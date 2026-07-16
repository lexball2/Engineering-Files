from types import SimpleNamespace

from backend.api.image_assets import _asset_matches_query, _limit_tags, _merge_tags, _rank_assets, _search_terms


def test_image_asset_tags_are_limited_to_five():
    assert _limit_tags("塞尔达, 林克, 荒野, 游戏, 截图, 风景") == "塞尔达, 林克, 荒野, 游戏, 截图"


def test_image_asset_tags_are_deduplicated():
    assert _limit_tags("Link, link, Zelda") == "Link, Zelda"


def test_manual_tag_is_kept_first_when_merging_tags():
    assert _merge_tags("实拍", "建筑, 城市, 夜景, 蓝色, 路灯", limit=5) == "实拍, 建筑, 城市, 夜景, 蓝色"


def test_multi_keyword_query_can_use_common_separators():
    assert _search_terms("塞尔达 林克,荒野、截图") == ["塞尔达", "林克", "荒野", "截图"]


def test_unrelated_image_asset_does_not_match_low_score_query():
    asset = SimpleNamespace(filename="工作汇报.png", description="办公室会议截图", tags="文档, 报告")

    assert not _asset_matches_query(asset, ["塞尔达", "林克"], 0.2)


def test_asset_matches_when_all_keywords_are_in_metadata():
    asset = SimpleNamespace(filename="zelda.png", description="塞尔达传说 林克 站在山顶", tags="游戏, 荒野")

    assert _asset_matches_query(asset, ["塞尔达", "林克"], 0.0)


def test_download_sort_orders_by_total_download_count():
    low = SimpleNamespace(id="low", download_count=1, last_downloaded_at=None, created_at=None)
    high = SimpleNamespace(id="high", download_count=10, last_downloaded_at=None, created_at=None)

    assert _rank_assets([low, high], {}, {}, unused_first=True, sort_mode="downloads") == [high, low]
