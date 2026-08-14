import uiautomator2 as u2
from PIL import Image
import io
import os

# ================= 🎛️ 截图参数配置 =================
DEVICE_ID = "127.0.0.1:16384"
# 日K底部到红绿柱中心的垂直距离
OFFSET_Y = 798
# 想要截取的宽度和高度
ROI_WIDTH = 730
ROI_HEIGHT = 100 
# =================================================

def capture_relative_roi():
    print("=== 📸 正在执行 [相对锚点] 区域截图 ===")
    try:
        d = u2.connect(DEVICE_ID)
        target = d(text="日K")
        
        if not target.exists:
            print("❌ 错误：未找到‘日K’按钮。")
            return
            
        # 1. 动态定位锚点
        day_k_bottom = target.info['bounds']['bottom']
        # 计算截图区域的中心高度
        center_y = day_k_bottom + OFFSET_Y
        
        # 2. 计算裁剪框 (Left, Top, Right, Bottom)
        left = 10
        top = center_y - (ROI_HEIGHT // 2)
        right = left + ROI_WIDTH
        bottom = top + ROI_HEIGHT
        
        print(f"📍 锚点 Y: {day_k_bottom} | 目标扫描线 Y: {center_y}")
        print(f"✂️ 裁剪区域坐标: ({left}, {top}) 到 ({right}, {bottom})")

        # 3. 抓取并裁剪
        full_img = d.screenshot(format='pillow')
        roi_img = full_img.crop((left, top, right, bottom))
        
        # 4. 保存并直接打开图片
        save_path = "debug_roi_check.png"
        roi_img.save(save_path)
        print(f"✅ 截图已保存至: {save_path}")
        
        # 自动调用 Mac 的预览程序打开图
        os.system(f"open {save_path}")
        
    except Exception as e:
        print(f"⚠️ 异常: {e}")

if __name__ == "__main__":
    capture_relative_roi()
