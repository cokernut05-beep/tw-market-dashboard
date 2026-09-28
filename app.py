import streamlit as st
import yfinance as yf
import pandas as pd
import datetime

st.set_page_config(page_title="台股多空戰情室", page_icon="📊", layout="centered")
st.title("📊 台股多空趨勢戰情室")

st.markdown(
    """
    <style>
    /* 強制讓 Metric 的所有內外層文字自動換行 */
    [data-testid="stMetricValue"], 
    [data-testid="stMetricValue"] > div {
        white-space: normal !important;
        word-break: break-word !important;
        font-size: 22px !important; 
    }
    </style>
    """,
    unsafe_allow_html=True
)
@st.cache_data(ttl=3600)
def get_market_data():
    # 抓取台股大盤資料 (^TWII)
    df = yf.download("^TWII", period="1y", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    # 計算均線與季線扣抵值 (60天前價格)
    df['5MA'] = df['Close'].rolling(5).mean()
    df['20MA'] = df['Close'].rolling(20).mean()
    df['60MA'] = df['Close'].rolling(60).mean()
    df['60MA_Deduct'] = df['Close'].shift(59) 
    
    # 計算 MACD (12, 26, 9)
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['Signal']
    
    # 計算 KD (9, 3, 3)
    low_min = df['Low'].rolling(9).min()
    high_max = df['High'].rolling(9).max()
    df['RSV'] = 100 * (df['Close'] - low_min) / (high_max - low_min)
    df['K'] = df['RSV'].ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    
    return df.dropna()

try:
    with st.spinner("抓取最新大盤資料中..."):
        df = get_market_data()
        latest = df.iloc[-1]
    
    st.subheader(f"加權指數 最新收盤：{latest['Close']:,.0f}")
    
    # --- 多空邏輯判定 ---
    short_bull = (latest['Close'] > latest['5MA']) and (latest['K'] > latest['D'])
    short_signal = "🟢 偏多" if short_bull else "🔴 偏空"
    
    mid_bull = (latest['Close'] > latest['60MA']) and (latest['Close'] > latest['60MA_Deduct'])
    mid_signal = "🟢 季線上彎 (多頭)" if mid_bull else "🔴 季線下彎 (空頭)"
    
    macd_signal = "🟢 動能強勢" if latest['MACD_Hist'] > 0 else "🔴 動能弱勢"

    # --- 視覺化卡片呈現 ---
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("短期走勢 (5MA+KD)", short_signal, f"5MA: {latest['5MA']:,.0f}")
    with col2:
        st.metric("中期走勢 (季線)", mid_signal, f"扣抵: {latest['60MA_Deduct']:,.0f}")
    with col3:
        st.metric("波段動能 (MACD)", macd_signal, f"MACD: {latest['MACD']:.0f}")

    st.divider()
    
    # --- 核心空方警報器 ---
    st.subheader("🚨 核心空方警報器 (扣抵值偵測)")
    if latest['Close'] < latest['60MA_Deduct']:
        st.error(f"**強烈警告：** 目前指數 ({latest['Close']:,.0f}) 低於 60 天前的扣抵值 ({latest['60MA_Deduct']:,.0f})。季線將加速下彎形成實質反壓，這是大空頭初期的關鍵特徵，請考慮避險！")
    else:
        st.success(f"**安全區間：** 目前指數高於季線扣抵值，季線具備實質支撐力道，多頭結構維持。")

except Exception as e:
    st.error("資料讀取失敗，請稍後再試。")
