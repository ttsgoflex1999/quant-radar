import uiautomator2 as u2
from PIL import ImageDraw

# ================= 🎯 瞄准点配置区 =================
DEVICE_URL = "127.0.0.1:16416"

# 当前代码中配置的【逻辑点击坐标】
TARGET_X = 450
TARGET_Y = 250
# ===================================================

def show_click_target():
    try:
        print(f"🔌 正在连接设备 {DEVICE_URL}...")
        d = u2.connect(DEVICE_URL)
        print("✅ 连接成功！")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return

    print("📸 正在截取当前屏幕...")
    img = d.screenshot()
    
    # 核心：计算安卓逻辑坐标与物理截图的缩放比例
    info = d.info
    scale_x = img.size[0] / info['displayWidth']
    scale_y = img.size[1] / info['displayHeight']
    
    # 将你代码里写的 (450, 250) 换算成图片上的真实物理像素
    pixel_x = int(TARGET_X * scale_x)
    pixel_y = int(TARGET_Y * scale_y)
    
    print(f"🎯 逻辑坐标 ({TARGET_X}, {TARGET_Y}) 在物理屏幕上的落点为: ({pixel_x}, {pixel_y})")

    # 开始在图片上画瞄准器
    draw = ImageDraw.Draw(img)
    width, height = img.size
    
    # 1. 画一条贯穿全屏的红色十字准星线
    draw.line([(0, pixel_y), (width, pixel_y)], fill=(255, 0, 0, 150), width=2)
    draw.line([(pixel_x, 0), (pixel_x, height)], fill=(255, 0, 0, 150), width=2)
    
    # 2. 画一个醒目的绿色瞄准圈
    r = 30
    draw.ellipse(
        (pixel_x - r, pixel_y - r, pixel_x + r, pixel_y + r), 
        outline=(0, 255, 0), 
        width=5
    )
    
    # 3. 靶心实心红点
    draw.ellipse(
        (pixel_x - 5, pixel_y - 5, pixel_x + 5, pixel_y + 5), 
        fill=(255, 0, 0)
    )
    
    # 4. 旁边打上文字标签
    draw.text(
        (pixel_x + 40, pixel_y - 40), 
        f"CLICK: ({TARGET_X}, {TARGET_Y})", 
        fill=(0, 255, 255)
    )

    save_path = "debug_click_result.jpg"
    img.save(save_path)
    img.show()
    print(f"✨ 侦察图像已生成并保存为 {save_path}。请检查绿圈是否完美套住了第一条股票结果！")
    print("💡 如果偏了，请直接在代码里修改 TARGET_X 和 TARGET_Y 的数值反复测试。")

if __name__ == "__main__":
    show_click_target()