import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import os
import shutil
import subprocess
import json
import psutil
import time

class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title("游戏列表")
        self.root.geometry("800x500")

        self.game_list_file = "game_list.json"
        self.game_list = self.load_game_list()
        self.selected_item = None  # 用于存储当前选中的项目
        self.local_emulator_path = self.load_local_emulator_path() # 加载本地模拟器路径
        self.save_manager_process = None # 用于存储存档管理器的进程对象

        self.create_widgets()
        self.update_game_list()

    def create_widgets(self):
        """创建 GUI 组件"""
        # 导航栏
        nav_frame = ttk.Frame(self.root)
        nav_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(nav_frame, text="添加游戏", command=self.add_game).pack(side=tk.LEFT, padx=5)
        ttk.Button(nav_frame, text="删除游戏", command=self.delete_game).pack(side=tk.LEFT, padx=5)
        ttk.Button(nav_frame, text="设置LE路径", command=self.set_local_emulator_path).pack(side=tk.LEFT, padx=5) # 设置LE路径按钮

        # 游戏列表
        columns = ("序号", "窗口标题", "转区启动")
        self.game_tree = ttk.Treeview(self.root, columns=columns, show="headings", selectmode="extended")
        for col in columns:
            self.game_tree.heading(col, text=col)
            if col == "序号":
                self.game_tree.column(col, width=10, anchor=tk.CENTER, minwidth=10)  # 调整序号列宽度
            elif col == "转区启动":
                self.game_tree.column(col, width=50, anchor=tk.CENTER, minwidth=50) # 调整转区启动列宽度
            else:
                self.game_tree.column(col, width=200, anchor=tk.W, minwidth=200)
        self.game_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.game_tree.bind("<ButtonRelease-1>", self.on_tree_select)  # 绑定选中事件
        self.game_tree.bind("<Double-1>", self.on_tree_double_click)  # 绑定双击事件
        self.game_tree.bind("<Button-3>", self.on_tree_right_click)  # 绑定右键菜单

        # 滚动条
        scrollbar = ttk.Scrollbar(self.root, orient=tk.VERTICAL, command=self.game_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.game_tree.configure(yscrollcommand=scrollbar.set)

        # 右键菜单
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="启动游戏", command=self.launch_game)
        self.menu.add_command(label="启动存档管理器", command=self.launch_save_manager)
        self.menu.add_command(label="打开游戏目录", command=self.open_game_dir)
        self.menu.add_command(label="打开存档目录", command=self.open_save_dir)
        self.menu.add_separator()
        self.menu.add_command(label="详细路径", command=self.show_detail_path)

        # 启动按钮框架
        self.button_frame = ttk.Frame(self.root)
        self.button_frame.pack(fill=tk.X, padx=10, pady=5)
        self.launch_game_button = ttk.Button(self.button_frame, text="启动游戏", command=self.launch_game, state=tk.DISABLED, padding=10)
        self.launch_game_button.pack(side=tk.RIGHT, padx=5)
        self.launch_save_button = ttk.Button(self.button_frame, text="启动存档管理器", command=self.launch_save_manager, state=tk.DISABLED, padding=10)
        self.launch_save_button.pack(side=tk.RIGHT, padx=5)

    def load_game_list(self):
        """加载游戏列表"""
        if os.path.exists(self.game_list_file):
            with open(self.game_list_file, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return []
        else:
            return []

    def save_game_list(self):
        """保存游戏列表"""
        with open(self.game_list_file, "w", encoding="utf-8") as f:
            json.dump(self.game_list, f, indent=4, ensure_ascii=False)

    def load_local_emulator_path(self):
        """加载本地模拟器路径"""
        config_file = "config.json"
        if os.path.exists(config_file):
            with open(config_file, "r", encoding="utf-8") as f:
                try:
                    config = json.load(f)
                    return config.get("local_emulator_path", "")
                except json.JSONDecodeError:
                    return ""
        return ""

    def save_local_emulator_path(self, path):
        """保存本地模拟器路径"""
        config_file = "config.json"
        config = {"local_emulator_path": path}
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

    def update_game_list(self):
        """更新游戏列表显示"""
        self.game_tree.delete(*self.game_tree.get_children())
        for i, game in enumerate(self.game_list):
            use_local_emulator = game.get("use_local_emulator", True)
            emulator_text = "转区运行" if use_local_emulator else "不转区运行"
            item_id = self.game_tree.insert("", "end", values=(i + 1, game["title"], emulator_text), tags=(game["save_path"], game.get("process_path", "")))
            self.game_tree.item(item_id, values=(i + 1, game["title"], emulator_text))
        
        if self.game_list:
            first_item = self.game_tree.get_children()[0]
            self.game_tree.selection_set(first_item)
            self.selected_item = first_item
            self.launch_save_button.config(state=tk.NORMAL)
            self.launch_game_button.config(state=tk.NORMAL)

    def add_game(self):
        """添加游戏"""
        # 启动 get_title.py 获取窗口标题
        try:
            subprocess.run(["python", "get_title.py"], check=True)
        except subprocess.CalledProcessError as e:
            messagebox.showerror("错误", f"捕获窗口标题失败：{e}")
            return

        # 读取 titles.json 获取窗口标题和进程路径
        titles_file = "titles.json"
        if os.path.exists(titles_file):
            with open(titles_file, "r", encoding="utf-8") as f:
                try:
                    titles = json.load(f)
                    if titles:
                        title = list(titles.keys())[0]
                        process_path = titles[title].get("process_path", "")  # 从 titles.json 中读取进程路径
                    else:
                        messagebox.showerror("错误", "未获取到窗口标题")
                        return
                except json.JSONDecodeError:
                    messagebox.showerror("错误", "读取窗口标题失败")
                    return
        else:
            messagebox.showerror("错误", "未找到窗口标题文件")
            return

        # 选择存档路径
        save_path = filedialog.askdirectory(title="选择存档路径")
        if not save_path:
            return

        # 添加到游戏列表
        self.game_list.append({"title": title, "save_path": save_path, "process_path": process_path, "use_local_emulator": True})
        self.save_game_list()
        self.update_game_list()

        # 删除 titles.json
        try:
            os.remove(titles_file)
        except Exception as e:
            print(f"删除 titles.json 失败: {e}")

    def delete_game(self):
        """删除游戏"""
        selected_item = self.game_tree.selection()
        if not selected_item:
            messagebox.showinfo("提示", "请选择要删除的游戏")
            return

        index = self.game_tree.index(selected_item[0])
        if messagebox.askyesno("确认删除", f"确定要删除选中的游戏吗？"):
            del self.game_list[index]
            self.save_game_list()
            self.update_game_list()

    def on_tree_double_click(self, event):
        """处理 Treeview 双击事件"""
        item = self.game_tree.identify_row(event.y)
        if item:
            column = self.game_tree.identify_column(event.x)
            if column == "#3":  # "转区启动" 列
                index = self.game_tree.index(item)  # 获取当前选中项的索引
                game = self.game_list[index]
                current_state = game.get("use_local_emulator", True)
                new_state_text = "禁用" if current_state else "启用"
                if messagebox.askyesno("确认", f"确定要{new_state_text}转区启动吗？"):
                    self.toggle_local_emulator(item)
                    # 重新选中该项
                    items = self.game_tree.get_children()
                    if items and index < len(items):
                        self.game_tree.selection_set(items[index])

    def start_save_manager(self, title, save_path):
        """启动存档管理器"""
        if not os.path.exists(save_path):
            messagebox.showerror("错误", "存档路径不存在")
            return

        # 获取当前脚本的目录
        current_dir = os.path.dirname(os.path.abspath(__file__))

        # 复制 get_title.py 和 save_manager.py 到存档路径
        try:
            shutil.copy(os.path.join(current_dir, "get_title.py"), save_path)
            shutil.copy(os.path.join(current_dir, "save_manager.py"), save_path)
        except Exception as e:
            messagebox.showerror("错误", f"复制文件失败: {e}")
            return

        # 切换工作目录到存档路径
        os.chdir(save_path)

        # 启动 save_manager.py
        try:
            self.save_manager_process = subprocess.Popen(["python", "save_manager.py"])
            self.root.withdraw()  # 隐藏主窗口
            self.root.after(100, self.check_save_manager_closed) # 检查存档管理器是否关闭
        except Exception as e:
            messagebox.showerror("错误", f"启动存档管理器失败: {e}")

    def on_tree_select(self, event):
        """选中单元格时启用启动按钮"""
        item = self.game_tree.selection()
        if item:
            self.selected_item = item[0]
            self.launch_save_button.config(state=tk.NORMAL)
            self.launch_game_button.config(state=tk.NORMAL)
        else:
            self.selected_item = None
            self.launch_save_button.config(state=tk.DISABLED)
            self.launch_game_button.config(state=tk.DISABLED)

    def on_tree_right_click(self, event):
        """右键点击显示菜单"""
        item = self.game_tree.identify_row(event.y)
        if item:
            self.game_tree.selection_set(item)
            self.selected_item = item
            self.menu.post(event.x_root, event.y_root)

    def launch_save_manager(self):
        """启动存档管理器"""
        selected_items = self.game_tree.selection()
        for item in selected_items:
            index = self.game_tree.index(item)
            game = self.game_list[index]
            self.start_save_manager(game["title"], game["save_path"])

    def launch_game(self):
        """启动游戏"""
        selected_items = self.game_tree.selection()
        for item in selected_items:
            index = self.game_tree.index(item)
            game = self.game_list[index]
            process_path = game.get("process_path")
            use_local_emulator = game.get("use_local_emulator", True)
            save_path = game.get("save_path")
            if process_path and os.path.exists(process_path):
                if save_path and os.path.exists(save_path):
                    self.start_save_manager(game["title"], save_path)
                if use_local_emulator and self.local_emulator_path:
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            subprocess.Popen([self.local_emulator_path, "-run", process_path])
                            break  # 启动成功，跳出循环
                        except Exception as e:
                            if attempt < max_retries - 1:
                                print(f"使用 Local Emulator 启动游戏失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                                time.sleep(1)  # 等待 1 秒后重试
                            else:
                                messagebox.showerror("错误", f"使用 Local Emulator 启动游戏失败 (多次尝试后): {e}")
                else:
                    try:
                        subprocess.Popen([process_path])
                    except Exception as e:
                        messagebox.showerror("错误", f"启动游戏失败: {e}")
            else:
                messagebox.showerror("错误", "未找到游戏进程路径")

    def open_game_dir(self):
        """打开游戏目录"""
        selected_items = self.game_tree.selection()
        if selected_items:
            for item in selected_items:
                index = self.game_tree.index(item)
                game = self.game_list[index]
                process_path = game.get("process_path")
                if process_path:
                    try:
                        game_dir = os.path.dirname(process_path)
                        os.startfile(game_dir)
                    except Exception as e:
                        messagebox.showerror("错误", f"打开游戏目录失败: {e}")
                else:
                    messagebox.showerror("错误", "未找到游戏进程路径")

    def show_detail_path(self):
        """显示详细路径"""
        if self.selected_item:
            index = self.game_tree.index(self.selected_item)
            game = self.game_list[index]
            messagebox.showinfo("详细路径", f"存档路径: {game['save_path']}\n进程路径: {game.get('process_path', '未找到')}")

    def set_local_emulator_path(self):
        """设置本地模拟器路径"""
        path = filedialog.askopenfilename(title="选择 Local Emulator 程序")
        if path:
            self.local_emulator_path = path
            self.save_local_emulator_path(path)

    def toggle_local_emulator(self, item_id):
        """切换转区启动状态"""
        index = self.game_tree.index(item_id)
        game = self.game_list[index]
        game["use_local_emulator"] = not game.get("use_local_emulator", True)
        self.save_game_list()
        self.update_game_list()

    def on_tree_click(self, event):
        """处理 Treeview 点击事件"""
        self.on_tree_select(event)

    def check_save_manager_closed(self):
        """检查存档管理器是否关闭"""
        if self.save_manager_process is None:
            return
        if self.save_manager_process.poll() is not None:
            self.root.deiconify()  # 显示主窗口
            os.chdir(os.path.dirname(os.path.abspath(__file__))) # 切换回主目录
            self.save_manager_process = None
        else:
            self.root.after(100, self.check_save_manager_closed) # 继续检查

    def is_save_manager_running(self):
        """检查存档管理器是否正在运行"""
        return self.save_manager_process is not None and self.save_manager_process.poll() is None

    def open_save_dir(self):
        """打开存档目录"""
        selected_items = self.game_tree.selection()
        if selected_items:
            for item in selected_items:
                index = self.game_tree.index(item)
                game = self.game_list[index]
                save_path = game.get("save_path")
                if save_path:
                    try:
                        os.startfile(save_path)
                    except Exception as e:
                        messagebox.showerror("错误", f"打开存档目录失败: {e}")
                else:
                    messagebox.showerror("错误", "未找到存档路径")

if __name__ == "__main__":
    root = tk.Tk()
    app = MainApp(root)
    root.mainloop() 