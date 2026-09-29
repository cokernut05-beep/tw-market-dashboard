import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import datetime
import re
import plotly.graph_objects as go
from bs4 import BeautifulSoup

st.set_page_config(page_title="台股多空戰情室 4.0", page_icon="📊", layout="centered")

st.markdown(
    """
    <style>
    [data-testid="stMetricValue"], 
    [data-testid="stMetricValue"] > div {
        white-space: normal !important;
        word-break: break-word !important;
        font-size: 20px !important; 
    }
    </style>
    """, unsafe_allow_html=True
)

st.title("📊 台股多空戰情室 4.0")

# ==========================================
#         通用資料函數
# ==========================================
@st.cache_data(ttl=3600)
def get_market_data():
    df = yf.download("^TWII", period="1y", progress=False)
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df['5MA'] = df['Close'].rolling(5).mean()
    df['20MA'] = df['Close'].rolling(20).mean()
    df['60MA'] = df['Close'].rolling(60).mean()
    df['60MA_Deduct'] = df['Close'].shift(59)
    df['Vol_20MA'] = df['Volume'].rolling(20).mean()
    df['MACD'] = df['Close'].ewm(span=12, adjust=False).mean() - df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD_Hist'] = df['MACD'] - df['MACD'].ewm(span=9, adjust=False).mean()
    low_min, high_max = df['Low'].rolling(9).min(), df['High'].rolling(9).max()
    df['RSV'] = 100 * (df['Close'] - low_min) / (high_max - low_min)
    df['K'] = df['RSV'].ewm(com=2, adjust=False).mean()
    df['D'] = df['K'].ewm(com=2, adjust=False).mean()
    return df.dropna()

@st.cache_data(ttl=86400)
def get_stock_name(ticker):
    try:
        res = requests.get(f"https://tw.stock.yahoo.com/quote/{ticker}", headers={'User-Agent': 'Mozilla/5.0'}, timeout=3)
        match = re.search(r'<title>(.*?)\(', res.text)
        return match.group(1).strip() if match else ticker
    except:
        return ticker

# 👇👇👇 請在這裡貼上你的 FinMind Token 👇👇👇
FINMIND_TOKEN = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoiY29rZXJudXQwNUBnbWFpbC5jb20iLCJlbWFpbCI6ImNva2VybnV0MDVAZ21haWwuY29tIiwidG9rZW5fdmVyc2lvbiI6MH0.GlzIUeSky4e4XeYhcaK5XoT4nwj1n3Wk_GSwhHyBHnc'

@st.cache_data(ttl=3600)
def get_foreign_oi():
    try:
        start = (datetime.datetime.now() - datetime.timedelta(days=15)).strftime('%Y-%m-%d')
        url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanFuturesInstitutionalInvestors&data_id=TX&start_date={start}&token={FINMIND_TOKEN}"
        data = requests.get(url, timeout=5).json()
        if data.get('msg') != 'success' or not data.get('data'): return None
        df = pd.DataFrame(data['data'])
        inv_col = next((c for c in df.columns if df[c].astype(str).str.contains('外資').any()), None)
        if not inv_col: return None
        last_row = df[df[inv_col].str.contains('外資', na=False)].iloc[-1]
        return int(last_row.get('long_open_interest_balance_volume', 0)) - int(last_row.get('short_open_interest_balance_volume', 0))
    except: return None

@st.cache_data(ttl=3600)
def get_stock_chips(ticker):
    """抓取個股三大法人買賣超 (換算為張數)"""
    try:
        start = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime('%Y-%m-%d')
        url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id={ticker}&start_date={start}&token={FINMIND_TOKEN}"
        data = requests.get(url, timeout=5).json()
        if data.get('msg') != 'success' or not data.get('data'): return None
        df = pd.DataFrame(data['data'])
        latest_date = df['date'].max()
        df_latest = df[df['date'] == latest_date]
        
        f_df = df_latest[df_latest['name'].str.contains('外資', na=False)]
        t_df = df_latest[df_latest['name'].str.contains('投信', na=False)]
        
        # 買賣股數相減後除以 1000 變成「張數」
        f_net = (f_df['buy'].sum() - f_df['sell'].sum()) // 1000 if not f_df.empty else 0
        t_net = (t_df['buy'].sum() - t_df['sell'].sum()) // 1000 if not t_df.empty else 0
        return {"date": latest_date, "foreign": f_net, "trust": t_net}
    except: return None

