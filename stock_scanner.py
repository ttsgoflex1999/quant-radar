import pyautogui
import time
import pandas as pd
import os

# ================= 1. 全局配置区 =================
# 🚀【扫描范围控制】(序号从 0 开始计算)
START_INDEX = 100      
END_INDEX = 201        

# ⏱️【时间与速度】(去掉了弹窗等待，现在速度极快)
TIME_QUICK = 0.5    
TIME_NORMAL = 1.0   
TIME_INPUT_DELAY = 0.5  # <--- 新增：光标就绪与文字写入的缓冲延时，防止吞字抢跑
TIME_SEARCH = 3.0     
TIME_PAGE_LOAD = 1.0  
TIME_INDICATOR = 0.5  

# 📍【坐标控制台】(去除了 POS_CANCEL)
POS_SEARCH = (1441, 123)  
POS_RESULT = (1200, 230)  
POS_BACK = (1180, 123)    

# 🎯【信号区域配置】(单线扫描)
SIGNAL_X_START = 1169
SIGNAL_X_END = 1347
SIGNAL_Y_OFFSET = 57

# 💾【动态输出文件名称】
OUTPUT_TXT = f"扫描战报_{START_INDEX}至{END_INDEX}.txt"
OUTPUT_CSV = f"底层数据_{START_INDEX}至{END_INDEX}.csv"
# =================================================


# ================= 2. 核心工具包 =================
def safe_locate(image_name):
    """【极速找图】因为没有弹窗干扰，直接返回坐标，不抛报错"""
    try:
        return pyautogui.locateCenterOnScreen(image_name, confidence=0.8)
    except pyautogui.ImageNotFoundException:
        return None

def reset_to_main_screen():
    """每次扫描结束后，连按两次返回，退回到初始搜索界面"""
    print("  <- [复位] 正在退回主界面，准备扫描下一只...")
    pyautogui.click(POS_BACK[0], POS_BACK[1])
    time.sleep(TIME_NORMAL)
    pyautogui.click(POS_BACK[0], POS_BACK[1])
    time.sleep(TIME_NORMAL)

def save_dual_track_result(code, name, visual_string, data_array):
    """【双轨制保存】同时保存视觉方块(TXT)和底层数字(CSV)"""
    current_time = time.strftime("%H:%M:%S", time.localtime())
    
    with open(OUTPUT_TXT, "a", encoding="utf-8") as f:
        f.write(f"[{current_time}] 代码:{code} | 名称:{name} | 扫描图:[{visual_string}]\n")
        
    if data_array is not None:
        if not os.path.exists(OUTPUT_CSV):
            with open(OUTPUT_CSV, "w", encoding="utf-8") as f:
                f.write("时间,代码,名称,红绿柱像素序列(1红,-1绿,0空)\n")
                
        data_str = ",".join(map(str, data_array))
        with open(OUTPUT_CSV, "a", encoding="utf-8") as f:
            f.write(f"{current_time},{code},{name},\"{data_str}\"\n")
# =================================================


