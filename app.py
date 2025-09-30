import os
import json
import datetime as dt
import requests
import pandas as pd
import streamlit as st
import time, random
import urllib.parse
import streamlit.components.v1 as components  # (참고: Trends는 보통 iframe 차단됨)
import isodate  # ISO8601 duration -> seconds

# ---- Config ----
st.set_page_config(page_title="키워드 급증 원인 체크", layout="centered")

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")

st.title("🔎 키워드 급증 원인 체크 (최강콘팀용)")
st.caption("입력한 키워드에 대해 최근 24~72시간(또는 7일) 내 외부 신호(YouTube / Google Trends / 네이버 데이터랩)를 조회해 잠정 원인을 보여줍니다.")

# ---- Inputs (ALTERNATIVE) ----
with st.form("controls"):
    r1c1, r1c2, r1c3 = st.columns([4, 1.2, 1.2])
    keyword = r1c1.text_input("키워드 입력", placeholder="키워드를 입력해주세요")
    hours_window = r1c2.selectbox("윈도우(시간)", [24, 48, 72, 168], index=0)
    region = r1c3.selectbox("지역", ["KR", "US", "JP", "GLOBAL"], index=0)

    # 다음 줄: 오른쪽 정렬 버튼
    r2c1, r2c2, r2c3, r2c4 = st.columns([4, 1.2, 1.2, 1.2])
    with r2c4:
        run_btn = st.form_submit_button("분석 실행", use_container_width=True, type="primary")

# ---- Helpers ----
def human_ts(ts: dt.datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M")

def youtube_search(keyword: str, api_key: str, hours: int = 24):
    """최근 hours 내 업로드된 유튜브 영상(숏츠 포함)을 조회하고, 키워드 매칭 여부까지 반환."""
    if not api_key:
        return pd.DataFrame(), "환경변수 YOUTUBE_API_KEY가 없습니다."

    published_after = (dt.datetime.utcnow() - dt.timedelta(hours=hours)).isoformat("T") + "Z"

    # 내부 헬퍼: 검색 요청 (지역/언어 힌트 + 최신순)
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

    # 상세 정보 조회(통계 + 길이로 숏츠 판별)
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

        # 키워드 메타데이터 매칭(제목/설명/태그)
        title = snip.get("title") or ""
        desc = snip.get("description") or ""
        tags = snip.get("tags", [])
        text_blob = " ".join([title, desc] + tags).lower()
        kw = keyword.lower()
        matched_in_meta = (kw in text_blob) or (("#" + kw) in text_blob)

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

@st.cache_data(show_spinner=False, ttl=1800)  # 30분 캐시로 과도한 요청 방지
def _fetch_trends_cached(keyword: str, region: str):
    # 내부 캐시용 함수: 성공시 (df, None), 실패시 (빈 DF, err_msg) 반환
    try:
        from pytrends.request import TrendReq
    except Exception as e:
        return pd.DataFrame(), f"pytrends 불러오기 실패: {e}"

    geo = "" if region == "GLOBAL" else region

    # (선택) 프록시: Secrets에 PROXY_HTTP/PROXY_HTTPS 넣어두면 사용
    proxies = {}
    if os.getenv("PROXY_HTTP"):
        proxies["http"] = os.getenv("PROXY_HTTP")
    if os.getenv("PROXY_HTTPS"):
        proxies["https"] = os.getenv("PROXY_HTTPS")

    # 재시도/백오프/타임아웃/헤더 설정
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125 Safari/537.36"}
    try:
        pytrends = TrendReq(
            hl="ko-KR", tz=540,
            timeout=(10, 30),     # (connect, read)
            retries=3,            # pytrends 내 재시도
            backoff_factor=0.5,   # 0.5, 1.0, 2.0 초로 증가
            requests_args={"headers": headers},
            proxies=proxies if proxies else None
        )
    except Exception as e:
        return pd.DataFrame(), f"pytrends 초기화 실패: {e}"

    # 첫 시도: now 7-d (실시간 구간)
    try:
        # 살짝 지터를 줘서 동시요청 완화
        time.sleep(0.3 + random.random() * 0.7)
        pytrends.build_payload([keyword], cat=0, timeframe="now 7-d", geo=geo, gprop="")
        df = pytrends.interest_over_time()
        if df is None or df.empty:
            return pd.DataFrame(), "결과 없음"
        if "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])
        df = df.reset_index().rename(columns={"date": "datetime", keyword: "interest"})
        return df, None
    except Exception as e1:
        msg = str(e1)

    # 429 등으로 막히면 완화된 구간으로 폴백: today 3-m (일 단위)
    try:
        time.sleep(1.0 + random.random())  # 백오프
        pytrends.build_payload([keyword], cat=0, timeframe="today 3-m", geo=geo, gprop="")
        df = pytrends.interest_over_time()
        if df is None or df.empty:
            return pd.DataFrame(), "결과 없음(폴백 구간)"
        if "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])
        df = df.reset_index().rename(columns={"date": "datetime", keyword: "interest"})
        return df, None
    except Exception as e2:
        return pd.DataFrame(), f"Google Trends 오류(429 가능): {msg} / fallback: {e2}"

def google_trends_pytrends(keyword: str, region: str):
    """Google Trends: 가능하면 pytrends로 그래프, 실패하면 링크 제공."""
    geo = "" if region == "GLOBAL" else region
    try:
        # pytrends가 설치되어 있고 동작하면 그래프 반환
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="ko-KR", tz=540)  # 최소 옵션
        pytrends.build_payload([keyword], timeframe="now 7-d", geo=geo)
        df = pytrends.interest_over_time()
        if df is None or df.empty:
            return pd.DataFrame(), "결과 없음"
        if "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])
        df = df.reset_index().rename(columns={"date": "datetime", keyword: "interest"})
        return df, None
    except Exception as e:
        # pytrends 미설치/오류 → 링크로 우회
        q = urllib.parse.quote(keyword)
        web_geo = geo or "KR"
        trends_url = f"https://trends.google.com/trends/explore?geo={web_geo}&q={q}"
        return pd.DataFrame(), f"Google Trends 사용 불가: {repr(e)}\n직접 확인: {trends_url}"

