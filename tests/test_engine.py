"""scan_signals.spearman, build_report formatters, runtime paths,
and fetch_bilibili (parse_length / record / errors / pagination) — no network."""
import asyncio

import pytest

import build_report as br
import fetch_bilibili as fb
import runtime
from scan_signals import spearman


# ----------------------------- spearman -----------------------------
def test_spearman_perfect_positive():
    r = spearman([1, 2, 3, 4, 5, 6], [10, 20, 30, 40, 50, 60])
    assert r is not None and r > 0.99


def test_spearman_perfect_negative():
    r = spearman([1, 2, 3, 4, 5, 6], [60, 50, 40, 30, 20, 10])
    assert r is not None and r < -0.99


def test_spearman_small_sample_is_none():
    assert spearman([1, 2, 3], [3, 2, 1]) is None     # n < 6 → 信号太弱,返回 None


# ----------------------------- build_report formatters -----------------------------
def test_fmt_play():
    assert br.fmt_play(814_0000) == "814.0万"
    assert br.fmt_play(150_000_000) == "1.50亿"
    assert br.fmt_play(None) == "-"


def test_fmt_dur():
    assert br.fmt_dur(125) == "2:05"
    assert br.fmt_dur(None) == "-"


def test_video_url():
    assert "bilibili.com/video/BV1xx" in br.video_url({"platform": "bilibili", "bvid": "BV1xx"})
    assert "youtube.com/watch?v=abc" in br.video_url({"platform": "youtube", "vid": "abc"})
    assert br.video_url({"platform": "bilibili"}) == ""   # 没 id


# ----------------------------- runtime paths (source mode) -----------------------------
def test_runtime_source_paths():
    assert runtime.FROZEN is False
    assert runtime.DATA.name == "data"
    assert runtime.REPORTS.name == "reports"


# ----------------------------- fetch_bilibili -----------------------------
def test_parse_length():
    assert fb.parse_length("12:34") == 12 * 60 + 34
    assert fb.parse_length("1:02:03") == 3723
    assert fb.parse_length("") == 0


def test_to_record_shape():
    rec = fb._to_record({"name": "N", "alias": "a", "zone": "z"},
                        {"bvid": "BV1", "title": "t", "play": 100, "created": 0, "length": "1:00"})
    assert rec["platform"] == "bilibili" and rec["bvid"] == "BV1" and rec["vid"] == "BV1"
    assert rec["duration_sec"] == 60 and rec["play"] == 100


def test_fetch_creator_missing_sessdata_raises():
    with pytest.raises(fb.BilibiliError):
        asyncio.run(fb.fetch_creator({"name": "N", "alias": "a", "zone": "z", "uid": 1}, ""))


def test_fetch_creator_missing_uid_raises():
    with pytest.raises(fb.BilibiliError):
        asyncio.run(fb.fetch_creator({"name": "N", "alias": "a", "zone": "z"}, "fake-sess"))


class _FakeUser:
    """A user.User stand-in whose get_videos returns canned pages (no network)."""

    def __init__(self, total):
        self.total = total

    async def get_videos(self, ps, pn):
        # 忠实模拟 B 站窗口语义:offset 由**本次请求的 ps** 决定([(pn-1)*ps, pn*ps)),
        # 不是常量 PAGE_MAX —— 之前用 PAGE_MAX 算,恰好掩盖了"末页改小 ps 导致窗口错位"的 bug
        start = (pn - 1) * ps
        n = max(0, min(ps, self.total - start))
        vlist = [{"bvid": f"BV{start + i}", "title": f"v{start + i}", "play": i, "created": 0}
                 for i in range(n)]
        return {"list": {"vlist": vlist}, "page": {"count": self.total}}


def test_fetch_creator_paginates_beyond_one_page(monkeypatch):
    # 创作者有 120 条;num=120 必须翻 3 页(50+50+20)——旧版只取第一页会漏 70 条
    monkeypatch.setattr(fb.user, "User", lambda uid, credential=None: _FakeUser(120))
    vids = asyncio.run(fb.fetch_creator({"name": "N", "alias": "a", "zone": "z", "uid": 1}, "sess", num=120))
    assert len(vids) == 120
    assert len({v["vid"] for v in vids}) == 120   # 分页窗口不重叠:120 条各不相同、无重复无遗漏


def test_fetch_creator_stops_when_no_more(monkeypatch):
    # 创作者只有 30 条,却要 100 → 只拿到 30,不死循环
    monkeypatch.setattr(fb.user, "User", lambda uid, credential=None: _FakeUser(30))
    vids = asyncio.run(fb.fetch_creator({"name": "N", "alias": "a", "zone": "z", "uid": 1}, "sess", num=100))
    assert len(vids) == 30
