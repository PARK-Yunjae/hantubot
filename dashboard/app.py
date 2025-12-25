# dashboard/app.py
"""
유목민 공부법 Streamlit 대시보드 - 메인 페이지
"""
import streamlit as st
import pandas as pd
from datetime import datetime
import plotly.express as px
from utils.db_loader import load_study_data, load_all_run_dates, load_ticker_frequency


# 한글 매핑 함수
def translate_reason_flag(reason_flag):
    """선정 사유를 한글로 변환"""
    mapping = {
        'limit_up': '상한가',
        'volume_10m': '거래량 천만주',
        'both': '상한가 + 거래량',
        'limit_up / volume_10m': '상한가 + 거래량',
        'volume_10m / limit_up': '상한가 + 거래량'
    }
    return mapping.get(reason_flag, reason_flag)


def translate_status(status):
    """상태를 한글로 변환"""
    mapping = {
        'pending': '대기중',
        'news_collected': '뉴스 수집 완료',
        'no_news': '뉴스 없음',
        'news_failed': '뉴스 수집 실패',
        'summarized': 'AI 요약 완료',
        'summary_failed': 'AI 요약 실패',
        'completed': '완료'
    }
    return mapping.get(status, status)

# 페이지 설정
st.set_page_config(
    page_title="유목민 공부법 대시보드",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 제목
st.title("📚 유목민 공부법 (100일 공부) 대시보드")
st.markdown("---")

# 사이드바: 날짜 선택
with st.sidebar:
    st.header("📅 날짜 선택")
    
    try:
        run_dates = load_all_run_dates(limit=100)
        
        if not run_dates:
            st.warning("데이터가 없습니다. 먼저 유목민 공부법을 실행해주세요.")
            st.stop()
        
        # 날짜 포맷팅 (YYYYMMDD → YYYY-MM-DD)
        formatted_dates = {
            f"{date[:4]}-{date[4:6]}-{date[6:8]}": date 
            for date in run_dates
        }
        
        selected_date_formatted = st.selectbox(
            "날짜 선택",
            options=list(formatted_dates.keys()),
            index=0
        )
        
        selected_date = formatted_dates[selected_date_formatted]
        
        st.markdown("---")
        st.info(f"💾 선택된 날짜: **{selected_date_formatted}**")
    
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")
        st.stop()

# 메인 데이터 로드
try:
    data = load_study_data(selected_date)
    run_info = data['run_info']
    candidates = data['candidates']
    news_by_ticker = data['news']
    summaries_by_ticker = data['summaries']
    
    if not candidates:
        st.warning(f"{selected_date_formatted}에 데이터가 없습니다.")
        st.stop()

except Exception as e:
    st.error(f"데이터 로드 중 오류: {e}")
    st.stop()

# ==================== 통계 요약 ====================
st.header("📊 오늘의 통계")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("후보 종목", f"{len(candidates)}개")

with col2:
    total_news = sum(len(news) for news in news_by_ticker.values())
    st.metric("뉴스 수집", f"{total_news}개")

with col3:
    st.metric("AI 요약", f"{len(summaries_by_ticker)}개")

with col4:
    if run_info:
        status_emoji = {"success": "✅", "partial": "⚠️", "fail": "❌"}
        status = run_info.get('status', 'unknown')
        st.metric("상태", f"{status_emoji.get(status, '❓')} {status}")

st.markdown("---")

# ==================== 필터링 ====================
st.header("🔍 종목 필터")

col_filter1, col_filter2, col_filter3 = st.columns(3)

with col_filter1:
    # 시장 필터
    markets = list(set(c['market'] for c in candidates if c.get('market')))
    selected_markets = st.multiselect(
        "시장",
        options=markets,
        default=markets
    )

with col_filter2:
    # 선정 사유 필터
    reasons = list(set(c['reason_flag'] for c in candidates if c.get('reason_flag')))
    selected_reasons = st.multiselect(
        "선정 사유",
        options=reasons,
        default=reasons
    )

with col_filter3:
    # 키워드 검색
    search_keyword = st.text_input("종목명 검색", "")

# 필터 적용
filtered_candidates = candidates

if selected_markets:
    filtered_candidates = [c for c in filtered_candidates if c.get('market') in selected_markets]

if selected_reasons:
    filtered_candidates = [c for c in filtered_candidates if c.get('reason_flag') in selected_reasons]

if search_keyword:
    filtered_candidates = [
        c for c in filtered_candidates 
        if search_keyword.lower() in c['name'].lower() or search_keyword in c['ticker']
    ]

st.markdown("---")

# ==================== 후보 종목 테이블 ====================
st.header(f"📋 후보 종목 ({len(filtered_candidates)}개)")

if filtered_candidates:
    # DataFrame 생성
    df_candidates = pd.DataFrame(filtered_candidates)
    
    # 표시할 컬럼 선택 (먼저 선택)
    display_columns = {
        'ticker': '종목코드',
        'name': '종목명',
        'market': '시장',
        'close_price': '종가',
        'change_pct': '등락률(%)',
        'volume': '거래량',
        'reason_flag': '선정사유',
        'data_collection_status': '상태'
    }
    
    df_display = df_candidates[[col for col in display_columns.keys() if col in df_candidates.columns]].copy()
    
    # 한글 번역 적용 (컬럼명 변경 전)
    if 'reason_flag' in df_display.columns:
        df_display['reason_flag'] = df_display['reason_flag'].apply(translate_reason_flag)
    if 'data_collection_status' in df_display.columns:
        df_display['data_collection_status'] = df_display['data_collection_status'].apply(translate_status)
    
    # 컬럼명을 한글로 변경
    df_display.columns = [display_columns[col] for col in df_display.columns]
    
    # 숫자 포맷팅
    if '종가' in df_display.columns:
        df_display['종가'] = df_display['종가'].apply(lambda x: f"{x:,}원" if pd.notnull(x) else "-")
    if '거래량' in df_display.columns:
        df_display['거래량'] = df_display['거래량'].apply(lambda x: f"{x:,}주" if pd.notnull(x) else "-")
    if '등락률(%)' in df_display.columns:
        df_display['등락률(%)'] = df_display['등락률(%)'].apply(lambda x: f"{x:.2f}%" if pd.notnull(x) else "-")
    
    # 테이블 표시
    st.dataframe(
        df_display,
        use_container_width=True,
        height=400
    )
    
    # ==================== 종목 상세 정보 ====================
    st.markdown("---")
    st.header("🔍 종목 상세 정보")
    
    # 종목 선택
    selected_ticker = st.selectbox(
        "종목 선택",
        options=[f"{c['name']} ({c['ticker']})" for c in filtered_candidates],
        index=0
    )
    
    # 선택된 종목 정보 추출
    ticker_code = selected_ticker.split('(')[1].rstrip(')')
    selected_candidate = next((c for c in filtered_candidates if c['ticker'] == ticker_code), None)
    
    if selected_candidate:
        col_detail1, col_detail2 = st.columns([1, 2])
        
        with col_detail1:
            st.subheader("📊 시세 정보")
            st.metric("종목명", selected_candidate['name'])
            st.metric("종목코드", selected_candidate['ticker'])
            st.metric("시장", selected_candidate.get('market', '-'))
            st.metric("종가", f"{selected_candidate['close_price']:,}원")
            st.metric("등락률", f"{selected_candidate['change_pct']:.2f}%")
            st.metric("거래량", f"{selected_candidate['volume']:,}주")
            st.metric("선정 사유", selected_candidate['reason_flag'])
        
        with col_detail2:
            # AI 요약
            st.subheader("🤖 AI 요약")
            summary = summaries_by_ticker.get(ticker_code)
            
            if summary:
                st.info(summary['summary_text'])
                st.caption(f"모델: {summary.get('llm_model', 'unknown')} | 생성일: {summary.get('created_at', '-')}")
            else:
                st.warning("AI 요약이 생성되지 않았습니다.")
            
            # 뉴스 리스트
            st.subheader("📰 관련 뉴스")
            news_items = news_by_ticker.get(ticker_code, [])
            
            if news_items:
                for i, news in enumerate(news_items, 1):
                    with st.expander(f"[{i}] {news['title']}"):
                        st.markdown(f"**발행처:** {news.get('publisher', '알 수 없음')}")
                        st.markdown(f"**발행 시간:** {news.get('published_at', '알 수 없음')}")
                        st.markdown(f"**요약:** {news.get('snippet', '내용 없음')}")
                        st.markdown(f"[🔗 기사 보기]({news['url']})")
            else:
                st.warning("관련 뉴스가 없습니다.")

else:
    st.warning("필터 조건에 맞는 종목이 없습니다.")

# ==================== 빈도 분석 ====================
st.markdown("---")
st.header("📈 종목 등장 빈도 분석 (최근 100일)")

try:
    freq_data = load_ticker_frequency(days=100)
    
    if freq_data:
        df_freq = pd.DataFrame(freq_data).head(20)
        
        # 차트
        fig = px.bar(
            df_freq,
            x='count',
            y='name',
            orientation='h',
            title='상위 20개 종목 등장 빈도',
            labels={'count': '등장 횟수', 'name': '종목명'},
            color='count',
            color_continuous_scale='Blues'
        )
        fig.update_layout(height=600, yaxis={'categoryorder': 'total ascending'})
        
        st.plotly_chart(fig, use_container_width=True)
        
        # 테이블
        with st.expander("📊 전체 데이터 보기"):
            st.dataframe(df_freq, use_container_width=True)
    else:
        st.info("빈도 분석 데이터가 없습니다.")

except Exception as e:
    st.error(f"빈도 분석 로드 실패: {e}")

# ==================== 푸터 ====================
st.markdown("---")
st.caption("💡 Tip: 사이드바에서 다른 날짜를 선택하여 과거 데이터를 확인할 수 있습니다.")
st.caption("🔄 데이터는 매일 장 마감 후 자동으로 수집됩니다.")
