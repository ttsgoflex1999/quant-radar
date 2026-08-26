import streamlit as st
import pandas as pd
import requests
import time
import os
from streamlit_autorefresh import st_autorefresh

# ================= 1. 网页全局配置 =================
st.set_page_config(page_title="猎鹰量化雷达引擎", page_icon="🦅", layout="wide")
st.markdown("<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}</style>", unsafe_allow_html=True)
st_autorefresh(interval=60000, limit=10000, key="data_refresh")

# ================= 2. 辅助函数：核心序列处理 =================
def format_seq(seq_str):
    """将数字序列转换为可视化的红绿方块"""
    if pd.isna(seq_str) or str(seq_str).strip() == "": return ""
    res = ""
    for s in str(seq_str).split(','):
        if s.strip() == '1': res += "🟥"
        elif s.strip() == '-1': res += "🟩"
        else: res += "➖"
    return res

def get_seq_priority(seq_str):
    """
    【核心排序算法】计算红绿柱的优先级权重
    返回: (偏移距离, 颜色权重)
    - 偏移距离: 越小说明异动越靠右（最新）
    - 颜色权重: 0为红柱(优先)，1为绿柱(靠后)，999为无信号
    """
    if pd.isna(seq_str) or str(seq_str).strip() == "":
        return (999, 999)
    
    seq_list = str(seq_str).split(',')
    # 反向遍历，从最右侧（最新日期）开始找
    for i, val in enumerate(reversed(seq_list)):
        val = val.strip()
        if val == '1':
            return (i, 0) # 距离 i, 红色优先
        elif val == '-1':
            return (i, 1) # 距离 i, 绿色其次
            
    return (999, 999) # 完全没有红绿柱的垫底

# ================= 3. 侧边栏及中控 =================
def get_active_mode_index():
    time_daily, time_pullup = 0, 0
    if os.path.exists("优质板块重点关注_最新.csv"):
        time_pullup = os.path.getmtime("优质板块重点关注_最新.csv")
    return 1 # 默认锁定到最新板块雷达模式

st.sidebar.title("🎛️ 猎鹰雷达中控台")
radar_mode = st.sidebar.radio(
    "请选择战术看板：",
    ["🔴 底部红绿柱雷达 (日K洗盘)", "🚀 准备拉升雷达 (周/月K拐点)"]
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

# ================= 5. 数据读取与渲染逻辑 =================
CSV_FILE = "优质板块重点关注_最新.csv"

try:
    df_target = pd.read_csv(CSV_FILE)
    df_target['代码'] = df_target['代码'].astype(str).str.zfill(6)
    
    # 算力注入：提前计算所有周期的排序权重
    df_target[['日K_dist', '日K_color']] = df_target['日K序列'].apply(lambda x: pd.Series(get_seq_priority(x)))
    df_target[['周K_dist', '周K_color']] = df_target['周K序列'].apply(lambda x: pd.Series(get_seq_priority(x)))
    df_target[['月K_dist', '月K_color']] = df_target['月K序列'].apply(lambda x: pd.Series(get_seq_priority(x)))

    # 获取实时价格
    df_live = get_tencent_live_data(df_target['代码'].tolist())
    if df_live is not None and not df_live.empty:
        final_df = pd.merge(df_target, df_live, on='代码', how='left')
    else:
        final_df = df_target.copy()
        final_df['最新价'] = 0.0
        final_df['涨跌幅'] = 0.0

    # ---------------- 模式 1：日K 洗盘 ----------------
    if "日K" in radar_mode:
        st.title("🦅 底部横盘与洗盘异动看板")
        st.markdown("---")
        
        df_daily = final_df[final_df['日K得分'] > 0].copy()
        
        # 🎯 日K 强力排序：位置最右优先 -> 红柱优先 -> 形态分最高优先
        df_daily = df_daily.sort_values(by=['日K_dist', '日K_color', '日K得分'], ascending=[True, True, False])
        
        df_daily['底层视觉序列'] = df_daily['日K序列'].apply(format_seq)
        
        show_df = df_daily[['代码', '名称', '综合共振标识', '日K信号', '日K得分', '日K定级', '底层视觉序列', '最新价', '涨跌幅']]
        show_df.columns = ['板块代码', '板块名称', '综合共振标识', '日K始字', '量化得分', '日K定级', '日K红绿柱序列', '实时最新价', '今日涨幅(%)']
        show_df.index = range(1, len(show_df) + 1)
        
        st.metric(label="当前锁定高潜横盘目标", value=f"{len(show_df)} 个")
        st.dataframe(show_df, use_container_width=True, height=700)

    # ---------------- 模式 2：周/月K 拉升 ----------------
    elif "周/月K" in radar_mode:
        st.title("🚀 周/月级【准备拉升】看板")
        st.markdown("---")
        
        final_df['周K信号'] = final_df['周K信号'].astype(str).str.lower() == 'true'
        final_df['月K信号'] = final_df['月K信号'].astype(str).str.lower() == 'true'
        final_df['周K视觉序列'] = final_df['周K序列'].apply(format_seq)
        final_df['月K视觉序列'] = final_df['月K序列'].apply(format_seq)

        df_both = final_df[(final_df['周K信号'] == True) & (final_df['月K信号'] == True)].copy()
        df_week = final_df[(final_df['周K信号'] == True) & (final_df['月K信号'] == False)].copy()
        df_month = final_df[(final_df['周K信号'] == False) & (final_df['月K信号'] == True)].copy()
        
        # 🎯 周/月K 强力排序：分别按各自周期序列的位置和颜色排序
        df_both = df_both.sort_values(by=['周K_dist', '周K_color', '月K_dist', '月K_color'], ascending=[True, True, True, True])
        df_week = df_week.sort_values(by=['周K_dist', '周K_color'], ascending=[True, True])
        df_month = df_month.sort_values(by=['月K_dist', '月K_color'], ascending=[True, True])
        
        def show_pullup_table(df_subset):
            if df_subset.empty:
                st.info("暂无符合该级别拉升信号的板块。")
                return
            df_subset.index = range(1, len(df_subset) + 1)
            df_show = df_subset[['代码', '名称', '综合共振标识', '周K视觉序列', '月K视觉序列', '最新价', '涨跌幅']]
            df_show.columns = ['板块代码', '板块名称', '共振定级', '周K红绿柱序列', '月K红绿柱序列', '实时最新价', '今日涨幅(%)']
            st.dataframe(df_show, use_container_width=True)

        col1, col2, col3 = st.columns(3)
        col1.metric(label="🔥 共振双启", value=f"{len(df_both)} 个")
        col2.metric(label="📈 周K单启", value=f"{len(df_week)} 个")
        col3.metric(label="🚀 月K单启", value=f"{len(df_month)} 个")

        st.markdown("### 🔥 【极品】周月共振启动")
        show_pullup_table(df_both)
        
        st.markdown("### 📈 【中期】周K级别启动")
        show_pullup_table(df_week)
        
        st.markdown("### 🚀 【长期】月K级别启动")
        show_pullup_table(df_month)

except FileNotFoundError:
    st.warning("⏳ 等待机甲生成优质板块文件 (找不到 优质板块重点关注_最新.csv)...")