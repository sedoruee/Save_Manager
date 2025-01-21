import tkinter as tk
import time
import platform
import json
import os
from PIL import ImageGrab, Image
import ctypes
import psutil

if platform.system() == "Windows":
    import win32gui
    import win32con
    import win32process  # 导入 win32process
else:
    print("此脚本仅支持 Windows 操作系统。")
    exit()

# 添加 Windows API 常量
DIB_RGB_COLORS = 0
SRCCOPY = 0x00CC0020
PW_RENDERFULLCONTENT = 0x00000002

# 使用 ctypes 定义 BITMAPINFOHEADER 结构体
class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint),
        ("biWidth", ctypes.c_long),
        ("biHeight", ctypes.c_long),
        ("biPlanes", ctypes.c_short),
        ("biBitCount", ctypes.c_short),
        ("biCompression", ctypes.c_uint),
        ("biSizeImage", ctypes.c_uint),
        ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long),
        ("biClrUsed", ctypes.c_uint),
        ("biClrImportant", ctypes.c_uint)
    ]

class WindowSelector:
    def __init__(self, master):
        self.master = master
        master.title("窗口标题获取器")

        self.crosshair_button = tk.Button(master, text="🎯 准星", relief=tk.RAISED)
        self.crosshair_button.pack(pady=20)

        self.window_name_label = tk.Label(master, text="拖拽准星到游戏窗口")
        self.window_name_label.pack(pady=10)
        
        self.json_file_path = "titles.json" # 定义json文件路径
        self.window_titles = self.load_window_titles() # 初始化window_titles
        
        self.is_pressing = False
        self.press_start_time = 0

        self.crosshair_button.bind("<ButtonPress-1>", self.on_press)
        self.crosshair_button.bind("<ButtonRelease-1>", self.on_release)

    def on_press(self, event):
        self.is_pressing = True
        self.press_start_time = time.time()
        self.master.config(cursor="crosshair")  # 更改鼠标为准星

    def on_release(self, event):
        self.is_pressing = False
        self.master.config(cursor="")  # 恢复默认鼠标

        if time.time() - self.press_start_time > 0.2:  # 设置长按阈值 (例如 0.2 秒)
            self.get_window_under_mouse()

    def get_window_under_mouse(self):
        point = win32gui.GetCursorPos()
        hwnd = win32gui.WindowFromPoint(point)

        # 获取顶层父窗口的句柄
        top_level_hwnd = win32gui.GetAncestor(hwnd, win32con.GA_ROOTOWNER)

        if top_level_hwnd:
            window_title = win32gui.GetWindowText(top_level_hwnd)
            process_path = self.get_process_path(top_level_hwnd)
            self.window_name_label.config(text=f"选中的窗口标题: {window_title}")
            self.update_window_titles(window_title, process_path)  # 调用方法更新Json
        else:
            self.window_name_label.config(text="未能获取到顶层窗口标题")

    def get_process_path(self, hwnd):
        """获取指定窗口句柄的进程路径"""
        try:
            thread_id, process_id = win32process.GetWindowThreadProcessId(hwnd)
            process = psutil.Process(process_id)
            return process.exe()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
            print(f"获取进程路径失败: {e}")
            return ""
        except Exception as e:
            print(f"获取进程路径时发生未知错误: {e}")
            return ""

    def load_window_titles(self):
        """加载已保存的窗口标题"""
        if os.path.exists(self.json_file_path):
            try:
                with open(self.json_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else {}
            except json.JSONDecodeError:
                print("JSON解码错误，已创建新JSON文件。")
                return {}
        else:
            return {}

    def update_window_titles(self, title, process_path):
        """更新或创建窗口标题数据, 保持唯一性"""
        self.window_titles = {title: {"process_path": process_path}}  # 直接覆盖为新的窗口标题和进程路径
        self.save_window_titles()
        print(f"已更新标题: {title}, 进程路径: {process_path}")
        
    def save_window_titles(self):
        """保存窗口标题到json文件"""
        with open(self.json_file_path, 'w', encoding='utf-8') as f:
            json.dump(self.window_titles, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    root = tk.Tk()
    app = WindowSelector(root)
    root.mainloop()