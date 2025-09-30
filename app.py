import os
import json
import time
import random
import urllib.parse
import datetime as dt
import requests
import pandas as pd
import streamlit as st
import isodate  # ISO8601 duration -> seconds

# --------------------------------------------------------------------------------------
# Page config
# --------------------------------------------------------------------------------------
st.set_page_config(page_title="키워드 급증 원인 체크", layout="centered")

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")

st.title("🔎 키워드 급증 원인 체크(최강콘팀용)")
st.caption("입력한 키워드에 대해 최근 24~72시간(또는 7일) 내 외부 신호(YouTube / Google Trends / 네이버 데이터랩)를 조회해 잠정 원인을 보여줍니다.")

# --------------------------------------------------------------------------------------
# Controls (폼 + 깔끔 정렬)
# --------------------------------------------------------------------------------------
with st.form("controls"):
    # 1) 레이블 줄
    lh1, lh2, lh3, lh4 = st.columns([4, 1.2, 1.2, 1.2])
    lh1.markdown("**키워드 입력**")
    lh2.markdown("**탐색 시간**")
    lh3.markdown("**지역**")
    lh4.markdown("&nbsp;")  # 버튼 자리용 placeholder

    # 2) 컨트롤 + 버튼 줄 (같은 baseline)
    c1, c2, c3, c4 = st.columns([4, 1.2, 1.2, 1.2])
    keyword = c1.text_input("", placeholder="키워드를 입력해주세요", label_visibility="collapsed")
    hours_window = c2.selectbox("", [24, 48, 72, 168], index=0, label_visibility="collapsed")
    region = c3.selectbox("", ["KR", "US", "JP", "GLOBAL"], index=0, label_visibility="collapsed")
    run_btn = c4.form_submit_button("분석 실행", use_container_width=True, type="primary")

    # 옵션(원하면 표시)
    opt1, _, _, _ = st.columns([2, 2, 2, 2])
    with opt1:
        broad_mode = st.checkbox("브로드 모드", value=True, help="제목/설명/태그에 없어도 댓글·변형어까지 넓게 탐색")

# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def _human_ts(ts: dt.datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:%M")

def _yt_request(url: str, params: dict, label: str):
    """YouTube API 호출 헬퍼(에러를 깔끔히 반환)."""
    try:
        r = requests.get(url, params=params, timeout=20)
        if r.status_code != 200:
            return None, f"{label} 오류: {r.status_code} {r.text[:200]}"
        return r.json(), None
    except Exception as e:
        return None, f"{label} 요청 실패: {e}"

def youtube_search(keyword: str, api_key: str, hours: int = 24, broad_mode: bool = True):
    """최근 hours 내 업로드 영상(숏츠 포함) 수집 + 변형어/댓글 매칭(옵션)."""
    if not api_key:
        return pd.DataFrame(), "환경변수 YOUTUBE_API_KEY가 없습니다."

    # ① 키워드 변형 사전
    def variants(kw: str):
        base = (kw or "").strip()
        no_space = base.replace(" ", "")
        v = {
            base, no_space,
            f"#{base}", f"#{no_space}",
            # 필요시 확장(영문/일문/띄어쓰기 변형 등)
            "saeng baekseju", "saengbaekseju",
            "생 백세주", "백세주 생",
        }
        return [x for x in {x for x in v if x}]

    published_after = (dt.datetime.utcnow() - dt.timedelta(hours=hours)).isoformat("T") + "Z"

    def _search_once(q):
        return _yt_request(
            "https://www.googleapis.com/youtube/v3/search",
            {
                "part": "snippet",
                "q": q,
                "type": "video",
                "order": "date",
                "maxResults": 25,
                "publishedAfter": published_after,
                "regionCode": "KR",
                "relevanceLanguage": "ko",
                "key": api_key,
            },
            "YOUTUBE search",
        )

    # ② 변형어들로 검색 병합
    items = []
    for q in variants(keyword):
        data, err = _search_once(q)
        if data and not err:
            items += data.get("items", [])

    video_ids = list({it.get("id", {}).get("videoId") for it in items if it.get("id", {}).get("videoId")})

    # ③ 브로드 모드: 키워드 없이 최근 업로드도 후보에 추가
    if broad_mode:
        data_b, err_b = _yt_request(
            "https://www.googleapis.com/youtube/v3/search",
            {
                "part": "snippet",
                "type": "video",
                "order": "date",
                "maxResults": 25,
                "publishedAfter": published_after,
                "regionCode": "KR",
                "relevanceLanguage": "ko",
                "key": api_key,
            },
            "YOUTUBE recent feed",
        )
        if data_b:
            items_b = data_b.get("items", [])
            video_ids += [it.get("id", {}).get("videoId") for it in items_b if it.get("id", {}).get("videoId")]
            video_ids = list({v for v in video_ids if v})

    if not video_ids:
        return pd.DataFrame(), "최근 업로드 결과 없음"

    # ④ 상세(통계/길이/태그)
    data2, err2 = _yt_request(
        "https://www.googleapis.com/youtube/v3/videos",
        {"part": "statistics,snippet,contentDetails", "id": ",".join(video_ids), "key": api_key},
        "YOUTUBE videos",
    )
    if err2 or not data2:
        return pd.DataFrame(), (err2 or "YOUTUBE videos 응답 없음")

    def is_shorts_from_iso(dur_iso):
        try:
            return int(isodate.parse_duration(dur_iso).total_seconds()) <= 60
        except Exception:
            return False

    # ⑤ 댓글 스캔(옵션)
    def comments_mentions(video_id: str, needles: list[str]) -> bool:
        if not broad_mode:
            return False
        data_c, err_c = _yt_request(
            "https://www.googleapis.com/youtube/v3/commentThreads",
            {
                "part": "snippet",
                "videoId": video_id,
                "maxResults": 20,  # 제한
                "order": "relevance",
                "textFormat": "plainText",
                "key": api_key,
            },
            "YOUTUBE comments",
        )
        if err_c or not data_c:
            return False
        arr = data_c.get("items", [])
        blob = " ".join(
            (it.get("snippet", {})
               .get("topLevelComment", {})
               .get("snippet", {})
               .get("textDisplay") or "")
            for it in arr
        ).lower()
        return any(v.lower() in blob for v in needles)

    needles = variants(keyword)
    rows = []
    for it in data2.get("items", []):
        snip = it.get("snippet", {}) or {}
        stats = it.get("statistics", {}) or {}
        cd = it.get("contentDetails", {}) or {}

        title = snip.get("title") or ""
        desc = snip.get("description") or ""
        tags = snip.get("tags", [])
        text_blob = " ".join([title, desc] + (tags or [])).lower()
        matched_in_meta = any(v.lower() in text_blob for v in needles)
        matched_in_comments = comments_mentions(it.get("id"), needles)

        rows.append({
            "videoId": it.get("id"),
            "title": title,
            "channel": snip.get("channelTitle"),
            "publishedAt": snip.get("publishedAt"),
            "viewCount": int(stats.get("viewCount", 0)) if stats.get("viewCount") else 0,
            "durationSec": int(isodate.parse_duration(cd.get("duration")).total_seconds()) if cd.get("duration") else None,
            "isShorts": is_shorts_from_iso(cd.get("duration")),
            "matchedInMeta": matched_in_meta,
            "matchedInComments": matched_in_comments,
            "url": f"https://www.youtube.com/watch?v={it.get('id')}"
        })

    df = pd.DataFrame(rows).sort_values("viewCount", ascending=False)
    return df, None

