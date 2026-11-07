---
name: aseprite
description: 使用本机 Aseprite 绘制和编辑像素画、角色精灵、逐帧动画、图层、调色板及精灵表。用户指定 Aseprite、需要操作该软件当前画布或制作可编辑 .aseprite 工程时使用。
---

# Aseprite 像素画工作室

通过 `aseprite` MCP 服务调用本机 Aseprite 官方 Lua API。先调用 `aseprite_status` 确认可执行程序和当前文档桥接状态。

## 选择操作方式

- 文件创作和转换：使用默认 `mode="batch"`。每次在独立进程打开输入，编辑时提供 `.aseprite` 输出；默认不覆盖已有文件。相对路径落在工具返回的 `output_dir`，交付时使用工具返回的绝对路径。
- 用户要求操作正在打开、尚未保存的画布：调用 `aseprite_connect`，确认 `connected=true`，随后使用 `mode="live"`。先 `aseprite_inspect`，不传 input 即读取当前活动文档。live 传 input 会打开指定文件并切换活动文档，避免无意操作其他画布。
- 已打开的窗口可从 `File > Scripts > Connect to Codex` 启用安装的扩展；启动新窗口的连接脚本也可用。若 Aseprite 显示自己的 Lua 文件访问提示，应说明需要用户允许该桥接访问工程目录，不能声称尚未完成的连接已成功。窗口有模态对话框时 Timer 可能暂停；超时先检查文档，避免重复编辑。

## 创作与验收

1. 根据用途确定画布、视角、透明背景、配色及动画帧。信息足够时直接创作；保留用户给定尺寸和风格。
2. 小尺寸像素图可用 `aseprite_create` 的字符行格式；所有字符都必须在 palette 显式定义，包括透明字符。每层分别给出 frames，`durations_ms` 决定总帧数。帧和 tag 使用 1 起始，像素坐标使用 0 起始。
3. 复杂绘制、现有文件修改、分组、选区、调色板、变换、动画和切片用 `aseprite_eval`。返回 JSON 可序列化的 table/number/string，不返回 Sprite、Color 等 userdata。读取 [Lua 操作示例](references/lua.md) 获取可编辑 cel、工具笔触和动画示例；特殊 API 查官方 https://aseprite.org/api/，按本机版本处理能力差异。
4. 保持主体、装备、背景和效果可分别编辑。先定轮廓和统一光源，再加细节。每个主要绘制阶段调用 `aseprite_preview` 看实际结果，修正杂点、轮廓和可读性；动画还要检查关键帧和首尾循环。
5. 保存 `.aseprite` 母版，用 `aseprite_export` 输出 GIF/WebP 或 `kind="sheet"` 的 PNG+JSON。image PNG 导出第一帧；指定其他帧或放大用 `aseprite_preview`，多帧图集用 sheet。
6. 检查工具返回成功、文件存在且重新 inspect 的尺寸/图层/帧符合需求，再给用户工程、导出物和预览。只完成技术连接时不把测试小图描述为正式美术作品。

## 实时预览与回放（N7z/aseprite-live）

需要看绘制过程时，先调用 `aseprite_viewer(action="start",watch="作品目录")`，再用 `open_in_codex` 将返回的 url 打开到当前聊天右侧。默认监视 output_dir；更换目录前先 stop，status 查询地址。此功能需要通过 `scripts/install_live.ps1` 独立安装 AGPL-3.0 的 N7z/aseprite-live，缺失时按工具提示处理。保持使用同一个 `.aseprite` 输出路径并在各阶段保存，才能在同一条时间线上看到版本回放；覆盖该生成文件时设 overwrite=true。预览服务依赖已保存文件，live 内存修改也要指定 output 才能出现在浏览器。独立 CLI 接入不提供 MCP 工具标签。

页面可查看所有帧、按真实时长播放动画、选择 tag、显示像素网格、缩放、拖动时间线和回放。历史保存在内存，每个文件默认最多200个版本；重启服务会丢失该回放历史，源工程仍保留。此实时浏览器预览与 mode=live 当前文档编辑是两项独立功能。

## Lua 与文档约束

`aseprite_eval` 提供完整本机 Lua 权限，不是沙箱；`read_only=true` 只是调用者声明，不能限制代码。只执行本任务所需代码，尊重用户文件和实际权限。默认给已有文档的编辑加一次名为 Codex edit 的撤销事务；没有活动文档时直接执行。导出和有自身事务的命令可设 `transaction=false`。批处理修改必须提供 output；live 未提供 output 时只改内存，不等于保存。

修改 cel 像素时复制 `Image(cel.image)`，完成后赋回 `cel.image`，这样撤销和脏标记可靠。cel 位置是画布坐标，image 的坐标是 cel 局部坐标。删除或合并图层等操作遵循当前请求范围，保存新版本便于回退。
