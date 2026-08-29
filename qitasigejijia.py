import uiautomator2 as u2
from PIL import ImageDraw

# ================= 诊断配置 =================
DEVICE_IP = "127.0.0.1:16480"  # 用一号机做测试

# 📍 1. 红绿柱检测参数 (Y轴基于日K按钮偏移)
OFFSET_Y = 850           
SCAN_X_START = 10
SCAN_X_END = 755

# 📍 2. 始字检测参数 (Y轴基于日K按钮偏移，X轴绝对位置)
SHI_X_START = 730
SHI_X_END = 770
SHI_Y_START = 1030
SHI_Y_END = 1060

# 📍 3. 横盘评分大框参数 (Y轴基于日K按钮偏移，X轴右边界绝对位置)
BOX_TOP_OFFSET = 100           
BOX_BOTTOM_OFFSET = 560        
BOX_X_END = 770                
AMP_MAX_TOLERANCE = 0.30       
DRIFT_MAX_TOLERANCE = 0.20     
# ============================================

def analyze_sideways_score(img):
    """横盘评分核心逻辑，从主程序1:1复刻"""
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


def debug_vision_full():
    print(f"🔌 正在连接设备 {DEVICE_IP} ...")
    try:
        d = u2.connect(DEVICE_IP)
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return

    print("📸 正在截取屏幕并分析坐标...")
    img = d.screenshot(format='pillow').convert('RGB')
    
    info = d.info
    scale_y = img.size[1] / info['displayHeight']
    
    target = d(text="日K")
    if not target.exists:
        print("❌ 当前屏幕上找不到'日K'按钮，请确保停留在板块详情的 K线 界面！")
        return
        
    base_bottom = target.info['bounds']['bottom']
    pixel_base_y = int(base_bottom * scale_y)

    # ================= 开始提取实际数据 =================
    
    # 1. 模拟机甲测算红绿柱
    target_y = int(max(10, min(base_bottom + OFFSET_Y, 1900)))
    seq_terminal = ""
    last_red_x, last_green_x = -1, -1
    
    for x in range(SCAN_X_START, SCAN_X_END + 1, 2):
        r, g, b = img.getpixel((x, target_y))
        if r > 180 and g < 100 and b < 100:
            seq_terminal += "\033[91m█\033[0m" # 红色方块
            last_red_x = x
        elif g > 150 and r < 120 and b < 120:
            seq_terminal += "\033[92m█\033[0m" # 绿色方块
            last_green_x = x
        else:
            seq_terminal += "\033[90m-\033[0m" # 灰色虚线
            
    # 2. 模拟机甲测算“始”字
    shi_top = pixel_base_y + SHI_Y_START
    shi_bottom = pixel_base_y + SHI_Y_END
    width, height = img.size
    left, right = max(0, min(SHI_X_START, width)), max(0, min(SHI_X_END, width))
    top, bottom = max(0, min(shi_top, height)), max(0, min(shi_bottom, height))
    
    gray_pixel_count = 0
    for x in range(left, right):
        for y in range(top, bottom):
            r, g, b = img.getpixel((x, y))
            if (50 < r < 170) and (50 < g < 170) and (50 < b < 170):
                if abs(r - g) < 25 and abs(r - b) < 25 and abs(g - b) < 25:
                    gray_pixel_count += 1
    has_shi = gray_pixel_count > 12

    # 3. 模拟机甲测算横盘得分
    best_score, best_tier = 0, "无评级"
    dynamic_left_x = SCAN_X_START 
    box_top = int(base_bottom + BOX_TOP_OFFSET)
    box_bottom = int(base_bottom + BOX_BOTTOM_OFFSET)
    
    print("\n" + "-"*30)
    # 🎯 核心修改：绝对优先级判断！红柱优先，绿柱兜底
    target_left_x = -1
    if last_red_x != -1:
        target_left_x = max(0, last_red_x - 5)
        print(f"🔍 评分锚点定位: 发现红柱！以最右红柱为左边界 (X={target_left_x})")
    elif last_green_x != -1:
        target_left_x = max(0, last_green_x - 5)
        print(f"🔍 评分锚点定位: 未发现红柱。降级以最右绿柱为左边界 (X={target_left_x})")
    else:
        print(f"🔍 评分锚点定位: 未发现任何异动资金柱，放弃评分。")

    if target_left_x != -1 and target_left_x < BOX_X_END:
        best_score, best_tier = analyze_sideways_score(img.crop((target_left_x, box_top, BOX_X_END, box_bottom)))
        dynamic_left_x = target_left_x

    # ================= 打印诊断结果 =================
    print("\n" + "="*50)
    print(f"🚀 【始字检测结果】: {'🔴有始字' if has_shi else '➖无'} (特征像素数: {gray_pixel_count}/12)")
    print(f"📦 【横盘形态评分】: 得分 {best_score} | 定级 {best_tier}")
    print(f"🔴 【红绿柱序列】:\n[{seq_terminal}]")
    print("="*50 + "\n")

    # ================= 开始画图可视化 =================
    draw = ImageDraw.Draw(img)
    
    # 🔴 1. 画出【红绿柱】序列扫描线 (黄线)
    draw.line([(SCAN_X_START, target_y), (SCAN_X_END, target_y)], fill="yellow", width=4)
    draw.text((SCAN_X_START, target_y - 30), f"红绿柱扫描线 (OFFSET_Y={OFFSET_Y})", fill="yellow")

    # 🚀 2. 画出【始字】检测框 (红框)
    draw.rectangle([(SHI_X_START, shi_top), (SHI_X_END, shi_bottom)], outline="red", width=5)
    draw.text((SHI_X_START - 150, shi_top - 30), f"始字检测区", fill="red")

    # 📦 3. 画出【横盘评分】大框 (蓝框)
    draw.rectangle([(dynamic_left_x, box_top), (BOX_X_END, box_bottom)], outline="blue", width=6)
    draw.text((dynamic_left_x + 10, box_top + 10), f"动态评分区 (左:{dynamic_left_x} 右:{BOX_X_END})", fill="blue")
    
    save_path = "debug_full_vision.jpg"
    img.save(save_path)
    print(f"✅ 可视化诊断图已生成！请打开当前文件夹下的 【{save_path}】 对比实际画面。")

if __name__ == "__main__":
    debug_vision_full()