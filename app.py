import streamlit as st
import yfinance as yf
import pandas as pd
import requests
import datetime
import re
import plotly.graph_objects as go
from bs4 import BeautifulSoup

st.set_page_config(page_title="台股多空戰情室", page_icon="📊", layout="centered")

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

st.title("📊 台股多空戰情室")

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
FINMIND_TOKEN = '貼上你的_FINMIND_TOKEN'

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
    """抓取個股三大法人買賣超 (自帶 X光透視鏡版)"""
    try:
        start = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime('%Y-%m-%d')
        url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInstitutionalInvestorsBuySell&data_id={ticker}&start_date={start}&token={FINMIND_TOKEN}"
        data = requests.get(url, timeout=5).json()
        
        if data.get('msg') != 'success' or not data.get('data'): return None
        df = pd.DataFrame(data['data'])
        latest_date = df['date'].max()
        df_latest = df[df['date'] == latest_date]
        
        # 1. 自動尋找「法人名稱」的欄位
        inv_col = None
        for col in df.columns:
            if df[col].astype(str).str.contains('外資|外陸資|投信|自營|Foreign|Dealer|Investment', na=False, regex=True).any():
                inv_col = col
                break
        if not inv_col: inv_col = 'name' if 'name' in df.columns else df.columns[-1]
            
        # 2. 自動尋找買賣欄位 (加入中英文防呆，應付官方亂改名稱)
        buy_col = next((c for c in df.columns if any(k in c.lower() for k in ['buy', 'long', '買'])), None)
        sell_col = next((c for c in df.columns if any(k in c.lower() for k in ['sell', 'short', '賣'])), None)
        
        # 3. 寬鬆過濾三大法人
        f_df = df_latest[df_latest[inv_col].astype(str).str.contains('外資|外陸資|Foreign', na=False, regex=True)]
        t_df = df_latest[df_latest[inv_col].astype(str).str.contains('投信|Investment', na=False, regex=True)]
        d_df = df_latest[df_latest[inv_col].astype(str).str.contains('自營|Dealer', na=False, regex=True)]
        
        def get_net(sub_df):
            if sub_df.empty: return 0
            b_val = sub_df[buy_col].astype(float).sum() if buy_col and buy_col in sub_df.columns else 0
            s_val = sub_df[sell_col].astype(float).sum() if sell_col and sell_col in sub_df.columns else 0
            return int((b_val - s_val) // 1000)
            
        return {
            "date": latest_date, 
            "foreign": get_net(f_df), 
            "trust": get_net(t_df), 
            "dealer": get_net(d_df),
            # 以下為 X 光除錯資訊
            "debug_cols": list(df.columns),
            "debug_names": list(df_latest[inv_col].unique()) if inv_col else []
        }
    except Exception as e: 
        return {"error": str(e)}

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

@st.cache_data(ttl=3600)
def get_stock_data_auto(ticker, period="6mo"):
    clean_ticker = ticker.replace(".TWO", "").replace(".TW", "").strip()
    df = yf.download(f"{clean_ticker}.TW", period=period, progress=False)
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    if not df.empty and not df['Close'].isna().all(): return df
    df = yf.download(f"{clean_ticker}.TWO", period=period, progress=False)
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    if not df.empty and not df['Close'].isna().all(): return df
    return pd.DataFrame()

tab1, tab2, tab3 = st.tabs(["📊 大盤與雷達", "🏥 個股深度健診", "📋 自選股總表"])

with tab1:
    try:
        with st.spinner("同步大盤與籌碼資料中..."):
            df = get_market_data()
            latest = df.iloc[-1]
            foreign_oi = get_foreign_oi()
        st.subheader(f"加權指數：{latest['Close']:,.0f}")
        s_bull = (latest['Close'] > latest['5MA']) and (latest['K'] > latest['D'])
        m_bull = (latest['Close'] > latest['60MA']) and (latest['Close'] > latest['60MA_Deduct'])
        c1, c2, c3 = st.columns(3)
        c1.metric("短期(5MA+KD)", "🟢 偏多" if s_bull else "🔴 偏空", f"5MA: {latest['5MA']:,.0f}")
        c2.metric("中期(季線)", "🟢 季線上彎" if m_bull else "🔴 季線下彎", f"扣抵: {latest['60MA_Deduct']:,.0f}")
        c3.metric("波段(MACD)", "🟢 動能強勢" if latest['MACD_Hist'] > 0 else "🔴 動能弱勢", f"值: {latest['MACD']:.0f}")
        st.divider()
        c4, c5 = st.columns(2)
        if foreign_oi is None: c4.metric("外資期指淨未平倉", "讀取中")
        else: c4.metric("外資期指淨未平倉", "🔴 警戒" if foreign_oi <= -90000 else "🟡 偏空" if foreign_oi < 0 else "🟢 偏多", f"{foreign_oi:,.0f} 口")
        c5.metric("大盤量能", "🔥 帶量" if latest['Volume'] > latest['Vol_20MA'] else "❄️ 量縮", "")
        st.divider()
        if latest['Close'] < latest['60MA_Deduct']: st.error(f"🚨 **破線警報：** 指數低於季線扣抵，請控管資金！")
        elif foreign_oi is not None and foreign_oi <= -90000: st.error(f"🚨 **籌碼警報：** 外資淨空單達 {foreign_oi:,.0f} 口，提防崩跌！")
        else: st.success("✅ **安全區間：** 大盤結構健康。")
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

with tab2:
    user_input = st.text_input("輸入股票代號 (如 2317 或 8358)：", "2330", key="single_stock").strip().upper()
    if user_input:
        clean_ticker = user_input.replace(".TWO", "").replace(".TW", "")
        try:
            name = get_stock_name(clean_ticker)
            with st.spinner(f"正在分析 {name}..."):
                sdf = get_stock_data_auto(clean_ticker, period="6mo")
                if sdf.empty: st.warning(f"找不到代號 {clean_ticker} 的資料，請確認代號是否正確。")
                else:
                    sdf['5MA'] = sdf['Close'].rolling(5).mean()
                    sdf['60MA'] = sdf['Close'].rolling(60).mean()
                    sdf['60MA_Deduct'] = sdf['Close'].shift(59)
                    macd = sdf['Close'].ewm(span=12, adjust=False).mean() - sdf['Close'].ewm(span=26, adjust=False).mean()
                    sdf['MACD_Hist'] = macd - macd.ewm(span=9, adjust=False).mean()
                    ls = sdf.iloc[-1]
                    
                    st.markdown(f"#### {name} ({clean_ticker}) - 收盤：{ls['Close']:,.1f}")
                    fig = go.Figure(data=[go.Candlestick(x=sdf.index, open=sdf['Open'], high=sdf['High'], low=sdf['Low'], close=sdf['Close'], name='K線')])
                    fig.add_trace(go.Scatter(x=sdf.index, y=sdf['5MA'], line=dict(color='orange', width=1.5), name='5MA'))
                    fig.add_trace(go.Scatter(x=sdf.index, y=sdf['60MA'], line=dict(color='blue', width=1.5), name='季線'))
                    fig.update_layout(xaxis_rangeslider_visible=False, margin=dict(l=0, r=0, t=10, b=0), height=300)
                    st.plotly_chart(fig, use_container_width=True)
                    
                    sc1, sc2, sc3 = st.columns(3)
                    sc1.metric("5日均線", "🟢 偏多" if ls['Close'] > ls['5MA'] else "🔴 偏空", f"{ls['5MA']:.1f}")
                    sc2.metric("季線扣抵", "🟢 有支撐" if ls['Close'] > ls['60MA_Deduct'] else "🔴 破線", f"{ls['60MA_Deduct']:.1f}")
                    sc3.metric("MACD動能", "🟢 轉強" if ls['MACD_Hist'] > 0 else "🔴 轉弱", f"{ls['MACD_Hist']:.2f}")
                    
                    chips = get_stock_chips(clean_ticker)
                    if chips:
                        if "error" in chips:
                            st.error(f"籌碼讀取發生錯誤：{chips['error']}")
                        else:
                            st.caption(f"📅 法人籌碼最後更新日：{chips['date']}")
                            
                            # 🌟 X光透視鏡：如果全部都是 0，印出除錯資訊！
                            if chips['foreign'] == 0 and chips['trust'] == 0 and chips['dealer'] == 0:
                                st.warning("⚠️ 偵測到法人籌碼皆為 0！FinMind 官方可能已更改欄位格式。")
                                st.error(f"🔍 [透視資料] 欄位名稱: {chips.get('debug_cols')}")
                                st.error(f"🔍 [透視資料] 法人名稱: {chips.get('debug_names')}")
                                
                            fc1, fc2, fc3 = st.columns(3)
                            fc1.metric("外資", f"🔴 {chips['foreign']} 張" if chips['foreign'] < 0 else f"🟢 +{chips['foreign']} 張")
                            fc2.metric("投信", f"🔴 {chips['trust']} 張" if chips['trust'] < 0 else f"🟢 +{chips['trust']} 張")
                            fc3.metric("自營商", f"🔴 {chips['dealer']} 張" if chips['dealer'] < 0 else f"🟢 +{chips['dealer']} 張")
                    else:
                        st.caption("目前無最新法人籌碼資料")
        except Exception as e: st.error(f"分析失敗 ({e})")

with tab3:
    st.info("請輸入多檔股票代號，用「半形逗號」隔開。不管是上市或上櫃，輸入數字即可！")
    multi_input = st.text_input("自選股清單：", "2330, 8358, 2317, 3293")
    if st.button("執行總表掃描"):
        tickers = [t.strip() for t in multi_input.split(",") if t.strip()]
        results = []
        with st.spinner("掃描中，請稍候..."):
            for t in tickers:
                c_ticker = t.replace(".TWO", "").replace(".TW", "")
                name = get_stock_name(c_ticker)
                try:
                    df_s = get_stock_data_auto(c_ticker, period="3mo")
                    if not df_s.empty:
                        c_price = df_s['Close'].iloc[-1]
                        ma5 = df_s['Close'].rolling(5).mean().iloc[-1]
                        ma60 = df_s['Close'].rolling(60).mean().iloc[-1]
                        s_5ma = "🟢 多" if c_price > ma5 else "🔴 空"
                        s_60ma = "🟢 站上" if c_price > ma60 else "🔴 跌破"
                        results.append({"代號": c_ticker, "名稱": name, "收盤價": round(c_price, 1), "短線(5MA)": s_5ma, "生命線(季線)": s_60ma})
                    else:
                        results.append({"代號": c_ticker, "名稱": name, "收盤價": "無資料", "短線(5MA)": "-", "生命線(季線)": "-"})
                except:
                    results.append({"代號": c_ticker, "名稱": name, "收盤價": "錯誤", "短線(5MA)": "-", "生命線(季線)": "-"})
            if results:
                st.dataframe(pd.DataFrame(results), use_container_width=True)