@st.cache_data(ttl=1800)
def get_yahoo_ranking(url):
    try:
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
        soup = BeautifulSoup(res.text, 'html.parser')
        items = soup.find_all('li', class_='List(n)')
        result = []
        for i, item in enumerate(items[:5]):
            name = item.find('div', class_='Lh(20px)')
            if not name: continue
            spans = item.find_all('span')
            price = spans[0].text.strip() if len(spans)>0 else ""
            change = spans[1].text.strip() if len(spans)>1 else ""
            result.append(f"{i+1}. **{name.text.strip()}** ({price} | {change})")
        return "\n".join(result)
    except: return "讀取失敗"

# ==========================================
#         建立三個分頁
# ==========================================
tab1, tab2, tab3 = st.tabs(["📊 大盤與雷達", "🏥 個股深度健診", "📋 自選股總表"])

# --- 分頁 1：大盤與雷達 ---
with tab1:
    try:
        with st.spinner("同步大盤與籌碼資料中..."):
            df = get_market_data()
            latest = df.iloc[-1]
            foreign_oi = get_foreign_oi()
        
        st.subheader(f"加權指數：{latest['Close']:,.0f}")
        
        # 技術面
        s_bull = (latest['Close'] > latest['5MA']) and (latest['K'] > latest['D'])
        m_bull = (latest['Close'] > latest['60MA']) and (latest['Close'] > latest['60MA_Deduct'])
        c1, c2, c3 = st.columns(3)
        c1.metric("短期(5MA+KD)", "🟢 偏多" if s_bull else "🔴 偏空", f"5MA: {latest['5MA']:,.0f}")
        c2.metric("中期(季線)", "🟢 季線上彎" if m_bull else "🔴 季線下彎", f"扣抵: {latest['60MA_Deduct']:,.0f}")
        c3.metric("波段(MACD)", "🟢 動能強勢" if latest['MACD_Hist'] > 0 else "🔴 動能弱勢", f"值: {latest['MACD']:.0f}")

        st.divider()
        # 籌碼面
        c4, c5 = st.columns(2)
        if foreign_oi is None: c4.metric("外資期指淨未平倉", "讀取中")
        else: c4.metric("外資期指淨未平倉", "🔴 警戒" if foreign_oi <= -90000 else "🟡 偏空" if foreign_oi < 0 else "🟢 偏多", f"{foreign_oi:,.0f} 口")
        c5.metric("大盤量能", "🔥 帶量" if latest['Volume'] > latest['Vol_20MA'] else "❄️ 量縮", "")

        st.divider()
        if latest['Close'] < latest['60MA_Deduct']: st.error(f"🚨 **破線警報：** 指數低於季線扣抵，請控管資金！")
        elif foreign_oi is not None and foreign_oi <= -90000: st.error(f"🚨 **籌碼警報：** 外資淨空單達 {foreign_oi:,.0f} 口，提防崩跌！")
        else: st.success("✅ **安全區間：** 大盤結構健康。")
        
        # 盤中資金雷達
        st.markdown("### ⚡ 市場資金雷達 (Yahoo 即時)")
        r1, r2 = st.columns(2)
        with r1:
            st.info("**上市成交量 Top 5**")
            st.markdown(get_yahoo_ranking('https://tw.stock.yahoo.com/rank/volume?exchange=TAI'))
        with r2:
            st.info("**上櫃成交量 Top 5**")
            st.markdown(get_yahoo_ranking('https://tw.stock.yahoo.com/rank/volume?exchange=TWO'))
            
    except Exception as e:
        st.error(f"資料讀取失敗 ({e})")

