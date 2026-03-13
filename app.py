import os
import re
import html
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
st.set_page_config(page_title="키워드 급증 원인 체크", page_icon="🔎", layout="wide")

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")

# ---- Global CSS ----------------------------------------------------------------------
st.markdown("""
<style>
/* ===== DAILYSHOT BRAND · LIGHT THEME ===== */

/* 전체 배경 / 레이아웃 */
.main, [data-testid="stAppViewContainer"] { background: #f5f6f8; }
.block-container { max-width: 980px !important; padding: 24px 28px !important; }
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stHeader"] { display: none !important; }
[data-testid="stToolbar"] { display: none !important; }

/* ── 사이드바 ── */
[data-testid="stSidebar"] {
  background: #ffffff !important;
  border-right: 1px solid #e8eaed !important;
  min-width: 230px !important; max-width: 240px !important;
}
[data-testid="stSidebar"] > div:first-child { padding-top: 0 !important; }
[data-testid="stSidebar"] section { padding: 22px 18px !important; }

/* 로고 */
.sidebar-logo {
  font-size: 16px; font-weight: 900; color: #111; letter-spacing: -0.03em;
  padding-bottom: 16px; border-bottom: 1px solid #efefef; margin-bottom: 18px;
}
.sidebar-logo em { color: #FE5000; font-style: normal; }

/* 컨트롤 레이블 */
.ctrl-label {
  font-size: 10px; font-weight: 700; color: #b0b4bc;
  text-transform: uppercase; letter-spacing: 0.10em;
  margin-bottom: 4px; margin-top: 14px;
}

/* 폼 테두리 제거 */
[data-testid="stForm"] { border: none !important; padding: 0 !important; background: transparent !important; }

/* 인풋 / 셀렉트 */
.stTextInput input, .stSelectbox select {
  border-radius: 8px !important; border: 1.5px solid #e4e6ea !important;
  background: #fafbfc !important; font-size: 14px !important; color: #111 !important;
}
.stTextInput input:focus {
  border-color: #FE5000 !important;
  box-shadow: 0 0 0 3px rgba(254,80,0,0.12) !important;
}

/* 분석 실행 버튼 */
[data-testid="stFormSubmitButton"] > button {
  background: #FE5000 !important; color: #fff !important;
  border: none !important; font-weight: 800 !important;
  border-radius: 10px !important; font-size: 14px !important;
  padding: 12px !important; width: 100% !important;
  letter-spacing: 0.01em !important;
  transition: background 0.15s !important; margin-top: 10px !important;
}
[data-testid="stFormSubmitButton"] > button:hover { background: #e04500 !important; }

/* ── 섹션 카드 ── */
.section-card {
  background: #ffffff; border: 1px solid #e8eaed; border-radius: 12px;
  padding: 16px 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
.section-title {
  margin: 0 0 12px 0; font-size: 10px; font-weight: 700; color: #9aa0ab;
  display: flex; align-items: center; gap: 6px;
  text-transform: uppercase; letter-spacing: 0.10em;
}
.section-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; flex-shrink: 0; }

/* ── YouTube 카드 ── */
.yt-card {
  border-radius: 10px; background: #fff; overflow: hidden;
  box-shadow: 0 1px 4px rgba(0,0,0,0.07); border: 1px solid #e8eaed;
  display: flex; flex-direction: column;
}
/* 썸네일 영역 — 랭크·조회수 오버레이 */
.yt-thumb-wrap {
  display: block; position: relative; width: 100%;
  aspect-ratio: 16/9; overflow: hidden; background: #eaecef;
}
.yt-thumb {
  width: 100%; height: 100%; object-fit: cover; display: block;
}
.yt-rank {
  position: absolute; top: 8px; left: 8px;
  width: 22px; height: 22px; border-radius: 5px;
  background: #FE5000; color: #fff; font-weight: 900; font-size: 11px;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 1px 4px rgba(0,0,0,0.35);
}
.yt-view-overlay {
  position: absolute; bottom: 7px; right: 7px;
  background: rgba(0,0,0,0.62); color: #fff; font-size: 10px; font-weight: 700;
  padding: 2px 6px; border-radius: 4px; letter-spacing: 0.01em;
}
/* 카드 본문 */
.yt-body { padding: 11px 12px; display: flex; flex-direction: column; gap: 4px; }
/* 1순위: 제목 — 굵고 크게 */
.yt-title {
  font-weight: 700; font-size: 13px; line-height: 1.5; color: #111;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; word-break: keep-all; margin-bottom: 2px;
}
/* 2순위: 채널명 — 중간 */
.yt-channel { font-size: 12px; color: #555; font-weight: 500; }
/* 3순위: 조회수·태그 — 작고 연하게 */
.yt-foot { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; margin-top: 3px; }
.yt-views { color: #FE5000; font-size: 11px; font-weight: 700; }
.yt-sep { color: #d1d5db; font-size: 10px; }
.yt-type { font-size: 10px; color: #9ca3af; background: #f3f4f6; padding: 1px 6px; border-radius: 3px; }
.badge-green { background: #fff4f0; color: #c73d00; font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 3px; display: inline-block; border: 1px solid #ffd6c8; }
.badge-blue  { background: #eff6ff; color: #1d4ed8; font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 3px; display: inline-block; margin-left: 3px; border: 1px solid #dbeafe; }
.divider-space { height: 12px; }

/* ── 뉴스/카페 리스트 ── */
.news-item { padding: 10px 0; border-bottom: 1px solid #f0f1f3; }
.news-item:last-child { border-bottom: none; padding-bottom: 0; }
/* 1순위: 제목 — 굵고 */
.news-title { font-size: 13px; font-weight: 700; color: #111; line-height: 1.45; margin-bottom: 4px; }
.news-title a { color: #111; text-decoration: none; }
.news-title a:hover { color: #FE5000; }
/* 2순위: 출처명 — 중간 */
.news-source { font-size: 11px; font-weight: 600; color: #555; }
/* 3순위: 날짜 — 연하게 */
.news-date { font-size: 11px; color: #b8bdc7; }
.news-row { display: flex; align-items: center; gap: 5px; }
.news-dot { color: #d1d5db; font-size: 9px; }

/* 기타 정리 */
.stMarkdown p { margin-bottom: 0 !important; }
[data-testid="column"] { padding-right: 6px !important; }
hr { border-color: #e8eaed !important; }
/* 하단 잘림 방지 */
.block-container { padding-bottom: 80px !important; }
.main .block-container { overflow: visible !important; }
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------------------------------------------
# URL Query Params -> Defaults
# --------------------------------------------------------------------------------------
qp = st.query_params  # dict-like

def _get1(d, k, default):
    v = d.get(k, default)
    if isinstance(v, list):
        return v[0] if v else default
    return v

default_keyword = _get1(qp, "q", "")
h_raw = _get1(qp, "h", "168")
b_raw = _get1(qp, "b", "0")

hours_options = [24, 48, 72, 168]
try:
    default_hours = int(h_raw)
    if default_hours not in hours_options:
        default_hours = 168
except:
    default_hours = 168

default_broad = (str(b_raw) == "1")

# ---- 사이드바 Hero + Controls -------------------------------------------------------
with st.sidebar:
    st.markdown('<div class="sidebar-logo">Daily<em>shot</em> 키워드 체커</div>', unsafe_allow_html=True)
    with st.form("controls"):
        st.markdown('<div class="ctrl-label">키워드</div>', unsafe_allow_html=True)
        keyword = st.text_input("키워드", placeholder="키워드를 입력하세요",
                                value=default_keyword, label_visibility="collapsed")
        st.markdown('<div class="ctrl-label">탐색 시간</div>', unsafe_allow_html=True)
        hours_window = st.selectbox("탐색 시간", hours_options,
                                    index=hours_options.index(default_hours), label_visibility="collapsed")
        broad_mode = st.checkbox("브로드 모드", value=default_broad,
                                 help="제목/설명/태그에 없어도 댓글·변형어까지 넓게 탐색")
        st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)
        run_btn = st.form_submit_button("분석 실행 →", use_container_width=True, type="primary")


# --------------------------------------------------------------------------------------
# Helpers (+ cache)
# --------------------------------------------------------------------------------------
def _yt_request(url: str, params: dict, label: str):
    try:
        r = requests.get(url, params=params, timeout=20)
        if r.status_code != 200:
            return None, f"{label} 오류: {r.status_code} {r.text[:200]}"
        return r.json(), None
    except Exception as e:
        return None, f"{label} 요청 실패: {e}"

@st.cache_data(ttl=600)
def youtube_search(keyword: str, api_key: str, hours: int = 24, broad_mode: bool = False):
    if not api_key:
        return pd.DataFrame(), "환경변수 YOUTUBE_API_KEY가 없습니다."

    def variants(kw: str):
        base = (kw or "").strip()
        no_space = base.replace(" ", "")
        v = {base, no_space, f"#{base}", f"#{no_space}"}
        return [x for x in v if x]

    published_after = (
        dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    ).isoformat().replace("+00:00", "Z")

    def _search_once(q):
        return _yt_request(
            "https://www.googleapis.com/youtube/v3/search",
            {"part": "snippet", "q": q, "type": "video", "order": "date",
             "maxResults": 25, "publishedAfter": published_after,
             "regionCode": "KR", "relevanceLanguage": "ko", "key": api_key},
            "YOUTUBE search"
        )

    items = []
    for q in variants(keyword):
        data, err = _search_once(q)
        if data and not err:
            items += data.get("items", [])

    video_ids = list({it.get("id", {}).get("videoId") for it in items if it.get("id", {}).get("videoId")})

    # 브로드 모드: 키워드 없이 최근 업로드도 후보에 추가
    if broad_mode:
        data_b, _ = _yt_request(
            "https://www.googleapis.com/youtube/v3/search",
            {"part": "snippet", "type": "video", "order": "date",
             "maxResults": 25, "publishedAfter": published_after,
             "regionCode": "KR", "relevanceLanguage": "ko", "key": api_key},
            "YOUTUBE recent feed"
        )
        if data_b:
            items_b = data_b.get("items", [])
            video_ids += [it.get("id", {}).get("videoId") for it in items_b if it.get("id", {}).get("videoId")]
            video_ids = list({v for v in video_ids if v})

    if not video_ids:
        return pd.DataFrame(), "최근 업로드 결과 없음"

    data2, err2 = _yt_request(
        "https://www.googleapis.com/youtube/v3/videos",
        {"part": "statistics,snippet,contentDetails",
         "id": ",".join(video_ids), "key": api_key},
        "YOUTUBE videos"
    )
    if err2 or not data2:
        return pd.DataFrame(), err2 or "YOUTUBE videos 응답 없음"

    def is_shorts_from_iso(dur_iso):
        try:
            return int(isodate.parse_duration(dur_iso).total_seconds()) <= 60
        except Exception:
            return False

    def comments_mentions(video_id: str, needles: list[str]) -> bool:
        if not broad_mode:
            return False
        data_c, _ = _yt_request(
            "https://www.googleapis.com/youtube/v3/commentThreads",
            {"part": "snippet", "videoId": video_id, "maxResults": 20,
             "order": "relevance", "textFormat": "plainText", "key": api_key},
            "YOUTUBE comments"
        )
        if not data_c:
            return False
        arr = data_c.get("items", [])
        blob = " ".join(
            (it.get("snippet", {}).get("topLevelComment", {}).get("snippet", {}).get("textDisplay") or "")
            for it in arr
        ).lower()
        return any(v.lower() in blob for v in needles)

    MAX_COMMENT_CHECKS = 10  # 브로드 모드에서 댓글 API 호출 최대 횟수
    rows = []
    needles = variants(keyword)
    comment_check_count = 0
    for it in data2.get("items", []):
        snip = it.get("snippet", {}) or {}
        stats = it.get("statistics", {}) or {}
        cd = it.get("contentDetails", {}) or {}
        title = snip.get("title") or ""
        desc = snip.get("description") or ""
        tags = snip.get("tags", [])
        text_blob = " ".join([title, desc] + (tags or [])).lower()
        matched_in_meta = any(v.lower() in text_blob for v in needles)
        if comment_check_count < MAX_COMMENT_CHECKS:
            matched_in_comments = comments_mentions(it.get("id"), needles)
            if broad_mode:
                comment_check_count += 1
        else:
            matched_in_comments = False
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

    return pd.DataFrame(rows).sort_values("viewCount", ascending=False), None

@st.cache_data(ttl=600)
def google_trends_pytrends(keyword: str, region: str):
    geo = "" if region == "GLOBAL" else region
    try:
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl="ko-KR", tz=540)
        time.sleep(0.3 + random.random() * 0.7)  # 429 완화
        pytrends.build_payload([keyword], timeframe="now 7-d", geo=geo)
        df = pytrends.interest_over_time()
        if df is None or df.empty:
            return pd.DataFrame(), "결과 없음"
        if "isPartial" in df.columns:
            df = df.drop(columns=["isPartial"])
        df = df.reset_index().rename(columns={"date": "datetime", keyword: "interest"})
        return df, None
    except Exception:
        q = urllib.parse.quote(keyword or "")
        web_geo = geo or "KR"
        trends_url = f"https://trends.google.com/trends/explore?geo={web_geo}&q={q}"
        return pd.DataFrame(), trends_url  # 에러 문구 대신 URL만

@st.cache_data(ttl=600)
def naver_datalab_searchtrend(keyword: str):
    if not (NAVER_CLIENT_ID and NAVER_CLIENT_SECRET):
        return pd.DataFrame(), "NAVER_CLIENT_ID/SECRET 환경변수가 없습니다."
    url = "https://openapi.naver.com/v1/datalab/search"
    headers = {"X-Naver-Client-Id": NAVER_CLIENT_ID,
               "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
               "Content-Type": "application/json"}
    today = dt.date.today()
    start_date = (today - dt.timedelta(days=14)).strftime("%Y-%m-%d")
    end_date = (today - dt.timedelta(days=1)).strftime("%Y-%m-%d")
    body = {"startDate": start_date, "endDate": end_date,
            "timeUnit": "date",
            "keywordGroups": [{"groupName": keyword, "keywords": [keyword]}],
            "device": "pc"}
    r = requests.post(url, headers=headers, data=json.dumps(body), timeout=20)
    if r.status_code != 200:
        return pd.DataFrame(), f"Naver DataLab 오류: {r.status_code} {r.text}"
    res = r.json()
    results = res.get("results", [])
    if not results:
        return pd.DataFrame(), "Naver DataLab 결과 없음"
    data = results[0].get("data", [])
    df = pd.DataFrame(data)
    if df.empty:
        return pd.DataFrame(), "Naver DataLab 결과 없음"
    df["period"] = pd.to_datetime(df["period"])
    return df.rename(columns={"ratio": "search_ratio"}), None

@st.cache_data(ttl=300)
def naver_search(keyword: str, search_type: str, hours: int = 168):
    """search_type: 'news' | 'cafearticle'"""
    if not (NAVER_CLIENT_ID and NAVER_CLIENT_SECRET):
        return pd.DataFrame(), "NAVER_CLIENT_ID/SECRET 환경변수가 없습니다."
    url = f"https://openapi.naver.com/v1/search/{search_type}.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {"query": keyword, "display": 20, "sort": "date"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        if r.status_code != 200:
            return pd.DataFrame(), f"Naver {search_type} 오류: {r.status_code} {r.text[:200]}"
        items = r.json().get("items", [])
        if not items:
            return pd.DataFrame(), "결과 없음"
        df = pd.DataFrame(items)
        if "pubDate" in df.columns:
            df["pubDate"] = pd.to_datetime(df["pubDate"], format="%a, %d %b %Y %H:%M:%S %z", utc=True, errors="coerce")
            cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
            df = df[df["pubDate"] >= cutoff]
            if df.empty:
                return pd.DataFrame(), f"최근 {hours}시간 내 결과 없음"
        else:
            df["pubDate"] = pd.NaT  # 날짜 없는 API (카페글 등)
        # API 응답 title/description에 <b> 태그 포함 → 제거
        for col in ["title", "description"]:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: re.sub(r"<[^>]+>", "", x or ""))
        return df.sort_values("pubDate", ascending=False).reset_index(drop=True), None
    except Exception as e:
        return pd.DataFrame(), f"Naver {search_type} 요청 실패: {e}"

# ---- Scoring -------------------------------------------------------------------------
def make_judgement(youtube_df, trends_df, naver_df, news_df=None, cafe_df=None):
    score, reasons = 0, []
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
    # Naver DataLab
    if isinstance(naver_df, pd.DataFrame) and not naver_df.empty:
        naver_df = naver_df.sort_values("period")
        if len(naver_df) >= 10:
            recent = naver_df.tail(3)["search_ratio"].mean()
            prev = naver_df.tail(10).head(7)["search_ratio"].mean()
            if prev and prev > 0 and (recent / prev) >= 1.3:
                score += 1; reasons.append("네이버 데이터랩 상승")
    # Naver 뉴스
    if isinstance(news_df, pd.DataFrame) and not news_df.empty:
        score += 1; reasons.append(f"네이버 뉴스 보도 감지 ({len(news_df)}건)")
    # Naver 카페
    if isinstance(cafe_df, pd.DataFrame) and not cafe_df.empty:
        score += 1; reasons.append(f"네이버 카페 커뮤니티 확산 감지 ({len(cafe_df)}건)")
    if score >= 4: verdict = "복합 외부 요인 가능성 높음"
    elif score == 3: verdict = "복합 채널 영향 가능"
    elif score == 2: verdict = "단일 채널 영향 가능"
    elif score == 1: verdict = "미약한 외부 신호"
    else: verdict = "외부 신호 증거 부족 (내부 요인/우연 가능)"
    return verdict, reasons, score

def _score_theme(score: int):
    if score >= 4: return {"emoji":"🔥","title":"복합 외부 요인 폭발","color":"#ef4444"}
    if score == 3: return {"emoji":"🟧","title":"복합 채널 영향","color":"#f97316"}
    if score == 2: return {"emoji":"🟨","title":"단일 채널 영향","color":"#eab308"}
    if score == 1: return {"emoji":"🟦","title":"약한 외부 신호","color":"#3b82f6"}
    return {"emoji":"🟩","title":"외부 신호 없음","color":"#22c55e"}

def render_scored_summary(score: int, verdict: str, reasons: list[str]):
    theme = _score_theme(score)
    frac = max(0, min(score, 6)) / 6
    reason_chips = "".join(
        f'<span style="display:inline-block;background:#f3f4f6;border-radius:999px;padding:3px 10px;font-size:11px;color:#6b7280;margin:2px 4px 2px 0;">• {r}</span>'
        for r in (reasons or ["근거 신호 없음"])
    )
    st.markdown(f"""
    <div style="background:white; border:1.5px solid {theme['color']}33; border-radius:14px;
                padding:18px 22px; box-shadow:0 2px 12px {theme['color']}18;">
      <div style="display:flex; align-items:center; gap:10px; margin-bottom:10px;">
        <div style="font-size:28px; line-height:1;">{theme['emoji']}</div>
        <div>
          <div style="font-weight:800; font-size:17px; color:#111; letter-spacing:-0.01em;">{theme['title']}</div>
          <div style="font-size:12px; color:#9ca3af; margin-top:2px;">잠정 결론: {verdict}</div>
        </div>
        <div style="margin-left:auto; text-align:right;">
          <div style="font-size:24px; font-weight:900; color:{theme['color']}; line-height:1;">{score}</div>
          <div style="font-size:11px; color:#aaa;">/ 6</div>
        </div>
      </div>
      <div style="height:5px; width:100%; background:#f0f2f5; border-radius:999px; overflow:hidden; margin:0 0 12px;">
        <div style="height:100%; width:{frac*100:.0f}%; background:{theme['color']}; border-radius:999px;"></div>
      </div>
      <div>{reason_chips}</div>
    </div>
    """, unsafe_allow_html=True)

# ---- Section wrapper -----------------------------------------------------------------
def section_card(title_html: str, body_render_fn):
    st.markdown(f'<div class="section-card"><div class="section-title">{title_html}</div>', unsafe_allow_html=True)
    body_render_fn()
    st.markdown('</div>', unsafe_allow_html=True)

# --------------------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------------------
if run_btn and (keyword or "").strip():

    st.markdown(f"""
    <div style="display:flex; align-items:center; gap:10px; margin-bottom:16px;">
      <span style="background:#FE5000; color:#fff; font-weight:800; font-size:15px;
                   padding:5px 14px; border-radius:7px; letter-spacing:-0.01em;">{keyword}</span>
      <span style="color:#9ca3af; font-size:13px;">최근 {hours_window}시간 분석</span>
    </div>
    """, unsafe_allow_html=True)

    # -------------------- YouTube --------------------
    def _yt_body():
        with st.spinner("YouTube 데이터 수집 중..."):
            ydf, yerr = youtube_search(keyword, YOUTUBE_API_KEY, hours_window, broad_mode=broad_mode)
        if yerr:
            if any(x in yerr for x in ["quotaExceeded", "403", "429"]):
                st.error("YouTube API 쿼터 초과/제한으로 결과를 가져오지 못했습니다. 잠시 후 다시 시도해주세요.")
            else:
                st.info(yerr)
            return pd.DataFrame()

        # TOP3
        top3 = ydf.head(3).copy()

        # TOP3 제목 + '조회수 기준' 칩
        st.markdown("##### 🔺 TOP 3 영상")
        st.markdown(
            '<div style="margin:-6px 0 8px 0;">'
            '<span style="display:inline-block;padding:2px 8px;border-radius:999px;'
            'background:#eef2ff;color:#3730a3;font-size:11px;border:1px solid #e5e7eb;">조회수 기준</span>'
            '</div>', unsafe_allow_html=True
        )

        # 3열 카드
        try:
            c1, c2, c3 = st.columns(3, gap="medium")
        except TypeError:
            c1, c2, c3 = st.columns(3)
        cols = [c1, c2, c3]

        for i, (_, r) in enumerate(top3.iterrows()):
            meta_badge = '<span class="badge-green">메타매칭</span>' if r.get("matchedInMeta") else ""
            cmt_badge  = '<span class="badge-blue">댓글매칭</span>'  if r.get("matchedInComments") else ""
            is_shorts  = "숏츠" if r.get("isShorts") else "일반"
            view_txt   = f"{int(r.get('viewCount',0)):,}회"
            thumb_url  = f"https://i.ytimg.com/vi/{r.get('videoId','')}/hqdefault.jpg"  # 추가 API 소모 없음

            safe_title   = html.escape(r.get('title', ''))
            safe_channel = html.escape(r.get('channel', ''))
            with cols[i]:
                st.markdown(f"""
                <div class="yt-card">
                  <!-- 썸네일 + 오버레이 -->
                  <a class="yt-thumb-wrap" href="{r.get('url','')}" target="_blank">
                    <img class="yt-thumb" src="{thumb_url}" loading="lazy">
                    <span class="yt-rank">{i+1}</span>
                    <span class="yt-view-overlay">{view_txt}</span>
                  </a>
                  <!-- 카드 본문 -->
                  <div class="yt-body">
                    <div class="yt-title">{safe_title}</div>
                    <div class="yt-channel">{safe_channel}</div>
                    <div class="yt-foot">
                      <span class="yt-views">{view_txt}</span>
                      <span class="yt-sep">·</span>
                      <span class="yt-type">{is_shorts}</span>
                      {meta_badge}{cmt_badge}
                    </div>
                  </div>
                </div>
                """, unsafe_allow_html=True)

        # 간격 + 구분선
        st.markdown('<div class="divider-space"></div><hr style="border:none;height:1px;background:#eef2f7;">',
                    unsafe_allow_html=True)

        # 전체 목록 (깔끔 포맷)
        st.markdown("###### 전체 목록")
        df_show = ydf[["title","channel","viewCount","durationSec","isShorts",
                       "matchedInMeta","matchedInComments","publishedAt","url"]].rename(columns={
            "title":"제목","channel":"채널","viewCount":"조회수","durationSec":"길이(초)",
            "isShorts":"숏츠","matchedInMeta":"메타","matchedInComments":"댓글",
            "publishedAt":"업로드","url":"링크"
        })
        # 업로드 시각 포맷
        try:
            df_show["업로드"] = pd.to_datetime(df_show["업로드"]).dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass

        try:
            st.dataframe(
                df_show,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "조회수": st.column_config.NumberColumn(format="%,d"),
                    "숏츠": st.column_config.CheckboxColumn(),
                    "메타": st.column_config.CheckboxColumn(),
                    "댓글": st.column_config.CheckboxColumn(),
                    "링크": st.column_config.LinkColumn(display_text="열기"),
                },
            )
        except Exception:
            st.dataframe(df_show, use_container_width=True, hide_index=True)

        return ydf

    with st.container(border=True):
        st.markdown('<div class="section-title"><span class="section-dot" style="background:#ef4444;"></span> YouTube</div>', unsafe_allow_html=True)
        yt_df = _yt_body()

    # -------------------- Naver 뉴스 + 카페 (2-column) --------------------
    with st.spinner("네이버 뉴스 · 카페 검색 중..."):
        nws_df, nws_err = naver_search(keyword, "news", hours_window)
        caf_df, caf_err = naver_search(keyword, "cafearticle", hours_window)

    nc1, nc2 = st.columns(2, gap="medium")

    def _build_news_html(df, err, hours, kind="news"):
        """카드 전체 HTML을 한 문자열로 조립 → st.markdown 1회 호출"""
        if kind == "news":
            dot_color = "#64748b"
            label = "📰 네이버 뉴스"
        else:
            dot_color = "#7c3aed"
            label = "☕ 네이버 카페"

        header = (
            f'<div class="section-card">'
            f'<div class="section-title">'
            f'<span class="section-dot" style="background:{dot_color};"></span>{label}'
            f'</div>'
        )

        if err:
            body = f'<div style="color:#9ca3af;font-size:13px;padding:6px 0;">{html.escape(str(err))}</div>'
        elif df.empty:
            body = '<div style="color:#9ca3af;font-size:13px;padding:6px 0;">결과 없음</div>'
        else:
            count = f'<div style="font-size:11px;color:#b0b4bc;margin-bottom:6px;">최근 {hours}시간 내 {len(df)}건</div>'
            items = ""
            for _, row in df.head(5).iterrows():
                pub = row["pubDate"].strftime("%m/%d %H:%M") if pd.notna(row.get("pubDate")) else ""
                t = html.escape(row.get("title", ""))
                link = row.get("originallink") or row.get("link", "")
                if kind == "news":
                    try:
                        src = urllib.parse.urlparse(row.get("originallink","")).netloc.replace("www.","").split(".")[0]
                    except Exception:
                        src = ""
                else:
                    src = html.escape(row.get("cafename", ""))
                src_html = f'<span class="news-source">{src}</span><span class="news-dot">•</span>' if src else ""
                date_html = f'<span class="news-date">{pub}</span>' if pub else ""
                items += (
                    f'<div class="news-item">'
                    f'<div class="news-title"><a href="{link}" target="_blank">{t}</a></div>'
                    f'<div class="news-row">{src_html}{date_html}</div>'
                    f'</div>'
                )
            body = count + items

        return header + body + '</div>'

    with nc1:
        st.markdown(_build_news_html(nws_df, nws_err, hours_window, "news"),
                    unsafe_allow_html=True)

    with nc2:
        st.markdown(_build_news_html(caf_df, caf_err, hours_window, "cafe"),
                    unsafe_allow_html=True)

    # -------------------- Google Trends --------------------
    def _trends_body():
        with st.spinner("Google Trends 로딩 중..."):
            gdf, gerr = google_trends_pytrends(keyword, "KR")
        if gerr:
            trends_url = gerr if str(gerr).startswith("http") else f"https://trends.google.com/trends/explore?geo=KR&q={urllib.parse.quote(keyword or '')}"
            st.link_button("🔗 Google Trends에서 보기", trends_url, use_container_width=True)
            st.caption("일시적 제한으로 내부 차트를 생략했습니다.")
            return pd.DataFrame()
        st.line_chart(gdf.set_index("datetime")["interest"])
        trends_url = f"https://trends.google.com/trends/explore?geo=KR&q={urllib.parse.quote(keyword or '')}"
        st.link_button("🔗 Google Trends에서 보기", trends_url, use_container_width=True)
        return gdf

    # -------------------- Naver DataLab --------------------
    def _naver_body():
        with st.spinner("네이버 데이터랩 불러오는 중..."):
            ndf, nerr = naver_datalab_searchtrend(keyword)
        if nerr:
            st.info(nerr); return pd.DataFrame()
        st.line_chart(ndf.set_index("period")["search_ratio"])
        return ndf

    ch1, ch2 = st.columns(2, gap="medium")
    with ch1:
        with st.container(border=True):
            st.markdown('<div class="section-title"><span class="section-dot" style="background:#3b82f6;"></span> Google Trends</div>', unsafe_allow_html=True)
            tr_df = _trends_body()
    with ch2:
        with st.container(border=True):
            st.markdown('<div class="section-title"><span class="section-dot" style="background:#16a34a;"></span> 네이버 데이터랩</div>', unsafe_allow_html=True)
            nv_df = _naver_body()

    # -------------------- Summary Card --------------------
    st.markdown("---")
    verdict, reasons, score = make_judgement(yt_df, tr_df, nv_df, nws_df, caf_df)
    render_scored_summary(score, verdict, reasons)
    st.caption("※ 자동 추정 결과이며, 실제 원인은 추가 확인이 필요할 수 있습니다.")
    st.markdown("<div style='height:40px'></div>", unsafe_allow_html=True)

else:
    st.write("키워드를 입력하고 **분석 실행**을 눌러주세요.")