# ---- Google Trends (pytrends 우회) ----------------------------------------------------
def google_trends_pytrends(keyword: str, region: str):
    """가능하면 pytrends로 그래프, 실패/미설치면 링크 버튼만 제공."""
    geo = "" if region == "GLOBAL" else region
    try:
        from pytrends.request import TrendReq  # 3.13일 땐 설치 안 되어 있을 수 있음
        pytrends = TrendReq(hl="ko-KR", tz=540)
        # 살짝 지연(429 완화)
        time.sleep(0.3 + random.random() * 0.7)
        pytrends.build_payload([keyword], timeframe="now 7-d", geo=geo)
        df = pytrends.interest_over_time()
        if df is None or df.empty:
            return pd.DataFrame(), "결과 없음"
        if "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])
        df = df.reset_index().rename(columns={"date": "datetime", keyword: "interest"})
        return df, None
    except Exception as e:
        # 링크로 우회
        q = urllib.parse.quote(keyword or "")
        web_geo = geo or "KR"
        trends_url = f"https://trends.google.com/trends/explore?geo={web_geo}&q={q}"
        return pd.DataFrame(), trends_url  # 에러 문구 대신 URL만 넘김

# ---- Naver DataLab -------------------------------------------------------------------
def naver_datalab_searchtrend(keyword: str):
    """네이버 데이터랩 검색어 트렌드(최근 2주, 일 단위). device는 'pc'."""
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
        "device": "pc"
    }
    try:
        r = requests.post(url, headers=headers, data=json.dumps(body), timeout=20)
    except Exception as e:
        return pd.DataFrame(), f"Naver DataLab 요청 실패: {e}"
    if r.status_code != 200:
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

# ---- Scoring -------------------------------------------------------------------------
def make_judgement(youtube_df, trends_df, naver_df):
    score = 0
    reasons = []
    # YouTube
    if isinstance(youtube_df, pd.DataFrame) and not youtube_df.empty:
        top_views = int(youtube_df["viewCount"].iloc[0])
        total_views = int(youtube_df["viewCount"].sum())
        if top_views >= 50000 or total_views >= 100000:
            score += 2; reasons.append("YouTube 신규 영상/숏츠 영향 (조회수 큼)")
        else:
            score += 1; reasons.append("YouTube 신규 영상 등장")
    # Google Trends
    if isinstance(trends_df, pd.DataFrame) and not trends_df.empty:
        last = int(trends_df["interest"].iloc[-1])
        med = int(max(trends_df["interest"].median(), 1))
        lift = last / med
        if lift >= 1.5 and last >= 20:
            score += 1; reasons.append(f"Google Trends 상승 (x{lift:.1f})")
    # Naver
    if isinstance(naver_df, pd.DataFrame) and not naver_df.empty:
        naver_df = naver_df.sort_values("period")
        if len(naver_df) >= 10:
            recent = naver_df.tail(3)["search_ratio"].mean()
            prev = naver_df.tail(10).head(7)["search_ratio"].mean()
            if prev and prev > 0 and (recent / prev) >= 1.3:
                score += 1; reasons.append("네이버 데이터랩 상승")

    if score >= 3: verdict = "복합 외부 요인 가능성 높음"
    elif score == 2: verdict = "단일 외부 채널 영향 가능"
    elif score == 1: verdict = "미약한 외부 신호"
    else: verdict = "외부 신호 증거 부족 (내부 요인/우연 가능)"
    return verdict, reasons, score

