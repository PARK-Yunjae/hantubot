import streamlit as st
import json
import os
import glob
import pandas as pd
import random

# Page Config
st.set_page_config(
    page_title="Hantubot Nomad",
    page_icon="🦅",
    layout="wide"
)

# Mental Care Quotes
QUOTES = [
    "매수는 기술이고 매도는 예술이다.",
    "확신이 들지 않으면 매매하지 마라.",
    "잃지 않는 것이 버는 것보다 중요하다.",
    "시장은 언제나 옳다.",
    "욕심을 버리면 수익이 보인다.",
    "뇌동매매 금지! 원칙 매매 준수!",
    "오늘은 오늘의 태양이 뜬다.",
    "계좌를 지키는 것이 내일을 위한 투자다."
]

def load_data(date_str):
    file_path = os.path.join("data", f"daily_report_{date_str}.json")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def get_available_dates():
    files = glob.glob(os.path.join("data", "daily_report_*.json"))
    dates = []
    for f in files:
        basename = os.path.basename(f)
        # daily_report_20240101.json -> 20240101
        date_part = basename.replace("daily_report_", "").replace(".json", "")
        dates.append(date_part)
    dates.sort(reverse=True)
    return dates

def main():
    # Sidebar
    st.sidebar.title("Nomad Control")
    
    dates = get_available_dates()
    if not dates:
        st.warning("No data found. Please run 'run_study_v3.py' first.")
        return

    selected_date = st.sidebar.selectbox("Select Date", dates)
    
    # Mental Care
    st.sidebar.markdown("---")
    st.sidebar.subheader("💆 Mental Care")
    st.sidebar.info(random.choice(QUOTES))

    # Main Content
    data = load_data(selected_date)
    
    if data:
        st.header(f"📅 Daily Report: {selected_date}")
        st.metric("Total Candidates", data.get("count", 0))
        
        items = data.get("items", [])
        if items:
            df = pd.DataFrame(items)
            
            # Format Formatting
            # 'close', 'volume', 'amount' -> integer with commas
            # 'change' -> percentage
            
            # Display Table
            st.subheader("Candidate List")
            
            # Column config
            st.dataframe(
                df,
                column_config={
                    "ticker": "Ticker",
                    "name": "Name",
                    "close": st.column_config.NumberColumn("Price", format="%d원"),
                    "change": st.column_config.NumberColumn("Change", format="%.2f%%"),
                    "volume": st.column_config.NumberColumn("Volume", format="%d"),
                    "amount": st.column_config.NumberColumn("Amount (Won)", format="%d"),
                    "reasons": "Reasons"
                },
                use_container_width=True,
                hide_index=True
            )
            
            # Breakdown by Reason
            st.subheader("Analysis")
            upper_limit = [i for i in items if "Upper Limit" in i['reasons']]
            top_volume = [i for i in items if "Top Volume" in i['reasons']]
            
            col1, col2 = st.columns(2)
            with col1:
                st.info(f"🚀 Upper Limit: {len(upper_limit)}")
                for item in upper_limit:
                    st.write(f"- {item['name']} ({item['change']}%)")
            
            with col2:
                st.warning(f"🔥 Top Volume: {len(top_volume)}")
                for item in top_volume:
                    st.write(f"- {item['name']} ({item['amount']//100000000}억)")

    else:
        st.error(f"Failed to load data for {selected_date}")

if __name__ == "__main__":
    main()
