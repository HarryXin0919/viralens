"""shared_markers single-source + compare_form.off_tag + creators.validate_creators."""
import compare_form
from creators import validate_creators
from shared_markers import OFF_MARKERS_COMPARE, OFF_MARKERS_FULL


def test_markers_intentional_divergence():
    # FULL(特征工程)含 livestream / 联名;COMPARE(对比报告)故意更保守、去掉它们。
    assert "livestream" in OFF_MARKERS_FULL["EN"]
    assert "live stream" in OFF_MARKERS_FULL["EN"]
    assert "livestream" not in OFF_MARKERS_COMPARE["EN"]
    assert "联名" in OFF_MARKERS_FULL["商单"]
    assert "联名" not in OFF_MARKERS_COMPARE["商单"]


def test_compare_off_tag_youtube_scans_title_only():
    yt = {"platform": "youtube", "title": "My video", "description": "interview podcast sponsored"}
    assert compare_form.off_tag(yt) == ""             # 只扫 title,描述里的词不算
    yt2 = {"platform": "youtube", "title": "sponsored haul", "description": ""}
    assert compare_form.off_tag(yt2) == "EN"          # title 命中 sponsored(EN 类)


def test_compare_off_tag_does_not_flag_livestream():
    v = {"platform": "youtube", "title": "secretly in a livestream challenge", "description": ""}
    assert compare_form.off_tag(v) == ""              # COMPARE 口径不把 livestream 当偏题


def test_validate_creators_ok():
    good = [
        {"name": "A", "alias": "a", "zone": "知识", "platform": "bilibili", "uid": 1},
        {"name": "B", "alias": "b", "zone": "Ent", "platform": "youtube", "channel": "@b"},
    ]
    assert validate_creators(good) == []


def test_validate_creators_collects_all_problems():
    bad = [
        {"name": "X", "zone": "知识", "platform": "bilibili"},                 # 缺 alias
        {"name": "Y", "alias": "y", "zon": "typo", "platform": "bilibili"},    # 拼错 zon + 缺 zone
        {"name": "Z", "alias": "y", "zone": "z", "platform": "youtube"},       # alias 重复 + youtube 缺 channel
    ]
    blob = " ".join(validate_creators(bad))
    assert "缺必填字段 'alias'" in blob
    assert "未知字段 'zon'" in blob
    assert "缺必填字段 'zone'" in blob
    assert "重复" in blob
    assert "channel" in blob


def test_validate_creators_empty():
    assert validate_creators([]) == ["CREATORS 必须是非空列表"]
