import streamlit as st
import pandas as pd
import akshare as ak
import time
from streamlit_autorefresh import st_autorefresh

# ================= 1. 网页全局配置与隐私保护 =================
st.set_page_config(page_title="猎鹰量化看板", page_icon="🦅", layout="wide")

hide_streamlit_style = """
<style>
#MainMenu {visibility: hidden;} 
footer {visibility: hidden;}    
header {visibility: hidden;}    
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# ================= 2. 实时刷新引擎 =================
# 设定网页每隔 60000 毫秒 (60秒) 自动刷新一次，拉取最新数据
st_autorefresh(interval=60000, limit=10000, key="data_refresh")

st.title("🦅 猎鹰系统：今日异动目标实时看板")
st.markdown("⚡️ 本看板已接入云端直连行情引擎。交易时间内，**每 60 秒自动刷新获取最新盘口涨跌幅**。")
st.markdown("---")

# ================= 3. 数据处理与融合核心 =================
@st.cache_data(ttl=30)  # 缓存 30 秒，防止频繁请求被东方财富拉黑
def get_live_data():
    try:
        # 1. 读取我们昨晚扫描出的精华名单 和 底层像素名单
        df_target = pd.read_csv("今日重点关注_最新.csv")
        df_raw = pd.read_csv("底层数据_最新.csv")
        
        # 补齐6位股票代码
        df_target['代码'] = df_target['代码'].astype(str).str.zfill(6)
        df_raw['代码'] = df_raw['代码'].astype(str).str.zfill(6)
        
        # 2. 把 0 和 1 的像素数据合并到精华名单里
        df_merge = pd.merge(df_target, df_raw[['代码', '红绿柱像素序列(1红,-1绿,0空)']], on='代码', how='left')
        
        # 3. 瞬间拉取全市场几千只股票的此时此刻价格！
        live_market = ak.stock_zh_a_spot_em()
        live_market['代码'] = live_market['代码'].astype(str).str.zfill(6)
        
        # 只提取我们要的字段
        live_data = live_market[['代码', '最新价', '涨跌幅']]
        
        # 4. 将实时价格拼接到我们的精华名单上
        final_df = pd.merge(df_merge, live_data, on='代码', how='left')
        
        # 5. 【核心需求】按照涨跌幅从大到小排序！
        final_df = final_df.sort_values(by='涨跌幅', ascending=False).reset_index(drop=True)
        
        # 6. 整理最终显示的列顺序
        final_df.index = final_df.index + 1  # 让序号从 1 开始
        final_df = final_df[['代码', '名称', '最新价', '涨跌幅', '红绿柱像素序列(1红,-1绿,0空)']]
        final_df.columns = ['股票代码', '股票名称', '最新价', '今日涨幅(%)', '红绿柱展示']
        
        return final_df
    except Exception as e:
        return None

# ================= 4. UI 渲染与动态上色 =================
df = get_live_data()

if df is not None and not df.empty:
    col1, col2 = st.columns(2)
    col1.metric(label="当前监控目标数", value=f"{len(df)} 只")
    col2.metric(label="数据最后更新时间", value=time.strftime("%H:%M:%S"))
    
    # 【核心需求】定义上色规则：> 0 红，< 0 绿
    def color_rule(val):
        if isinstance(val, (int, float)):
            if val > 0:
                # 大于0设为红色，并加粗醒目
                return 'color: #FF3333; font-weight: bold;'
            elif val < 0:
                # 小于0设为绿色
                return 'color: #00CC66;'
        return ''

    # 使用 pandas 的 style 给数据框上色 (注: 新版 pandas 用 map, 老版用 applymap)
    try:
        styled_df = df.style.map(color_rule, subset=['今日涨幅(%)', '最新价'])
    except AttributeError:
        styled_df = df.style.applymap(color_rule, subset=['今日涨幅(%)', '最新价'])
    
    # 将极其精美的彩色表格渲染到网页上
    st.dataframe(styled_df, use_container_width=True, height=600)
    
else:
    st.warning("⏳ 正在等待盘后扫描数据生成，或当前网络无法连接行情服务器...")