# ---- Result styling helpers ----
def _score_theme(score: int):
    # max 4점: (YT 0~2) + (Trends 0~1) + (Naver 0~1)
    if score >= 3:
        return {"emoji":"🔥","title":"복합 외부 요인 폭발","color":"#ef4444"}  # red
    if score == 2:
        return {"emoji":"🟧","title":"단일 채널 영향","color":"#f97316"}        # orange
    if score == 1:
        return {"emoji":"🟨","title":"약한 외부 신호","color":"#eab308"}        # yellow
    return {"emoji":"🟩","title":"외부 신호 없음","color":"#22c55e"}            # green

def render_scored_summary(score: int, verdict: str, reasons: list[str]):
    theme = _score_theme(score)
    frac = max(0, min(score, 4)) / 4
    # 카드 스타일
    st.markdown(f"""
    <div style="
        border:1px solid {theme['color']}; border-radius:12px; padding:14px 16px; margin:8px 0;
        background: rgba(0,0,0,0);">
      <div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">
        <span style="font-size:22px;">{theme['emoji']}</span>
        <div style="font-weight:700; font-size:18px;">{theme['title']}</div>
        <div style="margin-left:auto; font-size:13px; opacity:.8;">스코어 <b>{score}</b> / 4</div>
      </div>
      <div style="height:8px; width:100%; background:#e5e7eb; border-radius:999px; overflow:hidden; margin:6px 0 10px;">
        <div style="height:100%; width:{frac*100:.0f}%; background:{theme['color']};"></div>
      </div>
      <div style="font-size:14px; line-height:1.5;">
        <div style="opacity:.8; margin-bottom:6px;"><b>잠정 결론</b>: {verdict}</div>
        {"".join(f"<div>• {r}</div>" for r in (reasons or ["근거 신호 없음"]))}
      </div>
    </div>
    """, unsafe_allow_html=True)

# --------------------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------------------
if run_btn and (keyword or "").strip():
    st.subheader(f"키워드: {keyword}")
    st.write(f"분석 윈도우: 최근 {hours_window}시간, 지역: {region}")

    # YouTube
    st.markdown("### 🟥 YouTube")
    ydf, yerr = youtube_search(keyword, YOUTUBE_API_KEY, hours_window, broad_mode=broad_mode)
    if yerr:
        st.info(yerr); ydf = pd.DataFrame()
    else:
        show_cols = ["title","channel","viewCount","durationSec","isShorts","matchedInMeta","matchedInComments","publishedAt","url"]
        st.dataframe(ydf[show_cols])

    # Google Trends
    st.markdown("### 🟨 Google Trends (최근 7일)")
    gdf, gerr = google_trends_pytrends(keyword, region)
    if gerr:
        # 에러문구 대신 깔끔한 버튼만 (gerr엔 URL만 들어있도록 위에서 처리함)
        trends_url = gerr if gerr.startswith("http") else f"https://trends.google.com/trends/explore?geo={region or 'KR'}&q={urllib.parse.quote(keyword or '')}"
        st.link_button("🔗 Google Trends에서 보기", trends_url, use_container_width=True)
        st.caption("일시적 제한으로 내부 차트를 생략했습니다.")
        gdf = pd.DataFrame()
    else:
        st.line_chart(gdf.set_index("datetime")["interest"])
        # 차트가 떠도 외부 확인 버튼 제공(원치 않으면 아래 두 줄 삭제)
        trends_url = f"https://trends.google.com/trends/explore?geo={(region if region!='GLOBAL' else 'KR')}&q={urllib.parse.quote(keyword or '')}"
        st.link_button("🔗 Google Trends에서 보기", trends_url, use_container_width=True)

    # Naver DataLab
    st.markdown("### 🟩 네이버 데이터랩 (최근 2주)")
    ndf, nerr = naver_datalab_searchtrend(keyword)
    if nerr:
        st.info(nerr); ndf = pd.DataFrame()
    else:
        st.line_chart(ndf.set_index("period")["search_ratio"])

    # ---- Result (REPLACE THIS BLOCK) ----
    st.markdown("---")
    verdict, reasons, score = make_judgement(ydf, gdf, ndf)
    render_scored_summary(score, verdict, reasons)
    st.caption("※ 자동 추정 결과이며, 실제 원인은 추가 확인이 필요할 수 있습니다.")
else:
    st.write("키워드를 입력하고 **분석 실행**을 눌러주세요.")
