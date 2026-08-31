import streamlit as st
import pandas as pd
import os
import time
import requests
import threading
import concurrent.futures
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# ================= 1. 网页全局配置 =================
st.set_page_config(page_title="猎鹰量化雷达引擎", page_icon="🦅", layout="wide")
st.markdown("<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}</style>", unsafe_allow_html=True)
st_autorefresh(interval=300000, limit=10000, key="data_refresh")  # 5分钟自动刷新，降低断连概率

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
    🎯 核心排序算法：红柱绝对优先！
    返回值：(是否有红柱(0有1无), 第一个红柱距离, -连续红柱数量, 第一个绿柱距离)
    """
    if pd.isna(seq_str) or str(seq_str).strip() == "":
        return (1, 9999, 0, 9999)

    seq_list = str(seq_str).split(',')
    rev_seq = list(reversed(seq_list))

    first_red_idx = -1
    first_green_idx = -1

    for i, val in enumerate(rev_seq):
        v = val.strip()
        if v == '1' and first_red_idx == -1:
            first_red_idx = i
        if v == '-1' and first_green_idx == -1:
            first_green_idx = i

    if first_red_idx != -1:
        continuous_reds = 0
        last_red_pos = first_red_idx
        for i in range(first_red_idx, len(rev_seq)):
            v = rev_seq[i].strip()
            if v == '1':
                if (i - last_red_pos) <= 6:
                    continuous_reds += 1
                    last_red_pos = i
                else:
                    break
        return (0, first_red_idx, -continuous_reds, first_green_idx if first_green_idx != -1 else 9999)
    else:
        return (1, 9999, 0, first_green_idx if first_green_idx != -1 else 9999)

def color_change(val):
    """涨红跌绿淡背景色 (A股惯例)"""
    if pd.isna(val) or not isinstance(val, (int, float)):
        return ''
    if val > 0:
        return 'background-color: #FFE1E1'
    elif val < 0:
        return 'background-color: #DFFFD8'
    return ''

def style_changes_df(df):
    """为涨跌列添加背景色样式（静默失败不影响展示）"""
    try:
        change_cols = [c for c in df.columns if '涨跌' in str(c)]
        if not change_cols:
            return df
        styler = df.style
        for col in change_cols:
            styler = styler.map(color_change, subset=[col])
        return styler
    except Exception:
        return df

# ================= 3. 侧边栏及中控 =================
st.sidebar.title("🎛️ 猎鹰雷达中控台")
radar_mode = st.sidebar.radio(
    "请选择战术看板：",
    ["🔴 红绿柱资金异动检测", "🚀 '始'字准备拉升变盘"]
)
st.sidebar.markdown("---")
st.sidebar.success("🤖 系统已连接最新板块全维数据。")

# ================= 4. 同花顺板块K线直连（单一数据源，日/周/月K各取各的官方数据，含最新实时） =================
_V_CODE = None
_V_TS = 0.0
_V_LOCK = threading.Lock()

def _get_v_code(force_refresh=False):
    """计算同花顺 v cookie（线程安全；每6小时自动轮换，失败可强制刷新，60秒内不重复刷）"""
    global _V_CODE, _V_TS
    with _V_LOCK:
        age = time.time() - _V_TS
        need = _V_CODE is None or age > 6 * 3600 or (force_refresh and age > 60)
        if need:
            try:
                from akshare.stock_feature.stock_board_industry_ths import _get_file_content_ths
                import py_mini_racer
                js = py_mini_racer.MiniRacer()
                js.eval(_get_file_content_ths("ths.js"))
                _V_CODE = js.call("v")
                _V_TS = time.time()
            except Exception:
                _V_CODE = ""
    return _V_CODE

def get_ths_headers():
    """每次实时组装headers，保证v cookie刷新后立即生效"""
    v = _get_v_code()
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36",
        "Referer": "http://q.10jqka.com.cn",
        "Host": "d.10jqka.com.cn",
        "Cookie": f"v={v}" if v else "",
    }

def _parse_year_lines(text):
    """解析某一年K线js文本 -> [(date, close), ...]（静默失败返回空）"""
    out = []
    try:
        from akshare.utils import demjson
        idx = text.find("{")
        if idx == -1:
            return out
        obj = demjson.decode(text[idx:-1])
        data = obj.get("data", "")
        for line in data.split(";"):
            parts = line.split(",")
            if len(parts) >= 5:
                try:
                    out.append((str(parts[0]), float(parts[4])))
                except (ValueError, TypeError):
                    continue
    except Exception:
        pass
    return out

_PERIOD_MAP = {"day": "01", "week": "11", "month": "21"}  # 同花顺官方周期代码

def fetch_recent_closes(code, period="day", need=7):
    """
    按周期直连同花顺官方日/周/月K线（一次请求返回全年，含最新实时一期）。
    数据不足时自动补上一年。失败自动刷新v cookie重试一次，仍失败静默返回空。
    """
    p = _PERIOD_MAP.get(period, "01")
    for _attempt in range(2):
        headers = get_ths_headers()
        year = datetime.now().year
        collected = []
        for y in (year, year - 1):
            try:
                url = f"https://d.10jqka.com.cn/v4/line/bk_{code}/{p}/{y}.js"
                r = requests.get(url, headers=headers, timeout=8)
                year_lines = _parse_year_lines(r.text)
                collected = year_lines + collected  # 上一年数据在前
                if len(collected) >= need:
                    break
            except Exception:
                continue
        if collected:
            return collected[-need:]
        _get_v_code(force_refresh=True)  # 失败刷新cookie后重试一次
    return []

def _calc_changes(closes, n=5):
    """最近n期涨跌幅：返回 (changes[0]=最新期涨跌, dates[0]=最新期日期, 最新价)"""
    if len(closes) < 2:
        return [0.0] * n, [''] * n, 0.0
    changes, dates = [], []
    for i in range(len(closes) - 1, 0, -1):
        prev_c = closes[i - 1][1]
        curr_c = closes[i][1]
        if prev_c <= 0:
            changes.append(0.0)
        else:
            changes.append(round((curr_c - prev_c) / prev_c * 100, 2))
        dates.append(closes[i][0])
        if len(changes) >= n:
            break
    while len(changes) < n:
        changes.append(0.0)
        dates.append('')
    return changes, dates, closes[-1][1]

@st.cache_data(ttl=600, show_spinner="📡 后台同步日/周/月K线官方数据（首次约半分钟，之后秒开）...")
def get_all_changes_multi(codes_tuple):
    """
    并发拉取全部板块的日K/周K/月K官方K线，分别计算最近5期涨跌幅。
    返回 {'day': (DataFrame, 最新期日期), 'week': (...), 'month': (...)}
    DataFrame列: [代码, 5个'{日期}涨跌%', 最新价]
    """
    tasks = [(c, p) for p in ("day", "week", "month") for c in codes_tuple]

    def work(args):
        code, period = args
        try:
            changes, dates, price = _calc_changes(fetch_recent_closes(code, period=period))
            return (code, period, changes, dates, price)
        except Exception:
            return (code, period, [0.0] * 5, [''] * 5, 0.0)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        for r in executor.map(work, tasks):
            results.append(r)

    def build(period):
        rows = []
        # date_buckets[n] 存放"从旧数第n期"的日期：bucket[1]=最旧期, bucket[5]=最新期
        date_buckets = {n: [] for n in range(1, 6)}
        for code, p, changes, dates, price in results:
            if p != period:
                continue
            rows.append({
                '代码': code,
                # chg_1..chg_5 从旧到新排列（右侧为最新）
                'chg_1': changes[4], 'chg_2': changes[3], 'chg_3': changes[2], 'chg_4': changes[1], 'chg_5': changes[0],
                'date_1': dates[4], 'date_2': dates[3], 'date_3': dates[2], 'date_4': dates[1], 'date_5': dates[0],
                '最新价': price,
            })
            for n in range(1, 6):
                d = dates[5 - n]
                if d:
                    date_buckets[n].append(d)

        # 取每列众数日期作为展示列头（保证全表口径一致）
        def mode_of(lst):
            if not lst:
                return ''
            return max(set(lst), key=lst.count)

        df = pd.DataFrame(rows)
        col_names = {}
        for n in range(1, 6):
            d = mode_of(date_buckets[n])
            label = f"{d[4:6]}-{d[6:8]}" if len(d) >= 8 else f"第{n}期"
            col_names[f'chg_{n}'] = f"{label}涨跌%"
        df = df.rename(columns=col_names)

        latest_date = mode_of(date_buckets[5])  # 最新一期日期
        return df, latest_date

    return {'day': build("day"), 'week': build("week"), 'month': build("month")}

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

    # 🎯 日/周/月K线分别拉取官方最近5期涨跌幅（含最新实时一期），各页面展示各自周期数据
    codes_list = df_target['代码'].tolist()
    changes_data = get_all_changes_multi(tuple(codes_list))

    def merge_period(base_df, period_data):
        out = base_df.copy()
        df_chg, latest = period_data
        if df_chg is not None and not df_chg.empty:
            out = pd.merge(out, df_chg, on='代码', how='left')
        if '最新价' not in out.columns:
            out['最新价'] = 0.0
        out['最新价'] = pd.to_numeric(out['最新价'], errors='coerce').fillna(0.0)
        # 静默填充缺失值（不在页面显示任何错误/警告）
        chg_cols = [c for c in out.columns if '涨跌' in str(c)]
        for c in chg_cols:
            out[c] = pd.to_numeric(out[c], errors='coerce').fillna(0.0)
        return out, chg_cols, latest

    final_df, day_chg_cols, day_latest = merge_period(df_target, changes_data['day'])
    week_df, week_chg_cols, week_latest = merge_period(df_target, changes_data['week'])
    month_df, month_chg_cols, month_latest = merge_period(df_target, changes_data['month'])

    def fmt_latest_date(raw):
        """最新期日期展示（当日实时会自动标注）"""
        if raw and len(raw) >= 8:
            s = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
            if raw == datetime.now().strftime('%Y%m%d'):
                s += "（今日实时）"
            return s
        return ""

    day_date_str = fmt_latest_date(day_latest)
    week_date_str = fmt_latest_date(week_latest)
    month_date_str = fmt_latest_date(month_latest)

    # ==========================
    # 模块一：红绿柱资金检测 (三分屏)
    # ==========================
    if "红绿柱" in radar_mode:
        st.title("🔴 猎鹰系统：红绿柱资金异动检测")
        st.markdown("---")

        tab_day, tab_week, tab_month = st.tabs(["日K级别异动", "周K级别异动", "月K级别异动"])

        with tab_day:
            if day_date_str:
                st.caption(f"📅 日K数据日期: {day_date_str}  |  最近5个交易日涨跌（右侧为最新）")
            df_day = final_df[final_df['日K_green_dist'] < 999].copy()
            df_day = df_day.sort_values(by=['日K_no_red', '日K_red_dist', '日K_red_cnt', '日K_green_dist'], ascending=[True, True, True, True])
            df_day['日K视觉序列'] = df_day['日K序列'].apply(format_seq)

            show_day = df_day[['代码', '名称', '日K定级', '日K得分', '日K视觉序列', '最新价'] + day_chg_cols[:5]]
            show_day.columns = ['板块代码', '板块名称', '日K定级', '横盘得分', '日K红绿柱序列', '最新价'] + day_chg_cols[:5]
            show_day.index = range(1, len(show_day) + 1)
            st.dataframe(style_changes_df(show_day), use_container_width=True)

        with tab_week:
            if week_date_str:
                st.caption(f"📅 周K数据日期: {week_date_str}  |  最近5个交易周涨跌（右侧为最新）")
            df_week = week_df[week_df['周K_green_dist'] < 999].copy()
            df_week = df_week.sort_values(by=['周K_no_red', '周K_red_dist', '周K_red_cnt', '周K_green_dist'], ascending=[True, True, True, True])
            df_week['周K视觉序列'] = df_week['周K序列'].apply(format_seq)

            show_week = df_week[['代码', '名称', '周K视觉序列', '最新价'] + week_chg_cols[:5]]
            show_week.columns = ['板块代码', '板块名称', '周K红绿柱序列', '最新价'] + week_chg_cols[:5]
            show_week.index = range(1, len(show_week) + 1)
            st.dataframe(style_changes_df(show_week), use_container_width=True)

        with tab_month:
            if month_date_str:
                st.caption(f"📅 月K数据日期: {month_date_str}  |  最近5个交易月涨跌（右侧为最新）")
            df_month = month_df[month_df['月K_green_dist'] < 999].copy()
            df_month = df_month.sort_values(by=['月K_no_red', '月K_red_dist', '月K_red_cnt', '月K_green_dist'], ascending=[True, True, True, True])
            df_month['月K视觉序列'] = df_month['月K序列'].apply(format_seq)

            show_month = df_month[['代码', '名称', '月K视觉序列', '最新价'] + month_chg_cols[:5]]
            show_month.columns = ['板块代码', '板块名称', '月K红绿柱序列', '最新价'] + month_chg_cols[:5]
            show_month.index = range(1, len(show_month) + 1)
            st.dataframe(style_changes_df(show_month), use_container_width=True)

    # ==========================
    # 模块二："始"字变盘捕获 (共振大表)
    # ==========================
    elif "准备拉升" in radar_mode:
        st.title("🚀 猎鹰系统：'始'字准备拉升变盘")
        if day_date_str:
            st.caption(f"📅 数据日期: {day_date_str}  |  最近5个交易日涨跌（右侧为最新）")
        st.markdown("---")

        final_df['日K始字'] = final_df['日K始字'].astype(str).str.lower() == 'true'
        final_df['周K始字'] = final_df['周K始字'].astype(str).str.lower() == 'true'
        final_df['月K始字'] = final_df['月K始字'].astype(str).str.lower() == 'true'

        for col in ['日K拉升强度', '周K拉升强度', '月K拉升强度']:
            if col not in final_df.columns: final_df[col] = 0
            else: final_df[col] = pd.to_numeric(final_df[col], errors='coerce').fillna(0)

        for col in ['日K新板块', '周K新板块', '月K新板块']:
            if col not in final_df.columns: final_df[col] = False
            else: final_df[col] = final_df[col].astype(str).str.lower() == 'true'

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

            show_shi = df_shi[['代码', '名称', '月K变盘', '周K变盘', '日K变盘', '共振周期数', '最新价'] + day_chg_cols[:5]]
            show_shi.columns = ['板块代码', '板块名称', '月K信号(最强)', '周K信号(中期)', '日K信号(短期)', '总共振数', '最新价'] + day_chg_cols[:5]
            show_shi.index = range(1, len(show_shi) + 1)

            st.metric(label="当前捕获变盘目标总数", value=f"{len(show_shi)} 个")
            st.dataframe(style_changes_df(show_shi), use_container_width=True, height=800)

except FileNotFoundError:
    # 静默处理：不在页面显示"未连接/找不到数据"类提示，仅展示标题等待后台自动重试
    st.title("🦅 猎鹰量化雷达引擎")
    st.caption("系统后台同步中，页面将自动刷新，请稍候...")
