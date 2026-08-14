# -*- coding: utf-8 -*-
"""
全 A 股实时数据极速获取引擎（雪球 API 分页旗舰版）
已修复 400 Bad Request 参数错误
极速直连、分页遍历、精准过滤京股、标注 ST 与退市标的
"""
import requests
import pandas as pd
import time

def fetch_all_a_shares_xueqiu():
    print("=== 🚀 启动雪球量化数据引擎 ===")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    
    session = requests.Session()
    session.headers.update(headers)
    
    try:
        # 步骤 1：获取令牌
        print("--> 步骤 1: 正在与服务器建立安全握手 (获取 Token)...")
        session.get("https://xueqiu.com/", timeout=10)
        
        # 步骤 2：分页循环拉取数据
        print("--> 步骤 2: 正在分页拉取全市场数据矩阵 (每页90条)...")
        url = "https://xueqiu.com/service/v5/stock/screener/quote/list"
        
        all_stocks = []
        page = 1
        page_size = 90  
        
        while True:
            # 🎯 修复点：修正了 order_by 拼写，并补全了 exchange 和时间戳参数
            params = {
                "page": page,
                "size": page_size,
                "order": "desc",
                "order_by": "percent",  
                "exchange": "CN",
                "market": "CN",
                "type": "sh_sz", 
                "_": int(time.time() * 1000) # 时间戳防止 CDN 缓存报错
            }
            
            response = session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            stock_list = data.get('data', {}).get('list', [])
            
            if not stock_list:
                break  
                
            all_stocks.extend(stock_list)
            print(f"    ✅ 成功拉取第 {page} 页，已累计获取 {len(all_stocks)} 只股票...")
            
            if len(stock_list) < page_size:
                break
                
            page += 1
            time.sleep(0.3)  
            
    except Exception as e:
        print(f"❌ 网络请求失败，请检查网络: {e}")
        return
        
    if not all_stocks:
        print("❌ 最终未获取到任何有效数据。")
        return
        
    print("--> 步骤 3: 数据拉取完毕，正在进行本地洗盘与排雷...")
    
    # 整理数据为 DataFrame
    df = pd.DataFrame(all_stocks)
    df = df[['symbol', 'name', 'current', 'percent', 'pe_ttm', 'pb', 'market_capital']].copy()
    df.columns = ['股票代码', '股票名称', '最新价格', '涨跌幅(%)', '市盈率PE', '市净率PB', '总市值']
    
    # 1. 规范代码: 雪球返回带前缀(如 SH600000)，正则去除字母留数字
    df['股票代码'] = df['股票代码'].astype(str).str.replace(r'^[A-Za-z]+', '', regex=True)
    
    # 2. 清理股票名称可能含有的空格
    df['股票名称'] = df['股票名称'].astype(str).str.replace(r'\s+', '', regex=True)
    
    # 3. 按代码前缀严格划定板块
    def classify_market(code):
        if code.startswith(('000', '001', '002', '003')):
            return '深交所主板'
        elif code.startswith(('600', '601', '603', '605')):
            return '上交所主板'
        elif code.startswith(('300', '301')):
            return '创业板'
        elif code.startswith('688'):
            return '科创板'
        return '其他'
        
    df['板块类型'] = df['股票代码'].apply(classify_market)
    
    # 4. 物理隔离：只保留明确划定板块的股票
    df_filtered = df[df['板块类型'] != '其他'].copy()
    
    # 5. 🎯 核心排雷：精准标注各种高危状态
    df_filtered['风险状态'] = '正常上市'
    
    # 后覆盖前原则
    df_filtered.loc[df_filtered['股票名称'].str.contains('ST', case=False), '风险状态'] = 'ST风险警示'
    df_filtered.loc[df_filtered['股票名称'].str.contains(r'\*ST', case=False), '风险状态'] = '*ST退市风险警示'
    df_filtered.loc[df_filtered['股票名称'].str.contains('退', case=False), '风险状态'] = '已退市/退市整理期'
    
    # 排序并生成最终报表
    df_filtered.sort_values(by=['板块类型', '股票代码'], inplace=True)
    df_filtered.to_csv('full_a_share_stocks_latest.csv', index=False, encoding='utf-8-sig')
    
    print(f"\n✅ 数据更新完美收官！共捕获 {len(df_filtered)} 只目标股票。")
    print(f"📁 战报已生成: full_a_share_stocks_latest.csv")

if __name__ == '__main__':
    fetch_all_a_shares_xueqiu()