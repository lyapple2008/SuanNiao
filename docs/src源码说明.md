`src/suanniao/` 是项目的核心 Python 包，共 8 个文件。整体采用“视觉识别 → 棋盘建模 → 搜索求解 → 设备点击/结果展示”的结构。

```text
src/suanniao/
├── __init__.py          # 包的公开接口
├── __main__.py          # python -m suanniao 入口
├── cli.py               # 命令行入口和业务流程编排
├── controller.py        # Android/iOS 设备控制
├── model.py             # 棋盘、树枝和移动规则
├── solver.py            # 束搜索求解器
├── vision.py            # 截图识别和鸟类聚类
└── solution_html.py     # 生成解题动画 HTML
```

### [__init__.py](../src/suanniao/__init__.py)

包的公开 API。

它从其他模块导出常用对象：

- `BoardState`、`Move`
- `BeamSolver`、`SolveResult`
- `BoardRecognizer`、`RecognitionResult`

因此外部代码可以直接写：

```python
from suanniao import BoardRecognizer, BeamSolver
```

而不需要关心具体模块位置。

### [__main__.py](../src/suanniao/__main__.py)

`python -m suanniao` 的执行入口。

文件本身很简单，只是调用：

```python
from .cli import main
main()
```

它和 `pyproject.toml` 中的 `suanniao` 命令最终都会进入 `cli.main()`。

### [cli.py](../src/suanniao/cli.py)

整个程序的业务编排层，负责把识别、求解和设备控制串起来。

提供两个子命令：

- `suanniao analyze <截图>`：分析一张静态截图。
- `suanniao play`：连接手机，自动截图、求解并点击。

主要函数：

- `analyze()`：读取截图，调用视觉识别和求解器，输出文本/JSON，并生成调试报告和动画 HTML。
- `play()`：不断截图、识别、规划、点击，直到游戏结束或达到最大轮数。
- `build_parser()`：定义所有命令行参数。
- `main()`：解析参数、调用对应处理函数，并统一处理错误。
- `_capture_game_board()`：等待稳定截图；遇到广告等中断画面时尝试恢复。
- `_next_move_batch()`：选择本轮连续执行的动作；出现整枝消除后立即停止批次并重新识别。
- `_click_point_for_contents()`：根据当前树枝内容计算点击位置。
- `_format_board()`、`_format_solution()`：格式化终端输出。

`play()` 的核心循环可以概括为：

```text
稳定截图 → 判断是否为棋盘 → 识别棋盘
       → 搜索解法 → 批量点击
       → 重新截图、重新识别和规划
```

### [controller.py](../src/suanniao/controller.py)

设备自动化适配层，屏蔽 Android 和 iOS 控制方式的差异。

主要组成：

- `DeviceController`：协议接口，定义截图、稳定截图、点击、处理中断、关闭连接等能力。
- `StableCaptureMixin`：连续获取截图并比较游戏区域，等画面稳定后再返回。
- `AdbController`：通过 ADB 控制 Android。
  - `adb exec-out screencap` 获取截图。
  - `adb shell input tap` 执行点击。
- `WdaController`：通过 WebDriverAgent HTTP API 控制 iPhone。
  - 创建或复用 WDA session。
  - 获取 Base64 截图。
  - 将 Retina 截图像素坐标转换为 iOS 逻辑点击坐标。
  - 兼容多种 WDA 点击接口。
  - 读取可访问性树，寻找明确标记为“关闭”“跳过广告”等控件。

文件后半部分的 `_find_close_control()` 等函数负责安全筛选广告关闭按钮：检查标签、可见性、可用状态、控件大小和屏幕位置，避免随意点击画面。

### [model.py](../src/suanniao/model.py)

游戏规则和状态模型，是识别器与求解器之间的数据基础。

核心类型：

- `Bird = int`：使用整数表示一种鸟。
- `Branch = tuple[Bird, ...]`：一根树枝上的鸟。
- `REMOVED = (-1,)`：表示已经完成并从棋盘消失的树枝。
- `Move`：一次移动，包括源树枝、目标树枝、移动数量和是否完成整枝。
- `BoardState`：完整棋盘状态。

树枝中的鸟按照：

```text
固定端/树干端 → 外端/可移动端
```

