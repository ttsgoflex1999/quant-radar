import streamlit as st
import pandas as pd
import os
import concurrent.futures
import akshare as ak
from datetime import datetime, timedelta
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

def color_change(val):
    """涨红跌绿配色 (中国股市惯例：涨为红，跌为绿)，颜色淡一点"""
    if pd.isna(val) or not isinstance(val, (int, float)):
        return ''
    if val > 0:
        return 'background-color: #FFD6D6'
    elif val < 0:
        return 'background-color: #D6FFD6'
    return ''

def style_changes_df(df):
    """为包含涨跌数据的DataFrame添加背景色样式"""
    change_cols = [c for c in df.columns if '涨跌' in c]
    if not change_cols:
        return df
    try:
        return df.style.map(color_change, subset=change_cols)
    except AttributeError:
        # 兼容旧版pandas
        return df.style.applymap(color_change, subset=change_cols)

# ================= 3. 侧边栏及中控 =================
st.sidebar.title("🎛️ 猎鹰雷达中控台")
radar_mode = st.sidebar.radio(
    "请选择战术看板：",
    ["🔴 红绿柱资金异动检测", "🚀 '始'字准备拉升变盘"]
)
st.sidebar.markdown("---")
st.sidebar.success("🤖 系统已连接最新板块全维数据。")

