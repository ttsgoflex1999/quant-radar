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

# ================= 2. 🤖 核心升级：自动嗅探最新激活的战术 =================
def get_active_mode_index():
    """根据底层数据文件的最后更新时间，智能判断当前正在运行的雷达类型"""
    time_daily = 0
    time_pullup = 0
    
    if os.path.exists("优质横盘重点关注_最新.csv"):
        time_daily = os.path.getmtime("优质横盘重点关注_最新.csv")
        
    if os.path.exists("准备拉升重点关注_最新.csv"):
        time_pullup = os.path.getmtime("准备拉升重点关注_最新.csv")
        
    # 如果拉升雷达的数据比日K雷达更新，默认选中索引 1，否则索引 0
    if time_pullup > time_daily:
        return 1 
    return 0

# ================= 3. 侧边栏：中控台 =================
st.sidebar.title("🎛️ 猎鹰雷达中控台")

active_index = get_active_mode_index()

radar_mode = st.sidebar.radio(
    "请选择当前激活的战术看板：",
    ["🔴 底部红绿柱雷达 (日K洗盘)", "🚀 准备拉升雷达 (周/月K拐点)"],
    index=active_index  # 👈 核心修改：将默认选项绑定给自动算出来的索引
)
st.sidebar.markdown("---")

if active_index == 1 and "准备拉升" in radar_mode:
    st.sidebar.success("🤖 系统已自动为您追踪至【准备拉升】最新战况")
elif active_index == 0 and "日K" in radar_mode:
    st.sidebar.success("🤖 系统已自动为您追踪至【日K洗盘】最新战况")
else:
    st.sidebar.info("📌 您当前正在手动回看历史面板")

# ================= 4. 腾讯底层接口极速获取引擎 =================
def get_tencent_live_data(stock_codes):
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

# ================= 5. 战术模式 1：底部红绿柱 (日K) =================
if "日K" in radar_mode:
    st.title("🦅 猎鹰系统：底部横盘与洗盘异动看板")
    st.markdown("⚡️ 搭载 U2视觉红绿柱雷达，锁定主力底仓。交易时间内每 60 秒刷新。")
    st.markdown("---")
    
    try:
        df_target = pd.read_csv("优质横盘重点关注_最新.csv")
        df_raw = pd.read_csv("底层综合数据_最新.csv")
        df_target['代码'] = df_target['代码'].astype(str).str.zfill(6)
        df_raw['代码'] = df_raw['代码'].astype(str).str.zfill(6)

        df_base = pd.merge(df_target, df_raw[['代码', '红绿柱像素序列(1红,-1绿,0空)']], on='代码', how='left')
        df_live = get_tencent_live_data(df_base['代码'].tolist())

        if df_live is not None and not df_live.empty:
            final_df = pd.merge(df_base, df_live, on='代码', how='left')
            final_df = final_df.sort_values(by=['量化得分', '涨跌幅'], ascending=[False, False]).reset_index(drop=True)
            final_df.index = final_df.index + 1  
            final_df = final_df[['代码', '名称', '异动类型', '量化得分', '形态定级', '最新价', '涨跌幅', '红绿柱像素序列(1红,-1绿,0空)']]
            final_df.columns = ['股票代码', '股票名称', '雷达研判类型', '量化得分(0-100)', '机器形态定级', '实时最新价', '今日涨幅(%)', '底层视觉序列']
            
            def color_rule_daily(val):
                if isinstance(val, (int, float)):
                    if val > 0: return 'color: #FF3333; font-weight: bold;'
                    elif val < 0: return 'color: #00CC66;'
                elif isinstance(val, str):
                    if 'S级' in val: return 'color: #FFD700; font-weight: bold; background-color: rgba(255, 215, 0, 0.1);'
                    elif 'A级' in val: return 'color: #FF8C00; font-weight: bold;'
                    elif '纯红' in val: return 'color: #FF3333; font-weight: bold;'
                    elif '纯绿' in val: return 'color: #00CC66; font-weight: bold;'
                    elif '双现' in val: return 'color: #FF8C00; font-weight: bold;'
                    elif '潜伏' in val: return 'color: #9370DB; font-weight: bold;'
                return ''

            try:
                styled_df = final_df.style.map(color_rule_daily, subset=['今日涨幅(%)', '实时最新价', '机器形态定级', '雷达研判类型'])
            except AttributeError:
                styled_df = final_df.style.applymap(color_rule_daily, subset=['今日涨幅(%)', '实时最新价', '机器形态定级', '雷达研判类型'])
            
            col1, col2, col3 = st.columns(3)
            col1.metric(label="当前锁定目标", value=f"{len(final_df)} 只")
            col2.metric(label="数据最后刷新", value=time.strftime("%H:%M:%S"))
            st.dataframe(styled_df, use_container_width=True, height=700)
            
    except FileNotFoundError:
        st.warning("⏳ 正在等待舰队红绿柱雷达数据生成 (找不到 优质横盘重点关注_最新.csv)...")