def naver_datalab_searchtrend(keyword: str):
    """네이버 데이터랩 검색어 트렌드(최근 2주, 일 단위). device는 'pc'로 명시."""
    if not (NAVER_CLIENT_ID and NAVER_CLIENT_SECRET):
        return pd.DataFrame(), "NAVER_CLIENT_ID/SECRET 환경변수가 없습니다."
    url = "https://openapi.naver.com/v1/datalab/search"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        "Content-Type": "application/json"
    }
    today = dt.date.today()
    start_date = (today - dt.timedelta(days=14)).strftime("%Y-%m-%d")
    end_date = (today - dt.timedelta(days=1)).strftime("%Y-%m-%d")

    body = {
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": "date",
        "keywordGroups": [{"groupName": keyword, "keywords": [keyword]}],
        "device": "pc"   # 허용값: 'pc' 또는 'mo'
    }

    try:
        r = requests.post(url, headers=headers, data=json.dumps(body), timeout=20)
    except Exception as e:
        return pd.DataFrame(), f"Naver DataLab 요청 실패: {e}"

    if r.status_code != 200:
        # 오류 본문까지 그대로 보여줘서 디버깅 쉽게
        return pd.DataFrame(), f"Naver DataLab 오류: {r.status_code} {r.text}"

    try:
        res = r.json()
    except Exception:
        return pd.DataFrame(), f"Naver DataLab 응답 파싱 실패: {r.text[:200]}"

    results = res.get("results", [])
    if not results:
        return pd.DataFrame(), "Naver DataLab 결과 없음"

    data = results[0].get("data", [])
    df = pd.DataFrame(data)
    if df.empty:
        return pd.DataFrame(), "Naver DataLab 결과 없음"

    df["period"] = pd.to_datetime(df["period"])
    df = df.rename(columns={"ratio": "search_ratio"})
    return df, None

