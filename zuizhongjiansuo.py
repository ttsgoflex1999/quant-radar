import uiautomator2 as u2
from PIL import Image, ImageDraw
import pandas as pd
import time
import os
import queue
import threading

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

# 🎯 视觉雷达黄金参数
OFFSET_Y = 845           
VALIDATOR_OFFSET_Y = 300  
SCAN_X_START = 10
SCAN_X_END = 750
BOX_TOP_OFFSET = 100
BOX_BOTTOM_OFFSET = 600
AMP_MAX_TOLERANCE = 0.30   
DRIFT_MAX_TOLERANCE = 0.20 

# 💾 数据输出配置 (针对板块/ETF专属)
INPUT_CSV = "all_boards_ths.csv" 
OUTPUT_TXT = "板块雷达战报_最新.txt"
OUTPUT_CSV = "板块全维底层数据_最新.csv"
FILTERED_CSV = "优质板块重点关注_最新.csv"

# 🔒 线程锁与全局计数器
file_lock = threading.Lock()
global_completed_count = 0 
count_lock = threading.Lock()

# ================= 2. ⚡️ 特征检测引擎 =================

def detect_shi_character_fast(img, pixel_base_y):
    """检测灰色的 '始' 字 (免疫红绿黑线干扰)"""
    X_START, X_END = 745, 755
    OFFSET_Y_START, OFFSET_Y_END = 1035, 1050
    
    top = pixel_base_y + OFFSET_Y_START
    bottom = pixel_base_y + OFFSET_Y_END
    
    width, height = img.size
    left, right = max(0, min(X_START, width)), max(0, min(X_END, width))
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
    """计算红绿柱洗盘形态分"""
    width, height = img.size
    kline_pixels = []
    for x in range(width):
        for y in range(height):
            r, g, b = img.getpixel((x, y))
            if (r > 160 and g < 130 and b < 130) or (g > 140 and r < 130 and b < 130):
                kline_pixels.append((x, y))

    if not kline_pixels:
        return 0, "无K线"

    y_coords = sorted([p[1] for p in kline_pixels])
    trim_idx = max(1, int(len(y_coords) * 0.05))
    core_y = y_coords[trim_idx:-trim_idx]
    if not core_y:
        return 0, "数据匮乏"

    core_amplitude = core_y[-1] - core_y[0]
    score_amp = max(0, 60 * (1 - ((core_amplitude / height) / AMP_MAX_TOLERANCE)))

    left_y = [p[1] for p in kline_pixels if p[0] < width * 0.3]
    right_y = [p[1] for p in kline_pixels if p[0] > width * 0.7]
    if not left_y or not right_y:
         return 0, "走势过短"

    gravity_drift = abs(sorted(left_y)[len(left_y)//2] - sorted(right_y)[len(right_y)//2])
    score_drift = max(0, 40 * (1 - ((gravity_drift / height) / DRIFT_MAX_TOLERANCE)))

    final_score = round(score_amp + score_drift, 1)
    tier = "[S级]极品横盘" if final_score >= 85 else "[A级]标准箱体" if final_score >= 60 else "[B级]宽幅震荡" if final_score >= 40 else "[C级]非横盘"
    return final_score, tier

# ================= 3. 核心工具包 =================

def reset_to_main_screen(d):
    """仅在异常兜底时触发退回"""
    d.click(75, 112)
    time.sleep(1.0)
    d.click(75, 112)
    time.sleep(1.5)

def extract_timeframe_data(d, tf_name, worker_name):
    """【高度集成】抽取指定周期下的两项核心指标"""
    target = d(text=tf_name)
    if not target.wait(timeout=4.0):
        print(f"  ⚠️ [{worker_name}] 未发现 {tf_name}，盲区唤醒点击 (450, 350)...")
        d.click(450, 350)
        time.sleep(1.0)
        if not target.wait(timeout=3.0):
            return False, None
            
    target.click()
    time.sleep(2.0) # 渲染缓冲

    img = d.screenshot(format='pillow').convert('RGB')
    info = d.info
    scale_y = img.size[1] / info['displayHeight']
    base_bottom = target.info['bounds']['bottom']

    # 1. 测定拉升 "始" 字
    pixel_base_y_shi = int(base_bottom * scale_y)
    has_shi = detect_shi_character_fast(img, pixel_base_y_shi)
    
    # 2. 测定红绿柱形态
    validator_y = int(max(10, min(base_bottom + VALIDATOR_OFFSET_Y, 1900)))
    target_y = int(max(10, min(base_bottom + OFFSET_Y, 1900)))
    
    canvas_loaded = any(abs(img.getpixel((x, validator_y))[0] - img.getpixel((x, validator_y))[1]) > 20 for x in range(SCAN_X_START, SCAN_X_END + 1, 10))
    if not canvas_loaded:
        return False, None

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

    best_score, best_tier = 0, "无信号"
    if last_red_x != -1 or last_green_x != -1:
        right = 755
        top, bottom = base_bottom + BOX_TOP_OFFSET, base_bottom + BOX_BOTTOM_OFFSET
        if last_red_x != -1 and (left_red := max(0, last_red_x - 5)) < right:
            score_r, tier_r = analyze_sideways_score(img.crop((left_red, top, right, bottom)))
            if score_r > best_score: best_score, best_tier = score_r, tier_r
        if last_green_x != -1 and (left_green := max(0, last_green_x - 5)) < right:
            score_g, tier_g = analyze_sideways_score(img.crop((left_green, top, right, bottom)))
            if score_g > best_score: best_score, best_tier = score_g, tier_g

    result = {
        "shi": has_shi, "score": best_score, "tier": best_tier, 
        "seq_file": seq_file, "seq_arr": data_array, "seq_term": seq_terminal
    }
    return True, result

def save_comprehensive_result(code, name, d_res, w_res, m_res):
    global global_completed_count
    current_time = time.strftime("%H:%M:%S", time.localtime())
    
    with file_lock: 
        if not os.path.exists(OUTPUT_CSV):
            with open(OUTPUT_CSV, "w", encoding="utf-8") as f:
                f.write('时间,代码,名称,日K始字,日K得分,日K定级,日K序列,周K始字,周K得分,周K定级,周K序列,月K始字,月K得分,月K定级,月K序列\n')
            
        with open(OUTPUT_CSV, "a", encoding="utf-8") as f:
            f.write(f"{current_time},{code},{name},"
                    f"{d_res['shi']},{d_res['score']},{d_res['tier']},\"{','.join(map(str, d_res['seq_arr']))}\","
                    f"{w_res['shi']},{w_res['score']},{w_res['tier']},\"{','.join(map(str, w_res['seq_arr']))}\","
                    f"{m_res['shi']},{m_res['score']},{m_res['tier']},\"{','.join(map(str, m_res['seq_arr']))}\"\n")
        
        with open(OUTPUT_TXT, "a", encoding="utf-8") as f:
            f.write(f"[{current_time}] {code} {name} | 日K[{'🔥' if d_res['shi'] else '➖'} {d_res['score']}] | 周K[{'🔥' if w_res['shi'] else '➖'} {w_res['score']}] | 月K[{'🔥' if m_res['shi'] else '➖'} {m_res['score']}]\n")
            
    with count_lock:
        global_completed_count += 1

# ================= 4. 🤖 打工人线程逻辑 (Worker) =================
def worker(device_id, task_queue, worker_name):
    try:
        d = u2.connect(device_id)
        print(f"✅ {worker_name} ({device_id}) 神经直连成功，准备抢单！")
    except Exception as e:
        print(f"❌ {worker_name} ({device_id}) 连接失败")
        return

    while True:
        try:
            task = task_queue.get(timeout=3)
        except queue.Empty:
            print(f"🎉 {worker_name} 发现任务队列已空，打卡下班！")
            break
            
        stock_code = task['代码']
        stock_name = task['名称']
        retry_count = task['重试次数']

        print(f"\n▶️ [{worker_name}] 锁定板块: [{stock_code}] {stock_name} {'(重试)' if retry_count>0 else ''}")

        try:
            if retry_count > 0:
                reset_to_main_screen(d)
            
            d.click(POS_SEARCH[0], POS_SEARCH[1])
            time.sleep(1.0) 

            # 广告拦截循环
            input_success = False
            for input_attempt in range(3):
                search_box = d(className="android.widget.EditText")
                if search_box.exists:
                    search_box.set_text(stock_code)
                else:
                    raise Exception("未找到搜索框")
                
                time.sleep(1.2) 
                
                if d(textContains="机构拆单策略").exists:
                    continue  
                else:
                    input_success = True
                    break  
            
            if not input_success:
                raise Exception("持续遭遇策略遮挡")

            # 动态分流
            if d(textContains="综合").exists:
                d.click(450, 350)
            else:
                d.click(POS_RESULT[0], POS_RESULT[1])
            time.sleep(1.5) 

            # 🎯 循环遍历 三大周期
            results = {}
            for tf in ["日K", "周K", "月K"]:
                success, res = extract_timeframe_data(d, tf, worker_name)
                if not success:
                    raise Exception(f"周期 {tf} 加载失败")
                results[tf] = res
                print(f"  📺 [{worker_name}] {tf} | 始字: {'🔴有' if res['shi'] else '无'} | 得分: {res['score']} | 序列: [{res['seq_term']}]")
            
            # 全周期提取成功，保存数据
            save_comprehensive_result(stock_code, stock_name, results["日K"], results["周K"], results["月K"])
            
            # 🎯 核心逻辑 1：不点返回，直接跳出结束本轮！
            task_queue.task_done()
            
        except Exception as e:
            print(f"  ⚠️ [{worker_name}] 板块 {stock_code} 异常: {e}")
            if retry_count < 3:
                task['重试次数'] += 1
                task_queue.put(task)
            reset_to_main_screen(d) 
            task_queue.task_done()

# ================= 5. 🚀 司令部总调度大厅 =================
def process_and_sync(is_final=True):
    try:
        if not os.path.exists(OUTPUT_CSV): return
        df_scan = pd.read_csv(OUTPUT_CSV)
        target_stocks = []
        
        for index, row in df_scan.iterrows():
            d_shi, d_score = str(row['日K始字']).strip() == 'True', pd.to_numeric(row['日K得分'], errors='coerce')
            w_shi, w_score = str(row['周K始字']).strip() == 'True', pd.to_numeric(row['周K得分'], errors='coerce')
            m_shi, m_score = str(row['月K始字']).strip() == 'True', pd.to_numeric(row['月K得分'], errors='coerce')
            
            # 🎯 严选条件：只要任意周期有始字，或任意周期得分 >= 60 (标准洗盘及以上)
            if d_shi or w_shi or m_shi or max(d_score, w_score, m_score) >= 60:
                action = []
                if w_shi and m_shi: action.append("🔥周月双启")
                elif w_shi: action.append("📈周K起爆")
                elif m_shi: action.append("🚀月K起爆")
                
                if max(d_score, w_score, m_score) >= 85: action.append("👑S级横盘")
                elif max(d_score, w_score, m_score) >= 60: action.append("📦A级洗盘")
                
                target_stocks.append({
                    '代码': str(row['代码']).zfill(6), 
                    '名称': row['名称'],
                    '综合共振标识': " | ".join(action) if action else "日K异动",
                    '日K信号': d_shi, '日K得分': d_score,
                    '周K信号': w_shi, '周K得分': w_score,
                    '月K信号': m_shi, '月K得分': m_score
                })
        
        filtered_df = pd.DataFrame(target_stocks)
        if not filtered_df.empty:
            filtered_df = filtered_df.sort_values(by=['周K信号', '月K信号', '周K得分'], ascending=[False, False, False])
            filtered_df.to_csv(FILTERED_CSV, index=False, encoding='utf-8-sig')
            print(f"  📁 阶段结算：捕获 {len(filtered_df)} 个高潜板块。")
        else:
            pd.DataFrame(columns=['代码', '名称', '综合共振标识', '日K信号', '日K得分', '周K信号', '周K得分', '月K信号', '月K得分']).to_csv(FILTERED_CSV, index=False, encoding='utf-8-sig')

        os.system('git add .') 
        tag = "全维度板块终止结算" if is_final else "全维度板块阶段同步"
        os.system(f'git commit -m "🤖 quant-radar {tag}：{time.strftime("%m-%d %H:%M")}"')
        os.system('git push')
        
    except Exception as e:
        print(f"\n  ⚠️ 后处理异常: {e}")

if __name__ == "__main__":
    print("=== 🚀 开启 quant-radar [板块/ETF 全维探测] 量化巡航系统 ===")
    
    try:
        # 🎯 精准匹配板块CSV结构的列名
        df = pd.read_csv(INPUT_CSV, dtype=str)
        df = df.dropna(subset=['板块代码']) # 剔除空行
        
        # 严格使用截图里的准确列名
        df['代码'] = df['板块代码'].astype(str).str.zfill(6)
        df['名称'] = df['板块名称'].astype(str)
        
    except FileNotFoundError:
        print(f"❌ 找不到 {INPUT_CSV}！请确保文件存在。")
        exit()
    except KeyError as e:
        print(f"❌ CSV 列名匹配失败！请确保文件中有 '板块代码' 和 '板块名称' 列。错误详情: {e}")
        exit()

    stock_list = df.iloc[START_INDEX:min(END_INDEX, len(df))]
    print(f"✅ 成功装载待扫描板块/ETF：{len(stock_list)} 个")
    
    if not os.path.exists(OUTPUT_CSV):
        with open(OUTPUT_CSV, "w", encoding="utf-8") as f:
            f.write('时间,代码,名称,日K始字,日K得分,日K定级,日K序列,周K始字,周K得分,周K定级,周K序列,月K始字,月K得分,月K定级,月K序列\n')

    with open(OUTPUT_TXT, "a", encoding="utf-8") as f:
        f.write(f"\n--- 🚀 新扫描启动: {time.strftime('%m-%d %H:%M')} ---\n")

    task_queue = queue.Queue()
    for index, row in stock_list.iterrows():
        task_queue.put({'代码': row['代码'], '名称': row['名称'], '重试次数': 0})
    
    total_tasks = task_queue.qsize()

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
            
            with count_lock:
                current_completed = global_completed_count
            
            # 🎯 针对板块数量较少，触发阈值调为 100
            if current_completed - last_sync_count >= 100:
                print(f"\n✨ [节点触发] 舰队已完成 {current_completed} 个板块探测，同步最新战果...")
                process_and_sync(is_final=False)
                last_sync_count = current_completed
                
    except KeyboardInterrupt:
        print("\n⚠️ 紧急停止！")
        with task_queue.mutex:
            task_queue.queue.clear()
            
    finally:
        print("\n=========================================")
        process_and_sync(is_final=True)
        print("💤 机甲休眠。")