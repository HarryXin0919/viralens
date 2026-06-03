"""features.extract / off_tag — pure metric+feature logic, no network."""
import time

from features import extract, off_tag


def _vid(**kw):
    base = {
        "title": "为什么天是蓝的", "description": "",
        "created_ts": time.time() - 86400 * 10,
        "play": 1_000_000, "duration_sec": 600, "comment": 2000,
        "danmaku": 5000, "platform": "bilibili",
    }
    base.update(kw)
    return base


def test_extract_basic_metrics():
    f = extract(_vid(), time.time())
    assert f["play"] == 1_000_000
    assert f["play_per_day"] > 0
    assert f["comment_per_10k"] > 0
    assert f["dur_bucket"] == "中 5-12min"
    assert f["has_question"] is False
    assert f["has_curiosity"] is True          # 标题含「为什么」


def test_off_format_bilibili_scans_description():
    # B 站扫 title + description;描述里的商单词应判偏题
    f = extract(_vid(title="正常标题", description="本视频与某品牌合作"), time.time())
    assert f["off_format"] is True


def test_off_format_youtube_title_only():
    # YouTube 简介塞满 hashtag,只扫 title;描述里的 sponsored 不算
    f = extract(_vid(platform="youtube", title="My normal video", description="sponsored by X"), time.time())
    assert f["off_format"] is False
    f2 = extract(_vid(platform="youtube", title="sponsored haul", description=""), time.time())
    assert f2["off_format"] is True


def test_off_tag_labels():
    assert off_tag("和某品牌合作", "") == "商单"
    assert off_tag("我的 vlog 日常", "") == "vlog"
    assert off_tag("正经硬核科普", "") == ""
