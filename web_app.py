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
# 设定网页每隔 60 秒自动刷新一次
st_autorefresh(interval=60000, limit=10000, key="data_refresh")

st.title("🦅 猎鹰系统：今日异动目标实时看板")
st.markdown("⚡️ 本看板已接入云端直连行情引擎。交易时间内，**每 60 秒自动刷新获取最新盘口涨跌幅**。")
st.markdown("---")

# ================= 3. 数据处理与融合核心 =================
@st.cache_data(ttl=30)  # 缓存 30 秒，防止请求过快
def get_live_data():
    try:
        # 1. 读取本地扫描生成的最新名单
        # 请确保你的 GitHub 仓库里有这两个文件，且 stock_scanner.py 生成的文件名也是这两个
        df_target = pd.read_csv("今日重点关注_最新.csv")
        df_raw = pd.read_csv("底层数据_最新.csv")
        
        # 补齐6位股票代码
        df_target['代码'] = df_target['代码'].astype(str).str.zfill(6)
        df_raw['代码'] = df_raw['代码'].astype(str).str.zfill(6)
        
        # 2. 合并像素数据
        df_merge = pd.merge(df_target, df_raw[['代码', '红绿柱像素序列(1红,-1绿,0空)']], on='代码', how='left')
        
        # 3. 【核心修复】由于云端服务器在海外，请求东财接口极易被挂断，这里加入 3 次重试机制
        max_retries = 3
        live_market = None
        
        for attempt in range(max_retries):
            try:
                # 尝试拉取实时行情
                live_market = ak.stock_zh_a_spot_em()
                if live_market is not None and not live_market.empty:
                    break # 成功拿到数据，跳出循环
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2) # 失败了等 2 秒再试
                    continue
                else:
                    # 3次都失败了，抛出具体的错误原因
                    st.error(f"🚨 接口连续 {max_retries} 次连接失败，原因: {e}")
                    return None

        # 4. 数据清洗与排序
        if live_market is not None:
            live_market['代码'] = live_market['代码'].astype(str).str.zfill(6)
            live_data = live_market[['代码', '最新价', '涨跌幅']]
            
            final_df = pd.merge(df_merge, live_data, on='代码', how='left')
            
            # 按涨幅降序排列
            final_df = final_df.sort_values(by='涨跌幅', ascending=False).reset_index(drop=True)
            
            # 整理列顺序和名称
            final_df.index = final_df.index + 1  
            final_df = final_df[['代码', '名称', '最新价', '涨跌幅', '红绿柱像素序列(1红,-1绿,0空)']]
            final_df.columns = ['股票代码', '股票名称', '最新价', '今日涨幅(%)', '红绿柱展示']
            
            return final_df
        return None

    except FileNotFoundError:
        st.warning("⚠️ 找不到 '今日重点关注_最新.csv'，请确认本地扫描脚本已成功上传数据。")
        return None
    except Exception as e:
        st.error(f"🚨 运行时发生未知错误: {e}")
        return None

# ================= 4. UI 渲染与动态上色 =================
df = get_live_data()

if df is not None and not df.empty:
    col1, col2 = st.columns(2)
    col1.metric(label="当前监控目标数", value=f"{len(df)} 只")
    col2.metric(label="数据最后更新时间", value=time.strftime("%H:%M:%S"))
    
    # 定义涨跌上色规则
    def color_rule(val):
        if isinstance(val, (int, float)):
            if val > 0: return 'color: #FF3333; font-weight: bold;' # 涨显红
            elif val < 0: return 'color: #00CC66;' # 跌显绿
        return ''

    # 应用样式
    try:
        styled_df = df.style.map(color_rule, subset=['今日涨幅(%)', '最新价'])
    except AttributeError:
        styled_df = df.style.applymap(color_rule, subset=['今日涨幅(%)', '最新价'])
    
    st.dataframe(styled_df, use_container_width=True, height=600)
    
else:
    # 如果 df 为空且没报错，显示等待提示
    if not any(msg.startswith('🚨') for msg in st.session_state.get('error_messages', [])):
        st.info("💡 正在加载数据或等待盘后扫描结果...")