import uiautomator2 as u2
from PIL import Image
import pandas as pd
import time
import os
import queue
import threading

# ================= 1. 🎛️ 终极舰队全局配置区 =================

# 🚀【超级舰队配置】
DEVICE_LIST = [
    "127.0.0.1:26656",  # 一号机
    "127.0.0.1:26624",
    # "127.0.0.1:16448",
    # "127.0.0.1:16480",
    # "127.0.0.1:16512",
    # "127.0.0.1:16544",
]

# 🚀【扫描范围控制】
START_INDEX = 0
END_INDEX = 3195     

# 📍【安卓底层物理坐标】
POS_SEARCH = (1016, 115)  
POS_BACK = (75, 112)      
POS_RESULT = (540, 250)   

# 🎯【视觉雷达黄金参数】回归原始单行设定！
OFFSET_Y = 844            # 焊死的黄金高度：日K底部往下 844
VALIDATOR_OFFSET_Y = 300  # 🎯【已修复】高空验证雷达：日K底部【往下】 300 像素，直指 K 线主图
SCAN_X_START = 5
SCAN_X_END = 741

# 💾【数据输出配置】
OUTPUT_TXT = "扫描战报_最新.txt"
OUTPUT_CSV = "底层数据_最新.csv"
FILTERED_CSV = "今日重点关注_最新.csv"

# 🔒【全局线程锁】
file_lock = threading.Lock()
# =======================================================


# ================= 2. 核心工具包 =================
def reset_to_main_screen(d, device_name):
    """【极速复位】"""
    d.click(POS_BACK[0], POS_BACK[1])
    time.sleep(0.8)
    d.click(POS_BACK[0], POS_BACK[1])
    time.sleep(0.8)

def save_dual_track_result(code, name, visual_string, data_array):
    """【线程安全保存】"""
    current_time = time.strftime("%H:%M:%S", time.localtime())
    
    with file_lock: 
        if not os.path.exists(OUTPUT_CSV):
            with open(OUTPUT_CSV, "w", encoding="utf-8") as f:
                f.write('时间,代码,名称,"红绿柱像素序列(1红,-1绿,0空)"\n')
            
        if data_array is not None:
            data_str = ",".join(map(str, data_array))
            with open(OUTPUT_CSV, "a", encoding="utf-8") as f:
                f.write(f"{current_time},{code},{name},\"{data_str}\"\n")
        
        with open(OUTPUT_TXT, "a", encoding="utf-8") as f:
            f.write(f"[{current_time}] {code} {name} | {visual_string}\n")


# ================= 3. 🤖 打工人线程逻辑 (Worker) =================
def worker(device_id, task_queue, worker_name):
    try:
        d = u2.connect(device_id)
        d.set_fastinput_ime(True) 
        print(f"✅ {worker_name} ({device_id}) 神经直连成功，准备抢单！")
    except Exception as e:
        print(f"❌ {worker_name} ({device_id}) 连接失败: {e}")
        return

    while True:
        try:
            task = task_queue.get(timeout=3)
        except queue.Empty:
            print(f"🎉 {worker_name} 发现任务队列已空，打卡下班！")
            break
            
        stock_code = task['代码']
        stock_name = task['名称']
        index = task['序号']
        retry_count = task['重试次数']

        tag = f"(第{retry_count + 1}次尝试)" if retry_count > 0 else ""
        print(f"\n▶️ [{worker_name}] 抢到订单: [{stock_code}] {stock_name} {tag} (总序号: {index})")

        try:
            d.click(POS_SEARCH[0], POS_SEARCH[1])
            time.sleep(0.5)

            d.clear_text()
            d.send_keys(stock_code)
            time.sleep(1.2) 
            
            d.click(POS_RESULT[0], POS_RESULT[1])
            time.sleep(1.5) 

            target = d(text="日K")
            if target.wait(timeout=5.0):
                target.click()
                time.sleep(0.5)

                day_k_bottom = target.info['bounds']['bottom']
                
                # 计算坐标
                raw_validator_y = day_k_bottom + VALIDATOR_OFFSET_Y 
                raw_target_y = day_k_bottom + OFFSET_Y
                
                # 🛡️【新增防爆装甲】强制限制坐标在屏幕范围内(10~1900)，死都不报错！
                validator_y = int(max(10, min(raw_validator_y, 1900)))
                target_y = int(max(10, min(raw_target_y, 1900)))
                
                canvas_loaded = False
                
                # 🚀 第一阶段：高空雷达检测 (确保网络 K 线已渲染)
                for attempt in range(3):
                    img = d.screenshot(format='pillow').convert('RGB')
                    for x in range(SCAN_X_START, SCAN_X_END + 1, 10): 
                        r, g, b = img.getpixel((x, validator_y))
                        if abs(r - g) > 20 or abs(g - b) > 20: 
                            canvas_loaded = True
                            break
                    if not canvas_loaded:
                        print(f"  ⏳ [{worker_name}] 高空雷达未扫到K线 (Y={validator_y})，等待重试 ({attempt + 1}/3)...")
                        time.sleep(1.5)
                        continue
                    else:
                        break 

                # 🚀 第二阶段：【回归初心】最原始霸道的单行像素雷达！
                if canvas_loaded:
                    radar_visual_terminal = "" 
                    radar_visual_file = ""
                    radar_data_array = []
                    
                    for x in range(SCAN_X_START, SCAN_X_END + 1, 2):
                        r, g, b = img.getpixel((x, target_y))
                        
                        if r > 180 and g < 100 and b < 100:
                            radar_visual_terminal += "\033[91m█\033[0m" 
                            radar_visual_file += "🟥"
                            radar_data_array.append(1)
                        elif g > 150 and r < 120 and b < 120:
                            radar_visual_terminal += "\033[92m█\033[0m" 
                            radar_visual_file += "🟩"
                            radar_data_array.append(-1)
                        else:
                            radar_visual_terminal += "\033[90m-\033[0m" 
                            radar_visual_file += "➖"
                            radar_data_array.append(0)

                    print(f"  📺 [{worker_name}] 单行雷达 (Y={target_y}): [{radar_visual_terminal}]")
                    save_dual_track_result(stock_code, stock_name, radar_visual_file, radar_data_array)
                    
                else:
                    if retry_count == 0:
                        print(f"  ⚠️ [{worker_name}] {stock_code} 画布加载失败，已扔回队列尾部！")
                        task['重试次数'] = 1 
                        task_queue.put(task) 
                    else:
                        print(f"  ❌ [{worker_name}] {stock_code} 第二次扫描依然失败，彻底放弃！")
                        save_dual_track_result(stock_code, stock_name, "彻底加载失败", None)

            else:
                if retry_count == 0:
                    print(f"  ⚠️ [{worker_name}] {stock_code} 未找到锚点，已扔回队列尾部！")
                    task['重试次数'] = 1
                    task_queue.put(task)
                else:
                    print(f"  ❌ [{worker_name}] {stock_code} 锚点彻底丢失，放弃！")
                    save_dual_track_result(stock_code, stock_name, "彻底加载失败", None)

            reset_to_main_screen(d, worker_name)
            task_queue.task_done()
            
        except Exception as e:
            print(f"⚠️ [{worker_name}] 扫描 {stock_code} 时发生异常: {e}")
            reset_to_main_screen(d, worker_name)
            task_queue.task_done()

    d.set_fastinput_ime(False)


