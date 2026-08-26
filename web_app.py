import streamlit as st
import pandas as pd
import requests
import os
from streamlit_autorefresh import st_autorefresh

# ================= 1. 网页全局配置 =================
st.set_page_config(page_title="猎鹰量化雷达引擎", page_icon="🦅", layout="wide")
st.markdown("<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}</style>", unsafe_allow_html=True)
st_autorefresh(interval=60000, limit=10000, key="data_refresh")

# ================= 2. 辅助函数：核心序列处理 =================
def format_seq(seq_str):
    if pd.isna(seq_str) or str(seq_str).strip() == "": return ""
    res = ""
    for s in str(seq_str).split(','):
        if s.strip() == '1': res += "🟥"
        elif s.strip() == '-1': res += "🟩"
        else: res += "➖"
    return res

def get_seq_priority(seq_str):
    """从右向左扫描红绿柱，距离越近越优先；同距离红优先于绿"""
    if pd.isna(seq_str) or str(seq_str).strip() == "": return (999, 999)
    seq_list = str(seq_str).split(',')
    for i, val in enumerate(reversed(seq_list)):
        val = val.strip()
        if val == '1': return (i, 0)
        elif val == '-1': return (i, 1)
    return (999, 999) 

# ================= 3. 侧边栏及中控 =================
st.sidebar.title("🎛️ 猎鹰雷达中控台")
radar_mode = st.sidebar.radio(
    "请选择战术看板：",
    ["🔴 红绿柱资金异动检测", "🚀 '始'字准备拉升变盘"]
)
st.sidebar.markdown("---")
st.sidebar.success("🤖 系统已连接最新板块全维数据。")

# ================= 4. 腾讯 API =================
def get_tencent_live_data(stock_codes):
    if not stock_codes: return pd.DataFrame()
    formatted_codes = [f"sh{str(c).zfill(6)}" if str(c).zfill(6).startswith('6') else f"sz{str(c).zfill(6)}" for c in stock_codes]
    query_str = ",".join(formatted_codes)
    url = f"http://qt.gtimg.cn/q={query_str}"
    try:
        response = requests.get(url, timeout=5)
        response.encoding = 'gbk'
        results = []
        for line in response.text.strip().split(';\n'):
            if "=" in line:
                fields = line.split('=')[1].strip('"').split('~')
                if len(fields) > 32:
                    results.append({'代码': fields[2], '最新价': float(fields[3] or 0), '涨跌幅': float(fields[32] or 0)})
        return pd.DataFrame(results)
    except:
        return None

# ================= 5. 数据读取与渲染 =================
# 🎯 核心变更：直接读取大盘底层数据库，绝不错杀任何信号
RAW_CSV = "板块全维底层数据_最新.csv"

