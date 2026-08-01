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
则立即结束批次，重新截图、识别和规划。普通搬运期间从第二步开始会在点击前快速截图，
检查棋盘是否存在并确认实际鸟位置与内存中的预期状态一致，避免广告或点击未生效后继续盲点。
每轮开始前还会点击一次屏幕中央空白区域，清除可能残留的鸟选择状态。
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

脚本会先完成 WDA 会话建立、首张截图请求和图片解码，然后提示“准备完成”。此时再在
iPhone 上开始游戏，回到终端按 Enter 后，程序才会进行第一轮棋盘识别和点击。使用
`--no-wait-for-start` 可以跳过这个确认。若目标设备上的 WDA 已经在线，启动脚本会直接
复用，不再重复执行 `xcodebuild`。

每次执行 `play` 都会自动新建 `.ios/runs/run-日期-时间/` 目录。每一回合会保存
`turn-001.png` 原始截图，并在 `turn-001-clusters/` 中保存检测标注图、鸟裁剪、
特征掩码、各候选聚类图片、`report.json` 和可视化 `index.html`，用于复盘识别与聚类结果。
iOS 启动脚本默认在游戏操作结束后再生成这些聚类报告，避免图片编码和磁盘写入占用游戏时间。
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
- `--wait-for-start` / `--no-wait-for-start`：设备预热后是否等待人工确认开始；
- `--debug-reports live|deferred|off`：实时、延后或不生成逐回合聚类报告；
- `--moves-per-plan 8`：没有发生树枝消除时，一次识别和搜索后最多连续执行多少步；
- `--tap-gap 0.12`：源树枝和目标树枝两次点击之间的等待秒数；
- `--move-wait 0.30`：普通移动后的等待秒数；
- `--elimination-wait 0.55`：树枝消除后的等待秒数；
- `--capture-interval 0.10`、`--capture-attempts 5`：稳定截图的间隔和最多尝试次数；
- `--interruption-timeout 300`：等待广告关闭或棋盘恢复的最长秒数；
- `--interruption-poll-interval 0.8`：中断期间重新检查画面的间隔秒数；
- `--no-move-confirmations 2`：连续多少张稳定截图都无可执行移动后才停止；
- `--save-frames frames`：在自动生成的运行目录之外，再额外复制每一步截图；
- `--beam-width 5000`：扩大搜索宽度，提高困难关卡的解题质量；
- `--time-limit 60`：允许单次规划使用更长时间。

`play` 的速度默认值为束宽 `120`、搜索时限 `2` 秒和每批最多 `8` 步；每次消除树枝后
都会重新截图计算。iOS 控制器会缓存截图、点击接口和窗口缩放尺寸，正常批次之间也不会
重复点击中央空白区域；仅在首次启动、点击未生效或中断恢复时清除残留选择。`analyze`
仍使用束宽 `2000`、搜索时限 `20` 秒，适合离线分析。如果实机动画较慢，可先增加
`--move-wait` 和 `--elimination-wait`；如果偶发点击未生效，可减小 `--moves-per-plan`。

正常棋盘要求至少检测到两根树枝，允许残局中的树枝只剩在同一侧。检测不到正常棋盘时，
程序只保存中断截图并输出日志，不读取或点击广告关闭控件。请手动处理广告或其他弹窗；程序
不会退出，会持续等待，棋盘重新出现后自动继续。`--dry-run` 同样不会点击游戏或广告按钮。
棋盘门禁还会检查天空区域是否被遮罩整体变暗，并限制相邻回合只能保持树枝/鸟数量不变，
或恰好消除一根树枝和 4 只鸟。识别结果变化过大时会保存为
`turn-NNN-suspicious-board-NNN.png`，按中断画面等待恢复。

## 当前适配范围

截图布局检测按本游戏当前的竖屏界面设计。程序会根据同侧树枝的中位间距自动估计游戏在
残局阶段使用的鸟和树枝缩放比例，并同步调整槽位、裁剪框和点击坐标，因此树枝消除后鸟变大
也会重新适配。若游戏换了皮肤、树枝颜色、每枝容量或整体界面布局，仍可能需要调整
`src/suanniao/vision.py` 中的视觉阈值或基础布局比例。

## 测试

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```
