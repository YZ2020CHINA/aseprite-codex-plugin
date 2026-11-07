# Aseprite 像素画工作室 · Codex 插件

用 Codex 操作本机 Aseprite：创建像素角色、编辑当前画布、制作逐帧动画，保存可编辑 `.aseprite` 工程，并导出 GIF、PNG、WebP 或精灵表与 JSON。插件代码使用 **MIT** 许可证。

包含 8 个 MCP 工具、Aseprite Lua 桥接和中文 skill。核心仅使用 Python 标准库，无需 API key。可选接入 [N7z/aseprite-live](https://github.com/N7z/aseprite-live)，实时查看已保存作品、动画和保存历史。

## 安装（Windows）

需要 Aseprite 1.3+、Python 3.12+、支持本地插件的 Codex CLI/桌面应用。可选实时预览安装还需要 Git。

```powershell
git clone https://github.com/YZ2020CHINA/aseprite-codex-plugin.git
cd aseprite-codex-plugin
.\install-plugin.ps1 -AsepritePath 'D:\Aseprite\Aseprite.exe'
```

安装器优先使用 Codex bundled Python，否则使用 PATH 中的 Python。可用 `-PythonPath 'C:\path\python.exe'` 指定。安装器生成本机配置、构建 marketplace、安装 `aseprite-local@aseprite-local-market`，并安装 Aseprite 的 `File > Scripts > Connect to Codex` 菜单扩展。`-SkipAsepriteExtension` 可跳过菜单扩展。

**安装后新建 Codex 聊天加载工具与 skill；重启 Aseprite 加载菜单。** 插件使用本机 Aseprite 自带的 logo，由安装器读取；仓库不分发原软件及图标。保持克隆目录在固定位置；移动后重新运行安装器。

已有旧版同名本地原型时，安装此版本会更新同名插件的注册位置。备份作品并保留原目录即可回退；安装器不会迁移旧作品。

## 实时预览（可选）

```powershell
.\scripts\install_live.ps1
```

此脚本从上游安装固定版本 `841fc81b519bd9d10f8ff9b29e43ea28e0c408f4`，存放到被 Git 忽略的 `.state/external/aseprite-live`，并更新本机配置。**aseprite-live 单独使用 AGPL-3.0，未被重新许可为 MIT。** 插件通过独立进程启动其原始 CLI，不复制或导入其代码。已有安装可在 `config.json` 的 `aseprite_live_path` 指定源码目录。

在聊天中让 Codex 调用 `aseprite_viewer(action="start", watch="作品目录")`，再把返回 URL 在右侧浏览器打开。默认端口 7777，冲突时由上游选择空闲端口。`status` 查询，`stop` 关闭本插件启动的独立预览进程；更换目录前先 stop。浏览器可查看逐帧动画、tag、像素网格、缩放和保存版本时间线，每个文件默认最多 200 个版本。历史仅在进程内保存；内存中未保存的编辑不会出现。

此接入使用上游 standalone viewer 模式，没有原型版本的 MCP 工具标签和动态添加监视目录功能。需要标签时，可自行使用上游提供的 `proxy` 模式，按其文档配置。

## 使用示例

- “用 Aseprite 画一个 32×32 招财猫，循环招手 3 帧，保存工程并导出 GIF。”
- “连接 Aseprite，检查当前图层，把角色围巾改成红色。”
- “打开实时预览，在同一工程上逐步保存，最后导出精灵表及 JSON。”

| 工具 | 用途 |
| --- | --- |
| `aseprite_status` | 版本、路径、当前文档桥接状态 |
| `aseprite_connect` | 启动带桥接的 Aseprite 窗口，或准备连接脚本 |
| `aseprite_inspect` | 尺寸、图层、帧、tag 和打开的文档 |
| `aseprite_create` | 用字符行和调色板创建可编辑分层像素动画 |
| `aseprite_eval` | 执行官方 Lua API，支持复杂绘制和修改 |
| `aseprite_export` | PNG/GIF/WebP、精灵表与 JSON |
| `aseprite_preview` | 放大指定帧，返回 MCP 内联图像 |
| `aseprite_viewer` | 管理独立安装的实时预览程序 |

默认 `mode="batch"` 在独立进程操作文件，修改须指定输出。`mode="live"` 操作软件当前文档；先连接、检查活动文档，再修改。Aseprite 可能询问 Lua 文件访问权限，需在软件中允许桥接。模态对话框可能暂停 Timer；超时后先检查文档，避免重复编辑。

Lua 具有本机脚本权限；`read_only` 是调用者声明。工具默认不覆盖输出文件，可用 `overwrite=true` 显式允许。live 修改没有指定 output 时仅修改内存。工程输出和连接状态分别位于 `outputs/`、`.state/`。

## 开发和打包

```powershell
# 配置可执行文件（安装器也会完成此步骤）
Copy-Item config.example.json config.json
$env:ASEPRITE_PATH = 'D:\Aseprite\Aseprite.exe'
python -X utf8 tests/test_bridge.py
python -X utf8 tests/test_distribution.py
python -X utf8 scripts/build_plugin.py
python -X utf8 server.py --call aseprite_status
```

发布包：`dist/aseprite-local-plugin-1.0.0.zip`，包含 MIT 源码和安装器。包中不包含外部预览程序、原软件、图标、作品、令牌、日志或机器路径配置。解压后运行安装器即可重建本机配置。生成的 `plugins/` 和 marketplace 是本机安装产物，不应直接作为远程 marketplace 安装。

卸载 Codex 插件：`.\uninstall-plugin.ps1`。作品和源码保留；菜单扩展可在 Aseprite Preferences > Extensions 中移除。

## 来源和许可证

插件主体使用 [MIT](LICENSE)。参考 [diivi/aseprite-mcp](https://github.com/diivi/aseprite-mcp) 的 Lua 批处理与预览思路，没有复制其源码。可选实时预览来自 N7z/aseprite-live，保持独立 AGPL 许可证。Aseprite 及其图标不属于本仓库 MIT 授权范围。详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
