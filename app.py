
import os
import datetime as dt
import requests
import pandas as pd
import streamlit as st

# ---- Config ----
st.set_page_config(page_title="키워드 급증 원인 체크", layout="centered")

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")

st.title("🔎 키워드 급증 원인 체크 (개인용)")
st.caption("입력한 키워드에 대해 최근 24~72시간 내 외부 신호(YouTube / Google Trends / 네이버 데이터랩)를 조회해 잠정 원인을 보여줍니다.")

# ---- Inputs ----
keyword = st.text_input("키워드 입력", value="긴샤치")
col1, col2, col3 = st.columns(3)
hours_window = col1.selectbox("윈도우(시간)", [24, 48, 72], index=0)
region = col2.selectbox("지역", ["KR", "US", "JP", "GLOBAL"], index=0)
run_btn = col3.button("분석 실행")

# ---- Helpers ----
def human_ts(ts: dt.datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M")

def youtube_search(keyword: str, api_key: str, hours: int = 24):
    if not api_key:
        return pd.DataFrame(), "환경변수 YOUTUBE_API_KEY가 없습니다."
    published_after = (dt.datetime.utcnow() - dt.timedelta(hours=hours)).isoformat("T") + "Z"
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "order": "date",
        "maxResults": 25,
        "publishedAfter": published_after,
        "key": api_key,
    }
    r = requests.get(url, params=params, timeout=20)
    if r.status_code != 200:
        return pd.DataFrame(), f"YOUTUBE search 오류: {r.status_code} {r.text[:200]}"
    items = r.json().get("items", [])
    if not items:
        return pd.DataFrame(), "최근 업로드 결과 없음"
    video_ids = [it["id"]["videoId"] for it in items if "videoId" in it.get("id", {})]
    if not video_ids:
        return pd.DataFrame(), "최근 업로드 결과 없음"
    # fetch statistics
    url2 = "https://www.googleapis.com/youtube/v3/videos"
    params2 = {
        "part": "statistics,snippet",
        "id": ",".join(video_ids),
        "key": api_key,
    }
    r2 = requests.get(url2, params=params2, timeout=20)
    if r2.status_code != 200:
        return pd.DataFrame(), f"YOUTUBE videos 오류: {r2.status_code} {r2.text[:200]}"
    rows = []
    for it in r2.json().get("items", []):
        stats = it.get("statistics", {})
        snip = it.get("snippet", {})
        rows.append({
            "videoId": it.get("id"),
            "title": snip.get("title"),
            "channel": snip.get("channelTitle"),
            "publishedAt": snip.get("publishedAt"),
            "viewCount": int(stats.get("viewCount", 0)),
            "likeCount": int(stats.get("likeCount", 0)) if stats.get("likeCount") else None,
            "commentCount": int(stats.get("commentCount", 0)) if stats.get("commentCount") else None,
            "url": f"https://www.youtube.com/watch?v={it.get('id')}"
        })
    df = pd.DataFrame(rows).sort_values("viewCount", ascending=False)
    return df, None

def google_trends_pytrends(keyword: str, region: str):
    # Lazy import to avoid dependency if user doesn't need it
    try:
        from pytrends.request import TrendReq
    except Exception as e:
        return pd.DataFrame(), f"pytrends 불러오기 실패: {e}"
    geo = "" if region == "GLOBAL" else region
    pytrends = TrendReq(hl="ko-KR", tz=540)
    try:
        pytrends.build_payload([keyword], cat=0, timeframe="now 7-d", geo=geo, gprop="")
        df = pytrends.interest_over_time()
        if df.empty:
            return pd.DataFrame(), "결과 없음"
        if "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])
        df = df.reset_index().rename(columns={"date": "datetime", keyword: "interest"})
        return df, None
    except Exception as e:
        return pd.DataFrame(), f"Google Trends 오류: {e}"

def naver_datalab_searchtrend(keyword: str):
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
        "keywordGroups": [
            {"groupName": keyword, "keywords": [keyword]}
        ],
        "device": "pc,mobile",
        "ages": [],
        "gender": ""
    }
    r = requests.post(url, headers=headers, data=json.dumps(body), timeout=20)
    if r.status_code != 200:
        return pd.DataFrame(), f"Naver DataLab 오류: {r.status_code} {r.text[:200]}"
    res = r.json()
    results = res.get("results", [])
    if not results:
        return pd.DataFrame(), "결과 없음"
    data = results[0].get("data", [])
    df = pd.DataFrame(data)
    if df.empty:
        return pd.DataFrame(), "결과 없음"
    df["period"] = pd.to_datetime(df["period"])
    df = df.rename(columns={"ratio": "search_ratio"})
    return df, None

def make_judgement(youtube_df, trends_df, naver_df):
    score = 0
    reasons = []
    # YouTube rule
    if not youtube_df.empty:
        top_views = int(youtube_df["viewCount"].iloc[0])
        total_views = int(youtube_df["viewCount"].sum())
        if top_views >= 50000 or total_views >= 100000:
            score += 2
            reasons.append("YouTube 신규 영상/숏츠 영향 (조회수 큼)")
        else:
            score += 1
            reasons.append("YouTube 신규 영상 등장")
    # Google Trends rule: 최근 값 vs 7일 중앙값 비교
    if not trends_df.empty:
        last = int(trends_df["interest"].iloc[-1])
        med = int(trends_df["interest"].median()) if trends_df["interest"].median() > 0 else 1
        lift = (last / med) if med else 0
        if lift >= 1.5 and last >= 20:
            score += 1
            reasons.append(f"Google Trends 상승 (x{lift:.1f})")
    # Naver DataLab rule: 최근 3일 평균 vs 이전 7일 평균
    if not naver_df.empty:
        naver_df = naver_df.sort_values("period")
        if len(naver_df) >= 10:
            recent = naver_df.tail(3)["search_ratio"].mean()
            prev = naver_df.tail(10).head(7)["search_ratio"].mean()
            if prev > 0 and (recent/prev) >= 1.3:
                score += 1
                reasons.append("네이버 데이터랩 상승")
    # Verdict
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
    else:
        st.dataframe(ydf[["title","channel","viewCount","publishedAt","url"]])

    # Google Trends
    st.markdown("### 🟨 Google Trends (최근 7일)")
    gdf, gerr = google_trends_pytrends(keyword, region)
    if gerr:
        st.info(gerr)
    else:
        st.line_chart(gdf.set_index("datetime")["interest"])

    # Naver DataLab
    st.markdown("### 🟩 네이버 데이터랩 (최근 2주)")
    ndf, nerr = naver_datalab_searchtrend(keyword)
    if nerr:
        st.info(nerr)
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
