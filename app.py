import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import datetime

st.set_page_config(page_title="台股多空戰情室", page_icon="📊", layout="centered")

# --- 解除文字截斷的 CSS 魔法 (終極版) ---
st.markdown(
    """
    <style>
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

st.title("📊 台股多空趨勢戰情室")

# ==========================================
#         資料抓取核心模組
# ==========================================
@st.cache_data(ttl=3600)
def get_market_data():
    df = yf.download("^TWII", period="1y", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    df['5MA'] = df['Close'].rolling(5).mean()
    df['20MA'] = df['Close'].rolling(20).mean()
    df['60MA'] = df['Close'].rolling(60).mean()
    df['60MA_Deduct'] = df['Close'].shift(59)
    df['Vol_20MA'] = df['Volume'].rolling(20).mean()
    
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['Signal']
    
    low_min = df['Low'].rolling(9).min()
    high_max = df['High'].rolling(9).max()
    df['RSV'] = 100 * (df['Close'] - low_min) / (high_max - low_min)
    df['K'] = df['RSV'].ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    
    return df.dropna()

@st.cache_data(ttl=3600)
def get_foreign_oi():
    # 👇👇👇 請在這裡貼上你的 FinMind Token 👇👇👇
    FINMIND_TOKEN = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoiY29rZXJudXQwNUBnbWFpbC5jb20iLCJlbWFpbCI6ImNva2VybnV0MDVAZ21haWwuY29tIiwidG9rZW5fdmVyc2lvbiI6MH0.GlzIUeSky4e4XeYhcaK5XoT4nwj1n3Wk_GSwhHyBHnc'
    
    try:
        start_date = (datetime.datetime.now() - datetime.timedelta(days=15)).strftime('%Y-%m-%d')
        url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanFuturesInstitutionalInvestors&data_id=TX&start_date={start_date}&token={FINMIND_TOKEN}"
        
        res = requests.get(url, timeout=5)
        data = res.json()
        
        if data.get('msg') != 'success': return None
        raw_data = data.get('data', [])
        if not raw_data or len(raw_data) == 0: return None
            
        df = pd.DataFrame(raw_data)
        
        investor_col = None
        for col in df.columns:
            if df[col].astype(str).str.contains('外資').any():
                investor_col = col
                break
        if not investor_col: return None
            
        df_foreign = df[df[investor_col].str.contains('外資', na=False)]
        last_row = df_foreign.iloc[-1]
        
        long_oi = last_row.get('long_open_interest_balance_volume', 0)
        short_oi = last_row.get('short_open_interest_balance_volume', 0)
        return int(long_oi) - int(short_oi)
            
    except:
        return None

# ==========================================
#         大盤戰情室 (前三區)
# ==========================================
try:
    with st.spinner("同步大盤與籌碼資料中..."):
        df = get_market_data()
        latest = df.iloc[-1]
        foreign_oi = get_foreign_oi()
    
    st.subheader(f"加權指數：{latest['Close']:,.0f}")
    
    # === 第一區：技術面大盤結構 ===
    st.markdown("### 📈 技術面結構")
    s_bull = (latest['Close'] > latest['5MA']) and (latest['K'] > latest['D'])
    m_bull = (latest['Close'] > latest['60MA']) and (latest['Close'] > latest['60MA_Deduct'])
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("短期 (5MA+KD)", "🟢 偏多" if s_bull else "🔴 偏空", f"5MA: {latest['5MA']:,.0f}")
    with col2:
        st.metric("中期 (季線)", "🟢 季線上彎" if m_bull else "🔴 季線下彎", f"扣抵: {latest['60MA_Deduct']:,.0f}")
    with col3:
        st.metric("波段 (MACD)", "🟢 動能強勢" if latest['MACD_Hist'] > 0 else "🔴 動能弱勢", f"值: {latest['MACD']:.0f}")

    st.divider()

    # === 第二區：籌碼與動能 ===
    st.markdown("### 💰 籌碼與資金動能")
    col4, col5 = st.columns(2)
    with col4:
        if foreign_oi is None:
            st.metric("外資期指淨未平倉", "資料讀取中", "")
        else:
            oi_sig = "🔴 警戒" if foreign_oi <= -90000 else "🟡 偏空" if foreign_oi < 0 else "🟢 偏多"
            st.metric("外資期指淨未平倉", oi_sig, f"{foreign_oi:,.0f} 口")
            
    with col5:
        vol_sig = "🔥 資金活絡(帶量)" if latest['Volume'] > latest['Vol_20MA'] else "❄️ 觀望氣氛(量縮)"
        st.metric("大盤量能 (相較月均)", vol_sig, "")

    st.divider()
    
    # === 第三區：核心警報器 ===
    if latest['Close'] < latest['60MA_Deduct']:
        st.error(f"🚨 **破線警報：** 目前指數已低於季線扣抵值 ({latest['60MA_Deduct']:,.0f})。季線將加速下彎，請嚴格控管資金！")
    elif foreign_oi is not None and foreign_oi <= -90000:
        st.error(f"🚨 **籌碼警報：** 外資淨空單高達 {foreign_oi:,.0f} 口，機構法人正進行避險，提防大崩跌！")
    else:
        st.success("✅ **安全區間：** 目前指數高於季線扣抵，且無極端異常籌碼，多方結構健康。")

except Exception as e:
    st.error(f"大盤資料讀取失敗，請確認網路狀態。({e})")

# ==========================================
#         個股健診 (第四區) 獨立於大盤錯誤之外
# ==========================================
st.divider()
st.markdown("### 🏥 自選股即時健診")

user_ticker = st.text_input("請輸入台股代號 (如 2330)：", "2330")

if user_ticker:
    ticker_symbol = f"{user_ticker}.TW"
    try:
        with st.spinner(f"正在診斷 {user_ticker} 中..."):
            stock_df = yf.download(ticker_symbol, period="1y", progress=False)
            if isinstance(stock_df.columns, pd.MultiIndex):
                stock_df.columns = stock_df.columns.get_level_values(0)
            
            if stock_df.empty:
                st.warning(f"找不到代號 {user_ticker}，請確認是否輸入正確。")
            else:
                stock_df['5MA'] = stock_df['Close'].rolling(5).mean()
                stock_df['60MA'] = stock_df['Close'].rolling(60).mean()
                stock_df['60MA_Deduct'] = stock_df['Close'].shift(59)
                
                macd = stock_df['Close'].ewm(span=12, False).mean() - stock_df['Close'].ewm(span=26, False).mean()
                stock_df['MACD_Hist'] = macd - macd.ewm(span=9, False).mean()
                
                latest_s = stock_df.iloc[-1]
                st.markdown(f"**最新收盤價：{latest_s['Close']:,.1f}**")
                
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("5日均線", "🟢 偏多" if latest_s['Close'] > latest_s['5MA'] else "🔴 偏空", f"{latest_s['5MA']:.1f}")
                with c2:
                    st.metric("季線扣抵", "🟢 有支撐" if latest_s['Close'] > latest_s['60MA_Deduct'] else "🔴 破線", f"{latest_s['60MA_Deduct']:.1f}")
                with c3:
                    st.metric("MACD動能", "🟢 轉強" if latest_s['MACD_Hist'] > 0 else "🔴 轉弱", f"{latest_s['MACD_Hist']:.2f}")
                    
    except Exception as e:
        st.error("個股資料讀取失敗，請確認代號是否正確。")
