import uiautomator2 as u2
from PIL import ImageDraw

# ================= 诊断配置 =================
DEVICE_IP = "127.0.0.1:16416"  # 用一号机做测试
OFFSET_Y = 930                 # 提取红绿序列的单线偏移量 (如果黄线没对齐红绿柱，就改这个数值！)
BOX_TOP_OFFSET = 120           # 横盘评分大框的上边界偏移 (已同步你的修改)
BOX_BOTTOM_OFFSET = 640        # 横盘评分大框的下边界偏移 (已同步你的修改)
SCAN_X_START = 10              # X轴扫描起点
SCAN_X_END = 765               # X轴扫描终点 (已同步你的修改)
# ============================================

def debug_vision():
    print(f"🔌 正在连接设备 {DEVICE_IP} ...")
    try:
        d = u2.connect(DEVICE_IP)
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return

    print("📸 正在截取屏幕并分析坐标...")
    img = d.screenshot(format='pillow').convert('RGB')
    
    # 获取屏幕缩放比例
    info = d.info
    scale_y = img.size[1] / info['displayHeight']
    
    # 寻找锚点：日K按钮
    target = d(text="日K")
    if not target.exists:
        print("❌ 当前屏幕上找不到'日K'按钮，请确保停留在股票详情界面！")
        return
        
    # 【这就是你说的相对位置锚点】获取“日K”按钮底部的物理像素 Y 坐标
    base_bottom = target.info['bounds']['bottom']
    print(f"📍 锚点 '日K' 按钮的底部逻辑坐标: {base_bottom}")
    
    # 核心：相对位置叠加计算！
    target_y = int(max(10, min(base_bottom + OFFSET_Y, 1900)))
    box_top = int(base_bottom + BOX_TOP_OFFSET)
    box_bottom = int(base_bottom + BOX_BOTTOM_OFFSET)
    
    print(f"📐 扫描红绿柱的【黄线】Y坐标: {target_y} (由锚点 {base_bottom} + 偏移量 {OFFSET_Y} 算得)")
    print(f"📦 评分K线的【蓝框】Y范围: {box_top} 到 {box_bottom}")

    # ================= 开始画图可视化 =================
    draw = ImageDraw.Draw(img)
    
    # 1. 画出序列扫描线 (黄线，让你看清它到底扫在了哪里)
    draw.line([(SCAN_X_START, target_y), (SCAN_X_END, target_y)], fill="yellow", width=4)
    draw.text((SCAN_X_START, target_y - 30), f"红绿柱扫描线 (当前OFFSET_Y={OFFSET_Y})", fill="yellow")

    # 2. 画出横盘评分框 (蓝框，让你看清它框住了哪里的K线)
    draw.rectangle([(SCAN_X_START, box_top), (SCAN_X_END, box_bottom)], outline="blue", width=6)
    draw.text((SCAN_X_START, box_top - 30), "横盘评分大框", fill="blue")
    
    # 保存图片
    save_path = "debug_red_green.jpg"
    img.save(save_path)
    print(f"✅ 诊断完毕！请立刻打开当前文件夹下的 【{save_path}】 查看划线位置。")

if __name__ == "__main__":
    debug_vision()