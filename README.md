# 算鸟：手机小游戏自动求解器

这个项目完成三件事：

1. 从手机截图中自动检测左右两侧的树枝和每只小鸟；
2. 用无监督视觉聚类判断哪些鸟完全相同，不需要提前标注训练集；
3. 用全局束搜索规划移动，并可自动点击 Android 手机、Android 模拟器或 iPhone。

程序按“固定端 → 外端/可移动端”保存每根树枝。一次点击会搬运源树枝外端连续的同类鸟，目标必须为空或外端为同类鸟，容量为 4；四只完全相同后，该树枝从棋盘中消除。

## 安装

建议使用 Python 3.10 或更高版本：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

## 分析截图

```bash
suanniao analyze game.jpg
```

分析完成后会自动生成 `game-solution.html`。页面按照原截图的宽高、树枝行和
槽位坐标重建棋盘，用 `A、B、C……` 代替鸟，并可播放求解器规划的移动与
整枝消除动画。页面提供播放、暂停、上一步、下一步、重置和速度控制。

可以指定输出位置或关闭 HTML 生成：

```bash
suanniao analyze game.jpg --html-output docs/game-solution.html
suanniao analyze game.jpg --no-html
```

也可以直接使用源码目录：

```bash
PYTHONPATH=src python3 -m suanniao analyze game.jpg
```

输出包括识别到的棋盘、鸟类聚类数量、预计最多消除的树枝数和移动步骤。若自动判断鸟类数量失败，可显式指定，例如：

```bash
suanniao analyze game.jpg --types 7
```

需要调试识别或聚类时，可以传入任意已保存的截图并生成可视化报告：

```bash
suanniao analyze .ios/debug-frames/turn-001.png \
  --debug-dir .ios/cluster-debug
```

打开 `.ios/cluster-debug/index.html` 可以查看：

- 树枝行、槽位坐标和鸟存在性判断；
- 每只鸟经过方向归一化、遮挡方向修正后的裁剪图，以及实际使用的特征掩码；
- 每个候选类型数 `k` 的普通 K-Means 数量、约束目标数量、最终分组和轮廓系数；
- 自动聚类最终选择的候选结果。

即使自动聚类失败，调试报告也会保留下来。若只想检查指定类型数的
分组效果，可以同时传入 `--types`：

```bash
suanniao analyze screenshot.png --types 7 --debug-dir .ios/cluster-debug-k7
```

## Android：通过 ADB 自动玩

先安装 Android platform-tools，打开手机的“开发者选项 → USB 调试”，并确认：

```bash
adb devices
```

设备可见后运行：

```bash
suanniao play
```

程序每次只执行规划中的第一步，然后重新截图、重新识别和重新规划。这能自动适应树枝消失、点击动画和偶发识别误差。建议先只验证一次点击坐标：

```bash
suanniao play --dry-run
```

## iPhone：通过 WebDriverAgent 自动玩

iOS 不提供类似 ADB 的系统级点击命令，因此程序通过
[WebDriverAgent](https://github.com/appium/WebDriverAgent)（WDA）获取截图和执行触摸。
程序直接调用 WDA 的 HTTP 接口，不要求同时运行 Appium Server。

项目已经提供 WDA 源码和一键启动脚本。首次准备步骤：

1. 在 Mac 上安装 Xcode；
2. 在 iPhone 中打开“设置 → 隐私与安全性 → 开发者模式”；
3. 在 `Xcode -> Settings -> Accounts` 登录 Apple ID，并确保开发团队可用；
4. 根据本机设备和 Team 修改 `.ios/wda.env`；
5. 运行环境自检：

```bash
scripts/ios/doctor.sh
```

脚本会通过 Xcode CoreDevice 隧道直接访问 iPhone，不需要手动运行 `iproxy`。
首次执行会自动创建 provisioning profile、安装并启动 WDA。

先验证截图识别和点击坐标，但不执行游戏点击：

```bash
scripts/ios/run.sh --dry-run
```

确认无误后自动运行：

```bash
scripts/ios/run.sh
```

每次执行 `play` 都会自动新建 `.ios/runs/run-日期-时间/` 目录。每一回合会保存
`turn-001.png` 原始截图，并在 `turn-001-clusters/` 中保存检测标注图、鸟裁剪、
特征掩码、各候选聚类图片、`report.json` 和可视化 `index.html`，用于复盘识别与聚类结果。
即使识别失败，已经生成的中间调试文件也会保留。

如果已经使用其他方式启动了 WDA，仍然可以直接指定地址：

```bash
suanniao play --platform ios --wda-url http://192.168.1.20:8100
```

iPhone 截图通常使用 Retina 像素，而 WDA 点击使用逻辑点。程序会读取 WDA
窗口尺寸，并自动完成像素坐标到触控坐标的缩放，无需手动设置 2x 或 3x 倍率。

常用参数：

- `--platform android|ios`：选择 Android/ADB 或 iPhone/WDA；
- `--serial DEVICE_ID`：有多个 Android ADB 设备时指定设备；
- `--wda-url URL`：指定 iPhone 的 WebDriverAgent 地址；
- `--wda-session-id ID`：复用已经创建的 WDA 会话；
- `--move-wait 1.2`：设备动画较慢时增加等待时间；
- `--save-frames frames`：在自动生成的运行目录之外，再额外复制每一步截图；
- `--beam-width 5000`：扩大搜索宽度，提高困难关卡的解题质量；
- `--time-limit 60`：允许单次规划使用更长时间。

## 当前适配范围

截图布局检测按本游戏当前的竖屏界面设计，坐标按图片宽高比例计算，因此不同分辨率通常可以直接使用。若游戏换了皮肤、树枝颜色、每枝容量或界面布局，需要调整 `src/suanniao/vision.py` 中的视觉阈值或布局比例。

## 测试

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```