# ================= 4. akshare 板块数据获取 =================
@st.cache_data(ttl=3600, show_spinner="📡 正在通过akshare获取板块最近5个交易日涨跌数据，请稍候...")
def get_sector_5days_changes(stock_data):
    """
    使用 akshare 获取每个板块最近5个交易日的涨跌情况。
    - 行业板块 (881xxx): stock_board_industry_index_ths
    - 概念板块 (885xxx / 886xxx): stock_board_concept_index_ths
    stock_data: list of (code, name) tuples
    返回: DataFrame[code, change_1..change_5, date_1..date_5, latest_price]
    """
    def fetch_one(item):
        code, name = item
        try:
            end_date = datetime.now().strftime('%Y%m%d')
            start_date = (datetime.now() - timedelta(days=25)).strftime('%Y%m%d')
            if str(code).startswith('881'):
                df = ak.stock_board_industry_index_ths(symbol=name, start_date=start_date, end_date=end_date)
            else:
                df = ak.stock_board_concept_index_ths(symbol=name, start_date=start_date, end_date=end_date)

            if df is None or df.empty or len(df) < 2:
                return (code, [0.0]*5, ['']*5, 0.0)

            closes = df['收盘价'].tolist()
            dates = df['日期'].tolist()
            latest_price = float(closes[-1])

            # 计算每日涨跌幅
            changes = []
            for i in range(1, len(closes)):
                prev = float(closes[i-1])
                curr = float(closes[i])
                pct = round((curr - prev) / prev * 100, 2)
                changes.append(pct)

            # 不足5天时前面补0
            while len(changes) < 5:
                changes.insert(0, 0.0)

            # 取最近5天的涨跌 + 对应日期
            changes = changes[-5:]
            # 对应日期(收盘日) - 取最近5个交易日
            date_list = [str(d) for d in dates[-5:]]
            while len(date_list) < 5:
                date_list.insert(0, '')

            return (code, changes, date_list, latest_price)
        except Exception:
            return (code, [0.0]*5, ['']*5, 0.0)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        futures = [executor.submit(fetch_one, item) for item in stock_data]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    rows = []
    for code, changes, dates, price in results:
        rows.append({
            '代码': code,
            '第5日涨跌(%)': changes[0],
            '第4日涨跌(%)': changes[1],
            '第3日涨跌(%)': changes[2],
            '第2日涨跌(%)': changes[3],
            '第1日涨跌(%)': changes[4],
            '第5日日期': dates[0],
            '第4日日期': dates[1],
            '第3日日期': dates[2],
            '第2日日期': dates[3],
            '第1日日期': dates[4],
            '最新价': price,
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=300, show_spinner="📡 获取今日实时涨跌数据...")
def get_today_realtime(sector_names):
    """
    获取今日实时涨跌数据。
    优先使用东方财富API（覆盖全行业+概念板块），回退到同花顺行业汇总。
    返回: {sector_name: (today_change_pct, today_close_price)}
    """
    result = {}

    # 1. 东方财富概念板块 (包含今日涨跌+最新价)
    try:
        df = ak.stock_board_concept_name_em()
        name_col = '板块名称' if '板块名称' in df.columns else df.columns[1]
        for _, row in df.iterrows():
            try:
                name = str(row[name_col])
                change = float(row.get('涨跌幅', 0))
                price = float(row.get('最新价', 0))
                result[name] = (change, price if price else None)
            except Exception:
                continue
    except Exception:
        pass

    # 2. 东方财富行业板块 (补充)
    try:
        df = ak.stock_board_industry_name_em()
        name_col = '板块名称' if '板块名称' in df.columns else df.columns[1]
        for _, row in df.iterrows():
            try:
                name = str(row[name_col])
                if name not in result:
                    change = float(row.get('涨跌幅', 0))
                    price = float(row.get('最新价', 0))
                    result[name] = (change, price if price else None)
            except Exception:
                continue
    except Exception:
        pass

    # 3. 同花顺行业汇总 (作为行业板块的回退)
    try:
        df = ak.stock_board_industry_summary_ths()
        for _, row in df.iterrows():
            try:
                name = str(row['板块'])
                change = float(row['涨跌幅'])
                if name not in result:
                    result[name] = (change, None)
            except Exception:
                continue
    except Exception:
        pass

    return result

# ================= 5. 数据读取与渲染 =================
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

    # 获取最近5个交易日涨跌数据
    stock_data = [(row['代码'], row['名称']) for _, row in df_target.iterrows()]
    df_changes = get_sector_5days_changes(stock_data)

    final_df = df_target.copy()
    if df_changes is not None and not df_changes.empty:
        final_df = pd.merge(final_df, df_changes, on='代码', how='left')
    else:
        for col in ['第5日涨跌(%)', '第4日涨跌(%)', '第3日涨跌(%)', '第2日涨跌(%)', '第1日涨跌(%)', '最新价']:
            final_df[col] = 0.0

    # 格式化 NaN 值
    fill_cols = ['第5日涨跌(%)', '第4日涨跌(%)', '第3日涨跌(%)', '第2日涨跌(%)', '第1日涨跌(%)', '最新价']
    final_df.fillna({c: 0.0 for c in fill_cols}, inplace=True)

    # 获取今日实时涨跌并合并 (将今日数据插入为第1日，历史数据顺延)
    sector_names = df_target['名称'].tolist()
    today_data = get_today_realtime(sector_names)
    today_date_str = datetime.now().strftime('%Y-%m-%d')
    has_today = [False]

    if today_data:
        def merge_today(row):
            name = str(row['名称'])
            if name in today_data:
                today_change, today_price = today_data[name]
                # 将历史 第1日→第2日, 第2日→第3日, ... 第4日→第5日
                row['第5日涨跌(%)'] = row['第4日涨跌(%)']
                row['第4日涨跌(%)'] = row['第3日涨跌(%)']
                row['第3日涨跌(%)'] = row['第2日涨跌(%)']
                row['第2日涨跌(%)'] = row['第1日涨跌(%)']
                row['第1日涨跌(%)'] = float(today_change)
                # 顺延日期
                row['第5日日期'] = row['第4日日期']
                row['第4日日期'] = row['第3日日期']
                row['第3日日期'] = row['第2日日期']
                row['第2日日期'] = row['第1日日期']
                row['第1日日期'] = today_date_str
                # 更新最新价
                if today_price:
                    row['最新价'] = float(today_price)
                has_today[0] = True
            return row

        final_df = final_df.apply(merge_today, axis=1)

    # 提取最新交易日信息
    latest_date_str = ""
    if has_today[0]:
        latest_date_str = f"{today_date_str} (今日实时)"
    elif not df_changes.empty and '第1日日期' in df_changes.columns:
        valid_dates = df_changes[df_changes['第1日日期'] != '']['第1日日期']
        if not valid_dates.empty:
            latest_date_str = valid_dates.iloc[0]

    # ==========================
    # 模块一：红绿柱资金检测 (三分屏)
    # ==========================
    if "红绿柱" in radar_mode:
        st.title("🔴 猎鹰系统：红绿柱资金异动检测")
        if latest_date_str:
            st.caption(f"📅 最新交易日: {latest_date_str}  |  展示最近5个交易日板块涨跌情况 (第1日=最新)")
        st.markdown("---")

        tab_day, tab_week, tab_month = st.tabs(["日K级别异动", "周K级别异动", "月K级别异动"])

        with tab_day:
            df_day = final_df[final_df['日K_green_dist'] < 999].copy()
            df_day = df_day.sort_values(by=['日K_no_red', '日K_red_dist', '日K_red_cnt', '日K_green_dist'], ascending=[True, True, True, True])
            df_day['日K视觉序列'] = df_day['日K序列'].apply(format_seq)

            show_day = df_day[['代码', '名称', '日K定级', '日K得分', '日K视觉序列', '最新价',
                               '第5日涨跌(%)', '第4日涨跌(%)', '第3日涨跌(%)', '第2日涨跌(%)', '第1日涨跌(%)']]
            show_day.columns = ['板块代码', '板块名称', '日K定级', '横盘得分', '日K红绿柱序列', '最新价',
                                '第5日涨跌(%)', '第4日涨跌(%)', '第3日涨跌(%)', '第2日涨跌(%)', '第1日涨跌(%)']
            show_day.index = range(1, len(show_day) + 1)
            st.dataframe(style_changes_df(show_day), use_container_width=True)

        with tab_week:
            df_week = final_df[final_df['周K_green_dist'] < 999].copy()
            df_week = df_week.sort_values(by=['周K_no_red', '周K_red_dist', '周K_red_cnt', '周K_green_dist'], ascending=[True, True, True, True])
            df_week['周K视觉序列'] = df_week['周K序列'].apply(format_seq)

            show_week = df_week[['代码', '名称', '周K视觉序列', '最新价',
                                 '第5日涨跌(%)', '第4日涨跌(%)', '第3日涨跌(%)', '第2日涨跌(%)', '第1日涨跌(%)']]
            show_week.columns = ['板块代码', '板块名称', '周K红绿柱序列', '最新价',
                                 '第5日涨跌(%)', '第4日涨跌(%)', '第3日涨跌(%)', '第2日涨跌(%)', '第1日涨跌(%)']
            show_week.index = range(1, len(show_week) + 1)
            st.dataframe(style_changes_df(show_week), use_container_width=True)

        with tab_month:
            df_month = final_df[final_df['月K_green_dist'] < 999].copy()
            df_month = df_month.sort_values(by=['月K_no_red', '月K_red_dist', '月K_red_cnt', '月K_green_dist'], ascending=[True, True, True, True])
            df_month['月K视觉序列'] = df_month['月K序列'].apply(format_seq)

            show_month = df_month[['代码', '名称', '月K视觉序列', '最新价',
                                   '第5日涨跌(%)', '第4日涨跌(%)', '第3日涨跌(%)', '第2日涨跌(%)', '第1日涨跌(%)']]
            show_month.columns = ['板块代码', '板块名称', '月K红绿柱序列', '最新价',
                                  '第5日涨跌(%)', '第4日涨跌(%)', '第3日涨跌(%)', '第2日涨跌(%)', '第1日涨跌(%)']
            show_month.index = range(1, len(show_month) + 1)
            st.dataframe(style_changes_df(show_month), use_container_width=True)

    # ==========================
    # 模块二："始"字变盘捕获 (共振大表)
    # ==========================
    elif "准备拉升" in radar_mode:
        st.title("🚀 猎鹰系统：'始'字准备拉升变盘")
        if latest_date_str:
            st.caption(f"📅 最新交易日: {latest_date_str}  |  展示最近5个交易日板块涨跌情况 (第1日=最新)")
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

            show_shi = df_shi[['代码', '名称', '月K变盘', '周K变盘', '日K变盘', '共振周期数', '最新价',
                               '第5日涨跌(%)', '第4日涨跌(%)', '第3日涨跌(%)', '第2日涨跌(%)', '第1日涨跌(%)']]
            show_shi.columns = ['板块代码', '板块名称', '月K信号(最强)', '周K信号(中期)', '日K信号(短期)', '总共振数', '最新价',
                                '第5日涨跌(%)', '第4日涨跌(%)', '第3日涨跌(%)', '第2日涨跌(%)', '第1日涨跌(%)']
            show_shi.index = range(1, len(show_shi) + 1)

            st.metric(label="当前捕获变盘目标总数", value=f"{len(show_shi)} 个")
            st.dataframe(style_changes_df(show_shi), use_container_width=True, height=800)

except FileNotFoundError:
    st.warning("⏳ 等待机甲生成底层数据文件 (找不到底层 CSV)...")
