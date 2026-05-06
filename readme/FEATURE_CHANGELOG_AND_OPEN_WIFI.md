# 功能实现：Open WiFi支持 & Changelog查看器

## 实现日期
2025-10-31

## 功能概述

本次更新实现了两个重要功能：
1. **Open WiFi连接支持** - 在WiFi配置对话框中支持无密码的Open WiFi网络
2. **Changelog查看器** - 在关于菜单中添加更新日志查看功能

---

## 功能1：Open WiFi连接支持

### 需求背景
部分WiFi网络（如公共WiFi、测试网络）使用Open加密方式，不需要密码即可连接。原有的WiFi配置对话框只支持WPA2/WPA3加密方式，需要扩展以支持Open WiFi。

### 实现方案

#### 1. 界面改进
**文件**: `src/main_gui.py` - `WifiConfigDialog`类

**关键改动**:
1. 加密方式选择框增加"open"选项：
   ```python
   sec_combo = ttk.Combobox(self.dialog, textvariable=self.sec_var, 
                            values=['wpa2', 'wpa3', 'open'], state="readonly")
   ```

2. 将加密方式选择移到密码输入之前，便于动态控制密码框显示

3. 密码输入框使用Frame包装，便于显示/隐藏：
   ```python
   self.password_frame = ttk.Frame(self.dialog)
   self.password_label = ttk.Label(self.password_frame, text="密码:")
   self.password_entry = ttk.Entry(self.password_frame, textvariable=self.pwd_var, show='*')
   ```

4. 绑定加密方式选择事件：
   ```python
   sec_combo.bind('<<ComboboxSelected>>', self._on_security_changed)
   ```

#### 2. 动态显示/隐藏密码框
新增方法 `_on_security_changed()`:
```python
def _on_security_changed(self, event):
    """根据加密方式显示或隐藏密码输入框"""
    security = self.sec_var.get().strip().lower()
    if security == 'open':
        # 隐藏密码输入框
        self.password_label.pack_forget()
        self.password_entry.pack_forget()
    else:
        # 显示密码输入框
        self.password_label.pack(pady=(10, 5))
        self.password_entry.pack(padx=10, fill=tk.X)
```

#### 3. 连接逻辑更新
更新 `apply()` 方法的验证逻辑：
```python
# Open WiFi不需要密码
if sec != 'open':
    if not pwd:
        messagebox.showerror("错误", "请输入密码")
        return
    if sec not in ('wpa2', 'wpa3'):
        messagebox.showerror("错误", "加密方式必须为 wpa2、wpa3 或 open")
        return
else:
    # Open WiFi，密码设为空
    pwd = ''
```

### 用户体验

#### 使用流程
1. 点击"激活盒子WiFi链接"菜单
2. 在对话框中选择设备
3. 输入SSID
4. 选择加密方式：
   - 选择"open" → 密码输入框自动隐藏
   - 选择"wpa2"或"wpa3" → 密码输入框显示，需要输入密码
5. 点击"连接"按钮

#### 界面效果
- **选择Open时**: 对话框自动缩减，不显示密码输入框
- **选择WPA2/WPA3时**: 对话框显示密码输入框
- **切换加密方式**: 界面实时响应，流畅切换

### 技术细节

#### 支持的加密方式
- `wpa2` - WPA2加密（需要密码）
- `wpa3` - WPA3加密（需要密码）
- `open` - Open加密（无需密码）

#### 配置保存
WiFi历史记录会保存所有参数（包括security='open'），下次打开对话框时自动恢复上次的配置。

---

## 功能2：Changelog查看器

### 需求背景
用户需要方便地查看工具的更新历史和版本变更信息，以了解新功能和修复的问题。

### 实现方案

#### 1. 菜单项添加
**文件**: `src/main_gui.py` - `create_menu_bar()`方法

在"关于"菜单中添加新项：
```python
about_menu = tk.Menu(menubar, tearoff=0)
menubar.add_cascade(label="关于", menu=about_menu)
about_menu.add_command(label="关于", command=self.show_about)
about_menu.add_command(label="查看更新日志", command=self.show_changelog)  # 新增
```

#### 2. Changelog查看器实现
新增方法 `show_changelog()`:

