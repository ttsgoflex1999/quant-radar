import pyautogui
import time

# ================= 1. 全局配置区 =================
TIME_QUICK = 0.5    
TIME_NORMAL = 1.0   
TIME_SEARCH = 2.0     
TIME_PAGE_LOAD = 1.0  
TIME_INDICATOR = 0.5  

POS_SEARCH = (1441, 123)  
POS_RESULT = (1200, 230)  
POS_CANCEL = (1314, 665)  

SIGNAL_X_START = 1169
SIGNAL_X_END = 1347
SIGNAL_Y_OFFSET = 57

STOCK_CODE = "002634"
# =================================================


# ================= 2. 核心工具包 =================
def find_image_and_close_popup(image_name):
    try:
        pos = pyautogui.locateCenterOnScreen(image_name, confidence=0.8)
        print(f"  -> [系统] 触发了分享弹窗，正在自动关闭...")
        time.sleep(TIME_NORMAL) 
        pyautogui.click(POS_CANCEL[0], POS_CANCEL[1])
        time.sleep(TIME_NORMAL) 
        return pos 
    except pyautogui.ImageNotFoundException:
        return None
# =================================================


# ================= 3. 主业务流程 =================
if __name__ == "__main__":
    print("=== 🚀 开始极速版视觉测试 ===")
    print("请将镜像放好，1秒后发车...")
    time.sleep(1)

    print("-> 1. 点击搜索框...")
    pyautogui.click(POS_SEARCH[0], POS_SEARCH[1])
    time.sleep(TIME_QUICK)
    pyautogui.click(POS_SEARCH[0], POS_SEARCH[1])
    time.sleep(TIME_NORMAL)

    print(f"-> 2. 输入代码 {STOCK_CODE} 并立刻回车...")
    pyautogui.write(STOCK_CODE)
    pyautogui.press('enter')

    print(f"-> 2.5 等待搜索列表弹出 ({TIME_SEARCH}秒)...")
    time.sleep(TIME_SEARCH) 
    
    print("-> 2.5 点击第一条搜索结果...")
    pyautogui.click(POS_RESULT[0], POS_RESULT[1])
    
    print(f"-> 等待K线图页面整体加载 ({TIME_PAGE_LOAD}秒)...")
    time.sleep(TIME_PAGE_LOAD) 

    print("-> 3. 正在全屏扫描 '日K' 图标...")
    k_pos = find_image_and_close_popup('btn_day_k.png')
    
    if k_pos:
        print("  ✅ 成功识别 '日K'！")
        click_x = int(k_pos.x / 2) - 0
        click_y = int(k_pos.y / 2)
        print(f"  -> 正在点击 '日K': X={click_x}, Y={click_y}")
        pyautogui.click(click_x, click_y)
        
        print(f"  -> 等待主力吸筹指标刷新 ({TIME_INDICATOR}秒)...")
        time.sleep(TIME_INDICATOR) 
    else:
        print("  ❌ 未能找到 '日K' 图标...")

    print("-> 4. 正在全屏扫描 '主力吸筹' 图标...")
    zl_pos = find_image_and_close_popup('zhulixichou.png')
    
    if zl_pos:
        print("  ✅ 成功识别 '主力吸筹'！")
        real_x = int(zl_pos.x / 2)
        real_y = int(zl_pos.y / 2)
        
        # ================== 核心升级：可视化颜色雷达 ==================
        signal_y = real_y + SIGNAL_Y_OFFSET
        print(f"  -> 正在启动颜色雷达，扫描坐标线 (Y={signal_y})")

        screen_img = pyautogui.screenshot()
        scale = screen_img.width / pyautogui.size().width

        found_red = False
        found_green = False
        
        # 用于在终端打印图形的字符串
        radar_visual = "" 

        # 遍历像素
        for x in range(SIGNAL_X_START, SIGNAL_X_END + 1, 1):
            px = int(x * scale)
            py = int(signal_y * scale)

            try:
                # 完美解决 4 个值报错的问题：强制只取前3个 (RGB)
                pixel_data = screen_img.getpixel((px, py))
                r, g, b = pixel_data[:3] 

                if r > 180 and g < 100 and b < 100:
                    found_red = True
                    # 终端打印红色方块 (ANSI 代码)
                    radar_visual += "\033[91m█\033[0m"
                elif g > 150 and r < 120 and b < 120:
                    found_green = True
                    # 终端打印绿色方块
                    radar_visual += "\033[92m█\033[0m"
                else:
                    # 终端打印灰色横杠代表空白
                    radar_visual += "\033[90m-\033[0m"
                    
            except IndexError:
                radar_visual += " " # 越界则留空

        # 打印出极其直观的雷达扫描图！
        print("\n  📺 【扫描截面图】:")
        print(f"  [{radar_visual}]\n")

        # 结论输出
        if found_red:
            print("  🎯 结论：锁定目标！发现主力吸筹【红柱】！")
        else:
            print("  ⚪ 结论：未发现红柱。")
        # ============================================================

    else:
        print("  ❌ 未能找到 '主力吸筹' 图标。")

    print("=== 测试圆满结束 ===")