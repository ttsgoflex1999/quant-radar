import uiautomator2 as u2
from PIL import Image
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
END_INDEX = 4920    

POS_SEARCH = (1016, 115)  
POS_RESULT = (450, 250)   

INPUT_CSV = "full_a_share_stocks_latest.csv" 
OUTPUT_TXT = "拉升雷达战报_最新.txt"
OUTPUT_CSV = "拉升底层数据_最新.csv"
FILTERED_CSV = "准备拉升重点关注_最新.csv"

# 🔒 线程锁与全局计数器
file_lock = threading.Lock()
global_completed_count = 0 
count_lock = threading.Lock()

# ================= 2. ⚡️ 极速特征检测引擎 =================
def detect_shi_character_fast(img, pixel_base_y):
    """极速检测特定区域是否出现灰色的 '始' 字 (免疫红绿黑线干扰)"""
    X_START = 745
    X_END = 755
    OFFSET_Y_START = 1035
    OFFSET_Y_END = 1050
    
    top = pixel_base_y + OFFSET_Y_START
    bottom = pixel_base_y + OFFSET_Y_END
    
    width, height = img.size
    left = max(0, min(X_START, width))
    right = max(0, min(X_END, width))
    top = max(0, min(top, height))
    bottom = max(0, min(bottom, height))
    
    gray_pixel_count = 0
    
    for x in range(left, right):
        for y in range(top, bottom):
            r, g, b = img.getpixel((x, y))
            if (50 < r < 170) and (50 < g < 170) and (50 < b < 170):
                if abs(r - g) < 25 and abs(r - b) < 25 and abs(g - b) < 25:
                    gray_pixel_count += 1
                
    if gray_pixel_count > 12:
        return True
    return False

# ================= 3. 核心工具包 =================
def reset_to_main_screen(d, device_name):
    # 仅在异常兜底时触发退回
    d.click(75, 112)
    time.sleep(1.0)
    d.click(75, 112)
    time.sleep(1.5)

def save_shi_result(code, name, weekly_shi, monthly_shi):
    global global_completed_count
    current_time = time.strftime("%H:%M:%S", time.localtime())
    w_symbol = "🔥" if weekly_shi else "➖"
    m_symbol = "🔥" if monthly_shi else "➖"
    
    with file_lock: 
        if not os.path.exists(OUTPUT_CSV):
            with open(OUTPUT_CSV, "w", encoding="utf-8") as f:
                f.write('时间,代码,名称,周K拉升信号,月K拉升信号\n')
            
        with open(OUTPUT_CSV, "a", encoding="utf-8") as f:
            f.write(f"{current_time},{code},{name},{weekly_shi},{monthly_shi}\n")
        
        with open(OUTPUT_TXT, "a", encoding="utf-8") as f:
            f.write(f"[{current_time}] {code} {name} | 周K:{w_symbol} | 月K:{m_symbol}\n")
            
    with count_lock:
        global_completed_count += 1

# ================= 4. 🤖 打工人线程逻辑 (Worker) =================
def worker(device_id, task_queue, worker_name):
    try:
        d = u2.connect(device_id)
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
        retry_count = task['重试次数']

        tag = f"(第{retry_count}次重试)" if retry_count > 0 else ""
        print(f"\n▶️ [{worker_name}] 抢到订单: [{stock_code}] {stock_name} {tag}")

        try:
            if retry_count > 0:
                print(f"  🔄 [{worker_name}] 重试订单，执行环境大清洗...")
                reset_to_main_screen(d, worker_name)
            
            d.click(POS_SEARCH[0], POS_SEARCH[1])
            time.sleep(1.0) 

            input_success = False
            for input_attempt in range(3):
                search_box = d(className="android.widget.EditText")
                if search_box.exists:
                    search_box.set_text(stock_code)
                else:
                    raise Exception("未找到搜索输入框")
                
                time.sleep(1.2) 
                
                if d(textContains="机构拆单策略").exists:
                    print(f"  🛡️ [{worker_name}] 遭遇'机构拆单策略'遮挡，重新输入尝试刷新(第{input_attempt+1}次)...")
                    continue  
                else:
                    input_success = True
                    break  
            
            if not input_success:
                raise Exception("连续3次遭遇'机构拆单策略'干扰，主动触发整机重试")

            if d(textContains="综合").exists:
                print(f"  👀 [{worker_name}] 发现'综合'界面，修正点击落点至 (450, 350)")
                d.click(450, 350)
            else:
                d.click(POS_RESULT[0], POS_RESULT[1])
                
            time.sleep(1.5) 

            # 🎯 找周K
            target_zhou = d(text="周K")
            weekly_shi = False
            monthly_shi = False
            
            if target_zhou.wait(timeout=5.0):
                target_zhou.click()
                time.sleep(2.0) 
                
                info = d.info
                img_zhou = d.screenshot(format='pillow').convert('RGB')
                scale_y = img_zhou.size[1] / info['displayHeight']
                pixel_base_y_zhou = int(target_zhou.info['bounds']['bottom'] * scale_y)
                
                weekly_shi = detect_shi_character_fast(img_zhou, pixel_base_y_zhou)

                # 🎯 找月K
                target_yue = d(text="月K")
                if target_yue.wait(timeout=5.0):
                    target_yue.click()
                    time.sleep(2.0) 
                    
                    img_yue = d.screenshot(format='pillow').convert('RGB')
                    pixel_base_y_yue = int(target_yue.info['bounds']['bottom'] * scale_y)
                    
                    monthly_shi = detect_shi_character_fast(img_yue, pixel_base_y_yue)
                
                    w_tag = "🔴有" if weekly_shi else "无"
                    m_tag = "🔴有" if monthly_shi else "无"
                    print(f"  📺 [{worker_name}] 周K始字: {w_tag} | 月K始字: {m_tag}")
                    save_shi_result(stock_code, stock_name, weekly_shi, monthly_shi)
                    
                    # 🎯 【核心修正 1】：完美成功后，不做任何返回动作！取消 d.click(75, 112) 直接进入下一次循环
                    
                else:
                    if retry_count < 3:
                        task['重试次数'] += 1
                        print(f"  ⚠️ [{worker_name}] 月K加载失败，重回队列...")
                        task_queue.put(task)
                        reset_to_main_screen(d, worker_name) 
                    else:
                        print(f"  ❌ [{worker_name}] 连续3次月K加载失败，放弃该股！")
                        save_shi_result(stock_code, stock_name, False, False)
                        reset_to_main_screen(d, worker_name) 
            else:
                if retry_count < 3:
                    task['重试次数'] += 1
                    print(f"  ⚠️ [{worker_name}] 周K加载失败，重回队列...")
                    task_queue.put(task)
                    reset_to_main_screen(d, worker_name) 
                else:
                    print(f"  ❌ [{worker_name}] 连续3次周K加载失败，放弃该股！")
                    save_shi_result(stock_code, stock_name, False, False)
                    reset_to_main_screen(d, worker_name) 

            task_queue.task_done()
            
        except Exception as e:
            print(f"⚠️ [{worker_name}] 扫描 {stock_code} 发生异常: {e}")
            if retry_count < 3:
                task['重试次数'] += 1
                task_queue.put(task)
            else:
                save_shi_result(stock_code, stock_name, False, False)
            reset_to_main_screen(d, worker_name) 
            task_queue.task_done()

