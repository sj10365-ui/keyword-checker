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
st.set_page_config(page_title="키워드 급증 원인 체크", page_icon="🔎", layout="wide")

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "")

# ---- Global small CSS polish ---------------------------------------------------------
st.markdown("""
<style>
/* 전체 컨테이너 폭/여백 조정 */
.block-container { max-width: 1200px; padding-top: 36px !important; }
/* 섹션 카드 스타일 */
.section-card { border:1px solid #e5e7eb; border-radius:16px; padding:18px 18px; background:#fafafa; }
.section-title { margin:0 0 10px 0; font-size:18px; font-weight:700; display:flex; align-items:center; gap:8px; }
/* 유튜브 Top 카드 */
.vid-card { border:1px solid #e5e7eb; border-radius:12px; padding:12px; background:white; }
.vid-meta { color:#6b7280; font-size:13px; margin-top:4px; }
.badge { display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; border:1px solid #e5e7eb; background:#f3f4f6; }
.link { text-decoration:none; }

/* 여기서부터 새로 추가 */
.yt-card{
  border-radius:12px; background:white; padding:16px;
  box-shadow:0 2px 8px rgba(0,0,0,.06); border:1px solid #eef2f7;
  display:flex; flex-direction:column; justify-content:space-between;
  min-height:160px;
}
.yt-rank{
  width:28px;height:28px;border-radius:50%;
  background:linear-gradient(135deg,#6366f1,#22c55e);
  color:#fff;font-weight:700;font-size:13px;display:flex;align-items:center;justify-content:center;
  box-shadow:0 1px 4px rgba(0,0,0,.15);
}
.yt-title{
  font-weight:700; font-size:15px; line-height:1.35; margin:8px 0 6px 0;
  display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;
}
.yt-meta{font-size:12px; color:#6b7280; margin-bottom:8px;}
.badge-green{background:#dcfce7;color:#166534;font-size:11px;padding:2px 8px;border-radius:999px;display:inline-block}
.badge-blue{background:#dbeafe;color:#1e40af;font-size:11px;padding:2px 8px;border-radius:999px;display:inline-block;margin-left:4px}
.yt-link{font-size:12px; color:#2563eb; text-decoration:none}
.divider-space{height:18px}
</style>
""", unsafe_allow_html=True)

