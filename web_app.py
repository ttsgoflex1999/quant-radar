import streamlit as st
import pandas as pd
import requests
import os
import concurrent.futures
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
    """
    🎯 核心排序算法升级：红柱绝对优先！
    返回值：(是否有红柱(0有1无), 第一个红柱距离, -连续红柱数量(负数为了正序排), 第一个绿柱距离)
    """
    if pd.isna(seq_str) or str(seq_str).strip() == "": 
        return (1, 9999, 0, 9999)

    seq_list = str(seq_str).split(',')
    rev_seq = list(reversed(seq_list)) # 从右向左看

    first_red_idx = -1
    first_green_idx = -1

    for i, val in enumerate(rev_seq):
        v = val.strip()
        if v == '1' and first_red_idx == -1:
            first_red_idx = i
        if v == '-1' and first_green_idx == -1:
            first_green_idx = i

    if first_red_idx != -1:
        # 如果有红柱，计算向左的连续红柱数量
        # 因为扫描间距是2像素，允许最大6个单位(12像素)的合理空隙
        continuous_reds = 0
        last_red_pos = first_red_idx
        for i in range(first_red_idx, len(rev_seq)):
            v = rev_seq[i].strip()
            if v == '1':
                if (i - last_red_pos) <= 6: 
                    continuous_reds += 1
                    last_red_pos = i
                else:
                    break # 间距过大，红柱断裂，停止计算
        # 返回: (0代表有红柱, 红柱距离越小越好, 数量取负数越小越好(排在前面), 绿柱距离)
        return (0, first_red_idx, -continuous_reds, first_green_idx if first_green_idx != -1 else 9999)
    else:
        # 纯绿柱或没信号的垫底
        return (1, 9999, 0, first_green_idx if first_green_idx != -1 else 9999)

# ================= 3. 侧边栏及中控 =================
st.sidebar.title("🎛️ 猎鹰雷达中控台")
radar_mode = st.sidebar.radio(
    "请选择战术看板：",
    ["🔴 红绿柱资金异动检测", "🚀 '始'字准备拉升变盘"]
)
st.sidebar.markdown("---")
st.sidebar.success("🤖 系统已连接最新板块全维数据。")

# ================= 4. 腾讯 API 获取数据 =================
def get_tencent_live_data(stock_codes):
    """获取今日实时数据 (分块请求防阻断)"""
    if not stock_codes: return pd.DataFrame()
    results = []
    chunk_size = 100
    for i in range(0, len(stock_codes), chunk_size):
        chunk = stock_codes[i:i+chunk_size]
        formatted_codes = [f"sh{str(c).zfill(6)}" if str(c).zfill(6).startswith('6') else f"sz{str(c).zfill(6)}" for c in chunk]
        query_str = ",".join(formatted_codes)
        url = f"http://qt.gtimg.cn/q={query_str}"
        try:
            response = requests.get(url, timeout=5)
            response.encoding = 'gbk'
            for line in response.text.strip().split(';\n'):
                if "=" in line:
                    fields = line.split('=')[1].strip('"').split('~')
                    if len(fields) > 32:
                        results.append({'代码': fields[2], '最新价': float(fields[3] or 0), '今日涨幅(%)': float(fields[32] or 0)})
        except:
            pass
    return pd.DataFrame(results)

@st.cache_data(ttl=3600)  # 历史数据缓存1小时，防止频繁请求被封IP
def get_historical_2days(stock_codes):
    """多线程极速获取前日、昨日涨幅"""
    def fetch_hist(code):
        prefix = "sh" if str(code).startswith("6") else "sz"
        url = f"http://web.ifzq.gtimg.cn/appstock/app/kline/kline?param={prefix}{code},day,,,4,qfq"
        try:
            res = requests.get(url, timeout=3).json()
            days = res['data'][f'{prefix}{code}']['day']
            changes = []
            for i in range(1, len(days)):
                prev_c = float(days[i-1][2])
                curr_c = float(days[i][2])
                pct = round((curr_c - prev_c) / prev_c * 100, 2)
                changes.append(pct)
            
            if len(changes) >= 3:
                return code, changes[-3], changes[-2]
            elif len(changes) == 2:
                return code, 0.0, changes[-2]
            else:
                return code, 0.0, 0.0
        except:
            return code, 0.0, 0.0

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        futures = [executor.submit(fetch_hist, str(c).zfill(6)) for c in stock_codes]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
    return pd.DataFrame(results, columns=['代码', '前日涨幅(%)', '昨日涨幅(%)'])

