import streamlit as st
import pandas as pd
import requests
import time
from streamlit_autorefresh import st_autorefresh

# ================= 1. 网页全局配置 =================
st.set_page_config(page_title="准备拉升监控雷达", page_icon="🦅", layout="wide")
st.markdown("<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}</style>", unsafe_allow_html=True)
st_autorefresh(interval=60000, limit=10000, key="data_refresh")

st.title("🚀 猎鹰系统：周/月级【准备拉升】实时看板")
st.markdown("⚡️ 搭载深色像素灰度识别引擎，精准捕捉主力周月线变盘拐点。")
st.markdown("---")

# ================= 2. 腾讯底层接口极速获取引擎 =================
def get_tencent_live_data(stock_codes):
    """敲击腾讯底层接口获取实时行情"""
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
        # 读取全新的拉升专用 CSV 数据源
        df_target = pd.read_csv("准备拉升重点关注_最新.csv")
        
        if df_target.empty:
            return df_target

        df_target['代码'] = df_target['代码'].astype(str).str.zfill(6)

        target_codes = df_target['代码'].tolist()
        df_live = get_tencent_live_data(target_codes)

        if df_live is not None and not df_live.empty:
            final_df = pd.merge(df_target, df_live, on='代码', how='left')

            # 🎯 排序逻辑：优先将周月双启(最高级别)置顶，其次看涨跌幅
            final_df['优先级'] = final_df['共振级别'].apply(lambda x: 3 if '双启' in str(x) else (2 if '月K' in str(x) else 1))
            final_df = final_df.sort_values(by=['优先级', '涨跌幅'], ascending=[False, False]).reset_index(drop=True)
            final_df.index = final_df.index + 1  
            
            # 清理辅助排序字段
            final_df = final_df.drop(columns=['优先级'])

            # 重新排序列名
            final_df = final_df[['代码', '名称', '共振级别', '最新价', '涨跌幅', '周K信号', '月K信号']]
            final_df.columns = ['股票代码', '股票名称', '拉升共振级别', '实时最新价', '今日涨幅(%)', '周K启动(始)', '月K启动(始)']
            return final_df

        return df_target

    except FileNotFoundError:
        return "NO_FILE"
    except Exception as e:
        return f"ERROR: {e}"

# ================= 4. 渲染UI =================
result = load_and_merge_data()

if isinstance(result, pd.DataFrame) and not result.empty:
    col1, col2, col3 = st.columns(3)
    col1.metric(label="当前雷达锁定目标", value=f"{len(result)} 只")
    col2.metric(label="极品信号(周月双启)", value=f"{len(result[result['拉升共振级别'].str.contains('双启', na=False)])} 只")
    col3.metric(label="数据最后刷新", value=time.strftime("%H:%M:%S"))

    # 🎨 视觉增强着色器，专为拉升共振指标定制
    def color_rule(val):
        if isinstance(val, (int, float)):
            if val > 0: return 'color: #FF3333; font-weight: bold;'
            elif val < 0: return 'color: #00CC66;'
        elif isinstance(val, bool):
            if val is True: return 'color: #FF3333; font-weight: bold;'
            else: return 'color: #888888;'
        elif isinstance(val, str):
            if '双启' in val: return 'color: #FF0000; font-weight: bold; background-color: rgba(255, 0, 0, 0.1);'
            elif '周K单启' in val: return 'color: #FF8C00; font-weight: bold;'
            elif '月K单启' in val: return 'color: #9370DB; font-weight: bold;'
        return ''

    try:
        styled_df = result.style.map(color_rule, subset=['今日涨幅(%)', '实时最新价', '拉升共振级别', '周K启动(始)', '月K启动(始)'])
    except AttributeError:
        styled_df = result.style.applymap(color_rule, subset=['今日涨幅(%)', '实时最新价', '拉升共振级别', '周K启动(始)', '月K启动(始)'])

    # 将布尔值转换为更直观的符号
    styled_df = styled_df.format({'周K启动(始)': lambda x: '✅ 触发' if x else '➖', 
                                  '月K启动(始)': lambda x: '✅ 触发' if x else '➖'})

    st.dataframe(styled_df, use_container_width=True, height=700)

elif result == "NO_FILE":
    st.warning("⏳ 正在等待舰队拉升指标量化数据生成 (请确保后台检测脚本正在运行)...")
elif isinstance(result, str) and result.startswith("ERROR"):
    st.error(f"系统故障: {result}")
else:
    st.info("今日暂无触发【准备拉升】信号的目标股票。")