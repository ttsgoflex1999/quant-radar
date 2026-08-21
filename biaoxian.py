import uiautomator2 as u2
from PIL import Image, ImageDraw

# ================= 配置区 =================
DEVICE_URL = "127.0.0.1:16416"
# ==========================================

def test_dense_grid():
    try:
        print(f"🔌 连接设备 {DEVICE_URL}...")
        d = u2.connect(DEVICE_URL)
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return

    print("📸 正在截屏并计算分辨率...")
    # 获取原始截图，转换为 RGBA 模式以便绘制半透明网格
    img = d.screenshot().convert("RGBA")
    width, height = img.size
    
    # 获取系统逻辑坐标与物理像素的比例
    info = d.info
    scale_y = height / info['displayHeight']

    # 尝试寻找“日K”作为 0 坐标基准线
    target = d(text="日K")
    base_y = None
    if target.exists:
        logic_base_y = target.info['bounds']['bottom']
        base_y = int(logic_base_y * scale_y)
        print(f"📏 成功锁定 '日K' 基准线，真实物理 Y 坐标: {base_y}")
    else:
        print("⚠️ 未找到 '日K'，将仅显示绝对物理坐标。")

    print("🕸️ 正在全平面铺设【高对比深色】高密度量子网格...")
    
    # 创建一个纯透明图层用于画网格，避免遮挡底部 K 线
    overlay = Image.new('RGBA', img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)

    # 1. 绘制垂直网格 (X轴)：每 100 像素画一条线
    for x in range(0, width, 100):
        # 逢 200 像素线条加粗加黑
        if x % 200 == 0:
            color = (0, 0, 0, 180)  # 纯黑，半透明
            w = 2
        else:
            color = (0, 0, 0, 60)   # 纯黑，浅灰透明
            w = 1
        draw.line([(x, 0), (x, height)], fill=color, width=w)
        # 在顶部标出 X 坐标 (深蓝色文字)
        draw.text((x + 5, 20), f"X:{x}", fill=(0, 0, 255, 255))

    # 2. 绘制水平网格 (Y轴)：每 50 像素画一条线
    for y in range(0, height, 50):
        # 逢 100 像素线条加粗加深
        if y % 100 == 0:
            color = (0, 0, 150, 150) # 深蓝色
            w = 2
        else:
            color = (0, 0, 150, 50)  # 浅蓝色
            w = 1
        draw.line([(0, y), (width, y)], fill=color, width=w)

        # 智能文字标签
        if base_y is not None:
            offset = y - base_y
            label = f"Y:{y} | Offset:{offset}"
        else:
            label = f"Y:{y}"
            
        # 在屏幕最左侧和偏右侧分别打印 (品红色文字，极度醒目)
        draw.text((5, y + 2), label, fill=(200, 0, 200, 255))
        draw.text((width - 160, y + 2), label, fill=(200, 0, 200, 255))

    # 3. 绘制最显眼的“日K”红色基准线
    if base_y is not None:
        draw.line([(0, base_y), (width, base_y)], fill=(255, 0, 0, 255), width=5)
        draw.text((width // 2 - 80, base_y - 25), "🚨 0 基准线 (日K底部)", fill=(255, 0, 0, 255))

    # 将透明网格层覆盖到原图上
    final_img = Image.alpha_composite(img, overlay).convert("RGB")
    
    save_path = "dense_grid_ruler.jpg"
    final_img.save(save_path)
    print(f"✨ 高对比度网格已生成！保存为: {save_path}")
    final_img.show()
    
    print("-" * 50)
    print("💡 【超神使用说明】:")
    print("1. 查看弹出的图片，找到你想让红绿柱雷达扫过的横线。")
    print("2. 看看那条品红色文字写的 Offset 是多少。")
    print("3. 直接把代码里的 OFFSET_Y 改成这个 Offset 数值即可！")
    print("-" * 50)

if __name__ == "__main__":
    test_dense_grid()