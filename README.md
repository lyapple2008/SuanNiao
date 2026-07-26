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

分析完成后会自动生成 `game-solution.html`，并把检测和聚类中间结果保存到
`game-clusters/`。动画页面按照原截图的宽高、树枝行和槽位坐标重建棋盘，
用 `A、B、C……` 代替鸟，并可播放求解器规划的移动与整枝消除动画。
页面提供播放、暂停、上一步、下一步、重置和速度控制。

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

`analyze` 默认在截图旁创建 `<截图文件名>-clusters/`。例如分析
`.ios/debug-frames/turn-001.png` 时会生成
`.ios/debug-frames/turn-001-clusters/`。也可以用 `--debug-dir` 指定其他位置：

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

为满足关卡时间限制，程序默认一次规划后连续执行最多 8 步；如果其中某一步消除了一根树枝，
则立即结束批次，重新截图、识别和规划。普通搬运期间从第二步开始会在点击前快速截图检查
棋盘是否存在，避免广告弹出后继续盲点。
建议先只验证点击坐标：

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
如果遇到广告或其他中断画面，还会保存 `turn-001-interruption-001.png`；即使识别失败，
已经生成的中间调试文件也会保留。

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
- `--moves-per-plan 8`：没有发生树枝消除时，一次识别和搜索后最多连续执行多少步；
- `--tap-gap 0.08`：源树枝和目标树枝两次点击之间的等待秒数；
- `--move-wait 0.40`：普通移动后的等待秒数；
- `--elimination-wait 0.65`：树枝消除后的等待秒数；
- `--capture-interval 0.12`、`--capture-attempts 5`：稳定截图的间隔和最多尝试次数；
- `--interruption-timeout 300`：等待广告关闭或棋盘恢复的最长秒数；
- `--interruption-poll-interval 0.8`：中断期间重新检查画面的间隔秒数；
- `--save-frames frames`：在自动生成的运行目录之外，再额外复制每一步截图；
- `--beam-width 5000`：扩大搜索宽度，提高困难关卡的解题质量；
- `--time-limit 60`：允许单次规划使用更长时间。

`play` 的速度默认值为束宽 `500`、搜索时限 `8` 秒和每批最多 `8` 步；每次消除树枝后
都会重新截图计算。`analyze` 仍使用束宽 `2000`、搜索时限 `20` 秒，适合离线分析。如果实机动画较慢，可先增加
`--move-wait` 和 `--elimination-wait`；如果偶发点击未生效，可减小 `--moves-per-plan`。

程序只在检测不到正常游戏棋盘时处理广告。正常棋盘要求至少检测到两根树枝，允许残局中的
树枝只剩在同一侧；满足这个条件时不会查找或点击任何关闭按钮。棋盘缺失时，iPhone 版本会读取
WDA 可访问性树，仅点击明确标记为“关闭”“关闭广告”“Close Ad”“Skip Ad”等名称的
可见、可用小控件。找到后自动点击并等待棋盘恢复；找不到时提示手动关闭，但程序不会退出，
棋盘重新出现后会自动继续。Android 当前不自动查找关闭控件，会直接进入人工等待流程。
`--dry-run` 不会点击游戏或广告按钮。

## 当前适配范围

截图布局检测按本游戏当前的竖屏界面设计，坐标按图片宽高比例计算，因此不同分辨率通常可以直接使用。若游戏换了皮肤、树枝颜色、每枝容量或界面布局，需要调整 `src/suanniao/vision.py` 中的视觉阈值或布局比例。

## 测试

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```