保存，因此元组最后一个元素就是当前可以移动的鸟。

`BoardState` 主要负责：

- 统计鸟和已消除树枝数量。
- 判断是否已经完成。
- `legal_moves()`：枚举所有合法移动。
- `apply()`：应用移动并生成新的不可变状态。
- `canonical_key()`：忽略树枝实际位置，对称状态共用搜索记录，减少重复搜索。

它还做了一些搜索剪枝，例如空树枝之间可以互换，不会生成仅仅“交换两个等价空位”的动作。

### [solver.py](../src/suanniao/solver.py)

负责根据 `BoardState` 搜索移动方案。

核心类：

- `SolveResult`：保存动作序列、消除数量、目标数量、探索状态数、耗时和是否完全解决。
- `BeamSolver`：有宽度、深度和时间限制的束搜索求解器。

求解过程：

1. 从当前棋盘枚举合法移动。
2. 应用移动得到下一状态。
3. 使用 `canonical_key()` 去重。
4. 给候选状态评分。
5. 每一层只保留评分最高的 `beam_width` 个状态。
6. 达到消除目标时立即返回。

评分 `_rank()` 优先考虑：

1. 消除更多树枝。
2. 减少树枝内部不同颜色的连续段。
3. 形成更长的纯色树枝。
4. 避免塞满但颜色混杂的死锁树枝。
5. 保留更多空树枝。

如果时间或深度达到上限，会返回目前找到的最佳方案，结果中的 `solved` 会说明是不是完整解。

### [vision.py](../src/suanniao/vision.py)

项目中最大、最复杂的模块，负责把手机截图转换成 `BoardState`。

核心公开对象：

- `BoardRecognizer`：棋盘识别器。
- `DetectedBranch`：树枝的位置、槽位坐标和鸟类型。
- `RecognitionResult`：棋盘状态、识别坐标、聚类信息和截图尺寸。
- `RecognitionError`：识别失败异常。

识别流程大致为：

1. 根据木头颜色阈值检测左右两侧树枝所在行。
2. 按截图宽高比例计算每根树枝的 4 个槽位。
3. 分析槽位前景、连通区域和高度，判断有没有鸟。
4. 全局选择每根树枝的占用数量，并保证总鸟数是容量 4 的倍数。
5. 裁剪每只鸟；右侧树枝会水平翻转，使方向统一。
6. 从 HSV 颜色比例中提取鸟的视觉特征。
7. 对可能的鸟类型数量运行 K-Means。
8. 使用匈牙利算法进行容量约束分配，保证每一类鸟的数量是 4 的倍数。
9. 根据轮廓系数等指标选择最佳聚类结果。
10. 构造 `DetectedBranch` 和 `BoardState`。

该模块还会生成详细调试材料：

- 树枝和槽位标注图。
- 每只鸟的裁剪图、特征掩码。
- 不同聚类数量的候选结果。
- `report.json`。
- 可视化调试页面 `index.html`。

这里使用的是无监督识别，不依赖预先训练好的分类模型。

### [solution_html.py](../src/suanniao/solution_html.py)

把识别结果和求解步骤生成一个自包含的 HTML 动画页面。

`write_solution_animation()` 会把以下数据序列化进 HTML：

- 截图尺寸和树枝坐标。
- 各树枝上的鸟。
- 完整移动序列。
- 是否求解成功、搜索状态数和耗时。

文件后面的 `_HTML_TEMPLATE` 包含完整的 CSS、SVG 和 JavaScript，所以生成的 HTML 不依赖外部资源，可以直接在浏览器打开。页面支持播放、暂停、单步、重置和速度调节。

### 模块依赖关系

```text
__main__.py
    └── cli.py
         ├── vision.py ───────┐
         ├── solver.py ───────┤
         ├── controller.py    │
         ├── solution_html.py │
         └── model.py ◀───────┘

vision.py ──→ model.py
solver.py ──→ model.py
solution_html.py ──→ vision.py + solver.py
```

其中：

- `model.py` 是最底层的游戏规则。
- `vision.py` 将图片转换为模型。
- `solver.py` 对模型进行搜索。
- `controller.py` 负责与真实设备交互。
- `cli.py` 负责调度整个流程。
- `solution_html.py` 负责把结果展示出来。