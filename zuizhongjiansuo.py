import uiautomator2 as u2
from PIL import Image
import pandas as pd
import time
import os
import queue
import threading
import sys
import hashlib

# ================= 1. 🎛️ 终极舰队全局配置区 =================
DEVICE_LIST = [
    "127.0.0.1:16416",  
    "127.0.0.1:16384",
    "127.0.0.1:16448",
    "127.0.0.1:16480",
    "127.0.0.1:16512"
]

POS_SEARCH = (1016, 115)  
POS_RESULT = (450, 250)   

DEVICE_CONFIGS = {
    # "127.0.0.1:16416": {
    #     "OFFSET_Y": {"日K": 932, "周K": 932, "月K": 932},
    #     "SHI_Y_START": 1120, "SHI_Y_END": 1150,
    #     "BOX_TOP_OFFSET": 130, "BOX_BOTTOM_OFFSET": 650,
    #     "TAB_STEP_X": 100  # 👈 一号机横向间隔距离(像素)
    # },
    "127.0.0.1:16416": {
        "OFFSET_Y": {"日K": 850, "周K": 850, "月K": 850},
        "SHI_Y_START": 1020, "SHI_Y_END": 1050,
        "BOX_TOP_OFFSET": 100, "BOX_BOTTOM_OFFSET": 560,
        "TAB_STEP_X": 100  # 👈 其他机甲横向间隔距离(像素)
    },
    "DEFAULT": {
        "OFFSET_Y": {"日K": 850, "周K": 850, "月K": 850},
        "SHI_Y_START": 1020, "SHI_Y_END": 1050,
        "BOX_TOP_OFFSET": 100, "BOX_BOTTOM_OFFSET": 560,
        "TAB_STEP_X": 100  # 👈 其他机甲横向间隔距离(像素)
    }
}

VALIDATOR_OFFSET_Y = 300  
SCAN_X_START = 10
SCAN_X_END = 755
SHI_X_START = 730
SHI_X_END = 770
BOX_X_END = 770              
AMP_MAX_TOLERANCE = 0.30   
DRIFT_MAX_TOLERANCE = 0.20 

INPUT_CSV = "all_boards_ths.csv" 
OUTPUT_TXT = "板块雷达战报_最新.txt"
OUTPUT_CSV = "板块全维底层数据_最新.csv"

file_lock = threading.Lock()
global_completed_count = 0 
count_lock = threading.Lock()
completed_stocks_set = set()

data_lock = threading.RLock()  

phase_1_data = {}  
phase_1_hash = {}  
suspicious_stocks = {}  
phase_3_votes = {} 

all_phases_completed = False 

# ================= 2. ⚡️ 特征检测引擎 =================
def get_result_hash(results_dict):
    h_str = ""
    for tf in ["日K", "周K", "月K"]:
        r = results_dict[tf]
        seq = "".join(map(str, r['seq_arr']))
        h_str += f"[{tf}:{r['shi']}_{r['score']}_{seq}]"
    return h_str

