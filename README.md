# 키워드 급증 원인 체크 (개인용)

입력한 키워드에 대해 최근 24~72시간 내 외부 시그널(YouTube, Google Trends, 네이버 데이터랩)을 조회해
"왜 검색이 늘었는지"를 추정하는 개인용 도구입니다. (사내 공유/배포 전제 없음)

## 빠른 시작

1) 프로젝트 파일 받기
```bash
pip install -r requirements.txt
```

2) 환경변수 설정(선택)
- `.env` 파일을 직접 쓰지 않습니다. 터미널에서 아래처럼 입력하거나, OS의 환경변수에 등록하세요.
    - macOS/Linux 예:
    ```bash
    export YOUTUBE_API_KEY="발급받은_API키"
    export NAVER_CLIENT_ID="발급받은_ID"
    export NAVER_CLIENT_SECRET="발급받은_SECRET"
    ```

3) 실행
```bash
streamlit run app.py
```
브라우저에 앱이 열리면, 키워드를 입력하고 **분석 실행** 버튼을 클릭하세요.

## 필요한 키/권한
- **YouTube Data API v3**: API Key 필요(콘솔에서 활성화)
- **네이버 데이터랩**: 애플리케이션 등록 후 Client ID/Secret 발급
- **Google Trends**: pytrends는 키 없이 사용 가능

## 판정 로직(초간단 규칙 기반)
- YouTube 조회수(상위/합계), Google Trends 최근값 vs 7일 중앙값, 네이버 데이터랩 최근3일 평균 vs 이전7일 평균을 점수화
- 점수에 따라 `복합 외부 요인` / `단일 외부 채널` / `미약한 신호` / `증거 부족`으로 표시

## 커스터마이즈 아이디어
- 내부 로그(푸시/배너/특가) CSV를 업로드 받아서 교차검증
- 뉴스/커뮤니티(구글 뉴스, 네이버 뉴스) API 추가
- 윈도우/임계치 조정 및 가중치 커스텀