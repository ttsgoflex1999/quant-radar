import uiautomator2 as u2
from PIL import Image
import pandas as pd
import time
import os
import queue
import threading
import sys

# ================= 1. 🎛️ 终极舰队全局配置区 =================
DEVICE_LIST = [
    "127.0.0.1:16416",  
    "127.0.0.1:16384",
    "127.0.0.1:16448",
    "127.0.0.1:16480",
    "127.0.0.1:16512"
]

START_INDEX = 0
END_INDEX = 5000    

POS_SEARCH = (1016, 115)  
POS_RESULT = (450, 250)   

# 📍 1. 红绿柱检测参数 (Y轴基于日K按钮偏移)
OFFSET_Y = 932              
VALIDATOR_OFFSET_Y = 300  
SCAN_X_START = 10
SCAN_X_END = 755

# 📍 2. 始字检测参数 (Y轴基于日K按钮偏移，X轴绝对位置)
SHI_X_START = 730
SHI_X_END = 770
SHI_Y_START = 1120
SHI_Y_END = 1150

# 📍 3. 横盘评分大框参数 (Y轴基于日K按钮偏移)
BOX_TOP_OFFSET = 130           
BOX_BOTTOM_OFFSET = 650        
BOX_X_END = 770              # 👈 核心修改 1：提取评分大框的右侧固定边界
AMP_MAX_TOLERANCE = 0.30   
DRIFT_MAX_TOLERANCE = 0.20 

INPUT_CSV = "all_boards_ths.csv" 
OUTPUT_TXT = "板块雷达战报_最新.txt"
OUTPUT_CSV = "板块全维底层数据_最新.csv"
FILTERED_CSV = "优质板块重点关注_最新.csv"

# 🔒 线程锁、计数器与防重复记录集合
file_lock = threading.Lock()
global_completed_count = 0 
count_lock = threading.Lock()

# 🎯 全局已完成代码集合（防止重复记录）
completed_stocks_set = set()
set_lock = threading.Lock()

pause_event = threading.Event()
pause_event.set()

# ================= 1.5 🕹️ 终端指战员控制台 =================
def command_listener():
    while True:
        try:
            cmd = input().strip().lower()
            if cmd == 'p':
                print("\n" + "="*50)
                print("⏸️ 【系统暂停】各机甲将在完成当前任务后悬停。")
                print("⏳ 正在尝试将当前战果强制推送到网站云端...")
                pause_event.clear()
                process_and_sync(is_final=False)
                print("="*50 + "\n")
            elif cmd == 'r':
                print("\n" + "="*50)
                print("▶️ 【系统恢复】机甲解除锁定，继续执行扫描！")
                print("="*50 + "\n")
                pause_event.set()   
        except EOFError:
            break

# ================= 2. ⚡️ 特征检测引擎 =================
def detect_shi_character_fast(img, pixel_base_y):
    top = pixel_base_y + SHI_Y_START
    bottom = pixel_base_y + SHI_Y_END
    
    width, height = img.size
    left, right = max(0, min(SHI_X_START, width)), max(0, min(SHI_X_END, width))
    top, bottom = max(0, min(top, height)), max(0, min(bottom, height))
    
    gray_pixel_count = 0
    for x in range(left, right):
        for y in range(top, bottom):
            r, g, b = img.getpixel((x, y))
            if (50 < r < 170) and (50 < g < 170) and (50 < b < 170):
                if abs(r - g) < 25 and abs(r - b) < 25 and abs(g - b) < 25:
                    gray_pixel_count += 1
                
    return gray_pixel_count > 12

