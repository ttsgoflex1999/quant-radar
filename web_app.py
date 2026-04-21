import streamlit as st
import pandas as pd
import requests
import time
from streamlit_autorefresh import st_autorefresh

# ================= 1. 网页全局配置 =================
st.set_page_config(page_title="猎鹰量化看板", page_icon="🦅", layout="wide")
st.markdown("<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}</style>", unsafe_allow_html=True)
st_autorefresh(interval=60000, limit=10000, key="data_refresh")

st.title("🦅 猎鹰系统：今日异动目标实时看板")
st.markdown("⚡️ 本看板已部署 **腾讯财经底层直连引擎**，免疫海外IP封锁。交易时间内每 60 秒极速刷新。")
st.markdown("---")

# ================= 2. 腾讯底层接口极速获取引擎 =================
def get_tencent_live_data(stock_codes):
    """直接敲击腾讯底层接口，只获取目标池的股票，不封IP且极快"""
    if not stock_codes:
        return pd.DataFrame()
    
    # 给代码加上 sh 或 sz 前缀 (腾讯接口要求)
    formatted_codes = []
    for code in stock_codes:
        code_str = str(code).zfill(6)
        if code_str.startswith('6'):
            formatted_codes.append(f"sh{code_str}")
        else:
            formatted_codes.append(f"sz{code_str}")
            
    query_str = ",".join(formatted_codes)
    url = f"http://qt.gtimg.cn/q={query_str}"
    
    try:
        # 发送请求，哪怕在海外服务器也能秒回
        response = requests.get(url, timeout=5)
        response.encoding = 'gbk'
        lines = response.text.strip().split(';\n')
        
        results = []
        for line in lines:
            if "=" in line:
                data_str = line.split('=')[1].strip('"')
                fields = data_str.split('~')
                if len(fields) > 32:
                    # 腾讯接口解析：1是名称，3是最新价，32是涨跌幅
                    code = fields[2]
                    name = fields[1]
                    price = float(fields[3]) if fields[3] else 0.0
                    pct_change = float(fields[32]) if fields[32] else 0.0
                    results.append({'代码': code, '最新价': price, '涨跌幅': pct_change})
                    
        return pd.DataFrame(results)
    except Exception as e:
        return None

# ================= 3. 数据融合处理 =================
@st.cache_data(ttl=20) # 20秒缓存，极速响应
def load_and_merge_data():
    try:
        # 读取本地扫描传上来的“静态”名单
        df_target = pd.read_csv("今日重点关注_最新.csv")
        df_raw = pd.read_csv("底层数据_最新.csv")
        
        df_target['代码'] = df_target['代码'].astype(str).str.zfill(6)
        df_raw['代码'] = df_raw['代码'].astype(str).str.zfill(6)
        
        # 合并出带有红绿柱的底表
        df_base = pd.merge(df_target, df_raw[['代码', '红绿柱像素序列(1红,-1绿,0空)']], on='代码', how='left')
        
        # 去腾讯拉取这批股票的实时价格！
        target_codes = df_base['代码'].tolist()
        df_live = get_tencent_live_data(target_codes)
        
        if df_live is not None and not df_live.empty:
            final_df = pd.merge(df_base, df_live, on='代码', how='left')
            # 排序！涨得多的排前面
            final_df = final_df.sort_values(by='涨跌幅', ascending=False).reset_index(drop=True)
            final_df.index = final_df.index + 1  
            
            final_df = final_df[['代码', '名称', '最新价', '涨跌幅', '红绿柱像素序列(1红,-1绿,0空)']]
            final_df.columns = ['股票代码', '股票名称', '最新价', '今日涨幅(%)', '红绿柱展示']
            return final_df
        return df_base # 如果拉取失败，返回没价格的基础表
        
    except FileNotFoundError:
        return "NO_FILE"
    except Exception as e:
        return f"ERROR: {e}"

# ================= 4. 渲染UI =================
result = load_and_merge_data()

if isinstance(result, pd.DataFrame) and not result.empty:
    col1, col2 = st.columns(2)
    col1.metric(label="当前监控目标数", value=f"{len(result)} 只")
    col2.metric(label="数据最后刷新", value=time.strftime("%H:%M:%S"))
    
    def color_rule(val):
        if isinstance(val, (int, float)):
            if val > 0: return 'color: #FF3333; font-weight: bold;'
            elif val < 0: return 'color: #00CC66;'
        return ''

    try:
        styled_df = result.style.map(color_rule, subset=['今日涨幅(%)', '最新价'])
    except AttributeError:
        styled_df = result.style.applymap(color_rule, subset=['今日涨幅(%)', '最新价'])
        
    st.dataframe(styled_df, use_container_width=True, height=600)

elif result == "NO_FILE":
    st.warning("⏳ 正在等待盘后扫描数据生成，或当前网络无法连接行情服务器...")
elif isinstance(result, str) and result.startswith("ERROR"):
    st.error(f"系统故障: {result}")
else:
    st.info("今日暂无符合条件的目标。")