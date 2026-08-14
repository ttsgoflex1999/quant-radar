import uiautomator2 as u2

# 填入你的模拟器端口
DEVICE_ID = "127.0.0.1:16384"

print("=== 🚀 启动 [真机底层 UI] 自动校准 ===")
try:
    d = u2.connect(DEVICE_ID)
    print("✅ 连接模拟器成功！")

    # 1. 直接查底层 UI 树，绝对不会有色彩冲突！
    if d(textContains="主力吸筹").exists:
        # 获取控件边界
        bounds = d(textContains="主力吸筹").info['bounds']
        text_bottom_y = bounds['bottom']
        
        print(f"\n🎯 锁定目标！'主力吸筹' 底部绝对 Y 坐标为: 【{text_bottom_y}】")
        
        # 2. 顺手抓一张当前的原生无损图，方便你量坐标
        d.screenshot("live_calibration.png")
        print("📸 已将当前真机画面保存为 'live_calibration.png'。")
        
        print("\n================ 📏 终极测量公式 ================")
        print("1. 请用 Mac 的‘预览’打开刚才生成的 live_calibration.png。")
        print("2. 用鼠标框选工具，把光标停在下方【红绿柱的正中心】。")
        print(f"3. 记下光标所在位置的 Y 坐标（假设是 1100）。")
        print(f"4. 你的终极偏移量 = 红绿柱 Y 坐标 - 【{text_bottom_y}】")
        print("==================================================")
        
    else:
        print("❌ 模拟器当前页面没有找到 '主力吸筹' 这四个字，请检查同花顺是否在这个界面。")

except Exception as e:
    print(f"⚠️ 发生错误: {e}")