def detect_shi_character_fast(img, pixel_base_y, config):
    top = pixel_base_y + config["SHI_Y_START"]
    bottom = pixel_base_y + config["SHI_Y_END"]
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
def extract_timeframe_data(d, tf_name, worker_name, device_id, calc_score=True):
    # 🎯 永远只找“日K”作为唯一的绝对锚点！
    anchor = d(text="日K")
    if not anchor.wait(timeout=5.0): 
        return False, None
        
    bounds = anchor.info['bounds']
    base_bottom = bounds['bottom']
    
    # 提取日K按钮的正中心物理坐标
    base_x = (bounds['left'] + bounds['right']) // 2
    base_y = (bounds['top'] + bounds['bottom']) // 2
    
    config = DEVICE_CONFIGS.get(device_id, DEVICE_CONFIGS["DEFAULT"])
    step_x = config.get("TAB_STEP_X", 100) 
    
    # 🎯 降维打击：通过日K坐标盲推点击位置
    click_x = base_x
    click_y = base_y
    if tf_name == "周K":
        click_x = base_x + step_x
    elif tf_name == "月K":
        click_x = base_x + (step_x * 2)

    # 🎯 坐标盲狙暴力双击！绕开一切UI检索误导
    d.click(click_x, click_y)
    time.sleep(0.2)
    d.click(click_x, click_y)

    # 给足 2.5 秒的绝对渲染时间，彻底抹平网络延迟
    time.sleep(2.5) 

    img = d.screenshot(format='pillow').convert('RGB')
    info = d.info
    scale_y = img.size[1] / info['displayHeight']

    pixel_base_y_shi = int(base_bottom * scale_y)
    has_shi = detect_shi_character_fast(img, pixel_base_y_shi, config)
    validator_y = int(max(10, min(base_bottom + VALIDATOR_OFFSET_Y, 1900)))
    current_offset_y = config["OFFSET_Y"].get(tf_name, config["OFFSET_Y"]["日K"])
    target_y = int(max(10, min(base_bottom + current_offset_y, 1900)))

    # 🎯 提取当前切片的像素指纹防伪
    val_box = img.crop((SCAN_X_START, target_y - 20, SCAN_X_END, target_y + 20))
    pixel_fingerprint = hashlib.md5(val_box.tobytes()).hexdigest()

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
    if calc_score:
        box_top = int(base_bottom + config["BOX_TOP_OFFSET"])
        box_bottom = int(base_bottom + config["BOX_BOTTOM_OFFSET"])
        target_left_x = -1
        if last_red_x != -1: target_left_x = max(0, last_red_x - 5)
        elif last_green_x != -1: target_left_x = max(0, last_green_x - 5)
        if target_left_x != -1 and target_left_x < BOX_X_END:
            best_score, best_tier = analyze_sideways_score(img.crop((target_left_x, box_top, BOX_X_END, box_bottom)))

    result = {
        "shi": has_shi, "score": best_score, "tier": best_tier, 
        "seq_file": seq_file, "seq_arr": data_array, "seq_term": seq_terminal,
        "fingerprint": pixel_fingerprint
    }
    return True, result

