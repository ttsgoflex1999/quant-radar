import pyautogui
import time

print("开始测量坐标，按 Ctrl+C 停止...")
try:
    while True:
        x, y = pyautogui.position()
        print(f"当前鼠标坐标: X: {x}, Y: {y}", end='\r')
        time.sleep(0.1)
except KeyboardInterrupt:
    print('\n测量结束。')