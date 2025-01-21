import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import os
import shutil
import json
import datetime
import re
import time
import threading
import subprocess
import queue
from PIL import Image, ImageTk
import psutil
import pygetwindow as gw
from utils import logger

class SaveManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("存档管理器")
        self.root.geometry("1200x550")

        self.save_dir = os.getcwd()  # 获取当前工作目录作为存档目录
        self.config_file = os.path.join(self.save_dir, "save_config.json")
        self.temp_dir = os.path.join(self.save_dir, "temp_save")
        self.titles_file = os.path.join(self.save_dir, "titles.json")
        self.img_dir = os.path.join(self.save_dir, "img")
        os.makedirs(self.img_dir, exist_ok=True)

        self.save_data = self.load_config()
        self.current_group = self.get_current_group()
        self.auto_refresh_interval = 3 # 自动刷新间隔
        self._auto_refresh_id = None
        self.editing_item = None
        self.editing_column = None
        self.edit_entry = None
        self.current_title = self.load_titles()
        # self.last_file_info = {} # 用于存储上次的文件信息，用于判断是否是新增存档
        self.task_queue = queue.Queue() # 任务队列
        self.is_processing_task = False # 是否正在处理任务
        self.all_files_info = {} # 用于存储所有文件信息
        self.selected_item_path = None # 当前选中的存档路径
        self.game_list_file = self.find_game_list_file()
        self.game_list = self.load_game_list()
        self.current_game_title = self.get_current_game_title()
        self.max_saves_per_group = 9999 # 默认最大存档数
        self.pending_group_change = None # 待处理的组切换

        self.create_widgets()
        self.update_save_list()
        self.start_auto_refresh()
        self.root.after(100, self.init_show_selected_image) # 初始化时加载截图

    def load_config(self):
        """加载配置文件"""
        if os.path.exists(self.config_file):
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.max_saves_per_group = data.get("max_saves_per_group", 9999) # 加载最大存档数
                return data
        else:
            return {
                "current_group": 1,
                "groups": {},
                "group_names": {},
                "selected_files": {},
                "max_saves_per_group": 9999
            }

    def save_config(self):
        """保存配置文件"""
        self.save_data["max_saves_per_group"] = self.max_saves_per_group # 保存最大存档数
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.save_data, f, indent=4, ensure_ascii=False)

    def load_titles(self):
        """加载标题配置文件"""
        if os.path.exists(self.titles_file):
            with open(self.titles_file, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return {}
        else:
            return {}

    def save_titles(self):
        """保存标题配置文件"""
        with open(self.titles_file, "w", encoding="utf-8") as f:
            json.dump(self.current_title, f, indent=4, ensure_ascii=False)

    def start_auto_refresh(self):
        """启动定时自动刷新"""
        self.stop_auto_refresh()  # 确保只有一个定时器在运行
        self._auto_refresh_id = self.root.after(self.auto_refresh_interval * 1000 , self.auto_refresh)

    def stop_auto_refresh(self):
        """停止定时自动刷新"""
        if self._auto_refresh_id:
            self.root.after_cancel(self._auto_refresh_id)
            self._auto_refresh_id = None

    def auto_refresh(self):
         """定时自动刷新"""
         self.update_save_list()
         self.process_task_queue() # 每次刷新都检查是否有任务
         self.start_auto_refresh()

    def create_widgets(self):
        """创建GUI组件"""

        # 导航栏
        nav_frame = ttk.Frame(self.root)
        nav_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(nav_frame, text="选择存档目录", command=self.select_save_directory).pack(side=tk.LEFT, padx=5)
        self.group_label = ttk.Label(nav_frame, text=self.get_group_display_name(self.current_group))
        self.group_label.pack(side=tk.LEFT, padx=5)
        self.prev_button = ttk.Button(nav_frame, text="上一组", command=self.prev_group)
        self.prev_button.pack(side=tk.LEFT, padx=5)
        self.next_button = ttk.Button(nav_frame, text="下一组", command=self.next_group)
        self.next_button.pack(side=tk.LEFT, padx=5)
        ttk.Button(nav_frame, text="修改组名", command=self.rename_group).pack(side=tk.LEFT, padx=5)
        self.title_label = ttk.Label(nav_frame, text="")
        self.title_label.pack(side=tk.LEFT, padx=5)
        ttk.Button(nav_frame, text="打开游戏目录", command=self.open_game_dir).pack(side=tk.LEFT, padx=5) # 打开游戏目录按钮
        ttk.Button(nav_frame, text="打开存档目录", command=self.open_save_dir).pack(side=tk.LEFT, padx=5) # 打开存档目录按钮
        ttk.Button(nav_frame, text="设置存档上限", command=self.set_max_saves).pack(side=tk.LEFT, padx=5)

        # 主框架
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 存档列表
        columns = ("序号", "备注", "日期", "名称") # 序号列放最左边
        self.save_tree = ttk.Treeview(main_frame, columns=columns, show="headings", selectmode="extended")
        for col in columns:
            self.save_tree.heading(col, text=col)
            self.save_tree.column(col, width=120, anchor=tk.W) # 默认左对齐
            if col == "名称":
                self.save_tree.column(col, width=50, anchor=tk.W) # 名称列宽度缩小到原来的四分之一
            else:
                self.save_tree.column(col, width=120, anchor=tk.W)
        self.save_tree.column("备注", width=200)
        self.save_tree.column("日期", width=150)
        self.save_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.save_tree.bind("<ButtonRelease-1>", self.on_tree_click)
        self.save_tree.tag_configure("important", anchor="e") # 星星靠右对齐
        self.save_tree.tag_configure("normal", anchor="w") # 序号靠左对齐
        self.save_tree.bind("<Double-1>", self.on_tree_double_click)

        # 滚动条
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=self.save_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.save_tree.configure(yscrollcommand=scrollbar.set)

        # 右侧功能按钮框架
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side=tk.RIGHT, padx=5)

        # 水平排列缩进按钮
        indent_frame = ttk.Frame(button_frame)
        indent_frame.pack(fill=tk.X, pady=5)
        ttk.Button(indent_frame, text="←左缩进", command=self.unindent_save, width=8).pack(side=tk.LEFT, padx=2) # 减少缩进按钮
        ttk.Button(indent_frame, text="右缩进→", command=self.indent_save, width=8).pack(side=tk.LEFT, padx=2) # 增加缩进按钮
        self.important_button = ttk.Button(indent_frame, text="标记关键存档", command=self.toggle_important, width=15)
        self.important_button.pack(side=tk.LEFT, padx=2)
        self.ignore_button = ttk.Button(indent_frame, text="标记忽略存档", command=self.toggle_ignore, width=15)
        self.ignore_button.pack(side=tk.LEFT, padx=2)

        ttk.Button(button_frame, text="删除存档", command=self.delete_save).pack(fill=tk.X, pady=5)
        
        # 截图显示区域
        self.image_frame = ttk.Frame(button_frame, width=600, height=400, relief=tk.SOLID, borderwidth=1) # 宽度和高度都放大到原来的两倍
        self.image_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        self.image_label = ttk.Label(self.image_frame)
        self.image_label.pack(fill=tk.BOTH, expand=True)
        self.show_default_image()
        self.update_title_label()
        self.image_label.bind("<Double-1>", self.open_image)

        # 启动按钮框架
        self.button_frame = ttk.Frame(self.root)
        self.button_frame.pack(fill=tk.X, padx=10, pady=5)
        self.launch_save_button = ttk.Button(self.button_frame, text="打开存档目录", command=self.open_save_dir, state=tk.DISABLED, padding=10)
        self.launch_save_button.pack(side=tk.RIGHT, padx=5)

    def select_save_directory(self):
        """选择存档目录"""
        directory = filedialog.askdirectory(title="选择存档目录")
        if directory:
            self.save_dir = directory
            os.chdir(self.save_dir) # 将程序的工作目录切换到新选的存档目录
            self.config_file = os.path.join(self.save_dir, "save_config.json") # 同时更新配置文件路径
            self.temp_dir = os.path.join(self.save_dir, "temp_save")
            self.titles_file = os.path.join(self.save_dir, "titles.json")
            self.img_dir = os.path.join(self.save_dir, "img")
            os.makedirs(self.img_dir, exist_ok=True)
            self.save_data = self.load_config()
            self.current_group = self.get_current_group()
            self.current_title = self.load_titles()
            self.update_save_list()
            self.update_title_label()
            self.current_game_title = self.get_current_game_title()

    def update_save_list(self):
        """更新存档列表显示，现在显示根目录的存档"""
        self.save_tree.delete(*self.save_tree.get_children())
        self.group_label.config(text=self.get_group_display_name(self.current_group))
        files = self.get_save_files_in_dir(self.save_dir)  # 直接获取根目录的存档文件
        if files:
            self.all_files_info[str(self.current_group)] = {} # 初始化当前组的文件信息
            for i, file_info in enumerate(files):
                group_char = chr(64 + self.current_group)  # 获取组序号 A, B, C...
                file_path = file_info.get("path","")
                self.all_files_info[str(self.current_group)][file_path] = file_info # 存储文件信息
                note = self.save_data.get('groups',{}).get(str(self.current_group),{}).get(file_path, {}).get('note', '')
                is_important = self.save_data.get('groups',{}).get(str(self.current_group),{}).get(file_path, {}).get('important', False)
                indent_level = self.save_data.get('groups',{}).get(str(self.current_group),{}).get(file_path, {}).get('indent', 0) # 获取缩进级别
                file_name = file_info['original_name'].rsplit('.', 1)[0] # 去除后缀
                display_name = f"{file_name}" # 名称
                date = file_info.get("date","")
                is_ignored = self.save_data.get('groups',{}).get(str(self.current_group),{}).get(file_path, {}).get('ignore', False)
                if is_ignored:
                    continue # 如果被忽略则跳过
                # 检查存档是否是新的
                is_new = self.is_new_save(file_path, file_info)
                if is_new:
                    self.capture_save_image(file_path, file_info) # 如果是新存档则捕获截图
                # 记录存档新旧状态
                self.save_data.setdefault('groups', {}).setdefault(str(self.current_group), {}).setdefault(file_path, {})['is_new'] = is_new # 记录新旧状态
                
                tag = "important" if is_important else "normal"  # 根据是否重要设置tag
                index = f"{'→ ' * indent_level}Save {group_char}{i + 1} {'★' if is_important else ''}" # 将星星和缩进添加到序号中
                self.save_tree.insert("", "end", iid=file_path, values=(index, note, date, display_name), tags=(file_path,tag))
            self.restore_selected_items()
            self.show_selected_image()
            self.check_and_auto_switch_group() # 检查是否需要自动切换组

    def get_save_files_in_dir(self, directory):
        """获取指定目录下所有匹配规则的存档文件，并按数字排序"""
        files = []
        pattern = re.compile(r'^(?P<base>.*?)(?P<num>\d+)(?P<ext>\..*)$')
        all_files = os.listdir(directory)
        for filename in all_files:
            if os.path.isfile(os.path.join(directory, filename)):
                match = pattern.match(filename)
                if match:
                    base = match.group("base")
                    num = int(match.group("num"))
                    ext = match.group("ext")
                    count = 0
                    for other_filename in all_files:
                        if os.path.isfile(os.path.join(directory, other_filename)):
                            other_match = pattern.match(other_filename)
                            if other_match and other_match.group("base") == base and other_match.group("ext") == ext:
                                count+=1
                    # 修改这里，允许只有一组存档时也能显示
                    if count >= 1:
                        file_path = os.path.join(directory, filename)
                        is_ignored = False
                        for group_key in self.save_data.get('groups', {}):
                            if file_path in self.save_data['groups'].get(group_key, {}):
                                if self.save_data['groups'][group_key][file_path].get('ignore', False):
                                    is_ignored = True
                                    break
                        if is_ignored:
                            continue # 如果被忽略则跳过
                        files.append({
                            'original_name': filename,
                            'base_name': base,
                            'num': num,
                            'ext': ext,
                            'path': file_path,
                            'date': self.get_file_creation_date(file_path)
                        })
        files.sort(key=lambda x: x['num'])
        return files

    def get_files_in_group(self, group_index):
        """获取指定存档组的所有文件信息，并按数字排序"""
        group_dir = os.path.join(self.save_dir, f"save{group_index}")
        if os.path.exists(group_dir):
            files = []
            pattern = re.compile(r'^(?P<base>.*?)(?P<num>\d+)(?P<ext>\..*)$')
            for f in os.listdir(group_dir):
                if os.path.isfile(os.path.join(group_dir, f)):
                    match = pattern.match(f)
                    if match:
                        files.append({
                            'original_name': f,
                            'base_name': match.group("base"),
                            'num': int(match.group("num")),
                            'ext': match.group("ext"),
                            'path': os.path.join(group_dir, f),
                            'date': self.get_file_creation_date(os.path.join(group_dir, f))
                        })
            files.sort(key=lambda x: x['num'])
            return files
        return []

    def get_file_creation_date(self,filepath):
        """获取文件的创建日期"""
        timestamp = os.path.getctime(filepath)
        date = datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        return date

    def is_new_save(self, file_path, file_info):
        """判断存档是否是新的"""
        group_str = str(self.current_group)
        # 优先使用 JSON 中的新旧状态
        if 'groups' in self.save_data and group_str in self.save_data['groups'] and file_path in self.save_data['groups'][group_str] and 'is_new' in self.save_data['groups'][group_str][file_path]:
            if self.save_data['groups'][group_str][file_path]['is_new']:
                self.save_data['groups'][group_str][file_path]['is_new'] = False # 修改为False，避免重复触发
                self.check_and_auto_switch_group() # 检查是否需要自动切换组
                return True
            else:
                return False

        img_name = f"{group_str}_{file_info['original_name'].rsplit('.', 1)[0]}.png"
        img_path = os.path.join(self.img_dir, img_name)
        if not os.path.exists(img_path):
            creation_time = os.path.getctime(file_path)
            current_time = time.time()
            return current_time - creation_time <= 60  # 一分钟内创建的认为是新存档
        return False

    def get_current_group(self):
       """ 获取当前根目录所属的存档组，没有则默认为1"""
       return self.save_data.get("current_group",1)

    def set_current_group(self, group_index):
        """设置当前根目录所属的存档组"""
        self.save_data["current_group"] = group_index
        self.save_config()

    def prev_group(self):
        """切换到上一组存档"""
        target_group = max(1, self.current_group - 1)
        self.change_group(target_group)

    def next_group(self):
        """切换到下一组存档"""
        self.change_group(self.current_group + 1)

    def change_group(self, target_group):
        """切换存档组核心逻辑"""
        if self.pending_group_change is not None:
            return # 如果有待处理的组切换，则直接返回
        self.pending_group_change = target_group
        self.task_queue.put(target_group) # 添加任务到队列
        self.process_task_queue() # 尝试处理任务

    def process_task_queue(self):
        """处理任务队列"""
        if self.is_processing_task:
            return  # 如果正在处理任务则直接返回
        if not self.task_queue.empty():
            self.is_processing_task = True
            task = self.task_queue.get()
            if isinstance(task, tuple) and len(task) == 3:
                title, img_path, delay_time = task
                if time.time() >= delay_time:
                    threading.Thread(target=self.execute_capture_image, args=(title, img_path)).start()
                    self.is_processing_task = False  # 只有在执行任务后才释放锁
                    self.process_task_queue() # 执行完任务后，再次尝试处理队列
                else:
                    self.task_queue.put((title, img_path, delay_time))  # 如果时间未到，则重新放回队列
                    self.is_processing_task = False # 释放锁，以便下次处理
                    self.root.after(100, self.process_task_queue)  # 延迟100毫秒后再次尝试
            else:
                threading.Thread(target=self.execute_group_change, args=(task,)).start()

    def execute_group_change(self, target_group):
        """执行组切换的核心逻辑"""
        try:
            self.save_selected_items() # 保存当前选中项
            self.stop_auto_refresh() # 切换组时停止自动刷新

            old_group = self.current_group

            # 移动当前根目录的存档文件到旧的组文件夹
            old_group_dir = os.path.join(self.save_dir, f"save{old_group}")
            os.makedirs(old_group_dir, exist_ok=True)
            current_root_save_files = self.get_save_files_in_dir(self.save_dir)
            for file_info in current_root_save_files:
                try:
                    shutil.move(file_info['path'], old_group_dir)
                except Exception as e:
                    print(f"Error moving {file_info['original_name']} to save{old_group}: {e}")
                    messagebox.showerror("错误", f"移动文件 {file_info['original_name']} 失败：{e}")

            # 移动目标组的存档文件到根目录
            target_group_dir = os.path.join(self.save_dir, f"save{target_group}")
            if not os.path.exists(target_group_dir):
                os.makedirs(target_group_dir)

            target_group_save_files = self.get_files_in_group(target_group)
            for file_info in target_group_save_files:
                try:
                    shutil.move(file_info['path'], self.save_dir)
                except Exception as e:
                    print(f"Error moving {file_info['original_name']} from save{target_group} to root: {e}")
                    messagebox.showerror("错误", f"移动文件 {file_info['original_name']} 失败：{e}")

            self.current_group = target_group
            self.set_current_group(target_group)
            self.update_save_list()
            
            # 切换组后更新截图显示
            self.root.after(100, self.show_selected_image)  # 延迟执行，确保文件移动完成

            self.start_auto_refresh()  # 切换完成后重新启动自动刷新
        finally:
            self.is_processing_task = False
            self.pending_group_change = None # 清除待处理的组切换
            self.process_task_queue() # 再次尝试处理任务

    def edit_note(self, item_id, column):
        """在 Treeview 的单元格上编辑备注"""
        if self.edit_entry:  # 如果已经有编辑器，则销毁
            self.edit_entry.destroy()

        self.editing_item = item_id
        self.editing_column = column
        current_note = self.save_data.get('groups',{}).get(str(self.current_group), {}).get(item_id, {}).get('note', '')

        # 获取单元格的 bounding box
        x, y, width, height = self.save_tree.bbox(item_id, column)

        # 创建 Entry 控件
        self.edit_entry = tk.Entry(self.save_tree, width=int(width/7), relief=tk.FLAT)
        self.edit_entry.insert(0, current_note)
        self.edit_entry.select_range(0, tk.END)  # 选中所有文本
        self.edit_entry.focus_set()
        self.edit_entry.bind("<FocusOut>", self.finish_edit)
        self.edit_entry.bind("<Return>", self.finish_edit)
        self.edit_entry.place(x=x, y=y, width=width, height=height)
        self.stop_auto_refresh() # 编辑时停止自动刷新

    def finish_edit(self, event=None):
        """完成编辑并保存备注"""
        if self.editing_item and self.editing_column and self.edit_entry:
            new_note = self.edit_entry.get()
            group_str = str(self.current_group)
            self.save_data.setdefault('groups', {}).setdefault(group_str, {}).setdefault(self.editing_item, {})['note'] = new_note
            self.save_config()
            # 不需要刷新整个列表，只需要更新修改的项
            current_values = self.save_tree.item(self.editing_item, 'values')
            self.save_tree.item(self.editing_item, values=(current_values[0], new_note, current_values[2], current_values[3]))
            self.edit_entry.destroy()
            self.edit_entry = None
            self.editing_item = None
            self.editing_column = None
            self.start_auto_refresh() # 结束编辑后恢复自动刷新

    def toggle_important(self):
         """标记/取消标记选中存档为关键存档"""
         selected_items = self.save_tree.selection()
         if not selected_items:
             messagebox.showinfo("提示", "请选择要标记的存档")
             return
         for item in selected_items:
            file_path = self.save_tree.item(item, 'tags')[0]
            if 'groups' not in self.save_data:
                self.save_data["groups"] = {}
            group_str = str(self.current_group)
            if group_str not in self.save_data["groups"]:
                self.save_data["groups"][group_str] = {}
            if file_path not in self.save_data["groups"][group_str]:
                self.save_data["groups"][group_str][file_path] = {}
            current_important = self.save_data["groups"][group_str][file_path].get('important', False)
            self.save_data["groups"][group_str][file_path]['important'] = not current_important
         self.save_config()
         self.update_save_list()

    def toggle_ignore(self):
        """标记/取消标记选中存档为忽略存档"""
        selected_items = self.save_tree.selection()
        if not selected_items:
            messagebox.showinfo("提示", "请选择要标记的存档")
            return
        for item in selected_items:
            file_path = self.save_tree.item(item, 'tags')[0]
            if 'groups' not in self.save_data:
                self.save_data["groups"] = {}
            group_str = str(self.current_group)
            if group_str not in self.save_data["groups"]:
                self.save_data["groups"][group_str] = {}
            if file_path not in self.save_data["groups"][group_str]:
                self.save_data["groups"][group_str][file_path] = {}
            current_ignore = self.save_data["groups"][group_str][file_path].get('ignore', False)
            self.save_data["groups"][group_str][file_path]['ignore'] = not current_ignore
        self.save_config()
        self.update_save_list()

    def delete_save(self):
        """删除选中存档"""
        selected_items = self.save_tree.selection()
        if not selected_items:
            messagebox.showinfo("提示", "请选择要删除的存档")
            return
        if messagebox.askyesno("确认删除", f"确定要删除选中的 {len(selected_items)} 个存档吗？"):
            for item in selected_items:
                file_path = self.save_tree.item(item, 'tags')[0]
                try:
                    os.remove(file_path)
                    group_str = str(self.current_group)
                    if 'groups' in self.save_data and group_str in self.save_data['groups']:
                        if file_path in self.save_data['groups'][group_str]:
                            del self.save_data['groups'][group_str][file_path]
                    # 删除对应的截图
                    img_name = f"{group_str}_{os.path.basename(file_path).rsplit('.', 1)[0]}.png"
                    img_path = os.path.join(self.img_dir, img_name)
                    if os.path.exists(img_path):
                        os.remove(img_path)
                except Exception as e:
                    print(f"Error deleting {os.path.basename(file_path)}: {e}")
                    messagebox.showerror("错误", f"删除存档失败：{e}")
            self.save_config()
            self.update_save_list()

    def indent_save(self):
        """增加选中存档的缩进"""
        selected_items = self.save_tree.selection()
        if not selected_items:
            messagebox.showinfo("提示", "请选择要增加缩进的存档")
            return
        for item in selected_items:
            file_path = self.save_tree.item(item, 'tags')[0]
            group_str = str(self.current_group)
            if 'groups' not in self.save_data:
                self.save_data["groups"] = {}
            if group_str not in self.save_data["groups"]:
                self.save_data["groups"][group_str] = {}
            if file_path not in self.save_data["groups"][group_str]:
                self.save_data["groups"][group_str][file_path] = {}
            current_indent = self.save_data["groups"][group_str][file_path].get('indent', 0)
            self.save_data["groups"][group_str][file_path]['indent'] = min(current_indent + 1, 5) # 最大缩进5级
        self.save_config()
        self.update_save_list()

    def unindent_save(self):
        """减少选中存档的缩进"""
        selected_items = self.save_tree.selection()
        if not selected_items:
            messagebox.showinfo("提示", "请选择要减少缩进的存档")
            return
        for item in selected_items:
            file_path = self.save_tree.item(item, 'tags')[0]
            group_str = str(self.current_group)
            if 'groups' not in self.save_data:
                self.save_data["groups"] = {}
            if group_str not in self.save_data["groups"]:
                self.save_data["groups"][group_str] = {}
            if file_path not in self.save_data["groups"][group_str]:
                self.save_data["groups"][group_str][file_path] = {}
            current_indent = self.save_data["groups"][group_str][file_path].get('indent', 0)
            self.save_data["groups"][group_str][file_path]['indent'] = max(current_indent - 1, 0) # 最小缩进0级
        self.save_config()
        self.update_save_list()

    def on_close(self):
        """程序关闭时的操作"""
        self.save_selected_items()
        self.stop_auto_refresh()
        self.root.destroy()

    def on_tree_click(self, event):
        """保持 Treeview 的选中状态并更新配置文件"""
        item = self.save_tree.identify_row(event.y)
        if item:
            if event.state & 0x0001 or event.state & 0x0004:  # Shift or Ctrl key is pressed
                self.save_tree.selection_add(item)
            else:
                self.save_tree.selection_set(item)
            self.save_selected_items()
            selected_items = self.save_tree.selection()
            if selected_items:
                self.selected_item_path = self.save_tree.item(selected_items[0], 'tags')[0]
            else:
                self.selected_item_path = None
            self.show_selected_image()

    def on_tree_double_click(self, event):
        """双击 Treeview 项目时编辑备注"""
        item_id = self.save_tree.identify_row(event.y)
        column_id = self.save_tree.identify_column(event.x) # 获取点击的列
        if item_id and column_id == "#2":  # 备注列
            self.edit_note(item_id, column_id)
        else: # 双击其他列时取消编辑状态
            if self.edit_entry:
                self.finish_edit()

    def get_group_display_name(self, group_index):
        """获取组的显示名称"""
        group_name = self.save_data.get("group_names", {}).get(str(group_index), "")
        return f"第{group_index}页, {group_name}"

    def rename_group(self):
        """修改当前组的名称"""
        group_name = self.save_data.get("group_names", {}).get(str(self.current_group), "")
        new_name = simpledialog.askstring("修改组名", f"修改第{self.current_group}组的名称:", initialvalue=group_name)
        if new_name is not None:
            if "group_names" not in self.save_data:
                self.save_data["group_names"] = {}
            self.save_data["group_names"][str(self.current_group)] = new_name
            self.save_config()
            self.group_label.config(text=self.get_group_display_name(self.current_group))

    def save_selected_items(self):
        """保存当前选中的文件到配置文件"""
        selected_items = self.save_tree.selection()
        selected_paths = [self.save_tree.item(item, 'tags')[0] for item in selected_items]
        self.save_data.setdefault('selected_files', {})[str(self.current_group)] = selected_paths
        self.save_config()

    def restore_selected_items(self):
        """从配置文件恢复选中的文件"""
        if str(self.current_group) in self.save_data.get('selected_files', {}):
            selected_paths = self.save_data['selected_files'][str(self.current_group)]
            for item in self.save_tree.get_children():
                item_path = self.save_tree.item(item, 'tags')[0]
                if item_path in selected_paths:
                    self.save_tree.selection_add(item)

    def capture_save_image(self, file_path, file_info):
        """捕获指定存档的窗口截图"""
        if not self.current_game_title:
            return
        title = self.current_game_title
        group_str = str(self.get_current_group())
        img_name = f"{group_str}_{file_info['original_name'].rsplit('.', 1)[0]}.png"
        img_path = os.path.join(self.img_dir, img_name)
        try:
            # 检查是否已经存在截图，如果存在则跳过
            if not os.path.exists(img_path):
                # 检查任务队列中是否已经有相同的截图任务
                task_exists = False
                for item in self.task_queue.queue:
                    if isinstance(item, tuple) and len(item) == 3 and item[1] == img_path:
                        task_exists = True
                        break
                if not task_exists:
                    # 添加 4000 毫秒延迟
                    self.task_queue.put((title, img_path, time.time() + 2)) # 将截图任务添加到队列,并添加延迟时间
                    self.process_task_queue() # 尝试处理任务
                    # 立即将 is_new 设置为 False，避免重复触发
                    if 'groups' in self.save_data and group_str in self.save_data['groups'] and file_path in self.save_data['groups'][group_str]:
                        self.save_data['groups'][group_str][file_path]['is_new'] = False
                    # 添加选中逻辑
                    self.root.after(100, lambda: self.select_tree_item(file_path)) # 截图后选中对应的项
        except Exception as e:
            print(f"Error capturing image for {file_path}: {e}")

    def select_tree_item(self, file_path):
        """选中 Treeview 中的指定项"""
        for item in self.save_tree.get_children():
            item_path = self.save_tree.item(item, 'tags')[0]
            if item_path == file_path:
                self.save_tree.selection_set(item)
                self.save_selected_items() # 更新选中的json
                self.selected_item_path = file_path # 更新选中的路径
                self.show_selected_image() # 显示截图
                break

    def capture_window_image(self, window_title, save_path):
        """捕获指定窗口的截图并保存，使用 BitBlt API 和 DwmGetWindowAttribute"""
        import platform
        if platform.system() != "Windows":
            print("截图功能仅支持 Windows 操作系统。")
            return

        import win32gui
        import win32con
        import ctypes
        from PIL import Image

        # 添加 Windows API 常量
        DIB_RGB_COLORS = 0
        SRCCOPY = 0x00CC0020
        DWMWA_EXTENDED_FRAME_BOUNDS = 9

        # 使用 ctypes 定义 RECT 结构体
        class RECT(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

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

        hwnd = win32gui.FindWindow(None, window_title)
        if hwnd:
            try:
                # 获取窗口的实际大小
                rect = RECT()
                size = ctypes.sizeof(rect)
                ctypes.windll.dwmapi.DwmGetWindowAttribute(
                    hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), size
                )
                left = rect.left
                top = rect.top
                right = rect.right
                bottom = rect.bottom
                width = right - left
                height = bottom - top

                # 创建一个与窗口大小匹配的设备上下文
                hwnd_dc = win32gui.GetWindowDC(hwnd)
                dc = ctypes.windll.gdi32.CreateCompatibleDC(hwnd_dc)
                bitmap = ctypes.windll.gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
                ctypes.windll.gdi32.SelectObject(dc, bitmap)

                # 使用 BitBlt API 捕获窗口内容
                print("使用 BitBlt API 捕获窗口内容")
                ctypes.windll.gdi32.BitBlt(dc, 0, 0, width, height, hwnd_dc, 0, 0, SRCCOPY)

                # 将设备上下文中的内容复制到 PIL Image
                bitmap_header = BITMAPINFOHEADER()
                bitmap_header.biSize = ctypes.sizeof(bitmap_header)
                bitmap_header.biWidth = width
                bitmap_header.biHeight = -height  # 负数表示顶端为起始
                bitmap_header.biPlanes = 1
                bitmap_header.biBitCount = 32
                bitmap_header.biCompression = 0  # BI_RGB

                buffer = ctypes.create_string_buffer(width * height * 4)
                ctypes.windll.gdi32.GetDIBits(dc, bitmap, 0, height, buffer, ctypes.byref(bitmap_header), DIB_RGB_COLORS)
                image = Image.frombuffer("RGBA", (width, height), buffer.raw, "raw", "BGRA", 0, 1)

                # 清理资源
                ctypes.windll.gdi32.DeleteObject(bitmap)
                ctypes.windll.gdi32.DeleteDC(dc)
                win32gui.ReleaseDC(hwnd, hwnd_dc)

                # 保存截图
                image.save(save_path)
                print(f"成功捕获窗口 '{window_title}' 的截图并保存到 '{save_path}'")
            except Exception as e:
                print(f"捕获窗口截图失败: {e}")

    def show_selected_image(self):
        """显示选中存档的截图"""
        if not self.selected_item_path:
            self.show_default_image()
            return
        group_str = str(self.current_group)
        img_name = f"{group_str}_{os.path.basename(self.selected_item_path).rsplit('.', 1)[0]}.png"
        img_path = os.path.join(self.img_dir, img_name)
        if os.path.exists(img_path):
            try:
                if not self.image_frame.winfo_ismapped():
                    self.image_frame.pack(fill=tk.BOTH, expand=True, pady=10)
                # 获取 image_frame 的宽度
                frame_width = self.image_frame.winfo_width()
                if frame_width <= 1:
                    return # 如果宽度为0则不进行缩放
                # 获取原始图像尺寸
                image = Image.open(img_path)
                original_width, original_height = image.size
                aspect_ratio = original_width / original_height
                new_width = frame_width
                new_height = int(new_width / aspect_ratio)
                
                # 检查计算出的高度是否超过 image_frame 的高度，如果超过则以高度为基准
                frame_height = self.image_frame.winfo_height()
                if new_height > frame_height and frame_height > 1:
                    new_height = frame_height
                    new_width = int(new_height * aspect_ratio)

                image = image.resize((new_width, new_height), Image.LANCZOS)
                photo = ImageTk.PhotoImage(image)
                self.image_label.config(image=photo)
                self.image_label.image = photo
            except Exception as e:
                print(f"Error loading image {img_path}: {e}")
                self.show_no_image_text() # 显示无截图文本
        else:
            self.show_no_image_text() # 显示无截图文本

    def show_default_image(self):
        """显示默认的灰色矩形"""
        self.image_frame.pack_forget()
        self.image_label.config(image='', text="无截图", font=("Arial", 20), anchor="center")
        # 获取 image_frame 的请求尺寸
        width = self.image_frame.winfo_reqwidth()
        height = self.image_frame.winfo_reqheight()
        # 使用 place 方法设置 image_label 的大小和位置
        self.image_label.place(x=0, y=0, width=width, height=height)
        self.image_label.image = None

    def show_no_image_text(self):
        """显示无截图文本"""
        self.image_label.config(image='', text="无截图", font=("Arial", 20), anchor="center")
        # 获取 image_frame 的请求尺寸
        width = self.image_frame.winfo_reqwidth()
        height = self.image_frame.winfo_reqheight()
        # 使用 place 方法设置 image_label 的大小和位置
        self.image_label.place(x=0, y=0, width=width, height=height)
        self.image_label.image = None

    def update_title_label(self):
        """更新标题标签"""
        if self.current_game_title:
            self.title_label.config(text=f"当前窗口: {self.current_game_title}")
        else:
            self.title_label.config(text="未捕获窗口")

    def init_show_selected_image(self):
        """初始化时加载截图"""
        if self.save_tree.selection():
            item = self.save_tree.selection()[0]
            self.selected_item_path = self.save_tree.item(item, 'tags')[0]
        self.show_selected_image()

    def open_image(self, event):
        """双击打开图片"""
        if not self.selected_item_path:
            return
        group_str = str(self.current_group)
        img_name = f"{group_str}_{os.path.basename(self.selected_item_path).rsplit('.', 1)[0]}.png"
        img_path = os.path.join(self.img_dir, img_name)
        if os.path.exists(img_path):
            try:
                os.startfile(img_path)  # 使用系统默认程序打开图片
            except Exception as e:
                print(f"Error opening image {img_path}: {e}")
                messagebox.showerror("错误", f"打开图片失败：{e}")

    def open_save_dir(self):
        """打开存档目录"""
        if self.save_dir:
            try:
                os.startfile(self.save_dir)
            except Exception as e:
                messagebox.showerror("错误", f"打开存档目录失败: {e}")
        else:
            messagebox.showerror("错误", "未选择存档目录")

    def find_game_list_file(self):
        """查找 game_list.json 文件"""
        file_path = r"D:\Tools\Save_manager\game_list.json"
        print(f"尝试查找 game_list.json 路径: {file_path}")
        if os.path.exists(file_path):
            print(f"找到 game_list.json 文件: {file_path}")
            return file_path
        else:
            return None

    def load_game_list(self):
        """加载游戏列表"""
        if self.game_list_file and os.path.exists(self.game_list_file):
            with open(self.game_list_file, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return []
        else:
            return []

    def get_current_game_title(self):
        """获取当前游戏的标题"""
        if self.game_list:
            for game in self.game_list:
                if os.path.abspath(self.save_dir) == os.path.abspath(game.get("save_path", "")):
                    return game.get("title", "")
        return ""

    def open_game_dir(self):
        """打开游戏目录"""
        if self.current_game_title:
            try:
                # 从 game_list.json 中找到对应的游戏目录
                game_list_file = self.find_game_list_file()
                if game_list_file and os.path.exists(game_list_file):
                    with open(game_list_file, "r", encoding="utf-8") as f:
                        game_list = json.load(f)
                        for game in game_list:
                            if game.get("title", "") == self.current_game_title:
                                process_path = game.get("process_path", "")
                                if process_path:
                                    game_dir = os.path.dirname(process_path)
                                    os.startfile(game_dir)
                                    return
                messagebox.showerror("错误", "未找到游戏目录")
            except Exception as e:
                messagebox.showerror("错误", f"打开游戏目录失败: {e}")
        else:
            messagebox.showerror("错误", "未捕获窗口")

    def execute_capture_image(self, title, img_path):
        """执行截图任务"""
        try:
            self.capture_window_image(title, img_path)
        finally:
            self.is_processing_task = False
            self.process_task_queue() # 再次尝试处理任务

    def set_max_saves(self):
        """设置最大存档数"""
        max_saves = simpledialog.askinteger("设置存档上限", "请输入每个组的最大存档数:", initialvalue=self.max_saves_per_group)
        if max_saves is not None:
            self.max_saves_per_group = max_saves
            self.save_config()

    def check_and_auto_switch_group(self):
        """检查是否需要自动切换到下一组"""
        last_group = self.get_last_group_with_saves()
        if self.current_group == last_group:
            files = self.get_save_files_in_dir(self.save_dir)
            if files and len(files) >= self.max_saves_per_group:
                self.change_group(self.current_group + 1)

    def get_last_group_with_saves(self):
        """获取最后有存档的组"""
        max_group = 1
        for group_index in range(1, 1000):  # 假设最大组数为1000
            group_dir = os.path.join(self.save_dir, f"save{group_index}")
            if os.path.exists(group_dir) and os.listdir(group_dir):
                max_group = group_index
            elif group_index == self.current_group and self.get_save_files_in_dir(self.save_dir):
                max_group = group_index
        return max_group

if __name__ == "__main__":
    root = tk.Tk()
    app = SaveManagerApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()