def save_comprehensive_result(code, name, d_res, w_res, m_res):
    global global_completed_count
    current_time = time.strftime("%H:%M:%S", time.localtime())
    
    with data_lock:
        if code in completed_stocks_set: return False
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
    global all_phases_completed
    try:
        d = u2.connect(device_id)
        print(f"✅ {worker_name} ({device_id}) 神经直连成功！")
    except Exception as e:
        print(f"❌ {worker_name} ({device_id}) 连接失败")
        return

    while True:
        if all_phases_completed: 
            break
            
        try:
            task = task_queue.get(timeout=2)
        except queue.Empty:
            continue

        stock_code = task['代码']
        stock_name = task['名称']
        retry_count = task['重试次数']
        current_phase = task['phase']

        with data_lock:
            if stock_code in completed_stocks_set:
                task_queue.task_done()
                continue

        phase_tag = f"[阶段{current_phase}]"
        retry_tag = f"(重试第{retry_count}次)" if retry_count > 0 else ""
        print(f"\n▶️ [{worker_name}] {phase_tag} 锁定板块: [{stock_code}] {stock_name} {retry_tag}")

        try:
            input_success = False
            for search_attempt in range(2): 
                d.click(POS_SEARCH[0], POS_SEARCH[1])
                time.sleep(1.0) 
                search_box = d(className="android.widget.EditText")
                if not search_box.wait(timeout=3.0): 
                    d.click(POS_SEARCH[0], POS_SEARCH[1])
                    time.sleep(1.0)
                    if not search_box.exists: continue 
                
                search_box.clear_text()
                search_box.set_text(stock_code)
                time.sleep(1.5) 
                d.click(POS_RESULT[0], POS_RESULT[1])
                time.sleep(1.0)
                
                if d(text="日K").exists:
                    input_success = True
                    break
                print(f"  ⏳ [{worker_name}] 结果卡顿，二次补点...")
                d.click(POS_RESULT[0], POS_RESULT[1])
                if d(text="日K").wait(timeout=3.0):
                    input_success = True
                    break

            if not input_success: 
                raise Exception("搜索完全失败")

            # ============= 正常提取数据 =============
            results = {}
            for tf in ["日K", "周K", "月K"]:
                success, res = extract_timeframe_data(d, tf, worker_name, device_id, calc_score=(tf == "日K"))
                if not success: raise Exception(f"{tf} 加载或定位失败")
                
                is_empty = not any(x != 0 for x in res["seq_arr"])

                # 🎯 像素级指纹防伪机制
                for prev_tf, prev_res in results.items():
                    if res["fingerprint"] == prev_res["fingerprint"] and not is_empty:
                        raise Exception(f"🚨 幽灵卡顿发现！【{tf}】截取到了【{prev_tf}】的同模残影！强制重搜！")

                results[tf] = res
                shi_icon = "🔴有" if res['shi'] else "➖无"
                score_str = f"| 评分: {res['score']:>4} " if tf == "日K" else ""
                print(f"  📺 [{worker_name}] {tf} | 始字:{shi_icon} {score_str}\n      扫描: [{res['seq_term']}]")
            
        except Exception as e:
            print(f"  ⚠️ [{worker_name}] 板块 {stock_code} 异常: {e}")
            if retry_count < 3:
                task['重试次数'] += 1
                task_queue.put(task)
                task_queue.task_done()
                continue
            else:
                print(f"  ❌ [{worker_name}] 板块 {stock_code} 连续3次失败，使用保底空数据！")
                empty_res = {"shi": False, "score": 0, "tier": "提取失败", "seq_file": "", "seq_arr": [], "seq_term": "", "fingerprint": ""}
                results = {"日K": empty_res, "周K": empty_res, "月K": empty_res}

        # ================= 5. 🎯 多阶段校验逻辑 =================
        res_hash = get_result_hash(results)
        
        with data_lock:
            if current_phase == 1:
                phase_1_data[stock_code] = results
                phase_1_hash[stock_code] = res_hash
            
            elif current_phase == 2:
                p1_hash = phase_1_hash.get(stock_code)
                if res_hash == p1_hash:
                    print(f"  🛡️ [{worker_name}] 板块 {stock_code} 双重校验完美匹配！落库归档。")
                    save_comprehensive_result(stock_code, stock_name, results["日K"], results["周K"], results["月K"])
                else:
                    print(f"  🚨 [{worker_name}] 板块 {stock_code} 一二审出现分歧！打入黑名单，等待联合表决。")
                    suspicious_stocks[stock_code] = stock_name
                    phase_3_votes[stock_code] = [phase_1_data[stock_code], results]
            
            elif current_phase == 3:
                print(f"  📥 [{worker_name}] 已为分歧板块 {stock_code} 投出一票。")
                phase_3_votes[stock_code].append(results)

        task_queue.task_done()

# ================= 6. 🚀 司令部总调度大厅 =================
def process_and_sync():
    try:
        os.system('git add .') 
        os.system(f'git commit -m "🤖 quant-radar 自动战报同步：{time.strftime("%m-%d %H:%M")}"')
        os.system('git push')
        print("  ✅ 云端数据已成功推送至网站！")
    except Exception as e:
        pass

def wait_for_queue(tq):
    while tq.unfinished_tasks > 0:
        time.sleep(2)

