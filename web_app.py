import streamlit as st
import pandas as pd
import time

# 1. 网页全局配置
st.set_page_config(page_title="猎鹰量化看板", page_icon="🦅", layout="wide")

# 2. 页面标题
st.title("🦅 猎鹰系统：盘中异动实时看板")
st.markdown("本看板数据由 Python 自动化脚本实时驱动。")
st.markdown("---") # 画一条分割线

# 3. 实时读取数据的函数
# 这里的 ttl=2 表示缓存2秒，只要你的后台脚本更新了CSV，网页刷新就能看到最新数据
@st.cache_data(ttl=2) 
def load_data():
    try:
        df = pd.read_csv("底层数据_0至100.csv")
        return df
    except Exception:
        return None

df = load_data()

# 4. 渲染网页内容
if df is not None:
    # 顶部数据看板 (三列布局)
    col1, col2, col3 = st.columns(3)
    col1.metric(label="监控标的总数", value=f"{len(df)} 只")
    col2.metric(label="当前系统状态", value="🟢 运行中")
    col3.metric(label="最后刷新时间", value=time.strftime("%H:%M:%S"))
    
    st.subheader("📊 底层扫描数据表")
    
    # 渲染极具科技感的交互式表格
    st.dataframe(df, use_container_width=True)
    
    # 增加一个手动刷新按钮
    if st.button("🔄 手动获取最新数据"):
        st.cache_data.clear() # 清除缓存强制读取
        st.rerun()          # 重新刷新网页
else:
    st.warning("⏳ 正在等待数据源生成... 请确保你的爬虫脚本已经跑完并生成了 CSV 文件。")
    