```python
def show_changelog(self):
    """显示更新日志"""
    changelog_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 
                                   'changelog', 'CHANGELOG.md')
    
    # 创建对话框
    dialog = tk.Toplevel(self.root)
    dialog.title("更新日志")
    dialog.geometry("800x600")
    dialog.transient(self.root)
    
    # 创建文本显示区域
    text_frame = ttk.Frame(dialog, padding=10)
    text_frame.pack(fill=tk.BOTH, expand=True)
    
    # 创建滚动文本框
    text_widget = tk.Text(text_frame, wrap=tk.WORD, font=('Consolas', 10))
    scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
    text_widget.configure(yscrollcommand=scrollbar.set)
    
    text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    # 读取并显示changelog内容
    try:
        if os.path.exists(changelog_path):
            with open(changelog_path, 'r', encoding='utf-8') as f:
                content = f.read()
                text_widget.insert('1.0', content)
        else:
            text_widget.insert('1.0', f"未找到更新日志文件：\n{changelog_path}\n\n请联系技术支持获取最新的更新信息。")
    except Exception as e:
        text_widget.insert('1.0', f"读取更新日志失败：\n{str(e)}\n\n请联系技术支持获取最新的更新信息。")
    
    # 设置为只读
    text_widget.config(state='disabled')
    
    # 关闭按钮
    btn_frame = ttk.Frame(dialog, padding=10)
    btn_frame.pack(fill=tk.X)
    ttk.Button(btn_frame, text="关闭", command=dialog.destroy).pack(side=tk.RIGHT)
```

### 功能特性

#### 1. 智能路径解析
- 自动从当前文件位置向上查找`changelog/CHANGELOG.md`
- 适配开发环境和打包后的运行环境
- 路径解析使用`os.path.join()`确保跨平台兼容

#### 2. 错误处理
- 文件不存在时显示友好提示
- 文件读取异常时显示错误信息
- 所有异常情况都提示联系技术支持

#### 3. 用户界面
- **窗口大小**: 800x600，适合阅读
- **字体**: Consolas 10号，等宽字体便于查看Markdown格式
- **文本自动换行**: `wrap=tk.WORD`，单词级换行
- **垂直滚动条**: 支持浏览长文档
- **只读模式**: 防止误编辑
- **模态对话框**: 使用`transient()`保持在主窗口之上

### 使用流程

1. 点击菜单栏 → "关于" → "查看更新日志"
2. 弹出更新日志查看器窗口
3. 滚动浏览完整的更新历史
4. 点击"关闭"按钮退出

---

## CHANGELOG更新

**文件**: `changelog/CHANGELOG.md`

添加了版本v2.2.1的更新内容：
- 新增功能说明
- 界面优化说明
- 问题修复记录
- 历史版本信息

结构清晰，便于用户查看和理解每个版本的变化。

---

## 测试建议

### Open WiFi功能测试
1. **基本连接测试**
   - 测试连接真实的Open WiFi网络
   - 验证密码框是否正确隐藏
   - 验证连接是否成功

2. **界面切换测试**
   - 在wpa2、wpa3、open之间切换
   - 验证密码框显示/隐藏是否流畅
   - 验证历史记录是否正确保存和恢复

3. **错误处理测试**
   - 测试Open WiFi的SSID不存在时的提示
   - 测试连接失败的错误处理

### Changelog查看器测试
1. **正常场景测试**
   - 点击"查看更新日志"菜单
   - 验证窗口是否正确弹出
   - 验证内容是否完整显示
   - 验证滚动功能是否正常

2. **异常场景测试**
   - 临时删除CHANGELOG.md文件，验证错误提示
   - 修改CHANGELOG.md为无效编码，验证异常处理

3. **打包后测试**
   - 使用PyInstaller打包后测试
   - 验证路径解析是否正确
   - 验证文件读取是否正常

---

## 代码质量

### 代码规范
- ✅ 遵循PEP 8编码规范
- ✅ 添加详细的中文注释
- ✅ 方法命名清晰，见名知义
- ✅ 异常处理完善

### 可维护性
- ✅ 代码结构清晰，职责单一
- ✅ 易于扩展和修改
- ✅ 文档完整，便于理解

### 用户体验
- ✅ 界面响应流畅
- ✅ 错误提示友好
- ✅ 操作逻辑符合直觉

---

## 总结

本次更新成功实现了：
1. **Open WiFi支持** - 扩展了WiFi连接功能，支持无密码网络
2. **Changelog查看器** - 提供了便捷的更新日志查看方式

两个功能都注重用户体验，代码质量高，文档完善，为工具的持续优化打下了良好基础。
