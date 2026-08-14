import uiautomator2 as u2
from PIL import Image, ImageDraw
import pandas as pd
import time
import os
import queue
import threading

# ================= 1. 🎛️ 终极舰队全局配置区 =================

# 🚀【超级舰队配置】
DEVICE_LIST = [
    "127.0.0.1:16416",  # 一号机
    "127.0.0.1:16384",
    "127.0.0.1:16448",
    "127.0.0.1:16480"
]

# 🚀【扫描范围控制】
START_INDEX = 0
END_INDEX = 4920    

# 📍【安卓底层物理坐标】
POS_SEARCH = (1016, 115)  
POS_BACK = (75, 112)      
POS_RESULT = (540, 250)   

# 🎯【视觉雷达黄金参数】
OFFSET_Y = 845           
VALIDATOR_OFFSET_Y = 300  
SCAN_X_START = 10
SCAN_X_END = 750

# 🧠【形态评分盒子参数】
BOX_TOP_OFFSET = 100
BOX_BOTTOM_OFFSET = 600
AMP_MAX_TOLERANCE = 0.30   
DRIFT_MAX_TOLERANCE = 0.20 
SCORE_THRESHOLD = 60       

# 💾【数据输出配置】
INPUT_CSV = "full_a_share_stocks_latest.csv" 
OUTPUT_TXT = "雷达量化战报_最新.txt"
OUTPUT_CSV = "底层综合数据_最新.csv"
FILTERED_CSV = "优质横盘重点关注_最新.csv"

# 🔒【全局线程锁】
file_lock = threading.Lock()
# =======================================================