def make_judgement(youtube_df, trends_df, naver_df):
    """간단 점수화 규칙으로 잠정 결론 생성."""
    score = 0
    reasons = []
    # YouTube rule
    if isinstance(youtube_df, pd.DataFrame) and not youtube_df.empty:
        top_views = int(youtube_df["viewCount"].iloc[0])
        total_views = int(youtube_df["viewCount"].sum())
        if top_views >= 50000 or total_views >= 100000:
            score += 2
            reasons.append("YouTube 신규 영상/숏츠 영향 (조회수 큼)")
        else:
            score += 1
            reasons.append("YouTube 신규 영상 등장")
    # Google Trends rule: 최근 값 vs 7일 중앙값
    if isinstance(trends_df, pd.DataFrame) and not trends_df.empty:
        last = int(trends_df["interest"].iloc[-1])
        med_val = trends_df["interest"].median()
        med = int(med_val) if med_val and med_val > 0 else 1
        lift = (last / med) if med else 0
        if lift >= 1.5 and last >= 20:
            score += 1
            reasons.append(f"Google Trends 상승 (x{lift:.1f})")
    # Naver rule: 최근 3일 평균 vs 이전 7일 평균
    if isinstance(naver_df, pd.DataFrame) and not naver_df.empty:
        naver_df = naver_df.sort_values("period")
        if len(naver_df) >= 10:
            recent = naver_df.tail(3)["search_ratio"].mean()
            prev = naver_df.tail(10).head(7)["search_ratio"].mean()
            if prev and prev > 0 and (recent / prev) >= 1.3:
                score += 1
                reasons.append("네이버 데이터랩 상승")

    if score >= 3:
        verdict = "복합 외부 요인 가능성 높음"
    elif score == 2:
        verdict = "단일 외부 채널 영향 가능"
    elif score == 1:
        verdict = "미약한 외부 신호"
    else:
        verdict = "외부 신호 증거 부족 (내부 요인/우연 가능)"
    return verdict, reasons, score

# ---- Run ----
if run_btn and keyword.strip():
    st.subheader(f"키워드: {keyword}")
    st.write(f"분석 윈도우: 최근 {hours_window}시간, 지역: {region}")

    # YouTube
    st.markdown("### 🟥 YouTube")
    ydf, yerr = youtube_search(keyword, YOUTUBE_API_KEY, hours_window)
    if yerr:
        st.info(yerr)
        ydf = pd.DataFrame()
    else:
        show_cols = ["title", "channel", "viewCount", "durationSec", "isShorts", "matchedInMeta", "publishedAt", "url"]
        st.dataframe(ydf[show_cols])

    # Google Trends
    st.markdown("### 🟨 Google Trends (최근 7일)")
    gdf, gerr = google_trends_pytrends(keyword, region)

    import urllib.parse

    def _build_trends_url(keyword: str, region: str, fallback_from_err: str | None = None) -> str:
        # 에러 문자열 안에 링크가 있으면 그걸 우선 사용
        if fallback_from_err:
            for tok in fallback_from_err.split():
                if tok.startswith("http://") or tok.startswith("https://"):
                    return tok.strip()
        # 없으면 직접 구성
        geo = "" if region == "GLOBAL" else region or "KR"
        q = urllib.parse.quote(keyword)
        web_geo = geo or "KR"
        return f"https://trends.google.com/trends/explore?geo={web_geo}&q={q}"

    if gerr:
        # 에러 문구는 숨기고 버튼만 노출
        trends_url = _build_trends_url(keyword, region, gerr)
        st.link_button("🔗 Google Trends에서 보기", trends_url, use_container_width=True)
        st.caption("일시적 제한으로 내부 차트를 생략했습니다.")
        gdf = pd.DataFrame()
    else:
        st.line_chart(gdf.set_index("datetime")["interest"])
        # 차트가 떠도 외부 페이지 버튼 하나는 항상 제공(선택)
        trends_url = _build_trends_url(keyword, region, None)
        st.link_button("🔗 Google Trends에서 보기", trends_url, use_container_width=True)

    # Naver DataLab
    st.markdown("### 🟩 네이버 데이터랩 (최근 2주)")
    ndf, nerr = naver_datalab_searchtrend(keyword)
    if nerr:
        st.info(nerr)
        ndf = pd.DataFrame()
    else:
        st.line_chart(ndf.set_index("period")["search_ratio"])

    # Judgement
    st.markdown("---")
    verdict, reasons, score = make_judgement(ydf, gdf, ndf)
    st.markdown(f"## ✅ 잠정 결론: {verdict}  \n**스코어:** {score}")
    if reasons:
        st.write("- " + "\n- ".join(reasons))

    st.caption("※ 자동 추정 결과이며, 실제 원인은 추가 확인이 필요할 수 있습니다.")
else:
    st.write("키워드를 입력하고 **분석 실행**을 눌러주세요.")
