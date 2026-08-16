# Beam Search 核心动画

本目录包含一段约 115 秒的 Manim Community Edition 动画：

- 以 `game.jpg` 实图引入玩法，将不同鸟类转换为 A–G 字母示意图；
- 在第一步讲解外侧同类、目标匹配、空位和四只消除规则；
- 按 `docs/game-solution.html` 的 46 步解法加速播放，直到 16 组鸟全部消除；
- 使用六根左右镜像树枝、四种圆形字母鸟；
- 开场用动态图示说明「树枝就是栈」、先进后出和目标状态；
- 介绍问题解决方案：左右并排同一棵不规则多叉搜索树，DFS / BFS 同步逐步点亮节点；到达叶子后高亮根到叶的路径与步数；
- 说明游戏时限 → 最少步数 → 选择 BFS；
- 展示 `canonical_key()` + `seen` 集合的重复分支剪枝；
- 演示 Beam Search（展开—评分—保留）平衡速度与搜索空间；
- 播放经过项目规则验证的 12 步完整解法；
- 输出为 1920×1080、30fps、H.264 MP4。

## 文件

- `beam_search_core.py`：Manim 源码；
- `manim.cfg`：项目渲染配置；
- `render.sh`：最终渲染脚本；
- `beam-search-core-1080p.mp4`：最终成片，渲染后生成；
- `beam-search-core-thumbnail.png`：结尾画面缩略图；
- `ManimCE从零到项目实战.md`：面向零基础的完整制作教程；
- `media/`：Manim 的中间媒体和缓存输出。

## 渲染

```bash
cd video
bash render.sh
```

开发阶段可显式覆盖分辨率和帧率，生成低清预览：

```bash
cd video
XDG_CACHE_HOME=/tmp/suanniao-manim-cache \
  manim --config_file manim.cfg \
  -r 854,480 --fps 15 \
  -o beam-search-preview \
  beam_search_core.py BeamSearchCore
```