def analyze_sideways_score(img):
    width, height = img.size
    kline_pixels = []
    for x in range(width):
        for y in range(height):
            r, g, b = img.getpixel((x, y))
            if (r > 160 and g < 130 and b < 130) or (g > 140 and r < 130 and b < 130):
                kline_pixels.append((x, y))

    if not kline_pixels: return 0, "无K线"

    y_coords = sorted([p[1] for p in kline_pixels])
    trim_idx = max(1, int(len(y_coords) * 0.05))
    core_y = y_coords[trim_idx:-trim_idx]
    if not core_y: return 0, "数据匮乏"

    core_amplitude = core_y[-1] - core_y[0]
    score_amp = max(0, 60 * (1 - ((core_amplitude / height) / AMP_MAX_TOLERANCE)))

    left_y = [p[1] for p in kline_pixels if p[0] < width * 0.3]
    right_y = [p[1] for p in kline_pixels if p[0] > width * 0.7]
    if not left_y or not right_y: return 0, "走势过短"

    gravity_drift = abs(sorted(left_y)[len(left_y)//2] - sorted(right_y)[len(right_y)//2])
    score_drift = max(0, 40 * (1 - ((gravity_drift / height) / DRIFT_MAX_TOLERANCE)))

    final_score = round(score_amp + score_drift, 1)
    tier = "[S级]极品横盘" if final_score >= 85 else "[A级]标准箱体" if final_score >= 60 else "[B级]宽幅震荡" if final_score >= 40 else "[C级]非横盘"
    return final_score, tier

# ================= 3. 核心工具包 =================
def reset_to_main_screen(d):
    d.click(75, 112)
    time.sleep(1.0)
    d.click(75, 112)
    time.sleep(1.5)

def extract_timeframe_data(d, tf_name, worker_name, calc_score=True):
    target = d(text=tf_name)
    
    if not target.wait(timeout=5.0):
        return False, None
            
    target.click()
    time.sleep(2.0) 

    img = d.screenshot(format='pillow').convert('RGB')
    info = d.info
    scale_y = img.size[1] / info['displayHeight']
    base_bottom = target.info['bounds']['bottom']

    pixel_base_y_shi = int(base_bottom * scale_y)
    has_shi = detect_shi_character_fast(img, pixel_base_y_shi)
    
    validator_y = int(max(10, min(base_bottom + VALIDATOR_OFFSET_Y, 1900)))
    target_y = int(max(10, min(base_bottom + OFFSET_Y, 1900)))
    
    canvas_loaded = any(abs(img.getpixel((x, validator_y))[0] - img.getpixel((x, validator_y))[1]) > 20 for x in range(SCAN_X_START, SCAN_X_END + 1, 10))
    if not canvas_loaded: return False, None

    seq_terminal, seq_file, data_array = "", "", []
    last_red_x, last_green_x = -1, -1
    
    for x in range(SCAN_X_START, SCAN_X_END + 1, 2):
        r, g, b = img.getpixel((x, target_y))
        if r > 180 and g < 100 and b < 100:
            seq_terminal, seq_file, last_red_x = seq_terminal + "\033[91m█\033[0m", seq_file + "🟥", x
            data_array.append(1)
        elif g > 150 and r < 120 and b < 120:
            seq_terminal, seq_file, last_green_x = seq_terminal + "\033[92m█\033[0m", seq_file + "🟩", x
            data_array.append(-1)
        else:
            seq_terminal, seq_file = seq_terminal + "\033[90m-\033[0m", seq_file + "➖"
            data_array.append(0)

    best_score, best_tier = 0, "无评级"
    
    # 🎯 核心修改 2：采用绝对优先级的箱体边界判定，红柱优先，绿柱兜底
    if calc_score:
        box_top = int(base_bottom + BOX_TOP_OFFSET)
        box_bottom = int(base_bottom + BOX_BOTTOM_OFFSET)
        
        target_left_x = -1
        if last_red_x != -1:
            target_left_x = max(0, last_red_x - 5)
        elif last_green_x != -1:
            target_left_x = max(0, last_green_x - 5)
            
        if target_left_x != -1 and target_left_x < BOX_X_END:
            best_score, best_tier = analyze_sideways_score(img.crop((target_left_x, box_top, BOX_X_END, box_bottom)))

    result = {
        "shi": has_shi, "score": best_score, "tier": best_tier, 
        "seq_file": seq_file, "seq_arr": data_array, "seq_term": seq_terminal
    }
    return True, result

def save_comprehensive_result(code, name, d_res, w_res, m_res):
    global global_completed_count
    current_time = time.strftime("%H:%M:%S", time.localtime())
    
    with set_lock:
        if code in completed_stocks_set:
            return False
        completed_stocks_set.add(code)
    
    with file_lock: 
        if not os.path.exists(OUTPUT_CSV):
            with open(OUTPUT_CSV, "w", encoding="utf-8") as f:
                f.write('时间,代码,名称,日K始字,日K得分,日K定级,日K序列,周K始字,周K序列,月K始字,月K序列\n')
            
        with open(OUTPUT_CSV, "a", encoding="utf-8") as f:
            f.write(f"{current_time},{code},{name},"
                    f"{d_res['shi']},{d_res['score']},{d_res['tier']},\"{','.join(map(str, d_res['seq_arr']))}\","
                    f"{w_res['shi']},\"{','.join(map(str, w_res['seq_arr']))}\","
                    f"{m_res['shi']},\"{','.join(map(str, m_res['seq_arr']))}\"\n")
        
        with open(OUTPUT_TXT, "a", encoding="utf-8") as f:
            f.write(f"[{current_time}] {code} {name} | 日K[{'🔥' if d_res['shi'] else '➖'} {d_res['score']}] | 周K[{'🔥' if w_res['shi'] else '➖'}] | 月K[{'🔥' if m_res['shi'] else '➖'}]\n")
            
    with count_lock:
        global_completed_count += 1
    return True

# ================= 4. 🤖 打工人线程逻辑 (Worker) =================
def worker(device_id, task_queue, worker_name):
    try:
        d = u2.connect(device_id)
        print(f"✅ {worker_name} ({device_id}) 神经直连成功！")
    except Exception as e:
        print(f"❌ {worker_name} ({device_id}) 连接失败")
        return

    while True:
        pause_event.wait()
        
        try:
            task = task_queue.get(timeout=3)
        except queue.Empty:
            print(f"🎉 {worker_name} 任务空，下班！")
            break
            
        stock_code, stock_name, retry_count = task['代码'], task['名称'], task['重试次数']
        
        with set_lock:
            if stock_code in completed_stocks_set:
                task_queue.task_done()
                continue

        retry_tag = f"(第{retry_count + 1}次尝试)" if retry_count > 0 else ""
        print(f"\n▶️ [{worker_name}] 锁定板块: [{stock_code}] {stock_name} {retry_tag}")

        try:
            if retry_count > 0: 
                reset_to_main_screen(d)
            
            d.click(POS_SEARCH[0], POS_SEARCH[1])
            time.sleep(1.0) 

            input_success = False
            for _ in range(3):
                search_box = d(className="android.widget.EditText")
                if not search_box.wait(timeout=3.0): 
                    d.click(POS_SEARCH[0], POS_SEARCH[1])
                    time.sleep(1.0)
                    continue 
                    
                search_box.set_text(stock_code)
                time.sleep(1.2) 
                
                if d(textContains="机构拆单策略").exists: 
                    continue  
                else:
                    input_success = True
                    break  
            
            if not input_success: 
                raise Exception("遭遇严重遮挡或搜索框持续丢失")

            d.click(POS_RESULT[0], POS_RESULT[1])
            time.sleep(1.5) 

            results = {}
            for tf in ["日K", "周K", "月K"]:
                success, res = extract_timeframe_data(d, tf, worker_name, calc_score=(tf == "日K"))
                if not success: 
                    raise Exception(f"{tf} 加载失败")
                results[tf] = res
                score_display = f" | 得分: {res['score']}" if tf == "日K" else ""
                print(f"  📺 [{worker_name}] {tf} | 始字: {'🔴有' if res['shi'] else '无'}{score_display} | 序列: [{res['seq_term'][:20]}...]")
            
            saved = save_comprehensive_result(stock_code, stock_name, results["日K"], results["周K"], results["月K"])
            if not saved:
                print(f"  ⚠️ [{worker_name}] 板块 {stock_code} 此前已被记录，跳过写入。")
            task_queue.task_done()
            
        except Exception as e:
            print(f"  ⚠️ [{worker_name}] 板块 {stock_code} 异常: {e}")
            
            if retry_count < 3:
                task['重试次数'] += 1
                print(f"  🔄 [{worker_name}] 将板块 {stock_code} 重新推入队列 (已用机会: {task['重试次数']}/3)...")
                task_queue.put(task)
            else:
                print(f"  ❌ [{worker_name}] 板块 {stock_code} 连续 3 次检测失败，已达最大重试上限，放弃并保底记录！")
                empty_res = {"shi": False, "score": 0, "tier": "检测失败", "seq_file": "", "seq_arr": [], "seq_term": ""}
                save_comprehensive_result(stock_code, stock_name, empty_res, empty_res, empty_res)

            reset_to_main_screen(d) 
            task_queue.task_done()

# ================= 5. 🚀 司令部总调度大厅 =================
def process_and_sync(is_final=True):
    try:
        os.system('git add .') 
        tag = "系统终止同步" if is_final else "系统暂停同步"
        os.system(f'git commit -m "🤖 quant-radar {tag}：{time.strftime("%m-%d %H:%M")}"')
        
        push_status = os.system('git push')
        if push_status != 0:
            os.system('git config --global http.version HTTP/1.1')
            os.system('git push')
            os.system('git config --global http.version HTTP/2')
        print(f"  ✅ 云端数据 ({tag}) 已成功推送至网站！")
        
    except Exception as e:
        print(f"\n  ⚠️ 同步异常: {e}")

if __name__ == "__main__":
    print("=== 🚀 开启 quant-radar [板块全维探测] ===")
    print("💡 输入 'p' 回车暂停并上传数据，输入 'r' 回车恢复。")
    
    listener_thread = threading.Thread(target=command_listener)
    listener_thread.daemon = True
    listener_thread.start()
    
    try:
        df = pd.read_csv(INPUT_CSV, dtype=str)
        df = df.dropna(subset=['板块代码']) 
        df['代码'] = df['板块代码'].astype(str).str.zfill(6)
        df['名称'] = df['板块名称'].astype(str)
    except Exception as e:
        print(f"❌ 读取CSV失败: {e}")
        exit()

    if os.path.exists(OUTPUT_CSV):
        try:
            existing_df = pd.read_csv(OUTPUT_CSV, dtype=str)
            if '代码' in existing_df.columns:
                completed_stocks_set.update(existing_df['代码'].str.zfill(6).tolist())
                print(f"📦 已载入历史检测记录：{len(completed_stocks_set)} 个板块（自动避免重复写入）")
        except Exception:
            pass
    else:
        with open(OUTPUT_CSV, "w", encoding="utf-8") as f:
            f.write('时间,代码,名称,日K始字,日K得分,日K定级,日K序列,周K始字,周K序列,月K始字,月K序列\n')

    stock_list = df.iloc[START_INDEX:min(END_INDEX, len(df))]

    task_queue = queue.Queue()
    for index, row in stock_list.iterrows():
        if row['代码'] not in completed_stocks_set:
            task_queue.put({'代码': row['代码'], '名称': row['名称'], '重试次数': 0})
    
    print(f"🚀 装载待检测板块任务数：{task_queue.qsize()} 个")

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
        while task_queue.unfinished_tasks > 0:
            time.sleep(2)
            with count_lock: current_completed = global_completed_count
            if current_completed - last_sync_count >= 100:
                process_and_sync(is_final=False)
                last_sync_count = current_completed
                
    except KeyboardInterrupt:
        print("\n⚠️ 紧急停止！")
        with task_queue.mutex: task_queue.queue.clear()
            
    finally:
        print("🛑 所有机甲已汇报完成，正在执行最终上传...")
        process_and_sync(is_final=True)
        print("💤 机甲休眠。")