try:
    df_target = pd.read_csv(RAW_CSV)
    df_target['代码'] = df_target['代码'].astype(str).str.zfill(6)
    
    # 提前计算排序权重
    df_target[['日K_dist', '日K_color']] = df_target['日K序列'].apply(lambda x: pd.Series(get_seq_priority(x)))
    df_target[['周K_dist', '周K_color']] = df_target['周K序列'].apply(lambda x: pd.Series(get_seq_priority(x)))
    df_target[['月K_dist', '月K_color']] = df_target['月K序列'].apply(lambda x: pd.Series(get_seq_priority(x)))

    # 获取实时行情
    df_live = get_tencent_live_data(df_target['代码'].tolist())
    if df_live is not None and not df_live.empty:
        final_df = pd.merge(df_target, df_live, on='代码', how='left')
    else:
        final_df = df_target.copy()
        final_df['最新价'] = 0.0
        final_df['涨跌幅'] = 0.0

    # ==========================
    # 模块一：红绿柱资金检测 (三分屏)
    # ==========================
    if "红绿柱" in radar_mode:
        st.title("🔴 猎鹰系统：红绿柱资金异动检测")
        st.markdown("---")
        
        tab_day, tab_week, tab_month = st.tabs(["日K级别异动", "周K级别异动", "月K级别异动"])
        
        with tab_day:
            # 过滤出有红绿柱的数据 (距离 < 999)
            df_day = final_df[final_df['日K_dist'] < 999].copy()
            # 排序：距离越小越靠前 -> 红色优先 -> 日K得分从高到低
            df_day = df_day.sort_values(by=['日K_dist', '日K_color', '日K得分'], ascending=[True, True, False])
            df_day['日K视觉序列'] = df_day['日K序列'].apply(format_seq)
            
            show_day = df_day[['代码', '名称', '日K定级', '日K得分', '日K视觉序列', '最新价', '涨跌幅']]
            show_day.columns = ['板块代码', '板块名称', '日K定级', '横盘得分', '日K红绿柱序列', '最新价', '今日涨幅(%)']
            show_day.index = range(1, len(show_day) + 1)
            st.dataframe(show_day, use_container_width=True)
            
        with tab_week:
            df_week = final_df[final_df['周K_dist'] < 999].copy()
            df_week = df_week.sort_values(by=['周K_dist', '周K_color'], ascending=[True, True])
            df_week['周K视觉序列'] = df_week['周K序列'].apply(format_seq)
            
            show_week = df_week[['代码', '名称', '周K视觉序列', '最新价', '涨跌幅']]
            show_week.columns = ['板块代码', '板块名称', '周K红绿柱序列', '最新价', '今日涨幅(%)']
            show_week.index = range(1, len(show_week) + 1)
            st.dataframe(show_week, use_container_width=True)
            
        with tab_month:
            df_month = final_df[final_df['月K_dist'] < 999].copy()
            df_month = df_month.sort_values(by=['月K_dist', '月K_color'], ascending=[True, True])
            df_month['月K视觉序列'] = df_month['月K序列'].apply(format_seq)
            
            show_month = df_month[['代码', '名称', '月K视觉序列', '最新价', '涨跌幅']]
            show_month.columns = ['板块代码', '板块名称', '月K红绿柱序列', '最新价', '今日涨幅(%)']
            show_month.index = range(1, len(show_month) + 1)
            st.dataframe(show_month, use_container_width=True)

    # ==========================
    # 模块二：“始”字变盘捕获 (三分屏)
    # ==========================
    elif "始字" in radar_mode:
        st.title("🚀 猎鹰系统：'始'字准备拉升变盘")
        st.markdown("---")
        
        # 强制转换为布尔值
        final_df['日K始字'] = final_df['日K始字'].astype(str).str.lower() == 'true'
        final_df['周K始字'] = final_df['周K始字'].astype(str).str.lower() == 'true'
        final_df['月K始字'] = final_df['月K始字'].astype(str).str.lower() == 'true'
        
        tab_shi_day, tab_shi_week, tab_shi_month = st.tabs(["日K起爆点", "周K起爆点", "月K起爆点"])
        
        with tab_shi_day:
            df_shi_day = final_df[final_df['日K始字'] == True].copy()
            df_shi_day = df_shi_day.sort_values(by=['涨跌幅'], ascending=False)
            show_shi_day = df_shi_day[['代码', '名称', '最新价', '涨跌幅']]
            show_shi_day.columns = ['板块代码', '板块名称', '最新价', '今日涨幅(%)']
            show_shi_day.index = range(1, len(show_shi_day) + 1)
            st.dataframe(show_shi_day, use_container_width=True)
            
        with tab_shi_week:
            df_shi_week = final_df[final_df['周K始字'] == True].copy()
            df_shi_week = df_shi_week.sort_values(by=['涨跌幅'], ascending=False)
            show_shi_week = df_shi_week[['代码', '名称', '最新价', '涨跌幅']]
            show_shi_week.columns = ['板块代码', '板块名称', '最新价', '今日涨幅(%)']
            show_shi_week.index = range(1, len(show_shi_week) + 1)
            st.dataframe(show_shi_week, use_container_width=True)
            
        with tab_shi_month:
            df_shi_month = final_df[final_df['月K始字'] == True].copy()
            df_shi_month = df_shi_month.sort_values(by=['涨跌幅'], ascending=False)
            show_shi_month = df_shi_month[['代码', '名称', '最新价', '涨跌幅']]
            show_shi_month.columns = ['板块代码', '板块名称', '最新价', '今日涨幅(%)']
            show_shi_month.index = range(1, len(show_shi_month) + 1)
            st.dataframe(show_shi_month, use_container_width=True)

except FileNotFoundError:
    st.warning("⏳ 等待机甲生成底层数据文件 (找不到 板块全维底层数据_最新.csv)...")