# --- 分頁 2：個股深度健診 ---
with tab2:
    user_input = st.text_input("輸入一檔股票代號 (如 2317)：", "2330", key="single_stock").strip().upper()
    if user_input:
        clean_ticker = user_input.replace(".TWO", "").replace(".TW", "")
        ticker_sym = user_input if ".TW" in user_input or ".TWO" in user_input else f"{user_input}.TW"
        
        try:
            name = get_stock_name(clean_ticker)
            with st.spinner(f"正在分析 {name}..."):
                sdf = yf.download(ticker_sym, period="6mo", progress=False)
                if isinstance(sdf.columns, pd.MultiIndex): sdf.columns = sdf.columns.get_level_values(0)
                
                if sdf.empty: st.warning("找不到資料，上櫃股請加上 .TWO")
                else:
                    sdf['5MA'] = sdf['Close'].rolling(5).mean()
                    sdf['60MA'] = sdf['Close'].rolling(60).mean()
                    sdf['60MA_Deduct'] = sdf['Close'].shift(59)
                    macd = sdf['Close'].ewm(span=12, adjust=False).mean() - sdf['Close'].ewm(span=26, adjust=False).mean()
                    sdf['MACD_Hist'] = macd - macd.ewm(span=9, adjust=False).mean()
                    ls = sdf.iloc[-1]
                    
                    st.markdown(f"#### {name} ({clean_ticker}) - 收盤：{ls['Close']:,.1f}")
                    
                    # 互動 K 線圖 (Plotly)
                    fig = go.Figure(data=[go.Candlestick(x=sdf.index, open=sdf['Open'], high=sdf['High'], low=sdf['Low'], close=sdf['Close'], name='K線')])
                    fig.add_trace(go.Scatter(x=sdf.index, y=sdf['5MA'], line=dict(color='orange', width=1.5), name='5MA'))
                    fig.add_trace(go.Scatter(x=sdf.index, y=sdf['60MA'], line=dict(color='blue', width=1.5), name='季線'))
                    fig.update_layout(xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, t=10, b=0), height=300)
                    st.plotly_chart(fig, use_container_width=True)
                    
                    # 技術燈號
                    sc1, sc2, sc3 = st.columns(3)
                    sc1.metric("5日均線", "🟢 偏多" if ls['Close'] > ls['5MA'] else "🔴 偏空", f"{ls['5MA']:.1f}")
                    sc2.metric("季線扣抵", "🟢 有支撐" if ls['Close'] > ls['60MA_Deduct'] else "🔴 破線", f"{ls['60MA_Deduct']:.1f}")
                    sc3.metric("MACD動能", "🟢 轉強" if ls['MACD_Hist'] > 0 else "🔴 轉弱", f"{ls['MACD_Hist']:.2f}")
                    
                    # 法人籌碼 (張數)
                    chips = get_stock_chips(clean_ticker)
                    if chips:
                        st.caption(f"📅 法人籌碼最後更新日：{chips['date']}")
                        fc1, fc2 = st.columns(2)
                        fc1.metric("外資買賣超", f"🔴 {chips['foreign']} 張" if chips['foreign'] < 0 else f"🟢 +{chips['foreign']} 張")
                        fc2.metric("投信買賣超", f"🔴 {chips['trust']} 張" if chips['trust'] < 0 else f"🟢 +{chips['trust']} 張")
                    else:
                        st.caption("目前無最新法人籌碼資料")

        except Exception as e: st.error(f"分析失敗 ({e})")

# --- 分頁 3：自選股總表 ---
with tab3:
    st.info("請輸入多檔股票代號，用「半形逗號」隔開。")
    multi_input = st.text_input("自選股清單：", "2330, 2317, 2603, 2352")
    
    if st.button("執行總表掃描"):
        tickers = [t.strip() for t in multi_input.split(",") if t.strip()]
        results = []
        with st.spinner("掃描中，請稍候..."):
            for t in tickers:
                c_ticker = t.replace(".TWO", "").replace(".TW", "")
                sym = t if ".TW" in t or ".TWO" in t else f"{t}.TW"
                name = get_stock_name(c_ticker)
                try:
                    df_s = yf.download(sym, period="3mo", progress=False)
                    if isinstance(df_s.columns, pd.MultiIndex): df_s.columns = df_s.columns.get_level_values(0)
                    if not df_s.empty:
                        c_price = df_s['Close'].iloc[-1]
                        ma5 = df_s['Close'].rolling(5).mean().iloc[-1]
                        ma60 = df_s['Close'].rolling(60).mean().iloc[-1]
                        
                        s_5ma = "🟢 多" if c_price > ma5 else "🔴 空"
                        s_60ma = "🟢 站上" if c_price > ma60 else "🔴 跌破"
                        results.append({"代號": c_ticker, "名稱": name, "收盤價": round(c_price, 1), "短線(5MA)": s_5ma, "生命線(季線)": s_60ma})
                except:
                    results.append({"代號": c_ticker, "名稱": name, "收盤價": "錯誤", "短線(5MA)": "-", "生命線(季線)": "-"})
            
            if results:
                st.dataframe(pd.DataFrame(results), use_container_width=True)
