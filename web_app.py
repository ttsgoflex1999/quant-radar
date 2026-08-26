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
            df_day = final_df[final_df['日K_dist'] < 999].copy()
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
    # 模块二：“始”字变盘捕获 (共振大表)
    # ==========================
    elif "准备拉升" in radar_mode:
        st.title("🚀 猎鹰系统：'始'字准备拉升变盘")
        st.markdown("---")
        
        # 强制转换为布尔值
        final_df['日K始字'] = final_df['日K始字'].astype(str).str.lower() == 'true'
        final_df['周K始字'] = final_df['周K始字'].astype(str).str.lower() == 'true'
        final_df['月K始字'] = final_df['月K始字'].astype(str).str.lower() == 'true'
        
        # 🎯 核心逻辑：计算共振数量 (True=1, False=0)
        final_df['共振周期数'] = final_df['日K始字'].astype(int) + final_df['周K始字'].astype(int) + final_df['月K始字'].astype(int)
        
        # 仅筛选出至少在一个周期出现“始”字的板块
        df_shi = final_df[final_df['共振周期数'] > 0].copy()
        
        if df_shi.empty:
            st.info("暂无任何板块出现'始'字变盘信号。")
        else:
            # 🎯 极限排序：月K优先 -> 共振数越多越靠前 -> 周K次之 -> 当日涨幅
            df_shi = df_shi.sort_values(
                by=['月K始字', '共振周期数', '周K始字', '涨跌幅'], 
                ascending=[False, False, False, False]
            )
            
            # 美化显示
            df_shi['月K变盘(最高权重)'] = df_shi['月K始字'].apply(lambda x: "🔥 触发" if x else "➖")
            df_shi['周K变盘(中期)'] = df_shi['周K始字'].apply(lambda x: "🔥 触发" if x else "➖")
            df_shi['日K变盘(短期)'] = df_shi['日K始字'].apply(lambda x: "🔥 触发" if x else "➖")
            
            show_shi = df_shi[['代码', '名称', '月K变盘(最高权重)', '周K变盘(中期)', '日K变盘(短期)', '共振周期数', '最新价', '涨跌幅']]
            show_shi.columns = ['板块代码', '板块名称', '月K变盘(最高权重)', '周K变盘(中期)', '日K变盘(短期)', '总共振数量', '实时最新价', '今日涨幅(%)']
            show_shi.index = range(1, len(show_shi) + 1)
            
            st.metric(label="当前捕获变盘目标总数", value=f"{len(show_shi)} 个")
            st.dataframe(show_shi, use_container_width=True, height=800)

except FileNotFoundError:
    st.warning("⏳ 等待机甲生成底层数据文件 (找不到 板块全维底层数据_最新.csv)...")