# ================= 2. 🧠 形态量化引擎核心 =================
def analyze_sideways_score(img):
    width, height = img.size
    kline_pixels = []
    
    for x in range(width):
        for y in range(height):
            r, g, b = img.getpixel((x, y))
            is_red = (r > 160 and g < 130 and b < 130)
            is_green = (g > 140 and r < 130 and b < 130)
            if is_red or is_green:
                kline_pixels.append((x, y))
                
    if not kline_pixels:
        return 0, "❌ 未提取到K线", img

    y_coords = [p[1] for p in kline_pixels]
    y_coords.sort()
    
    trim_idx = max(1, int(len(y_coords) * 0.05))
    core_y = y_coords[trim_idx:-trim_idx]
    
    if not core_y:
        return 0, "❌ 数据量匮乏", img
        
    top_bound = core_y[0]      
    bottom_bound = core_y[-1]  
    core_amplitude = bottom_bound - top_bound
    amplitude_ratio = core_amplitude / height
    
    score_amp = max(0, 60 * (1 - (amplitude_ratio / AMP_MAX_TOLERANCE)))

    left_y = [p[1] for p in kline_pixels if p[0] < width * 0.3]
    right_y = [p[1] for p in kline_pixels if p[0] > width * 0.7]
    
    if not left_y or not right_y:
         return 0, "❌ 走势过短", img
         
    left_median = sorted(left_y)[len(left_y) // 2]
    right_median = sorted(right_y)[len(right_y) // 2]
    gravity_drift = abs(left_median - right_median)
    drift_ratio = gravity_drift / height
    
    score_drift = max(0, 40 * (1 - (drift_ratio / DRIFT_MAX_TOLERANCE)))

    final_score = round(score_amp + score_drift, 1)
    
    if final_score >= 85:
        tier = "[S级] 完美平推极品横盘"
    elif final_score >= 60:
        tier = "[A级] 标准震荡洗盘箱体"
    elif final_score >= 40:
        tier = "[B级] 劣质宽幅震荡"
    else:
        tier = "[C级] 破位或起飞趋势，非横盘"

    report = f"得分:{final_score} ({tier})"
    
    draw = ImageDraw.Draw(img)
    draw.line([(0, top_bound), (width, top_bound)], fill=(0, 0, 255), width=2)
    draw.line([(0, bottom_bound), (width, bottom_bound)], fill=(0, 0, 255), width=2)
    draw.rectangle([(width*0.15 - 5, left_median - 5), (width*0.15 + 5, left_median + 5)], fill=(255, 0, 255))
    draw.rectangle([(width*0.85 - 5, right_median - 5), (width*0.85 + 5, right_median + 5)], fill=(255, 0, 255))
    draw.line([(width*0.15, left_median), (width*0.85, right_median)], fill=(255, 0, 255), width=3)
    draw.rectangle([(0, height-25), (100, height)], fill=(0,0,0))
    draw.text((5, height-20), f"SCORE: {final_score}", fill=(0, 255, 0))

    return final_score, tier, report


# ================= 3. 核心工具包 =================
def reset_to_main_screen(d, device_name):
    d.click(POS_BACK[0], POS_BACK[1])
    time.sleep(0.8)
    d.click(POS_BACK[0], POS_BACK[1])
    time.sleep(0.8)

def save_dual_track_result(code, name, visual_string, data_array, score, tier):
    current_time = time.strftime("%H:%M:%S", time.localtime())
    
    with file_lock: 
        if not os.path.exists(OUTPUT_CSV):
            with open(OUTPUT_CSV, "w", encoding="utf-8") as f:
                f.write('时间,代码,名称,最终得分,横盘定级,"红绿柱像素序列(1红,-1绿,0空)"\n')
            
        data_str = ",".join(map(str, data_array)) if data_array else "None"
        with open(OUTPUT_CSV, "a", encoding="utf-8") as f:
            f.write(f"{current_time},{code},{name},{score},{tier},\"{data_str}\"\n")
        
        with open(OUTPUT_TXT, "a", encoding="utf-8") as f:
            f.write(f"[{current_time}] {code} {name} | 分数:{score} | {visual_string}\n")


# ================= 4. 🤖 打工人线程逻辑 (Worker) =================
def worker(device_id, task_queue, worker_name):
    try:
        d = u2.connect(device_id)
        d.set_input_ime(True) 
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
        print(f"\n▶️ [{worker_name}] 抢到订单: [{stock_code}] {stock_name} {tag}")

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
                
                raw_validator_y = day_k_bottom + VALIDATOR_OFFSET_Y 
                raw_target_y = day_k_bottom + OFFSET_Y
                validator_y = int(max(10, min(raw_validator_y, 1900)))
                target_y = int(max(10, min(raw_target_y, 1900)))
                
                canvas_loaded = False
                
                for attempt in range(3):
                    img = d.screenshot(format='pillow').convert('RGB')
                    for x in range(SCAN_X_START, SCAN_X_END + 1, 10): 
                        r, g, b = img.getpixel((x, validator_y))
                        if abs(r - g) > 20 or abs(g - b) > 20: 
                            canvas_loaded = True
                            break
                    if not canvas_loaded:
                        time.sleep(1.5)
                        continue
                    else:
                        break 

                if canvas_loaded:
                    radar_visual_terminal = "" 
                    radar_visual_file = ""
                    radar_data_array = []
                    last_red_x = -1
                    last_green_x = -1
                    
                    for x in range(SCAN_X_START, SCAN_X_END + 1, 2):
                        r, g, b = img.getpixel((x, target_y))
                        
                        if r > 180 and g < 100 and b < 100:
                            radar_visual_terminal += "\033[91m█\033[0m" 
                            radar_visual_file += "🟥"
                            radar_data_array.append(1)
                            last_red_x = x
                        elif g > 150 and r < 120 and b < 120:
                            radar_visual_terminal += "\033[92m█\033[0m" 
                            radar_visual_file += "🟩"
                            radar_data_array.append(-1)
                            last_green_x = x
                        else:
                            radar_visual_terminal += "\033[90m-\033[0m" 
                            radar_visual_file += "➖"
                            radar_data_array.append(0)

                    best_score = -1
                    best_tier = "未知"
                    
                    if last_red_x != -1 or last_green_x != -1:
                        right = 755
                        top = day_k_bottom + BOX_TOP_OFFSET
                        bottom = day_k_bottom + BOX_BOTTOM_OFFSET

                        if last_red_x != -1:
                            left_red = max(0, last_red_x - 5)
                            if left_red < right:
                                score_r, tier_r, _ = analyze_sideways_score(img.crop((left_red, top, right, bottom)))
                                if score_r > best_score:
                                    best_score = score_r
                                    best_tier = tier_r

                        if last_green_x != -1:
                            left_green = max(0, last_green_x - 5)
                            if left_green < right:
                                score_g, tier_g, _ = analyze_sideways_score(img.crop((left_green, top, right, bottom)))
                                if score_g > best_score:
                                    best_score = score_g
                                    best_tier = tier_g

                    if best_score == -1:
                        best_score = 0
                        best_tier = "信号区域过窄或无信号"

                    print(f"  📺 [{worker_name}] 序列: [{radar_visual_terminal}] | 最优形态分: {best_score}")
                    save_dual_track_result(stock_code, stock_name, radar_visual_file, radar_data_array, best_score, best_tier)
                    
                else:
                    if retry_count == 0:
                        task['重试次数'] = 1 
                        task_queue.put(task) 
                    else:
                        save_dual_track_result(stock_code, stock_name, "彻底加载失败", None, 0, "失败")

            else:
                if retry_count == 0:
                    task['重试次数'] = 1
                    task_queue.put(task)
                else:
                    save_dual_track_result(stock_code, stock_name, "彻底加载失败", None, 0, "失败")

            reset_to_main_screen(d, worker_name)
            task_queue.task_done()
            
        except Exception as e:
            print(f"⚠️ [{worker_name}] 扫描 {stock_code} 时发生异常: {e}")
            reset_to_main_screen(d, worker_name)
            task_queue.task_done()

    d.set_fastinput_ime(False)


# ================= 5. 🚀 司令部总调度大厅 =================

def process_and_sync(is_final=True):
    """【独立战术动作】数据清洗与云端自动化推送"""
    try:
        if not os.path.exists(OUTPUT_CSV):
            return
            
        df_scan = pd.read_csv(OUTPUT_CSV)
        target_stocks = []
        for index, row in df_scan.iterrows():
            seq_str = str(row['红绿柱像素序列(1红,-1绿,0空)'])
            score = pd.to_numeric(row['最终得分'], errors='coerce')
            
            if seq_str and seq_str != "None" and seq_str != "nan":
                # 清洗序列提取列表
                seq_list = [s.strip() for s in seq_str.split(',')]
                
                # 安全截取：最新 5 个像素 和 之前的像素
                if len(seq_list) >= 5:
                    last_5 = seq_list[-5:]
                    earlier_seq = seq_list[:-5]
                else:
                    last_5 = seq_list
                    earlier_seq = []
                
                # 判断特征
                has_red_last5 = '1' in last_5
                has_green_last5 = '-1' in last_5
                
                include_flag = False
                action_type = ""
                
                # 🎯 逻辑一：只要后五个像素发现红绿柱，即刻捕获，无视分数
                if has_red_last5 or has_green_last5:
                    include_flag = True
                    if has_red_last5 and not has_green_last5:
                        action_type = "🔥 近期介入(纯红)"
                    elif not has_red_last5 and has_green_last5:
                        action_type = "🟢 近期洗盘(纯绿)"
                    else:
                        action_type = "⚔️ 近期分歧(双现)"
                else:
                    # 🎯 逻辑二：后五个像素风平浪静，检查前期是否存在主力
                    has_red_earlier = '1' in earlier_seq
                    has_green_earlier = '-1' in earlier_seq
                    
                    if has_red_earlier or has_green_earlier:
                        # 重点检查：潜伏期必须满足横盘评分及格线
                        if score >= SCORE_THRESHOLD:
                            include_flag = True
                            action_type = "📦 前期潜伏(高分横盘)"
                    
                    # 兜底逻辑：既没有近期异动，前期也没有异动 -> 不做任何操作(被抛弃)
                
                if include_flag:
                    target_stocks.append({
                        '代码': str(row['代码']).zfill(6), 
                        '名称': row['名称'],
                        '异动类型': action_type,
                        '量化得分': score,
                        '形态定级': row['横盘定级']
                    })
        
        filtered_df = pd.DataFrame(target_stocks)
        if not filtered_df.empty:
            # 统一按照量化得分从高到低排序呈现
            filtered_df = filtered_df.sort_values(by='量化得分', ascending=False)
            filtered_df.to_csv(FILTERED_CSV, index=False, encoding='utf-8-sig')
            msg = f"最终结算：捕获 {len(filtered_df)} 只重点股票" if is_final else f"阶段结算：当前捕获 {len(filtered_df)} 只重点股票"
            print(f"  📁 {msg}。")
        else:
            # 防止Git报错的保底空表，加入新的字段 '异动类型'
            pd.DataFrame(columns=['代码', '名称', '异动类型', '量化得分', '形态定级']).to_csv(FILTERED_CSV, index=False, encoding='utf-8-sig')
            print("  📁 结算提示：当前批次无符合要求的股票。")

        # 云端同步
        os.system('git add .') 
        tag = "终止/盘后结算" if is_final else "阶段性同步"
        os.system(f'git commit -m "🤖 quant-radar {tag}：{time.strftime("%m-%d %H:%M")}"')
        
        push_status = os.system('git push')
        if push_status != 0:
            print("  ⚠️ 首次推送遇到网络波动，尝试强制 HTTP/1.1 协议重推...")
            os.system('git config --global http.version HTTP/1.1')
            os.system('git push')
            os.system('git config --global http.version HTTP/2')
            
        print(f"  ✅ 云端同步 ({tag}) 尝试执行完毕！")

    except Exception as e:
        print(f"\n  ⚠️ 后处理异常: {e}")


if __name__ == "__main__":
    print("=== 🚀 开启 quant-radar 终极多机并发量化巡航系统 ===")
    
    try:
        df = pd.read_csv(INPUT_CSV)
        df = df[df['风险状态'] == '正常上市'].copy()
        print(f"✅ 已剔除 ST 及退市整理股票，剩余有效标的: {len(df)} 只")
        df['股票代码'] = df['股票代码'].astype(str).str.zfill(6) 
    except FileNotFoundError:
        print(f"❌ 找不到 {INPUT_CSV}！请先运行检测程序。")
        exit()

    actual_end = min(END_INDEX, len(df))
    stock_list = df.iloc[START_INDEX:actual_end]
    
    file_exists = os.path.exists(OUTPUT_CSV)
    with open(OUTPUT_CSV, "a", encoding="utf-8") as f:
        if not file_exists:
            f.write('时间,代码,名称,最终得分,横盘定级,"红绿柱像素序列(1红,-1绿,0空)"\n')
            
    txt_exists = os.path.exists(OUTPUT_TXT)
    with open(OUTPUT_TXT, "a", encoding="utf-8") as f:
        if not txt_exists:
            f.write(f"=== 舰队并发量化战报 ===\n")
        f.write(f"\n--- 🚀 新一轮扫描启动: {time.strftime('%m-%d %H:%M')} ---\n")

    task_queue = queue.Queue()
    for index, row in stock_list.iterrows():
        task_queue.put({'序号': index, '代码': row['股票代码'], '名称': row['股票名称'], '重试次数': 0})
    
    total_tasks = task_queue.qsize()
    print(f"📦 装载 {total_tasks} 只股票进入发射架。")

    threads = []
    for i, device_id in enumerate(DEVICE_LIST):
        worker_name = f"🤖机甲-{i+1}号"
        t = threading.Thread(target=worker, args=(device_id, task_queue, worker_name))
        t.daemon = True 
        t.start()
        threads.append(t)
        time.sleep(1) 

    last_sync_count = 0
    try:
        while not task_queue.empty():
            time.sleep(2)
            completed_tasks = total_tasks - task_queue.qsize()
            
            if completed_tasks > 0 and completed_tasks % 500 == 0 and completed_tasks != last_sync_count:
                print(f"\n✨ [节点触发] 舰队已完成 {completed_tasks} 只股票探测，启动阶段性自动存档...")
                process_and_sync(is_final=False)
                last_sync_count = completed_tasks
                
    except KeyboardInterrupt:
        print("\n⚠️ 司令部收到紧急停止信号 (Ctrl+C)！正在呼叫所有机甲立刻返航...")
        with task_queue.mutex:
            task_queue.queue.clear()
            
    finally:
        print("\n=========================================")
        print("🛑 舰队扫描已终止！立即对 [已获取的存量数据] 执行最终存档与后处理...")
        process_and_sync(is_final=True)
        print("💤 机甲全员断电，系统安全休眠。")