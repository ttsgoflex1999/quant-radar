import uiautomator2 as u2
from PIL import Image, ImageDraw
import time
import os

# ================= 🎛️ 参数配置 =================
DEVICE_ID = "127.0.0.1:26656"
OFFSET_Y = 844            
SCAN_X_START = 10
SCAN_X_END = 751          

BOX_TOP_OFFSET = 100
BOX_BOTTOM_OFFSET = 600

# 💯 评分系统黄金耐受度阈值
AMP_MAX_TOLERANCE = 0.30   # 振幅超过 30% 视为不及格 (0分)
DRIFT_MAX_TOLERANCE = 0.20 # 重心倾斜超过 20% 视为不及格 (0分)
# ===============================================


def analyze_sideways_score(img):
    """
    视觉横盘 0-100 评分引擎 (纯粹的算分机器)
    """
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
        return 0, "❌ 零分：未提取到有效 K 线像素。", img

    # 算子A：振幅压缩分 (满分 60)
    y_coords = [p[1] for p in kline_pixels]
    y_coords.sort()
    
    trim_idx = max(1, int(len(y_coords) * 0.05))
    core_y = y_coords[trim_idx:-trim_idx]
    
    if not core_y:
        return 0, "❌ 零分：K 线数据量极度匮乏。", img
        
    top_bound = core_y[0]      
    bottom_bound = core_y[-1]  
    core_amplitude = bottom_bound - top_bound
    amplitude_ratio = core_amplitude / height
    
    score_amp = max(0, 60 * (1 - (amplitude_ratio / AMP_MAX_TOLERANCE)))

    # 算子B：重心平稳分 (满分 40)
    left_y = [p[1] for p in kline_pixels if p[0] < width * 0.3]
    right_y = [p[1] for p in kline_pixels if p[0] > width * 0.7]
    
    if not left_y or not right_y:
         return 0, "❌ 零分：K 线走势过短，无法测算左右重心对比。", img
         
    left_median = sorted(left_y)[len(left_y) // 2]
    right_median = sorted(right_y)[len(right_y) // 2]
    gravity_drift = abs(left_median - right_median)
    drift_ratio = gravity_drift / height
    
    score_drift = max(0, 40 * (1 - (drift_ratio / DRIFT_MAX_TOLERANCE)))

    # 汇总
    final_score = round(score_amp + score_drift, 1)
    
    if final_score >= 85:
        tier = "🏆 [S级] 完美平推极品横盘"
    elif final_score >= 60:
        tier = "🎯 [A级] 标准震荡洗盘箱体"
    elif final_score >= 40:
        tier = "⚠️ [B级] 劣质宽幅震荡"
    else:
        tier = "❌ [C级] 破位或起飞趋势，非横盘"

    report = (
        f"   ┣ 综合评分: {final_score} / 100 ({tier})\n"
        f"   ┣ 振幅得分: {round(score_amp, 1)}/60 (厚度占比 {round(amplitude_ratio*100, 1)}%)\n"
        f"   ┗ 重心得分: {round(score_drift, 1)}/40 (偏移占比 {round(drift_ratio*100, 1)}%)"
    )

    # 可视化作图
    draw = ImageDraw.Draw(img)
    draw.line([(0, top_bound), (width, top_bound)], fill=(0, 0, 255), width=2)
    draw.line([(0, bottom_bound), (width, bottom_bound)], fill=(0, 0, 255), width=2)
    draw.rectangle([(width*0.15 - 5, left_median - 5), (width*0.15 + 5, left_median + 5)], fill=(255, 0, 255))
    draw.rectangle([(width*0.85 - 5, right_median - 5), (width*0.85 + 5, right_median + 5)], fill=(255, 0, 255))
    draw.line([(width*0.15, left_median), (width*0.85, right_median)], fill=(255, 0, 255), width=3)
    draw.rectangle([(0, height-25), (100, height)], fill=(0,0,0))
    draw.text((5, height-20), f"SCORE: {final_score}", fill=(0, 255, 0))

    return final_score, report, img


def extract_and_score():
    print("=== ✂️ 启动双窗口动态横盘寻优系统 ===")
    try:
        d = u2.connect(DEVICE_ID)
        print("✅ 安卓底层直连成功！")

        target = d(text="日K")
        if not target.exists:
            print("❌ 未捕获‘日K’事件锚点，请确保界面正确！")
            return
            
        day_k_bottom = target.info['bounds']['bottom']
        radar_y = day_k_bottom + OFFSET_Y
        
        print("📸 正在提取底层画面矩阵...")
        img = d.screenshot(format='pillow').convert('RGB')
        
        # --- 步骤 1：同时定位最后一次红柱和绿柱 ---
        last_red_x = -1
        last_green_x = -1
        
        for x in range(SCAN_X_START, SCAN_X_END + 1, 2):
            r, g, b = img.getpixel((x, radar_y))
            if r > 180 and g < 100 and b < 100:     # 红色判定
                last_red_x = x
            elif g > 150 and r < 120 and b < 120:   # 绿色判定
                last_green_x = x
                
        if last_red_x == -1 and last_green_x == -1:
            print("⚪ 扫雷完毕，未发现任何主力红绿柱信号，跳过。")
            return
            
        print(f"📍 信号探测完毕：最后红柱 X={last_red_x} | 最后绿柱 X={last_green_x}")
        
        # --- 步骤 2：启动双重测算，决出胜者 ---
        best_score = -1
        best_report = ""
        best_img = None
        winning_anchor = ""
        
        right = 755
        top = day_k_bottom + BOX_TOP_OFFSET
        bottom = day_k_bottom + BOX_BOTTOM_OFFSET

        # 🎯 测试锚点 1：最后一根红柱
        if last_red_x != -1:
            left_red = max(0, last_red_x - 5)
            if left_red < right:
                box_red = img.crop((left_red, top, right, bottom))
                score_r, report_r, img_r = analyze_sideways_score(box_red)
                print(f"  🔍 红柱窗口测试得分: {score_r}")
                if score_r > best_score:
                    best_score = score_r
                    best_report = report_r
                    best_img = img_r
                    winning_anchor = "🔴 最后红柱 (主力进场点)"

        # 🎯 测试锚点 2：最后一根绿柱
        if last_green_x != -1:
            left_green = max(0, last_green_x - 5)
            if left_green < right:
                box_green = img.crop((left_green, top, right, bottom))
                score_g, report_g, img_g = analyze_sideways_score(box_green)
                print(f"  🔍 绿柱窗口测试得分: {score_g}")
                if score_g > best_score:
                    best_score = score_g
                    best_report = report_g
                    best_img = img_g
                    winning_anchor = "🟢 最后绿柱 (洗盘结束点)"

        # --- 步骤 3：输出最终结果 ---
        if best_score == -1:
            print("⚠️ 信号位置均过窄，无法生成横盘矩阵。")
            return

        print("\n" + "="*50)
        print(f"🏆 【寻优结束】最终采纳窗口: {winning_anchor}")
        print(best_report)
        print("="*50 + "\n")
        
        output_name = "sideways_scored_optimal.png"
        best_img.save(output_name)
        print(f"📁 最优判定透视图已保存为: [{output_name}]")

    except Exception as e:
        print(f"⚠️ 发生异常阻断: {e}")

if __name__ == "__main__":
    extract_and_score()