# ================= 5. 🚀 司令部总调度大厅 =================
def process_and_sync(is_final=True):
    try:
        if not os.path.exists(OUTPUT_CSV):
            return
            
        df_scan = pd.read_csv(OUTPUT_CSV)
        target_stocks = []
        for index, row in df_scan.iterrows():
            w_shi = str(row['周K拉升信号']).strip() == 'True'
            m_shi = str(row['月K拉升信号']).strip() == 'True'
            
            if w_shi or m_shi:
                action_type = "🔥 周月双启" if (w_shi and m_shi) else ("📈 周K单启" if w_shi else "🚀 月K单启")
                target_stocks.append({
                    '代码': str(row['代码']).zfill(6), 
                    '名称': row['名称'],
                    '共振级别': action_type,
                    '周K信号': w_shi,
                    '月K信号': m_shi
                })
        
        filtered_df = pd.DataFrame(target_stocks)
        if not filtered_df.empty:
            filtered_df.to_csv(FILTERED_CSV, index=False, encoding='utf-8-sig')
            msg = f"阶段结算：当前捕获 {len(filtered_df)} 只拉升股票"
            print(f"  📁 {msg}。")
        else:
            pd.DataFrame(columns=['代码', '名称', '共振级别', '周K信号', '月K信号']).to_csv(FILTERED_CSV, index=False, encoding='utf-8-sig')

        os.system('git add .') 
        tag = "准备拉升终止结算" if is_final else "准备拉升阶段同步"
        os.system(f'git commit -m "🤖 quant-radar {tag}：{time.strftime("%m-%d %H:%M")}"')
        
        push_status = os.system('git push')
        if push_status != 0:
            os.system('git config --global http.version HTTP/1.1')
            os.system('git push')
            os.system('git config --global http.version HTTP/2')
            
        print(f"  ✅ 云端同步 ({tag}) 尝试执行完毕！")

    except Exception as e:
        print(f"\n  ⚠️ 后处理异常: {e}")

if __name__ == "__main__":
    print("=== 🚀 开启 quant-radar [准备拉升专属] 量化巡航系统 ===")
    
    try:
        df = pd.read_csv(INPUT_CSV)
        df = df[df['风险状态'] == '正常上市'].copy()
        df['股票代码'] = df['股票代码'].astype(str).str.zfill(6) 
    except FileNotFoundError:
        print(f"❌ 找不到 {INPUT_CSV}！请先运行检测程序。")
        exit()

    stock_list = df.iloc[START_INDEX:min(END_INDEX, len(df))]
    
    if not os.path.exists(OUTPUT_CSV):
        with open(OUTPUT_CSV, "w", encoding="utf-8") as f:
            f.write('时间,代码,名称,周K拉升信号,月K拉升信号\n')

    with open(OUTPUT_TXT, "a", encoding="utf-8") as f:
        f.write(f"\n--- 🚀 新扫描启动: {time.strftime('%m-%d %H:%M')} ---\n")

    task_queue = queue.Queue()
    for index, row in stock_list.iterrows():
        task_queue.put({'序号': index, '代码': row['股票代码'], '名称': row['股票名称'], '重试次数': 0})
    
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
            
            # 🎯 【核心修正 2】：恢复并发同步容错逻辑 (区间跨度判定)
            if current_completed - last_sync_count >= 500:
                print(f"\n✨ [节点触发] 舰队实际已完成 {current_completed} 只探测，触发阶段性推流机制...")
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