if __name__ == "__main__":
    print("=== 🚀 开启 quant-radar [增强型双重校验与表决架构] ===")
    
    try:
        start_input = input("👉 请输入起始检测序号 (按回车默认从 0 开始): ").strip()
        START_INDEX = int(start_input) if start_input else 0
        end_input = input("👉 请输入结束检测序号 (按回车默认跑完 5000): ").strip()
        END_INDEX = int(end_input) if end_input else 5000
    except ValueError:
        print("⚠️ 输入格式错误，采用默认范围 0 - 5000")
        START_INDEX = 0
        END_INDEX = 5000
        
    print(f"🎯 本次任务雷达已锁定：第 {START_INDEX} 到 {END_INDEX} 个板块。")
    print("=======================================================\n")
    
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.join(BASE_DIR, INPUT_CSV)
    
    try:
        df = pd.read_csv(input_file, dtype=str)
        df = df.dropna(subset=['板块代码']) 
        df['代码'] = df['板块代码'].astype(str).str.zfill(6)
        df['名称'] = df['板块名称'].astype(str)
    except Exception as e:
        print(f"❌ 读取CSV失败: {e}")
        exit()

    output_file = os.path.join(BASE_DIR, OUTPUT_CSV)
    if os.path.exists(output_file):
        try:
            existing_df = pd.read_csv(output_file, dtype=str)
            if '代码' in existing_df.columns:
                completed_stocks_set.update(existing_df['代码'].str.zfill(6).tolist())
                print(f"📦 已载入历史检测记录：{len(completed_stocks_set)} 个板块（自动跳过）")
        except Exception:
            pass
    else:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write('时间,代码,名称,日K始字,日K得分,日K定级,日K序列,周K始字,周K序列,月K始字,月K序列\n')

    stock_list = df.iloc[START_INDEX:min(END_INDEX, len(df))]
    pending_stocks = [row for idx, row in stock_list.iterrows() if row['代码'] not in completed_stocks_set]
    
    if not pending_stocks:
        print("🎉 所选范围内的板块均已检测完毕，系统退出。")
        exit()

    task_queue = queue.Queue()
    
    threads = []
    for i, device_id in enumerate(DEVICE_LIST):
        worker_name = f"🤖机甲-{i+1}号"
        t = threading.Thread(target=worker, args=(device_id, task_queue, worker_name))
        t.daemon = True 
        t.start()
        threads.append(t)
        time.sleep(1) 

    try:
        # ================= 阶段一：初次扫描 =================
        print(f"\n=======================================================")
        print(f"🌀 【阶段一】开启全盘盲扫 (共 {len(pending_stocks)} 个板块)")
        print(f"=======================================================")
        for row in pending_stocks:
            task_queue.put({'代码': row['代码'], '名称': row['名称'], '重试次数': 0, 'phase': 1})
        wait_for_queue(task_queue)

        # ================= 阶段二：二次复核 =================
        print(f"\n=======================================================")
        print(f"🌀 【阶段二】开启全盘交叉复核！相同则归档，不同则打入黑名单")
        print(f"=======================================================")
        for row in pending_stocks:
            task_queue.put({'代码': row['代码'], '名称': row['名称'], '重试次数': 0, 'phase': 2})
        wait_for_queue(task_queue)

        # ================= 阶段三：终极表决 =================
        if suspicious_stocks:
            print(f"\n=======================================================")
            print(f"🌀 【阶段三】发现 {len(suspicious_stocks)} 个分歧板块！启动五机甲联合表决！")
            print(f"=======================================================")
            for code, name in suspicious_stocks.items():
                for _ in range(5):
                    task_queue.put({'代码': code, '名称': name, '重试次数': 0, 'phase': 3})
            wait_for_queue(task_queue)

            print("\n🗳️ 终极表决结束，正在统计票数...")
            for code, name in suspicious_stocks.items():
                votes = phase_3_votes[code]
                hash_counts = {}
                hash_to_res = {}
                for v in votes:
                    h = get_result_hash(v)
                    hash_counts[h] = hash_counts.get(h, 0) + 1
                    hash_to_res[h] = v
                
                best_hash = max(hash_counts, key=hash_counts.get)
                best_res = hash_to_res[best_hash]
                print(f"  🏆 [{code}] {name} 表决完成！最终高票结果占比: ({hash_counts[best_hash]}/{len(votes)} 票)")
                save_comprehensive_result(code, name, best_res["日K"], best_res["周K"], best_res["月K"])
        else:
            print(f"\n🎉 完美！所有板块一二审全部匹配，无需启动表决！")

    except KeyboardInterrupt:
        print("\n⚠️ 紧急停止！")
        with task_queue.mutex: task_queue.queue.clear()
            
    finally:
        all_phases_completed = True 
        print("🛑 所有机甲已遣散。正在执行云端代码同步...")
        process_and_sync()
        print("💤 指挥部断电休眠。")