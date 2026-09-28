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

# --- 資料抓取模組 ---
@st.cache_data(ttl=3600)
def get_market_data():
    df = yf.download("^TWII", period="1y", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    # 均線與扣抵
    df['5MA'] = df['Close'].rolling(5).mean()
    df['20MA'] = df['Close'].rolling(20).mean()
    df['60MA'] = df['Close'].rolling(60).mean()
    df['60MA_Deduct'] = df['Close'].shift(59)
    df['Vol_20MA'] = df['Volume'].rolling(20).mean()
    
    # MACD
    exp1 = df['Close'].ewm(span=12, adjust=False).mean()
    exp2 = df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD'] = exp1 - exp2
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['Signal']
    
    # KD
    low_min = df['Low'].rolling(9).min()
    high_max = df['High'].rolling(9).max()
    df['RSV'] = 100 * (df['Close'] - low_min) / (high_max - low_min)
    df['K'] = df['RSV'].ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    
    return df.dropna()

@st.cache_data(ttl=3600)
def get_foreign_oi():
    """透過 FinMind API 抓取外資台指期未平倉 (終極防護版)"""
    
    # 這裡填入你的 API Token
    FINMIND_TOKEN = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoiY29rZXJudXQwNUBnbWFpbC5jb20iLCJlbWFpbCI6ImNva2VybnV0MDVAZ21haWwuY29tIiwidG9rZW5fdmVyc2lvbiI6MH0.GlzIUeSky4e4XeYhcaK5XoT4nwj1n3Wk_GSwhHyBHnc'
    
    try:
        start_date = (datetime.datetime.now() - datetime.timedelta(days=15)).strftime('%Y-%m-%d')
        url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanFuturesInstitutionalInvestors&data_id=TX&start_date={start_date}&token={FINMIND_TOKEN}"
        
        res = requests.get(url, timeout=5)
        data = res.json()
        
        # 1. 檢查官方回傳狀態
        if data.get('msg') != 'success':
            st.error(f"🚨 連線失敗！官方回報：{data.get('msg')}")
            return None
            
        raw_data = data.get('data', [])
        
        # 2. 防呆機制：如果回傳的是空資料
        if not raw_data or len(raw_data) == 0:
            st.error("🚨 連線成功，但 FinMind 系統回傳了「空資料」。(可能剛好遇到官方主機維護中)")
            return None
            
        df = pd.DataFrame(raw_data)
        
        # 3. 智慧尋找包含「外資」字眼的欄位 (不怕官方改名)
        investor_col = None
        for col in df.columns:
            # 檢查該欄位中是否含有「外資」兩個字
            if df[col].astype(str).str.contains('外資').any():
                investor_col = col
                break
                
        if not investor_col:
            st.error(f"🚨 找不到法人的欄位！目前抓到的欄位有：{', '.join(df.columns)}")
            return None
            
        # 取出外資的資料
        df_foreign = df[df[investor_col].str.contains('外資', na=False)]
        last_row = df_foreign.iloc[-1]
        
        # 4. 智慧尋找「未平倉」數值的欄位 (包容多種命名)
        oi_col = None
        for col in ['open_interest_net_volume', 'NetOpenInterest']:
            if col in df.columns:
                oi_col = col
                break
        
        if oi_col:
            return int(last_row[oi_col])
        elif 'long_open_interest' in df.columns and 'short_open_interest' in df.columns:
            # 如果只提供多單與空單，我們自己算淨額
            return int(last_row['long_open_interest'] - last_row['short_open_interest'])
        else:
            st.error(f"🚨 找不到未平倉數值欄位！目前的欄位有：{', '.join(df.columns)}")
            return None
            
    except Exception as e:
        st.error(f"🚨 發生預期外的錯誤：{e}")
        return None
            
        last_row = df_foreign.iloc[-1]
        
        # 診斷 3：自動適應 FinMind 各種可能的「未平倉」欄位命名
        if 'open_interest_net_volume' in df.columns:
            return int(last_row['open_interest_net_volume'])
        elif 'NetOpenInterest' in df.columns:
            return int(last_row['NetOpenInterest'])
        elif 'long_open_interest' in df.columns and 'short_open_interest' in df.columns:
            return int(last_row['long_open_interest'] - last_row['short_open_interest'])
        else:
            # 如果欄位全都對不上，把現有欄位全部印出來給我們看！
            st.error(f"🚨 找不到未平倉欄位！目前 FinMind 提供的欄位有：{', '.join(df.columns)}")
            return None
            
    except Exception as e:
        st.error(f"🚨 系統發生預期外錯誤：{e}")
        return None

try:
    with st.spinner("同步證交所與期交所資料中..."):
        df = get_market_data()
        latest = df.iloc[-1]
        foreign_oi = get_foreign_oi()
    
    st.subheader(f"加權指數：{latest['Close']:,.0f}")
    
    # === 第一區：技術面大盤結構 ===
    st.markdown("### 📈 技術面結構")
    
    short_bull = (latest['Close'] > latest['5MA']) and (latest['K'] > latest['D'])
    short_signal = "🟢 偏多" if short_bull else "🔴 偏空"
    
    mid_bull = (latest['Close'] > latest['60MA']) and (latest['Close'] > latest['60MA_Deduct'])
    mid_signal = "🟢 季線上彎" if mid_bull else "🔴 季線下彎"
    
    macd_signal = "🟢 動能強勢" if latest['MACD_Hist'] > 0 else "🔴 動能弱勢"

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("短期 (5MA+KD)", short_signal, f"5MA: {latest['5MA']:,.0f}")
    with col2:
        st.metric("中期 (季線)", mid_signal, f"扣抵: {latest['60MA_Deduct']:,.0f}")
    with col3:
        st.metric("波段 (MACD)", macd_signal, f"值: {latest['MACD']:.0f}")

    st.divider()

    # === 第二區：籌碼與動能 ===
    st.markdown("### 💰 籌碼與資金動能")
    
    col4, col5 = st.columns(2)
    with col4:
        # 外資期貨未平倉邏輯判斷
        if foreign_oi is None:
            st.metric("外資期指淨未平倉", "資料讀取中", "")
        else:
            if foreign_oi <= -90000:
                oi_signal = "🔴 警戒 (重度避險)"
            elif foreign_oi < 0:
                oi_signal = "🟡 偏空 (微幅避險)"
            else:
                oi_signal = "🟢 偏多 (多單留倉)"
            st.metric("外資期指淨未平倉", oi_signal, f"{foreign_oi:,.0f} 口")
            
    with col5:
        # 量能邏輯判斷 (今日成交量是否大於月均量)
        if latest['Volume'] > latest['Vol_20MA']:
            vol_signal = "🔥 資金活絡 (帶量)"
        else:
            vol_signal = "❄️ 觀望氣氛 (量縮)"
        st.metric("大盤量能 (相較月均量)", vol_signal, "")

    st.divider()
    
    # === 第三區：核心警報器 ===
    if latest['Close'] < latest['60MA_Deduct']:
        st.error(f"🚨 **破線警報：** 目前指數 ({latest['Close']:,.0f}) 已低於季線扣抵值 ({latest['60MA_Deduct']:,.0f})。季線將加速下彎，請嚴格控管資金水位！")
    elif foreign_oi is not None and foreign_oi <= -90000:
        st.error(f"🚨 **籌碼警報：** 外資淨空單高達 {foreign_oi:,.0f} 口，機構法人正進行系統性避險，提防大崩跌！")
    else:
        st.success("✅ **安全區間：** 目前指數高於季線扣抵，且無極端異常籌碼，多方結構健康。")

except Exception as e:
    st.error(f"資料讀取失敗，請確認網路狀態。({e})")