# ================= 5. 数据读取与渲染 =================
# 自动适配最新 V5 版数据，如果没有则回退找旧版
RAW_CSV = "板块全维底层数据_V5最新版.csv"
if not os.path.exists(RAW_CSV):
    RAW_CSV = "板块全维底层数据_最新.csv"

try:
    df_target = pd.read_csv(RAW_CSV)
    df_target['代码'] = df_target['代码'].astype(str).str.zfill(6)
    
    # 提前计算高阶红绿排序权重
    df_target[['日K_no_red', '日K_red_dist', '日K_red_cnt', '日K_green_dist']] = df_target['日K序列'].apply(lambda x: pd.Series(get_seq_priority(x)))
    df_target[['周K_no_red', '周K_red_dist', '周K_red_cnt', '周K_green_dist']] = df_target['周K序列'].apply(lambda x: pd.Series(get_seq_priority(x)))
    df_target[['月K_no_red', '月K_red_dist', '月K_red_cnt', '月K_green_dist']] = df_target['月K序列'].apply(lambda x: pd.Series(get_seq_priority(x)))

    # 获取实时行情与历史三日数据
    df_live = get_tencent_live_data(df_target['代码'].tolist())
    df_hist = get_historical_2days(df_target['代码'].tolist())
    
    final_df = df_target.copy()
    if df_live is not None and not df_live.empty:
        final_df = pd.merge(final_df, df_live, on='代码', how='left')
    else:
        final_df['最新价'] = 0.0
        final_df['今日涨幅(%)'] = 0.0
        
    if df_hist is not None and not df_hist.empty:
        final_df = pd.merge(final_df, df_hist, on='代码', how='left')
    else:
        final_df['前日涨幅(%)'] = 0.0
        final_df['昨日涨幅(%)'] = 0.0

    # 格式化 NaN 值
    final_df.fillna({'今日涨幅(%)': 0.0, '昨日涨幅(%)': 0.0, '前日涨幅(%)': 0.0, '最新价': 0.0}, inplace=True)

    # ==========================
    # 模块一：红绿柱资金检测 (三分屏)
    # ==========================
    if "红绿柱" in radar_mode:
        st.title("🔴 猎鹰系统：红绿柱资金异动检测")
        st.markdown("---")
        
        tab_day, tab_week, tab_month = st.tabs(["日K级别异动", "周K级别异动", "月K级别异动"])
        
        with tab_day:
            df_day = final_df[final_df['日K_green_dist'] < 999].copy() # 只要有柱子就保留
            # 🎯 排序：有无红柱 -> 第一红柱越近越好 -> 红柱连击数量越大越好 -> 第一绿柱越近越好
            df_day = df_day.sort_values(by=['日K_no_red', '日K_red_dist', '日K_red_cnt', '日K_green_dist'], ascending=[True, True, True, True])
            df_day['日K视觉序列'] = df_day['日K序列'].apply(format_seq)
            
            show_day = df_day[['代码', '名称', '日K定级', '日K得分', '日K视觉序列', '最新价', '前日涨幅(%)', '昨日涨幅(%)', '今日涨幅(%)']]
            show_day.columns = ['板块代码', '板块名称', '日K定级', '横盘得分', '日K红绿柱序列', '最新价', '前日涨幅(%)', '昨日涨幅(%)', '今日涨幅(%)']
            show_day.index = range(1, len(show_day) + 1)
            st.dataframe(show_day, use_container_width=True)
            
        with tab_week:
            df_week = final_df[final_df['周K_green_dist'] < 999].copy()
            df_week = df_week.sort_values(by=['周K_no_red', '周K_red_dist', '周K_red_cnt', '周K_green_dist'], ascending=[True, True, True, True])
            df_week['周K视觉序列'] = df_week['周K序列'].apply(format_seq)
            
            show_week = df_week[['代码', '名称', '周K视觉序列', '最新价', '前日涨幅(%)', '昨日涨幅(%)', '今日涨幅(%)']]
            show_week.columns = ['板块代码', '板块名称', '周K红绿柱序列', '最新价', '前日涨幅(%)', '昨日涨幅(%)', '今日涨幅(%)']
            show_week.index = range(1, len(show_week) + 1)
            st.dataframe(show_week, use_container_width=True)
            
        with tab_month:
            df_month = final_df[final_df['月K_green_dist'] < 999].copy()
            df_month = df_month.sort_values(by=['月K_no_red', '月K_red_dist', '月K_red_cnt', '月K_green_dist'], ascending=[True, True, True, True])
            df_month['月K视觉序列'] = df_month['月K序列'].apply(format_seq)
            
            show_month = df_month[['代码', '名称', '月K视觉序列', '最新价', '前日涨幅(%)', '昨日涨幅(%)', '今日涨幅(%)']]
            show_month.columns = ['板块代码', '板块名称', '月K红绿柱序列', '最新价', '前日涨幅(%)', '昨日涨幅(%)', '今日涨幅(%)']
            show_month.index = range(1, len(show_month) + 1)
            st.dataframe(show_month, use_container_width=True)

    # ==========================
    # 模块二：“始”字变盘捕获 (共振大表)
    # ==========================
    elif "准备拉升" in radar_mode:
        st.title("🚀 猎鹰系统：'始'字准备拉升变盘")
        st.markdown("---")
        
        final_df['日K始字'] = final_df['日K始字'].astype(str).str.lower() == 'true'
        final_df['周K始字'] = final_df['周K始字'].astype(str).str.lower() == 'true'
        final_df['月K始字'] = final_df['月K始字'].astype(str).str.lower() == 'true'
        
        # 处理可能的新字段（向前兼容）
        for col in ['日K拉升强度', '周K拉升强度', '月K拉升强度']:
            if col not in final_df.columns: final_df[col] = 0
            else: final_df[col] = pd.to_numeric(final_df[col], errors='coerce').fillna(0)
            
        for col in ['日K新板块', '周K新板块', '月K新板块']:
            if col not in final_df.columns: final_df[col] = False
            else: final_df[col] = final_df[col].astype(str).str.lower() == 'true'
        
        # 🎯 核心逻辑：计算共振数量
        final_df['共振周期数'] = final_df['日K始字'].astype(int) + final_df['周K始字'].astype(int) + final_df['月K始字'].astype(int)
        
        df_shi = final_df[final_df['共振周期数'] > 0].copy()
        
        if df_shi.empty:
            st.info("暂无任何板块出现'始'字变盘信号。")
        else:
            # 🎯 极限排序：月K优先 -> 共振数越多越靠前 -> 周K次之 -> 日K强度
            df_shi = df_shi.sort_values(
                by=['月K始字', '共振周期数', '周K始字', '日K拉升强度'], 
                ascending=[False, False, False, False]
            )
            
            def format_shi(is_shi, intensity, is_new):
                res = "🔥触发" if is_shi else "➖"
                if intensity > 0: res += f"(强:{int(intensity)})"
                if is_new: res += " 🆕"
                return res

            df_shi['月K变盘'] = df_shi.apply(lambda row: format_shi(row['月K始字'], row['月K拉升强度'], row['月K新板块']), axis=1)
            df_shi['周K变盘'] = df_shi.apply(lambda row: format_shi(row['周K始字'], row['周K拉升强度'], row['周K新板块']), axis=1)
            df_shi['日K变盘'] = df_shi.apply(lambda row: format_shi(row['日K始字'], row['日K拉升强度'], row['日K新板块']), axis=1)
            
            show_shi = df_shi[['代码', '名称', '月K变盘', '周K变盘', '日K变盘', '共振周期数', '最新价', '前日涨幅(%)', '昨日涨幅(%)', '今日涨幅(%)']]
            show_shi.columns = ['板块代码', '板块名称', '月K信号(最强)', '周K信号(中期)', '日K信号(短期)', '总共振数', '最新价', '前日涨幅(%)', '昨日涨幅(%)', '今日涨幅(%)']
            show_shi.index = range(1, len(show_shi) + 1)
            
            st.metric(label="当前捕获变盘目标总数", value=f"{len(show_shi)} 个")
            st.dataframe(show_shi, use_container_width=True, height=800)

except FileNotFoundError:
    st.warning("⏳ 等待机甲生成底层数据文件 (找不到底层 CSV)...")