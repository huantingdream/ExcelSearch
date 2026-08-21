# ExcelSearch

ExcelSearch 是一个完全在本机运行的 Excel 内容搜索程序。它读取每个工作表的 A、B、C、D 四列文字并建立本地索引，让用户通过记得的内容片段找到对应的 Excel 文件、工作表和行。

Windows 是主要交付平台；macOS 可用于开发、测试和日常使用。

## 给 Windows 使用者

使用者不需要安装 Python、Excel 插件或数据库。

### 安装版

1. 双击 `ExcelSearch-Setup.exe`。
2. 按安装向导完成安装。
3. 从桌面或开始菜单打开 ExcelSearch。

### 便携版

1. 解压 `ExcelSearch-Windows-x64.zip`。
2. 双击其中的 `ExcelSearch.exe`。

不要只复制便携版中的单个 `.exe`，它需要同一目录里的运行文件。若需要只发送一个文件，应发送安装包 `ExcelSearch-Setup.exe`。

## 使用方法

1. 点击“添加 Excel 文件”或“添加文件夹”。
2. 等待程序完成索引。
3. 在搜索框输入 A、B、C、D 任一列中的内容片段，例如工厂代码、物料编号或物料名称。
4. 双击结果打开原始 Excel，或右键在文件管理器中显示文件。

多个用空格分隔的关键词采用“全部包含”匹配，关键词可以来自不同列。例如输入 `HZ015 四孔 墨西哥`，只会显示同一行 A–D 四列合并内容中同时包含这三个片段的结果。

添加文件夹时，程序会根据文件数量使用 2–4 个工作线程并行读取多个 Excel 文件，再安全地顺序写入本地索引。单个损坏文件不会中断其他文件的处理。

搜索结果会显示：

- Excel 文件名和完整路径。
- 工作表名称、A–D 列所在行和行号。
- 同一行 A 列的工厂代码。
- 同一行 B 列的物料编号。
- A、B、C、D 四列内容，并高亮搜索词。
- 原始文件的修改时间。

程序不会识别、提取或索引工作簿中的图片，也不会修改原始 Excel 文件。

## 在 Windows 上生成交付包

安装以下软件：

- 64 位 Python 3.12。
- [Inno Setup 6](https://jrsoftware.org/isinfo.php)（仅生成安装包时需要）。

在 PowerShell 中进入项目目录并执行：

```powershell
.\scripts\build_windows.ps1
```

脚本会安装构建依赖、运行测试并在 `release` 目录生成：

- `ExcelSearch-Setup.exe`
- `ExcelSearch-Windows-x64.zip`

## 在 macOS 上生成 Windows 成品

PyInstaller 不能在 macOS 上可靠地交叉生成 Windows 程序。本项目包含 GitHub Actions Windows 自动构建：

1. 将项目推送到 GitHub 的 `main` 分支。
2. 打开仓库的 **Actions** 页面。
3. 选择 **Test and build**，点击 **Run workflow**。
4. 构建完成后下载 `ExcelSearch-Windows-x64` 构建产物。

下载内容同时包含安装包和便携版，可直接发给 Windows 用户。

## macOS 开发运行

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m excel_search
```

运行测试：

```bash
python -m pytest
```

## 支持的文件

- `.xlsx`
- `.xlsm`
- `.xls`

Excel 临时文件（以 `~$` 开头）会被自动忽略。损坏、加密、无权读取或已经移动的文件会单独报告，不会中断其他文件的索引。

## 本地数据位置

索引数据库只包含可重建的文本索引，不包含图片：

- Windows：`%LOCALAPPDATA%\ExcelSearch\index.db`
- macOS：`~/Library/Application Support/ExcelSearch/index.db`

卸载程序不会删除原始 Excel，也不会主动删除上述本地索引。

## 技术结构

- Python 3.11+
- PySide6 跨平台桌面界面
- openpyxl（`.xlsx` / `.xlsm`）
- xlrd（`.xls`）
- SQLite FTS5 trigram 中文及片段索引，运行环境不支持时自动降级为普通子串搜索
- PyInstaller + Inno Setup Windows 打包
