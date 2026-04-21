import akshare as ak
import pandas as pd

print("⏳ 放弃高风险的申万接口，正在使用最安全的基础接口获取A股列表...")

try:
    # 获取最基础的A股代码和名称（这个接口非常稳定，几乎不封IP）
    stock_df = ak.stock_info_a_code_name()
    
    # 确保代码是6位字符串
    stock_df['code'] = stock_df['code'].astype(str).str.zfill(6)
    
    # 过滤：只保留 60 和 00 开头的普通主板股票
    main_board_df = stock_df[stock_df['code'].str.startswith(('60', '00'))]
    
    # 提取并重命名列
    final_df = main_board_df[['code', 'name']].rename(columns={'code': '代码', 'name': '名称'})
    
    # 保存为 CSV
    save_path = "target_stocks.csv"
    final_df.to_csv(save_path, index=False, encoding='utf-8-sig')
    
    print(f"🎉 成功！已成功保存 {len(final_df)} 只主板股票。")
    print(f"💾 数据弹药库已存入: {save_path}")

except Exception as e:
    print(f"❌ 获取失败，错误详情: {e}")