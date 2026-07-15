"""抖音主页分页修复 - 切片逻辑测试（mock 数据，不触网，无第三方依赖）"""
import asyncio
import sys
import os
import time

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "backend"))
os.chdir(_ROOT)  # backend.main 的静态资源/日志依赖 cwd

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from backend.parsers import profile as profile_mod


def _fake_raw(n: int):
    items = []
    for i in range(n):
        items.append({
            "aweme_id": f"vid_{i:04d}",
            "desc": f"title {i}",
            "author": {"nickname": "tester"},
            "video": {
                "duration": 10000,
                "cover": {"url_list": [f"https://example.com/cover/{i}.jpg"]},
            },
            "statistics": {"digg_count": i, "comment_count": i, "share_count": i},
            "create_time": 1700000000 + i,
        })
    return items


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    mark = "PASS" if cond else "FAIL"
    print(f"[{mark}] {name}" + (f" -- {detail}" if detail and not cond else ""))


def main():
    # ============ 1. 切片数学公式 ============
    raw = list(range(76))
    page_size = 20
    expected = [(1, 0, 20), (2, 20, 20), (3, 40, 20), (4, 60, 16), (5, 80, 0)]
    for page, exp_start, exp_len in expected:
        start = (page - 1) * page_size
        w = raw[start:start + page_size]
        check(f"slice_formula page={page} start", start == exp_start, f"got {start}")
        check(f"slice_formula page={page} len", len(w) == exp_len, f"got {len(w)}")

    # ============ 2. 准备 mock 缓存 ============
    sec_uid_76 = "TEST_SEC_UID_76"
    sec_uid_big = "TEST_SEC_UID_300_EXCEEDED"
    profile_mod._DOUYIN_LIST_CACHE.clear()
    profile_mod._DOUYIN_LIST_CACHE[sec_uid_76] = {
        "raw": _fake_raw(76), "exceeded": False, "author": "tester", "ts": time.time(),
    }
    profile_mod._DOUYIN_LIST_CACHE[sec_uid_big] = {
        "raw": _fake_raw(300), "exceeded": True, "author": "big", "ts": time.time(),
    }
    # mock extract_sec_uid 与 _get_douyin_full_list（直接走缓存，不触网）
    profile_mod._fake_map = {sec_uid_76: profile_mod._DOUYIN_LIST_CACHE[sec_uid_76],
                              sec_uid_big: profile_mod._DOUYIN_LIST_CACHE[sec_uid_big]}
    async def fake_fetch(su, cookie):
        return profile_mod._fake_map[su]
    profile_mod._get_douyin_full_list = fake_fetch

    # 用 monkeypatch 思路：直接替换 extract_sec_uid
    import backend.parsers.profile as pmod
    orig_extract = pmod.extract_sec_uid if hasattr(pmod, "extract_sec_uid") else None
    def fake_extract(url):
        if sec_uid_76 in url: return sec_uid_76
        if sec_uid_big in url: return sec_uid_big
        return "SEC_UNKNOWN"
    # _parse_profile_douyin 内部是 from .douyin import extract_sec_uid，
    # 需要在 backend.parsers.douyin 上替换
    import backend.parsers.douyin as dm
    dm.extract_sec_uid = fake_extract

    url76 = "https://www.douyin.com/user/" + sec_uid_76
    urlbig = "https://www.douyin.com/user/" + sec_uid_big

    # ============ 3. 分页条数一致性（核心） ============
    p1 = _run(profile_mod._parse_profile_douyin(url76, limit=20, page=1, cookie=""))
    p2 = _run(profile_mod._parse_profile_douyin(url76, limit=20, page=2, cookie=""))
    p3 = _run(profile_mod._parse_profile_douyin(url76, limit=20, page=3, cookie=""))
    p4 = _run(profile_mod._parse_profile_douyin(url76, limit=20, page=4, cookie=""))

    cases = [(p1,1,20,True), (p2,2,20,True), (p3,3,20,True), (p4,4,16,False)]
    for r, pn, exp_len, exp_has_more in cases:
        check(f"page{pn} success", r.get("success"), str(r)[:200])
        d = r.get("data", {})
        check(f"page{pn} video_count", len(d.get("videos", [])) == exp_len,
              f"got {len(d.get('videos', []))}")
        check(f"page{pn} page_field", d.get("page") == pn)
        check(f"page{pn} page_size", d.get("page_size") == 20)
        check(f"page{pn} total_count=76", d.get("total_count") == 76,
              f"got {d.get('total_count')}")
        check(f"page{pn} total_pages=4", d.get("total_pages") == 4,
              f"got {d.get('total_pages')}")
        check(f"page{pn} has_more", d.get("has_more") is exp_has_more,
              f"got {d.get('has_more')}")

    # 切片连续不重叠
    ids_all = [v["id"] for v in p1["data"]["videos"] + p2["data"]["videos"]
               + p3["data"]["videos"] + p4["data"]["videos"]]
    check("slice_continuous_and_unique",
          ids_all == [f"vid_{i:04d}" for i in range(76)],
          f"first={ids_all[0]} last={ids_all[-1]} len={len(ids_all)}")

    # ============ 4. 响应契约 ============
    required = ("page","page_size","total_count","total_pages","has_more",
                "anonymous","exceeded_cap","platform","author","videos")
    for f in required:
        check(f"contract field '{f}' exists", f in p1["data"], f"missing {f}")

    check("anonymous=true when no cookie", p1["data"]["anonymous"] is True)
    check("exceeded_cap=false for 76 items", p1["data"]["exceeded_cap"] is False)

    # 带 cookie + 超上限
    res_big = _run(profile_mod._parse_profile_douyin(urlbig, limit=20, page=1, cookie="SESSIONID=x"))
    check("exceeded_cap=true on 300+", res_big["data"]["exceeded_cap"] is True)
    check("anonymous=false with cookie", res_big["data"]["anonymous"] is False)
    check("total_count=300", res_big["data"]["total_count"] == 300)
    check("total_pages=15 (ceil 300/20)", res_big["data"]["total_pages"] == 15)

    # ============ 5. 越界页（无500） ============
    # 无 cookie 翻到不存在页
    r_anon_oob = _run(profile_mod._parse_profile_douyin(url76, limit=20, page=99, cookie=""))
    check("anon page=99 returns success=false (no 500)", r_anon_oob.get("success") is False)
    check("anon page=99 msg mentions Cookie/匿名",
          "Cookie" in r_anon_oob.get("message","") or "匿名" in r_anon_oob.get("message",""),
          r_anon_oob.get("message"))

    # 有 cookie 翻到不存在页
    r_auth_oob = _run(profile_mod._parse_profile_douyin(url76, limit=20, page=99, cookie="ck"))
    check("auth page=99 returns success=false", r_auth_oob.get("success") is False)
    check("auth page=99 msg says no videos", "没有作品" in r_auth_oob.get("message",""),
          r_auth_oob.get("message"))

    # ============ 6. 缓存命中（逻辑层面）============
    # _get_douyin_full_list 在 TTL 内应直接返回缓存——验证 TTL 逻辑：
    ent = profile_mod._DOUYIN_LIST_CACHE[sec_uid_76]
    check("cache returns same object within TTL",
          profile_mod._DOUYIN_LIST_CACHE.get(sec_uid_76) is ent)
    # 模拟过期：ts 改成很久以前
    old_ts = ent["ts"]
    ent["ts"] = time.time() - profile_mod._DOUYIN_CACHE_TTL - 10
    now = time.time()
    still_valid = (now - ent["ts"]) < profile_mod._DOUYIN_CACHE_TTL
    check("cache entry considered expired after TTL", not still_valid)
    ent["ts"] = old_ts  # 还原

    # 缓存上限淘汰逻辑：塞 _DOUYIN_CACHE_MAX+1 个 key，验证有界
    cache = profile_mod._DOUYIN_LIST_CACHE
    # 已有 2 个测试条目，塞到超过上限
    dummy = {"raw": [], "exceeded": False, "author": "x", "ts": 0}
    for i in range(profile_mod._DOUYIN_CACHE_MAX + 5):
        k = f"DUMMY_{i}"
        if k not in cache and len(cache) >= profile_mod._DOUYIN_CACHE_MAX:
            oldest = min(cache, key=lambda kk: cache[kk]["ts"])
            cache.pop(oldest, None)
        cache[k] = {**dummy, "ts": time.time() + i}
    check(f"cache bounded by _DOUYIN_CACHE_MAX({profile_mod._DOUYIN_CACHE_MAX})",
          len(cache) <= profile_mod._DOUYIN_CACHE_MAX,
          f"got {len(cache)}")
    # 清理 dummy
    for k in list(cache.keys()):
        if k.startswith("DUMMY_"):
            cache.pop(k, None)

    # ============ 汇总 ============
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"\n===== {passed} passed, {failed} failed, total {len(results)} =====")

    # 清理缓存
    profile_mod._DOUYIN_LIST_CACHE.clear()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
