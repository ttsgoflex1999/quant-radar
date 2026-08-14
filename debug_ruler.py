import uiautomator2 as u2
from PIL import Image, ImageDraw, ImageFont
import time

# ================= 🎛️ 调试配置 =================
DEVICE_ID = "127.0.0.1:26656"
# ===============================================

def run_visual_debugger():
    print("=== 📐 启动 K 线主图刻度尺生成器 ===")
    try:
        d = u2.connect(DEVICE_ID)
        print("✅ 连接成功！")

        target = d(text="日K")
        if not target.exists:
            print("❌ 没找到‘日K’按钮！")
            return
            
        day_k_bottom = target.info['bounds']['bottom']
        print(f"⚓ 锁定锚点：日K底部 Y = {day_k_bottom}")

        print("📸 正在提取安卓底层原图...")
        img = d.screenshot(format='pillow')
        draw = ImageDraw.Draw(img)
        
        # 尝试加载默认字体，如果为了更好看可以指定 Mac 本地字体路径
        # font = ImageFont.truetype("Arial.ttf", 30)
        
        # 📏 在日K下方，每隔 50 像素画一条刻度线，直到到底部主力信号区
        print("✍️ 正在图像上绘制游标卡尺...")
        for offset in range(50, 900, 50):
            y_pos = day_k_bottom + offset
            
            # 画一条横穿屏幕的红色半透明虚线/实线
            draw.line([(0, y_pos), (1080, y_pos)], fill=(255, 0, 0), width=3)
            
            # 在线旁边写上对应的 Offset（偏移量）
            # 注意：这里的文字会印在图片左侧边缘
            draw.text((10, y_pos - 25), f"Offset: {offset}", fill=(255, 0, 0))
            
            # 顺便把你现在的红绿柱主雷达 844 也画上去（用醒目的绿色）
            if offset == 850:
                radar_y = day_k_bottom + 844
                draw.line([(0, radar_y), (1080, radar_y)], fill=(0, 255, 0), width=5)
                draw.text((10, radar_y - 30), f"MAIN RADAR (844)", fill=(0, 255, 0))

        # 💾 保存这张带有刻度尺的图
        debug_img_name = "debug_ruler_result.png"
        img.save(debug_img_name)
        print(f"✅ 大功告成！请在当前文件夹打开 [{debug_img_name}] 查看！")

    except Exception as e:
        print(f"⚠️ 运行出现问题: {e}")

if __name__ == "__main__":
    run_visual_debugger()
