import streamlit as st
import pandas as pd
import requests
import time
from streamlit_autorefresh import st_autorefresh

# ================= 1. 网页全局配置 =================
st.set_page_config(page_title="猎鹰量化雷达", page_icon="🦅", layout="wide")
st.markdown("<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}</style>", unsafe_allow_html=True)
st_autorefresh(interval=60000, limit=10000, key="data_refresh")

st.title("🦅 猎鹰系统：形态量化与异动实时看板")
st.markdown("⚡️ 本看板已部署 **腾讯财经底层直连引擎** 与 **U2视觉多维雷达**。交易时间内每 60 秒极速刷新。")
st.markdown("---")

# ================= 2. 腾讯底层接口极速获取引擎 =================
def get_tencent_live_data(stock_codes):
    """直接敲击腾讯底层接口，只获取目标池的股票"""
    if not stock_codes:
        return pd.DataFrame()
    
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
        response = requests.get(url, timeout=5)
        response.encoding = 'gbk'
        lines = response.text.strip().split(';\n')
        
        results = []
        for line in lines:
            if "=" in line:
                data_str = line.split('=')[1].strip('"')
                fields = data_str.split('~')
                if len(fields) > 32:
                    code = fields[2]
                    price = float(fields[3]) if fields[3] else 0.0
                    pct_change = float(fields[32]) if fields[32] else 0.0
                    results.append({'代码': code, '最新价': price, '涨跌幅': pct_change})
                    
        return pd.DataFrame(results)
    except Exception as e:
        return None

# ================= 3. 数据融合处理 =================
@st.cache_data(ttl=20) 
def load_and_merge_data():
    try:
        df_target = pd.read_csv("优质横盘重点关注_最新.csv")
        df_raw = pd.read_csv("底层综合数据_最新.csv")
        
        df_target['代码'] = df_target['代码'].astype(str).str.zfill(6)
        df_raw['代码'] = df_raw['代码'].astype(str).str.zfill(6)
        
        df_base = pd.merge(df_target, df_raw[['代码', '红绿柱像素序列(1红,-1绿,0空)']], on='代码', how='left')
        
        target_codes = df_base['代码'].tolist()
        df_live = get_tencent_live_data(target_codes)
        
        if df_live is not None and not df_live.empty:
            final_df = pd.merge(df_base, df_live, on='代码', how='left')
            
            # 🎯 排序逻辑：优先看量化得分降序，其次看异动涨跌幅
            final_df = final_df.sort_values(by=['量化得分', '涨跌幅'], ascending=[False, False]).reset_index(drop=True)
            final_df.index = final_df.index + 1  
            
            # 融入新增加的异动类型字段
            final_df = final_df[['代码', '名称', '异动类型', '量化得分', '形态定级', '最新价', '涨跌幅', '红绿柱像素序列(1红,-1绿,0空)']]
            final_df.columns = ['股票代码', '股票名称', '雷达研判类型', '量化得分(0-100)', '机器形态定级', '实时最新价', '今日涨幅(%)', '底层视觉序列']
            return final_df
            
        return df_base
        
    except FileNotFoundError:
        return "NO_FILE"
    except Exception as e:
        return f"ERROR: {e}"

# ================= 4. 渲染UI =================
result = load_and_merge_data()

if isinstance(result, pd.DataFrame) and not result.empty:
    col1, col2, col3 = st.columns(3)
    col1.metric(label="当前雷达锁定目标", value=f"{len(result)} 只")
    col2.metric(label="近期异动(红/绿双现)数量", value=f"{len(result[result['雷达研判类型'].str.contains('近期', na=False)])} 只")
    col3.metric(label="数据最后刷新", value=time.strftime("%H:%M:%S"))
    
    # 🎨 视觉增强着色器，加入对异动类型的特殊着色
    def color_rule(val):
        if isinstance(val, (int, float)):
            if val > 0: return 'color: #FF3333; font-weight: bold;'
            elif val < 0: return 'color: #00CC66;'
        elif isinstance(val, str):
            # 形态定级着色
            if 'S级' in val: return 'color: #FFD700; font-weight: bold; background-color: rgba(255, 215, 0, 0.1);'
            elif 'A级' in val: return 'color: #FF8C00; font-weight: bold;'
            # 异动类型着色
            elif '纯红' in val: return 'color: #FF3333; font-weight: bold;'
            elif '纯绿' in val: return 'color: #00CC66; font-weight: bold;'
            elif '双现' in val: return 'color: #FF8C00; font-weight: bold;'
            elif '潜伏' in val: return 'color: #9370DB; font-weight: bold;'
        return ''

    try:
        styled_df = result.style.map(color_rule, subset=['今日涨幅(%)', '实时最新价', '机器形态定级', '雷达研判类型'])
    except AttributeError:
        styled_df = result.style.applymap(color_rule, subset=['今日涨幅(%)', '实时最新价', '机器形态定级', '雷达研判类型'])
        
    st.dataframe(styled_df, use_container_width=True, height=700)

elif result == "NO_FILE":
    st.warning("⏳ 正在等待舰队盘后量化数据生成 (请确保 master_quant_radar.py 已运行完毕)...")
elif isinstance(result, str) and result.startswith("ERROR"):
    st.error(f"系统故障: {result}")
else:
    st.info("今日暂无符合黄金阈值的高分目标或异动目标。")