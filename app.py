def youtube_search(keyword: str, api_key: str, hours: int = 24):
    """최근 hours 내 업로드된 유튜브 영상(숏츠 포함)을 조회하고, 키워드 매칭 여부까지 반환."""
    if not api_key:
        return pd.DataFrame(), "환경변수 YOUTUBE_API_KEY가 없습니다."

    published_after = (dt.datetime.utcnow() - dt.timedelta(hours=hours)).isoformat("T") + "Z"

    # 내부 헬퍼: 검색 요청
    def _search_once(q):
        url = "https://www.googleapis.com/youtube/v3/search"
        return requests.get(url, params={
            "part": "snippet",
            "q": q,
            "type": "video",
            "order": "date",
            "maxResults": 25,
            "publishedAfter": published_after,
            "regionCode": "KR",
            "relevanceLanguage": "ko",
            "key": api_key,
        }, timeout=20)

    # 일반 검색 + 해시태그 검색 병합
    r = _search_once(keyword)
    r_hash = _search_once(f"#{keyword}")
    items = []
    if r.status_code == 200:
        items += r.json().get("items", [])
    if r_hash.status_code == 200:
        items += r_hash.json().get("items", [])

    video_ids = list({it.get("id", {}).get("videoId") for it in items if it.get("id", {}).get("videoId")})
    if not video_ids:
        return pd.DataFrame(), "최근 업로드 결과 없음"

    # 상세 정보 조회
    url2 = "https://www.googleapis.com/youtube/v3/videos"
    params2 = {
        "part": "statistics,snippet,contentDetails",
        "id": ",".join(video_ids),
        "key": api_key,
    }
    r2 = requests.get(url2, params=params2, timeout=20)
    if r2.status_code != 200:
        return pd.DataFrame(), f"YOUTUBE videos 오류: {r2.status_code} {r2.text[:200]}"

    rows = []
    for it in r2.json().get("items", []):
        stats = it.get("statistics", {}) or {}
        snip = it.get("snippet", {}) or {}
        cd = it.get("contentDetails", {}) or {}

        # 길이 → 숏츠 판별
        duration_iso = cd.get("duration")
        try:
            duration_sec = int(isodate.parse_duration(duration_iso).total_seconds()) if duration_iso else None
        except Exception:
            duration_sec = None
        is_shorts = duration_sec is not None and duration_sec <= 60

        # 키워드 메타데이터 매칭
        title = snip.get("title") or ""
        desc = snip.get("description") or ""
        tags = snip.get("tags", [])
        text_blob = " ".join([title, desc] + tags).lower()
        kw = keyword.lower()
        matched_in_meta = (kw in text_blob) or (("#"+kw) in text_blob)

        rows.append({
            "videoId": it.get("id"),
            "title": title,
            "channel": snip.get("channelTitle"),
            "publishedAt": snip.get("publishedAt"),
            "viewCount": int(stats.get("viewCount", 0)) if stats.get("viewCount") else 0,
            "durationSec": duration_sec,
            "isShorts": is_shorts,
            "matchedInMeta": matched_in_meta,
            "url": f"https://www.youtube.com/watch?v={it.get('id')}"
        })

    df = pd.DataFrame(rows).sort_values("viewCount", ascending=False)
    return df, None
