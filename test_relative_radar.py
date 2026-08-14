import uiautomator2 as u2
from PIL import Image
import time

# ================= 🎛️ 相对锚点雷达面板 =================
DEVICE_ID = "127.0.0.1:26656"

# 你观察到的偏移量 (日K底部 -> 红绿柱中心)
# 如果扫出来不对，可以微调这个数字
RELATIVE_OFFSET_Y = 840

# 横向扫描范围 (10 到 741)
SCAN_X_START = 10
SCAN_X_END = 741
# =====================================================

def run_relative_radar():
    print("=== 🚀 启动 [日K相对锚点] 视觉雷达 ===")
    try:
        d = u2.connect(DEVICE_ID)
        print(f"✅ 已连接设备: {DEVICE_ID}")

        # 1. 动态寻找“日K”按钮 (这是安卓能识别的标准控件)
        target = d(text="日K")
        if not target.exists:
            print("❌ 错误：当前页面没找到‘日K’按钮，请确保在个股K线页。")
            return
        
        # 获取日K的底部坐标
        # info['bounds'] 返回 {'bottom': Y, 'left': X, 'right': X, 'top': Y}
        day_k_bottom = target.info['bounds']['bottom']
        scan_y = day_k_bottom + RELATIVE_OFFSET_Y
        print(f"📍 探测到‘日K’底部 Y 坐标: {day_k_bottom}")
        print(f"📏 计算得出红绿柱高度 Y 坐标: {scan_y}")

        # 2. 瞬间抓取内存原生截图 (Pillow 对象)
        # 直接通过 ADB 流传输，不存硬盘
        img = d.screenshot(format='pillow').convert('RGB')
        
        # 3. 提取这一行像素数据 (即你说的“传给 Mac 识别”)
        print(f"📡 正在提取 X({SCAN_X_START}-{SCAN_X_END}) 范围内的像素丝...")
        
        radar_visual = ""
        radar_data = []
        
        # 步长设为 2，兼顾精度与速度
        for x in range(SCAN_X_START, SCAN_X_END + 1, 2):
            r, g, b = img.getpixel((x, scan_y))
            
            # 颜色判断逻辑
            if r > 180 and g < 100 and b < 100:
                radar_visual += "\033[91m█\033[0m" # 红色
                radar_data.append(1)
            elif g > 150 and r < 120 and b < 120:
                radar_visual += "\033[92m█\033[0m" # 绿色
                radar_data.append(-1)
            else:
                radar_visual += "\033[90m-\033[0m" # 空白/灰色
                radar_data.append(0)

        # 4. 展示识别结果
        print("\n📺 【Mac 识别出的红绿柱截面图】:")
        print(f"[{radar_visual}]")
        
        # 核心逻辑：判断末端是否为红柱
        if radar_data and radar_data[-1] == 1:
            print("\n💡 结论：末端锁定红柱，发现目标异动！")
        else:
            print("\n💡 结论：末端未发现红柱信号。")

    except Exception as e:
        print(f"⚠️ 发生异常: {e}")

if __name__ == "__main__":
    run_relative_radar()