# ---- Hero ---------------------------------------------------------------------------
st.markdown("""
<div class="hero" style="text-align:center; margin:24px 0 16px 0;">
  <div style="font-size:34px; font-weight:800;">🔎 키워드 급증 원인 체크(최강콘팀용)</div>
  <div style="color:#6b7280;">YouTube · Google Trends · 네이버 데이터랩</div>
</div>
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
r_raw = _get1(qp, "r", "KR")
b_raw = _get1(qp, "b", "0")

hours_options = [24, 48, 72, 168]
try:
    default_hours = int(h_raw)
    if default_hours not in hours_options:
        default_hours = 168
except:
    default_hours = 168

region_options = ["KR", "US", "JP", "GLOBAL"]
default_region = r_raw if r_raw in region_options else "KR"
default_broad = (str(b_raw) == "1")

# --------------------------------------------------------------------------------------
# Controls (레이블 줄 + 컨트롤 줄)
# --------------------------------------------------------------------------------------
with st.form("controls"):
    lh1, lh2, lh3, lh4 = st.columns([4, 1.2, 1.2, 1.2])
    lh1.markdown("**키워드 입력**"); lh2.markdown("**탐색 시간**"); lh3.markdown("**지역**"); lh4.markdown("&nbsp;")

    c1, c2, c3, c4 = st.columns([4, 1.2, 1.2, 1.2])
    keyword = c1.text_input("키워드 입력", placeholder="키워드를 입력해주세요",
                            value=default_keyword, label_visibility="collapsed")
    hours_window = c2.selectbox("탐색 시간", hours_options,
                                index=hours_options.index(default_hours), label_visibility="collapsed")
    region = c3.selectbox("지역", region_options,
                          index=region_options.index(default_region), label_visibility="collapsed")
    run_btn = c4.form_submit_button("분석 실행", use_container_width=True, type="primary")

    opt1, opt2, opt3, opt4 = st.columns([2, 2, 2, 2])
    with opt1:
        broad_mode = st.checkbox("브로드 모드", value=default_broad,
                                 help="제목/설명/태그에 없어도 댓글·변형어까지 넓게 탐색")

# 실행 직후 URL 업데이트 + 자동 실행 플래그
auto_run = bool((default_keyword or "").strip())  # URL에 q가 있으면 자동 실행
if run_btn or auto_run:
    st.query_params.update({
        "q": (keyword or default_keyword or ""),
        "h": str(hours_window),
        "r": region,
        "b": "1" if broad_mode else "0",
    })

# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------
def _yt_request(url: str, params: dict, label: str):
    try:
        r = requests.get(url, params=params, timeout=20)
        if r.status_code != 200:
            return None, f"{label} 오류: {r.status_code} {r.text[:200]}"
        return r.json(), None
    except Exception as e:
        return None, f"{label} 요청 실패: {e}"

def youtube_search(keyword: str, api_key: str, hours: int = 24, broad_mode: bool = False):
    if not api_key:
        return pd.DataFrame(), "환경변수 YOUTUBE_API_KEY가 없습니다."

    def variants(kw: str):
        base = (kw or "").strip()
        no_space = base.replace(" ", "")
        v = {base, no_space, f"#{base}", f"#{no_space}",
             "saeng baekseju", "saengbaekseju", "생 백세주", "백세주 생"}
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

    return pd.DataFrame(rows).sort_values("viewCount", ascending=False), None

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

def make_judgement(youtube_df, trends_df, naver_df):
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

def _score_theme(score: int):
    if score >= 3: return {"emoji":"🔥","title":"복합 외부 요인 폭발","color":"#ef4444"}
    if score == 2: return {"emoji":"🟧","title":"단일 채널 영향","color":"#f97316"}
    if score == 1: return {"emoji":"🟨","title":"약한 외부 신호","color":"#eab308"}
    return {"emoji":"🟩","title":"외부 신호 없음","color":"#22c55e"}

def render_scored_summary(score: int, verdict: str, reasons: list[str]):
    theme = _score_theme(score)
    frac = max(0, min(score, 4)) / 4
    st.markdown(f"""
    <div style="border:1px solid {theme['color']}; border-radius:16px; padding:16px 18px; margin:8px 0; background:white;">
      <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
        <span style="font-size:22px;">{theme['emoji']}</span>
        <div style="font-weight:800; font-size:18px;">{theme['title']}</div>
        <div style="margin-left:auto; font-size:13px; opacity:.8;">스코어 <b>{score}</b> / 4</div>
      </div>
      <div style="height:8px; width:100%; background:#e5e7eb; border-radius:999px; overflow:hidden; margin:6px 0 12px;">
        <div style="height:100%; width:{frac*100:.0f}%; background:{theme['color']};"></div>
      </div>
      <div style="font-size:14px; line-height:1.5;">
        <div style="opacity:.8; margin-bottom:6px;"><b>잠정 결론</b>: {verdict}</div>
        {"".join(f"<div>• {r}</div>" for r in (reasons or ["근거 신호 없음"]))}
      </div>
    </div>
    """, unsafe_allow_html=True)

# ---- Small section wrapper -----------------------------------------------------------
def section_card(title_html: str, body_render_fn):
    st.markdown(f'<div class="section-card"><div class="section-title">{title_html}</div>', unsafe_allow_html=True)
    body_render_fn()
    st.markdown('</div>', unsafe_allow_html=True)

# --------------------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------------------
if (run_btn or auto_run) and ((keyword or default_keyword or "").strip()):
    if not (keyword or "").strip():
        keyword = default_keyword

    st.markdown(f"**키워드:** `{keyword}` &nbsp;·&nbsp; **윈도우:** 최근 {hours_window}시간 &nbsp;·&nbsp; **지역:** {region}")

    # -------------------- YouTube --------------------
    def _yt_body():
        with st.spinner("YouTube 데이터 수집 중..."):
            ydf, yerr = youtube_search(keyword, YOUTUBE_API_KEY, hours_window, broad_mode=broad_mode)
        if yerr:
            st.info(yerr); return pd.DataFrame()

        top3 = ydf.head(3).copy()
        st.markdown("##### 🔺 TOP 3 영상")
        c1, c2, c3 = st.columns(3)
        cols = [c1, c2, c3]

        for i, (_, r) in enumerate(top3.iterrows()):
            meta_badge = '<span class="badge-green">메타매칭</span>' if r.get("matchedInMeta") else ""
            cmt_badge  = '<span class="badge-blue">댓글매칭</span>'  if r.get("matchedInComments") else ""
            is_shorts  = "숏츠" if r.get("isShorts") else "일반"
            view_txt   = f"{int(r.get('viewCount',0)):,}회"

            with cols[i]:
                st.markdown(f"""
                <div class="yt-card">
                  <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
                    <div class="yt-rank">{i+1}</div>
                    <div class="yt-title">{r.get('title','')}</div>
                  </div>
                  <div class="yt-meta">👤 {r.get('channel','')} &nbsp;·&nbsp; 👁 {view_txt} &nbsp;·&nbsp; 🎬 {is_shorts}</div>
                  <div style="margin:6px 0;">{meta_badge}{cmt_badge}</div>
                  <a class="yt-link" target="_blank" href="{r.get('url','')}">🔗 영상 바로가기</a>
                </div>
                """, unsafe_allow_html=True)

        st.markdown('<div class="divider-space"></div><hr style="border:none;height:1px;background:#eef2f7;">', unsafe_allow_html=True)
        st.markdown("###### 전체 목록")
        cols_to_show = ["title","channel","viewCount","durationSec","isShorts","matchedInMeta","matchedInComments","publishedAt","url"]
        st.dataframe(ydf[cols_to_show])
        return ydf

    yt_df = None
    section_card('<span style="color:#ef4444;">🟥 YouTube</span>', lambda: None)
    yt_df = _yt_body()

    # -------------------- Google Trends --------------------
    def _trends_body():
        with st.spinner("Google Trends 로딩 중..."):
            gdf, gerr = google_trends_pytrends(keyword, region)
        if gerr:
            trends_url = gerr if str(gerr).startswith("http") else f"https://trends.google.com/trends/explore?geo={region or 'KR'}&q={urllib.parse.quote(keyword or '')}"
            st.link_button("🔗 Google Trends에서 보기", trends_url, use_container_width=True)
            st.caption("일시적 제한으로 내부 차트를 생략했습니다.")
            return pd.DataFrame()
        st.line_chart(gdf.set_index("datetime")["interest"])
        trends_url = f"https://trends.google.com/trends/explore?geo={(region if region!='GLOBAL' else 'KR')}&q={urllib.parse.quote(keyword or '')}"
        st.link_button("🔗 Google Trends에서 보기", trends_url, use_container_width=True)
        return gdf

    st.markdown('<div class="section-card"><div class="section-title" style="color:#3b82f6;">🟨 Google Trends</div>', unsafe_allow_html=True)
    tr_df = _trends_body()
    st.markdown('</div>', unsafe_allow_html=True)

    # -------------------- Naver DataLab --------------------
    def _naver_body():
        with st.spinner("네이버 데이터랩 불러오는 중..."):
            ndf, nerr = naver_datalab_searchtrend(keyword)
        if nerr:
            st.info(nerr); return pd.DataFrame()
        st.line_chart(ndf.set_index("period")["search_ratio"])
        return ndf

    st.markdown('<div class="section-card"><div class="section-title" style="color:#16a34a;">🟩 네이버 데이터랩</div>', unsafe_allow_html=True)
    nv_df = _naver_body()
    st.markdown('</div>', unsafe_allow_html=True)

    # -------------------- Summary Card --------------------
    st.markdown("---")
    verdict, reasons, score = make_judgement(yt_df, tr_df, nv_df)
    render_scored_summary(score, verdict, reasons)
    st.caption("※ 자동 추정 결과이며, 실제 원인은 추가 확인이 필요할 수 있습니다.")

else:
    st.write("키워드를 입력하고 **분석 실행**을 눌러주세요.")
