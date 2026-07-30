import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import plotly.express as px

st.set_page_config(page_title="박스오피스 대시보드 및 데이터 분석", layout="wide")
st.title("🎬 박스오피스 대시보드 & 계절별 분석")

# 비밀 금고에서 인증키 꺼내기
KOBIS_KEY = st.secrets.get("KOBIS_KEY", "")

if not KOBIS_KEY:
    st.error("KOBIS_KEY가 st.secrets에 설정되지 않았습니다.")
    st.stop()

# 한국 시간 기준 오늘 및 어제 날짜 계산
today_seoul = datetime.now(ZoneInfo("Asia/Seoul")).date()
yesterday = today_seoul - timedelta(days=1)

# API 호출 함수 (캐싱 적용)
@st.cache_data(ttl=3600)
def get_box_office_data(key, dt):
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    try:
        res = requests.get(url, params={"key": key, "targetDt": dt}, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return None

# 탭 구성: 1) 일별 대시보드, 2) 계절별 총량 분석
tab1, tab2 = st.tabs(["🗓️ 일별 박스오피스", "🍂 계절별 박스오피스 총량 분석"])

# ==========================================
# TAB 1: 일별 박스오피스
# ==========================================
with tab1:
    st.subheader("일별 박스오피스 조회")
    
    selected_date = st.date_input(
        "조회할 날짜를 선택하세요",
        value=yesterday,
        max_value=yesterday,
        key="daily_date_picker"
    )

    target_dt = selected_date.strftime("%Y%m%d")
    st.caption(f"선택한 조회 기준일: {selected_date.strftime('%Y-%m-%d')}")

    data = get_box_office_data(KOBIS_KEY, target_dt)

    if not data:
        st.error("서버 연결에 실패했거나 응답이 없습니다.")
    elif "faultInfo" in data:
        st.error("인증키가 올바르지 않습니다. Secrets의 KOBIS_KEY를 확인해 주세요.")
    else:
        box_list = data.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])

        if not box_list:
            st.warning("그날은 아직 집계 전입니다")
        else:
            df = pd.DataFrame(box_list)

            for col in ["rank", "rankInten", "audiCnt", "audiAcc", "scrnCnt", "showCnt"]:
                df[col] = pd.to_numeric(df[col])

            def format_rank_change(inten):
                if inten > 0:
                    return f"🔺 +{inten}"
                elif inten < 0:
                    return f"🔹 {inten}"
                else:
                    return "-"

            df["순위변동"] = df["rankInten"].apply(format_rank_change)

            def format_movie_title(row):
                title = row["movieNm"]
                if row["audiAcc"] >= 1_000_000:
                    title += " 🏆"
                return title

            df["표시영화명"] = df.apply(format_movie_title, axis=1)

            # 지표 카드
            top = df.sort_values("rank").iloc[0]
            c1, c2, c3 = st.columns(3)
            c1.metric("해당 일자 1위", top["표시영화명"])
            c2.metric("일일 관객수", f"{top['audiCnt']:,}명")
            c3.metric("누적 관객", f"{top['audiAcc']:,}명")

            # 표
            table = df[["rank", "순위변동", "표시영화명", "openDt", "audiCnt", "audiAcc", "scrnCnt"]].copy()
            table.columns = ["순위", "순위 변동", "영화명", "개봉일", "관객수", "누적관객", "스크린수"]
            table = table.sort_values("순위").reset_index(drop=True)

            st.markdown("#### 📋 박스오피스 TOP 10")
            st.dataframe(
                table,
                column_config={
                    "관객수": st.column_config.NumberColumn(format="%d명"),
                    "누적관객": st.column_config.NumberColumn(format="%d명"),
                    "스크린수": st.column_config.NumberColumn(format="%d개"),
                },
                use_container_width=True
            )

            st.markdown("#### 📈 관객수 상위 5편")
            top5 = table.sort_values("관객수", ascending=False).head(5)
            st.bar_chart(top5.set_index("영화명")["관객수"], horizontal=True)

