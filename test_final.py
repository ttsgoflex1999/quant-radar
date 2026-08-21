import uiautomator2 as u2
from PIL import Image

# ================= 🎛️ 终极黄金参数配置 =================
DEVICE_ID = "127.0.0.1:16416"
# 焊死的黄金距离：日K底部往下 798 个像素就是红绿柱中心
OFFSET_Y = 845
SCAN_X_START = 10
SCAN_X_END = 750
# =====================================================

def run_one_click_radar():
    print("=== 🚀 [一键全自动] 股票异动雷达启动 ===")
    try:
        # 1. 极速连接安卓
        d = u2.connect(DEVICE_ID)
        print("✅ 安卓底层连接成功！")

        # 2. 闭眼锁定“日K”当船锚
        target = d(text="日K")
        if not target.exists:
            print("❌ 没找到‘日K’按钮，请确认同花顺停在 K 线界面！")
            return
        
        # 3. 自动计算那一行像素的绝对高度
        day_k_bottom = target.info['bounds']['bottom']
        target_y = day_k_bottom + OFFSET_Y
        print(f"🎯 自动锁定扫描线高度：Y = {target_y}")

        # 4. 后台无感截图（不在 Mac 存图，全在内存里秒算）
        print("📡 正在瞬间抽取并扫描像素...")
        img = d.screenshot(format='pillow').convert('RGB')
        
        radar_visual = ""
        radar_data = []
        
        # 5. 横扫千军，直接判别红绿
        for x in range(SCAN_X_START, SCAN_X_END + 1, 2): # 步长为2，速度翻倍
            r, g, b = img.getpixel((x, target_y))
            
            if r > 180 and g < 100 and b < 100:
                radar_visual += "\033[91m█\033[0m" # 打印红方块
                radar_data.append(1)
            elif g > 150 and r < 120 and b < 120:
                radar_visual += "\033[92m█\033[0m" # 打印绿方块
                radar_data.append(-1)
            else:
                radar_visual += "\033[90m-\033[0m" # 打印灰线条
                radar_data.append(0)

        # 6. 直接给你最终人话结论
        print("\n📺 【当前红绿柱截面图】:")
        print(f"[{radar_visual}]")
        
        if radar_data and radar_data[-1] == 1:
            print("\n🔔 最终结论：【末端红柱】，发现主力异动信号！！！")
        elif 1 in radar_data or -1 in radar_data:
            print("\n⚪ 最终结论：有主力活动，但【末端不是红柱】。")
        else:
            print("\n⚪ 最终结论：一片空白，无信号。")

    except Exception as e:
        print(f"⚠️ 运行出现问题: {e}")

if __name__ == "__main__":
    run_one_click_radar()
