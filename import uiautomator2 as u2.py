import uiautomator2 as u2
from PIL import Image, ImageDraw
import cv2
import numpy as np
import logging
from paddleocr import PaddleOCR

# 屏蔽烦人的底层日志
logging.getLogger('ppocr').setLevel(logging.ERROR)

# ================= 🎯 狙击参数配置区 =================
DEVICE_URL = "127.0.0.1:16416"

TARGET_X = 750         # 你在网格图上看到的 X 坐标
OFFSET_Y = 1040        # 你在网格图上看到的 Offset 偏移量

# 视野范围（以目标坐标为中心，向四周各扩展 80 像素，剪下一块 160x160 的小方块）
ROI_SIZE = 80          
# ==================================================

print("🧠 正在加载 AI 视觉模型...")
ocr = PaddleOCR(use_textline_orientation=False, lang="ch")

def test_roi_ocr():
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
    target = d(text="月K")
    if not target.exists:
        print("❌ 未找到'月K'，无法计算基准线！")
        return
        
    info = d.info
    scale_y = height / info['displayHeight']
    logic_base_y = target.info['bounds']['bottom']
    pixel_base_y = int(logic_base_y * scale_y)
    
    # 计算目标物理绝对坐标
    center_x = TARGET_X
    center_y = pixel_base_y + OFFSET_Y
    print(f"🎯 狙击中心锁定: 绝对坐标 ({center_x}, {center_y})")

    # 计算裁剪边界 (防越界保护)
    left = max(0, center_x - ROI_SIZE)
    top = max(0, center_y - ROI_SIZE)
    right = min(width, center_x + ROI_SIZE)
    bottom = min(height, center_y + ROI_SIZE)

    print(f"✂️ 正在裁剪局部视野: [{left}, {top}, {right}, {bottom}]")
    roi_img = img.crop((left, top, right, bottom))
    
    # 转换供 OpenCV 和 AI 引擎使用
    img_cv = cv2.cvtColor(np.array(roi_img), cv2.COLOR_RGB2BGR)
    
    print("🤖 正在启动 AI 引擎对该局部区域进行扫描...")
    try:
        raw_result = ocr.predict(img_cv)
        result = list(raw_result) if hasattr(raw_result, '__iter__') and not isinstance(raw_result, list) else raw_result
    except Exception as e:
        print(f"❌ AI 识别异常: {e}")
        return
    
    draw = ImageDraw.Draw(roi_img)
    # 在裁剪图的绝对中心画个小红点，代表你的瞄准心
    draw.ellipse((ROI_SIZE - 4, ROI_SIZE - 4, ROI_SIZE + 4, ROI_SIZE + 4), fill=(255, 0, 0))

    found = False
    if result and result[0]:
        data_list = result[0]
        # 兼容新老版本的数据结构
        if isinstance(data_list, dict): 
            iterator = zip(data_list.get('dt_polys', []), data_list.get('rec_text', []), data_list.get('rec_score', []))
        else:
            iterator = [(line[0], line[1][0], line[1][1]) for line in data_list]

        for box, text, confidence in iterator:
            print(f"🔍 局部雷达捕获文字: '{text}' (置信度: {float(confidence):.2f})")
            
            # 画绿框标出文字
            pts = [(p[0], p[1]) for p in box]
            pts.append(pts[0])
            draw.line(pts, fill=(0, 255, 0), width=2)

            if "始" in text:
                found = True
                print(f"🎉 【击中目标】成功在该坐标区域捕捉到包含 '始' 的文本：【{text}】")
                
    else:
        print("👀 局部区域内未识别到任何有效文字。")

    if not found:
        print("⚠️ 未找到 '始' 字。请查看弹出的图片，检查红点是否偏离了你要找的字！")
        
    save_path = "debug_roi_crop.jpg"
    roi_img.save(save_path)
    roi_img.show()
    print(f"✨ 局部视觉透视图已保存至 {save_path}。")
    print("💡 【图例】：红点 = 你输入的坐标靶心，绿框 = AI实际“看”到的字")

if __name__ == "__main__":
    test_roi_ocr()