# ================= 3. 主业务大循环 =================
if __name__ == "__main__":
    print("=== 🚀 开启全自动 A 股巡航系统 (极速版) ===")
    
    try:
        df = pd.read_csv("target_stocks.csv")
        df['代码'] = df['代码'].astype(str).str.zfill(6) 
    except FileNotFoundError:
        print("❌ 找不到 target_stocks.csv，请确保它和代码在同一个文件夹！")
        exit()

    total_stocks = len(df)
    actual_end = min(END_INDEX, total_stocks)
    stock_list = df.iloc[START_INDEX:actual_end]
    
    print(f"\n🎯 检索范围已设定：从第 {START_INDEX} 只 到 第 {actual_end} 只股票。")
    print("请将同花顺置于主界面，1秒后发车...")
    time.sleep(1)

    # ================= 循环开始 =================
    for index, row in stock_list.iterrows():
        stock_code = row['代码']
        stock_name = row['名称']
        
        print(f"\n-----------------------------------------")
        print(f"▶️ 正在侦察: [{stock_code}] {stock_name} (当前序号: {index})")
        print(f"-----------------------------------------")

        # 步骤 1：点击搜索框并输入
        pyautogui.click(POS_SEARCH[0], POS_SEARCH[1])
        time.sleep(TIME_QUICK)
        pyautogui.click(POS_SEARCH[0], POS_SEARCH[1])
        time.sleep(TIME_NORMAL)

        # 【防抢跑缓冲】确保搜索框光标彻底准备就绪
        time.sleep(TIME_INPUT_DELAY)
        pyautogui.write(stock_code)
        
        # 【防吞字缓冲】确保数字完全被软件接收后，再按下回车
        time.sleep(TIME_INPUT_DELAY)
        pyautogui.press('enter')
        time.sleep(TIME_SEARCH) 
        
        # 步骤 2：进入详情页
        pyautogui.click(POS_RESULT[0], POS_RESULT[1])
        time.sleep(TIME_PAGE_LOAD) 

        # 步骤 3：识别日K
        k_pos = safe_locate('btn_day_k.png')
        if k_pos:
            print("  ✅ 成功识别 '日K'！")
            click_x = int(k_pos.x / 2) - 0
            click_y = int(k_pos.y / 2)
            pyautogui.click(click_x, click_y)
            time.sleep(TIME_INDICATOR) 
        else:
            print(f"  ❌ 未找到 '日K' 图标，直接放弃该股票。")
            save_dual_track_result(stock_code, stock_name, "扫描失败(未加载日K)", None)
            reset_to_main_screen()
            continue

        # 步骤 4：识别主力吸筹
        zl_pos = safe_locate('zhulixichou.png')
        if zl_pos:
            print("  ✅ 成功识别 '主力吸筹'！开始极速雷达扫描...")
            
            real_x = int(zl_pos.x / 2)
            real_y = int(zl_pos.y / 2)
            signal_y = real_y + SIGNAL_Y_OFFSET
            
            # 【执行雷达扫描：静默截取整块屏幕】
            screen_img = pyautogui.screenshot()
            scale = screen_img.width / pyautogui.size().width

            found_red = False
            found_green = False
            
            radar_visual_terminal = "" 
            radar_visual_file = ""
            radar_data_array = []

            for x in range(SIGNAL_X_START, SIGNAL_X_END + 1, 1):
                px = int(x * scale)
                py = int(signal_y * scale)
                try:
                    r, g, b = screen_img.getpixel((px, py))[:3] 
                    if r > 180 and g < 100 and b < 100:
                        found_red = True
                        radar_visual_terminal += "\033[91m█\033[0m" 
                        radar_visual_file += "🟥"                     
                        radar_data_array.append(1)
                    elif g > 150 and r < 120 and b < 120:
                        found_green = True
                        radar_visual_terminal += "\033[92m█\033[0m" 
                        radar_visual_file += "🟩"                     
                        radar_data_array.append(-1)
                    else:
                        radar_visual_terminal += "\033[90m-\033[0m" 
                        radar_visual_file += "➖"                     
                        radar_data_array.append(0)
                except IndexError:
                    radar_visual_terminal += " " 
                    radar_visual_file += " "
                    radar_data_array.append(0)

            print(f"\n  📺 【扫描截面图】: [{radar_visual_terminal}]")

            # 【双轨制保存】
            if found_red or found_green:
                print("  🎯 结论：锁定目标！已保存数据。")
                save_dual_track_result(stock_code, stock_name, radar_visual_file, radar_data_array)
            else:
                print("  ⚪ 结论：一片空白。")
                save_dual_track_result(stock_code, stock_name, radar_visual_file, radar_data_array)

        else:
            print("  ❌ 未找到 '主力吸筹' 图标。")
            save_dual_track_result(stock_code, stock_name, "扫描失败(未加载主力吸筹)", None)

        # 步骤 5：状态复位
        reset_to_main_screen()

    print("\n=========================================")
    print(f"🛑 任务完成！本次检索范围: {START_INDEX} 至 {actual_end}")
    print("=========================================")