"""B站解析器"""

import re
from typing import Dict, Any

import httpx

from ._utils import _headers, _follow_redirects, _make_info, _empty_result, _ok


DOMAINS = ["b23.tv", "www.bilibili.com", "m.bilibili.com", "bilibili.com"]


async def parse(url: str) -> Dict[str, Any]:
    url = url.rstrip("/")
    if "b23.tv" in url:
        url = await _follow_redirects(url)

    m = re.search(r"(BV[\w]{10})", url)
    if not m:
        return _empty_result("无法提取 B 站视频 BV 号")
    bvid = m.group(1)

    api = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    headers = _headers(referer="https://www.bilibili.com/")
    try:
        async with httpx.AsyncClient(timeout=15, verify=False) as c:
            r = await c.get(api, headers=headers)
            data = r.json()
    except Exception:
        return _empty_result("B 站 API 请求失败")

    if data.get("code") != 0:
        return _empty_result(data.get("message", "B 站解析失败"))

    vdata = data.get("data", {})
    cid = vdata.get("cid", 0)
    if not cid:
        pages = vdata.get("pages", [])
        cid = pages[0]["cid"] if pages else 0

    play_api = f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn=80&fnval=1"
    try:
        async with httpx.AsyncClient(timeout=15, verify=False) as c:
            r = await c.get(play_api, headers=headers)
            play_data = r.json()
    except Exception:
        return _empty_result("B 站播放地址获取失败")

    durl = play_data.get("data", {}).get("durl", [])
    video_url = durl[0]["url"] if durl else ""

    stat = vdata.get("stat", {})
    owner = vdata.get("owner", {})
    pic = vdata.get("pic", "")

    # B站使用 bl:// 前缀，下载时走 yt-dlp（CDN 防盗链严格，直接下载容易 403）
    return _ok(_make_info(
        id=bvid, platform="bilibili",
        title=vdata.get("title", "") or "无标题",
        author=owner.get("name", "未知作者"),
        author_avatar=owner.get("face", ""),
        cover=pic if pic.startswith("http") else f"https:{pic}" if pic.startswith("//") else pic,
        duration=vdata.get("duration", 0),
        video_url=f"bl://{bvid}",
        video_url_no_watermark=video_url,
        create_time=vdata.get("pubdate", 0),
        digg_count=stat.get("like", 0),
        comment_count=stat.get("reply", 0),
        share_count=stat.get("share", 0),
    ))
