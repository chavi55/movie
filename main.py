import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

st.set_page_config(page_title="박스오피스 대시보드", layout="wide")
st.title("🎬 일별 박스오피스 대시보드")

# 비밀 금고에서 인증키 꺼내기
KOBIS_KEY = st.secrets["KOBIS_KEY"]

# 한국 시간 기준 오늘 및 어제 날짜 계산
today_seoul = datetime.now(ZoneInfo("Asia/Seoul")).date()
yesterday = today_seoul - timedelta(days=1)

# 1. 날짜 선택기 (최대 선택 가능한 날짜는 '어제')
selected_date = st.date_input(
    "조회할 날짜를 선택하세요",
    value=yesterday,
    max_value=yesterday
)

target_dt = selected_date.strftime("%Y%m%d")
st.caption(f"선택한 조회 기준일: {selected_date.strftime('%Y-%m-%d')}")

# API 호출 함수 (캐싱 적용)
@st.cache_data(ttl=3600)
def get_box_office_data(key, dt):
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    return requests.get(url, params={"key": key, "targetDt": dt}, timeout=10)

try:
    res = get_box_office_data(KOBIS_KEY, target_dt)
except Exception as e:
    st.error(f"서버 연결 오류가 발생했습니다: {e}")
    st.stop()

if res.status_code != 200:
    st.error(f"요청이 실패했습니다 (상태코드: {res.status_code})")
    st.stop()

data = res.json()

# KOBIS 예외 처리
if "faultInfo" in data:
    st.error("인증키가 올바르지 않습니다. 금고(Secrets)의 KOBIS_KEY를 확인해 주세요.")
    st.stop()

box_list = data.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])

# 2. 데이터가 비어 있을 때 처리
if not box_list:
    st.warning("그날은 아직 집계 전입니다")
    st.stop()

df = pd.DataFrame(box_list)

# 숫자 타입 변환 (rankInten 추가)
for col in ["rank", "rankInten", "audiCnt", "audiAcc", "scrnCnt", "showCnt"]:
    df[col] = pd.to_numeric(df[col])

# 3. 순위 변동(rankInten) 화살표 및 문구 가공
def format_rank_change(inten):
    if inten > 0:
        return f"🔺 +{inten}"
    elif inten < 0:
        return f"🔹 {inten}"
    else:
        return "-"

df["순위변동"] = df["rankInten"].apply(format_rank_change)

# 4. 누적 관객 100만 이상 트로피 🏆 표시
def format_movie_title(row):
    title = row["movieNm"]
    if row["audiAcc"] >= 1_000_000:
        title += " 🏆"
    return title

df["표시영화명"] = df.apply(format_movie_title, axis=1)

# 1위 영화 지표 카드
top = df.sort_values("rank").iloc[0]
c1, c2, c3 = st.columns(3)
c1.metric("해당 일자 1위", top["표시영화명"])
c2.metric("일일 관객수", f"{top['audiCnt']:,}명")
c3.metric("누적 관객", f"{top['audiAcc']:,}명")

# 표 데이터 정리
table = df[["rank", "순위변동", "표시영화명", "openDt", "audiCnt", "audiAcc", "scrnCnt"]].copy()
table.columns = ["순위", "순위 변동", "영화명", "개봉일", "관객수", "누적관객", "스크린수"]
table = table.sort_values("순위").reset_index(drop=True)

st.subheader("📋 박스오피스 TOP 10")
st.dataframe(
    table,
    column_config={
        "관객수": st.column_config.NumberColumn(format="%d명"),
        "누적관객": st.column_config.NumberColumn(format="%d명"),
        "스크린수": st.column_config.NumberColumn(format="%d개"),
    },
    use_container_width=True
)

st.subheader("📈 관객수 상위 5편")
top5 = table.sort_values("관객수", ascending=False).head(5)
st.bar_chart(top5.set_index("영화명")["관객수"], horizontal=True)