# ================= 4. 🚀 司令部总调度大厅 =================
if __name__ == "__main__":
    print("=== 🚀 开启 U2 终极多机并发巡航系统 ===")
    
    try:
        df = pd.read_csv("target_stocks.csv")
        df['代码'] = df['代码'].astype(str).str.zfill(6) 
    except FileNotFoundError:
        print("❌ 找不到 target_stocks.csv！")
        exit()

    actual_end = min(END_INDEX, len(df))
    stock_list = df.iloc[START_INDEX:actual_end]
    
    with open(OUTPUT_CSV, "w", encoding="utf-8") as f:
        f.write('时间,代码,名称,"红绿柱像素序列(1红,-1绿,0空)"\n')
    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        f.write(f"=== {time.strftime('%m-%d')} 舰队并发扫描战报 ===\n")

    task_queue = queue.Queue()
    for index, row in stock_list.iterrows():
        task_queue.put({'序号': index, '代码': row['代码'], '名称': row['名称'], '重试次数': 0})
    print(f"📦 装载 {task_queue.qsize()} 只股票。")

    threads = []
    for i, device_id in enumerate(DEVICE_LIST):
        worker_name = f"🤖机甲-{i+1}号"
        t = threading.Thread(target=worker, args=(device_id, task_queue, worker_name))
        t.start()
        threads.append(t)
        time.sleep(1) 

    task_queue.join()
    for t in threads:
        t.join()

    print("\n=========================================")
    print("🛑 舰队扫描任务完成！执行后处理...")

    # ================= 5. 🧠 数据清洗与云端自动化 =================
    try:
        df_scan = pd.read_csv(OUTPUT_CSV)
        target_stocks = []
        for index, row in df_scan.iterrows():
            seq_str = str(row['红绿柱像素序列(1红,-1绿,0空)'])
            if seq_str and seq_str != "None" and seq_str != "nan":
                seq_list = seq_str.split(',')
                if len(seq_list) > 0 and seq_list[-1].strip() == '1':
                    target_stocks.append({'代码': str(row['代码']).zfill(6), '名称': row['名称']})
        
        filtered_df = pd.DataFrame(target_stocks)
        filtered_df.to_csv(FILTERED_CSV, index=False, encoding='utf-8-sig')
        print(f"  📁 捕获 {len(filtered_df)} 只重点股票。")

        os.system(f'git add "{FILTERED_CSV}" "{OUTPUT_CSV}"') 
        os.system(f'git commit -m "🤖 舰队自动更新：{time.strftime("%m-%d")} 盘后数据"')
        os.system('git push')
        print("  ✅ 云端同步完成！")

    except Exception as e:
        print(f"\n  ⚠️ 后处理异常: {e}")