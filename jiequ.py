import uiautomator2 as u2
from PIL import Image

# ================= 🎯 精确裁剪区域配置 =================
DEVICE_URL = "127.0.0.1:16416"

# 横坐标 (绝对物理坐标)
X_START = 720
X_END = 760

# 纵坐标 (相对"日K"底部的 Offset)
OFFSET_Y_START = 1035
OFFSET_Y_END = 1060
# =======================================================

def test_specific_crop():
    try:
        print(f"🔌 连接设备 {DEVICE_URL}...")
        d = u2.connect(DEVICE_URL)
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return

    print("📸 正在获取全屏截图...")
    img = d.screenshot()
    width, height = img.size

    # 计算日K基准线
    target = d(text="日K")
    if not target.exists:
        print("❌ 未找到'日K'，无法计算基准线！请确保界面停留在K线图。")
        return
        
    info = d.info
    scale_y = height / info['displayHeight']
    logic_base_y = target.info['bounds']['bottom']
    pixel_base_y = int(logic_base_y * scale_y)
    
    print(f"📏 锁定 '日K' 基准线，物理 Y 坐标: {pixel_base_y}")

    # 计算精确裁剪边界
    left = X_START
    right = X_END
    top = pixel_base_y + OFFSET_Y_START
    bottom = pixel_base_y + OFFSET_Y_END

    # 边界防越界保护
    left = max(0, min(left, width))
    right = max(0, min(right, width))
    top = max(0, min(top, height))
    bottom = max(0, min(bottom, height))

    print(f"✂️ 正在精准切割指定区域: X[{left}:{right}], Y[{top}:{bottom}]")
    
    # 执行裁剪
    crop_img = img.crop((left, top, right, bottom))
    
    # 🔍 核心优化：由于 25x15 像素太小，强行放大 10 倍 (使用近邻插值法保持像素边缘，不模糊)
    magnification = 10
    display_img = crop_img.resize(
        ((right - left) * magnification, (bottom - top) * magnification), 
        Image.NEAREST
    )

    save_path = "debug_exact_crop.jpg"
    display_img.save(save_path)
    display_img.show()
    
    print(f"✨ 裁剪完成！为了方便肉眼观察，图像已放大 {magnification} 倍并保存至 {save_path}。")
    print("💡 看看弹出的图片，确认是不是你想找的那个字！")

if __name__ == "__main__":
    test_specific_crop()