# ================= 6. 战术模式 2：准备拉升 (周/月K) =================
elif "周/月K" in radar_mode:
    st.title("🚀 猎鹰系统：周/月级【准备拉升】看板")
    st.markdown("⚡️ 搭载深色灰度识别引擎，精准捕捉主力周月线变盘拐点。")
    st.markdown("---")

    try:
        df_target = pd.read_csv("准备拉升重点关注_最新.csv")
        df_target['代码'] = df_target['代码'].astype(str).str.zfill(6)
        
        # 转换布尔值为标准格式方便处理
        df_target['周K信号'] = df_target['周K信号'].astype(str).str.lower() == 'true'
        df_target['月K信号'] = df_target['月K信号'].astype(str).str.lower() == 'true'

        df_live = get_tencent_live_data(df_target['代码'].tolist())

        if df_live is not None and not df_live.empty:
            final_df = pd.merge(df_target, df_live, on='代码', how='left')
            final_df = final_df.sort_values(by=['涨跌幅'], ascending=[False]).reset_index(drop=True)
            
            # 数据切分：双启、仅周、仅月
            df_both = final_df[(final_df['周K信号'] == True) & (final_df['月K信号'] == True)].copy()
            df_week = final_df[(final_df['周K信号'] == True) & (final_df['月K信号'] == False)].copy()
            df_month = final_df[(final_df['周K信号'] == False) & (final_df['月K信号'] == True)].copy()
            
            def style_and_show(df_subset, color_theme):
                if df_subset.empty:
                    st.info("该级别暂无触发信号的股票。")
                    return
                    
                df_subset.index = df_subset.index + 1
                df_show = df_subset[['代码', '名称', '最新价', '涨跌幅']]
                df_show.columns = ['股票代码', '股票名称', '实时最新价', '今日涨幅(%)']
                
                def color_rule_pullup(val):
                    if isinstance(val, (int, float)):
                        if val > 0: return 'color: #FF3333; font-weight: bold;'
                        elif val < 0: return 'color: #00CC66;'
                    return ''
                
                try:
                    styled = df_show.style.map(color_rule_pullup, subset=['今日涨幅(%)', '实时最新价'])
                except AttributeError:
                    styled = df_show.style.applymap(color_rule_pullup, subset=['今日涨幅(%)', '实时最新价'])
                st.dataframe(styled, use_container_width=True)

            col1, col2, col3, col4 = st.columns(4)
            col1.metric(label="数据最后刷新", value=time.strftime("%H:%M:%S"))
            col2.metric(label="共振双启数量", value=f"{len(df_both)} 只")
            col3.metric(label="周K单启数量", value=f"{len(df_week)} 只")
            col4.metric(label="月K单启数量", value=f"{len(df_month)} 只")

            st.markdown("### 🔥 【极品】周月共振启动")
            style_and_show(df_both, 'both')
            
            st.markdown("### 📈 【中期】周K级别启动")
            style_and_show(df_week, 'week')
            
            st.markdown("### 🚀 【长期】月K级别启动")
            style_and_show(df_month, 'month')

    except FileNotFoundError:
        st.warning("⏳ 正在等待舰队拉升指标量化数据生成 (找不到 准备拉升重点关注_最新.csv)...")