# ==========================================
# TAB 2: 계절별 박스오피스 총량 분석
# ==========================================
with tab2:
    st.subheader("❄️🌸☀️🍂 계절별 극장가 관객 총량 분석")
    st.markdown("""
    지정한 기간 동안 일별 박스오피스 TOP 10 전체 관객수 및 매출액을 수집하여 **계절별(봄·여름·가을·겨울)** 총 극장 이용 트렌드를 분석합니다.
    """)

    # 기간 선택 (기본값: 최근 1년)
    col_s, col_e = st.columns(2)
    start_date = col_s.date_input("분석 시작일", value=yesterday - timedelta(days=365), max_value=yesterday, key="season_start")
    end_date = col_e.date_input("분석 종료일", value=yesterday, max_value=yesterday, key="season_end")

    if start_date > end_date:
        st.error("시작일은 종료일보다 이전이어야 합니다.")
        st.stop()

    days_diff = (end_date - start_date).days + 1

    if days_diff > 366:
        st.warning("⚠️ API 호출량이 많아 분석 기간이 1년을 초과하면 시간이 다소 걸릴 수 있습니다.")

    if st.button("🚀 계절별 데이터 수집 및 분석 시작", type="primary"):
        daily_records = []
        progress_bar = st.progress(0)
        status_text = st.empty()

        # 일별 데이터 수집
        curr_date = start_date
        step = 0

        while curr_date <= end_date:
            dt_str = curr_date.strftime("%Y%m%d")
            status_text.text(f"데이터 수집 중... ({curr_date.strftime('%Y-%m-%d')} / {step + 1}/{days_diff}일)")
            
            res_data = get_box_office_data(KOBIS_KEY, dt_str)
            if res_data and "boxOfficeResult" in res_data:
                daily_list = res_data["boxOfficeResult"].get("dailyBoxOfficeList", [])
                if daily_list:
                    tot_audi = sum(int(m.get("audiCnt", 0)) for m in daily_list)
                    tot_sales = sum(int(m.get("salesAmt", 0)) for m in daily_list)
                    
                    # 월 기준으로 계절 분류
                    month = curr_date.month
                    if month in [3, 4, 5]:
                        season = "봄 (3~5월)"
                    elif month in [6, 7, 8]:
                        season = "여름 (6~8월)"
                    elif month in [9, 10, 11]:
                        season = "가을 (9~11월)"
                    else:
                        season = "겨울 (12~2월)"

                    daily_records.append({
                        "date": curr_date,
                        "year": curr_date.year,
                        "month": month,
                        "season": season,
                        "total_audi": tot_audi,
                        "total_sales": tot_sales
                    })

            curr_date += timedelta(days=1)
            step += 1
            progress_bar.progress(step / days_diff)

        status_text.empty()
        progress_bar.empty()

        if not daily_records:
            st.warning("수집된 박스오피스 데이터가 없습니다.")
        else:
            season_df = pd.DataFrame(daily_records)

            # 계절 순서 정렬을 위한 Categorical 설정
            season_order = ["봄 (3~5월)", "여름 (6~8월)", "가을 (9~11월)", "겨울 (12~2월)"]
            season_df["season"] = pd.Categorical(season_df["season"], categories=season_order, ordered=True)

            # 계절별 집계
            summary = season_df.groupby("season", observed=False).agg(
                총관객수=("total_audi", "sum"),
                총매출액=("total_sales", "sum"),
                조회일수=("date", "count"),
                일평균관객수=("total_audi", "mean")
            ).reset_index()

            # 요약 지표 카드
            best_season = summary.sort_values("총관객수", ascending=False).iloc[0]
            m1, m2, m3 = st.columns(3)
            m1.metric("총 분석 일수", f"{len(season_df)}일")
            m2.metric("가장 관객이 많은 계절", f"{best_season['season']}")
            m3.metric("해당 계절 일평균 관객수", f"{int(best_season['일평균관객수']):,}명")

            st.divider()

            # 시각화 (Plotly)
            chart_col1, chart_col2 = st.columns(2)

            with chart_col1:
                st.markdown("##### 📊 계절별 총 관객수 비교")
                fig_bar = px.bar(
                    summary,
                    x="season",
                    y="총관객수",
                    color="season",
                    text_auto=",.0f",
                    labels={"season": "계절", "총관객수": "총 관객수(명)"},
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                fig_bar.update_traces(textposition="outside")
                fig_bar.update_layout(showlegend=False, yaxis_title="총 관객수 (명)")
                st.plotly_chart(fig_bar, use_container_width=True)

            with chart_col2:
                st.markdown("##### 🥧 계절별 관객 점유율")
                fig_pie = px.pie(
                    summary,
                    names="season",
                    values="총관객수",
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                fig_pie.update_traces(textinfo="percent+label")
                st.plotly_chart(fig_pie, use_container_width=True)

            # 데이터 표
            st.markdown("##### 📋 계절별 집계 상세 데이터")
            st.dataframe(
                summary,
                column_config={
                    "총관객수": st.column_config.NumberColumn(format="%d명"),
                    "총매출액": st.column_config.NumberColumn(format="%d원"),
                    "조회일수": st.column_config.NumberColumn(format="%d일"),
                    "일평균관객수": st.column_config.NumberColumn(format="%d명"),
                },
                use_container_width=True
            )
