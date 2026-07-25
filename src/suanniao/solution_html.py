from __future__ import annotations

import json
from html import escape
from pathlib import Path

from .solver import SolveResult
from .vision import RecognitionResult


def write_solution_animation(
    recognition: RecognitionResult,
    solution: SolveResult,
    destination: str | Path,
    *,
    source_name: str = "screenshot",
) -> Path:
    """Write a self-contained HTML animation for one recognized solution path."""
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "width": recognition.image_size[0],
        "height": recognition.image_size[1],
        "capacity": recognition.state.capacity,
        "typeCount": recognition.type_count,
        "clusterSizes": recognition.cluster_sizes,
        "silhouette": recognition.silhouette,
        "branches": [
            {
                "side": branch.side,
                "branchY": branch.branch_y,
                "birdY": branch.bird_y,
                "slots": branch.slots,
                "birds": branch.birds,
            }
            for branch in recognition.branches
        ],
        "moves": [
            {
                "source": move.source,
                "destination": move.destination,
                "count": move.count,
                "completesBranch": move.completes_branch,
            }
            for move in solution.moves
        ],
        "solution": {
            "solved": solution.solved,
            "eliminated": solution.eliminated,
            "target": solution.target,
            "exploredStates": solution.explored_states,
            "elapsedSeconds": solution.elapsed_seconds,
        },
    }
    title = escape(f"{source_name} · 算鸟消除动画")
    document = (
        _HTML_TEMPLATE.replace("__TITLE__", title)
        .replace(
            "__BOARD_DATA__",
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )
    )
    output.write_text(document, encoding="utf-8")
    return output


_HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>__TITLE__</title>
  <style>
    :root {
      color-scheme: light dark;
      --page: #eef6fb;
      --surface: #ffffff;
      --surface-soft: #e5f1f8;
      --text: #17212b;
      --muted: #607080;
      --border: #cbd8e2;
      --primary: #2563eb;
      --primary-text: #ffffff;
      --wood: #87512f;
      --wood-light: #bd7b45;
      --slot: #8aa0b2;
      --success: #16835b;
      --shadow: 0 12px 36px rgba(49, 77, 99, 0.14);
      --bird-0: #f0c83e;
      --bird-1: #ec8752;
      --bird-2: #ea8faf;
      --bird-3: #65788e;
      --bird-4: #4aa978;
      --bird-5: #9a72d0;
      --bird-6: #d4d8dc;
      --bird-7: #50a3c2;
      --bird-8: #de6b6b;
      --bird-9: #86a94b;
    }

    @media (prefers-color-scheme: dark) {
      :root {
        --page: #0f1720;
        --surface: #18232e;
        --surface-soft: #223241;
        --text: #edf5fb;
        --muted: #aab9c6;
        --border: #34495a;
        --primary: #86a8ff;
        --primary-text: #101722;
        --wood: #a86c42;
        --wood-light: #d39a69;
        --slot: #71889a;
        --success: #64d5a7;
        --shadow: 0 12px 36px rgba(0, 0, 0, 0.28);
      }
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      background: var(--page);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    button, select { font: inherit; }

    button:focus-visible, select:focus-visible {
      outline: 3px solid color-mix(in srgb, var(--primary) 40%, transparent);
      outline-offset: 2px;
    }

    main {
      width: min(920px, 100%);
      margin: 0 auto;
      padding: 20px;
    }

    header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 14px;
    }

    h1 {
      margin: 0 0 5px;
      font-size: clamp(1.25rem, 4vw, 1.8rem);
      font-weight: 600;
    }

    .summary {
      margin: 0;
      color: var(--muted);
    }

    .controls {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      flex-wrap: wrap;
      margin-bottom: 12px;
    }

    button, select {
      min-height: 40px;
      border: 1px solid var(--border);
      border-radius: 9px;
      padding: 8px 13px;
      background: var(--surface);
      color: var(--text);
      cursor: pointer;
    }

    button.primary {
      border-color: var(--primary);
      background: var(--primary);
      color: var(--primary-text);
    }

    button:disabled { cursor: not-allowed; opacity: 0.45; }

    label {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      color: var(--muted);
    }

    .status {
      min-height: 48px;
      margin: 0 auto 12px;
      padding: 10px 14px;
      border-top: 1px solid var(--border);
      border-bottom: 1px solid var(--border);
      text-align: center;
      font-variant-numeric: tabular-nums;
    }

    .status strong { color: var(--text); font-weight: 600; }

    .board-frame {
      width: min(100%, 440px);
      margin: 0 auto;
      overflow: hidden;
      border: 1px solid var(--border);
      border-radius: 22px;
      background: var(--surface-soft);
      box-shadow: var(--shadow);
    }

    #board {
      display: block;
      width: 100%;
      height: auto;
      background:
        radial-gradient(circle at 18% 12%, color-mix(in srgb, var(--surface) 70%, transparent) 0 7%, transparent 7.5%),
        radial-gradient(circle at 84% 23%, color-mix(in srgb, var(--surface) 58%, transparent) 0 9%, transparent 9.5%),
        linear-gradient(180deg, color-mix(in srgb, var(--primary) 18%, var(--surface-soft)), var(--surface-soft));
    }

    .branch-line {
      stroke: var(--wood);
      stroke-linecap: round;
    }

    .branch-highlight {
      stroke: var(--primary);
      opacity: 0;
      transition: opacity 160ms ease;
      stroke-linecap: round;
    }

    .branch.active .branch-highlight { opacity: 0.9; }

    .slot-guide {
      fill: none;
      stroke: var(--slot);
      opacity: 0.2;
      stroke-width: 1.5;
      stroke-dasharray: 4 5;
    }

    .bird circle {
      stroke: color-mix(in srgb, var(--text) 45%, transparent);
      stroke-width: 1.5;
      filter: drop-shadow(0 3px 2px rgba(0, 0, 0, 0.16));
    }

    .bird text {
      fill: #17212b;
      font-weight: 700;
      text-anchor: middle;
      dominant-baseline: central;
      pointer-events: none;
    }

    .progress-track {
      width: min(100%, 440px);
      height: 5px;
      margin: 12px auto 0;
      overflow: hidden;
      border-radius: 999px;
      background: var(--border);
    }

    .progress-bar {
      width: 0;
      height: 100%;
      background: var(--primary);
      transition: width 220ms ease;
    }

    @media (max-width: 620px) {
      main { padding: 14px; }
      header { display: block; }
      .summary { margin-bottom: 10px; }
      .controls { justify-content: flex-start; }
      .board-frame { border-radius: 16px; }
    }

    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {
        scroll-behavior: auto !important;
        transition-duration: 0.01ms !important;
        animation-duration: 0.01ms !important;
      }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>算鸟消除过程</h1>
        <p class="summary" id="summary"></p>
      </div>
    </header>

    <div class="controls" aria-label="动画控制">
      <button type="button" id="previous">上一步</button>
      <button type="button" id="play" class="primary">播放</button>
      <button type="button" id="next">下一步</button>
      <button type="button" id="reset">重置</button>
      <label for="speed">速度
        <select id="speed">
          <option value="0.65">0.65×</option>
          <option value="1" selected>1×</option>
          <option value="1.5">1.5×</option>
          <option value="2">2×</option>
        </select>
      </label>
    </div>

    <div class="status" id="status" aria-live="polite"></div>

    <div class="board-frame">
      <svg id="board" role="img" aria-label="按原截图位置排列的字母鸟消除动画">
        <g id="branches"></g>
        <g id="birds"></g>
      </svg>
    </div>
    <div class="progress-track" aria-hidden="true"><div class="progress-bar" id="progress"></div></div>
  </main>

  <script>
    const data = __BOARD_DATA__;
    const svgNS = "http://www.w3.org/2000/svg";
    const board = document.getElementById("board");
    const branchLayer = document.getElementById("branches");
    const birdLayer = document.getElementById("birds");
    const status = document.getElementById("status");
    const summary = document.getElementById("summary");
    const progress = document.getElementById("progress");
    const previousButton = document.getElementById("previous");
    const playButton = document.getElementById("play");
    const nextButton = document.getElementById("next");
    const resetButton = document.getElementById("reset");
    const speedSelect = document.getElementById("speed");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

    board.setAttribute("viewBox", `0 0 ${data.width} ${data.height}`);
    const tokenRadius = Math.max(17, data.width * 0.029);
    const branchStroke = Math.max(5, data.width * 0.008);
    const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
    const symbol = value => value < letters.length ? letters[value] : String(value);
    const birdColor = value => {
      const preset = getComputedStyle(document.documentElement)
        .getPropertyValue(`--bird-${value}`).trim();
      return preset || `hsl(${(value * 53) % 360} 62% 62%)`;
    };

    let state;
    let birdElements;
    let branchElements;
    let stepIndex = 0;
    let playing = false;
    let animating = false;
    let generation = 0;

    function svgElement(name, attributes = {}) {
      const element = document.createElementNS(svgNS, name);
      for (const [key, value] of Object.entries(attributes)) {
        element.setAttribute(key, String(value));
      }
      return element;
    }

    function buildInitialState() {
      let nextBirdId = 0;
      return data.branches.map(branch => ({
        removed: false,
        birds: branch.birds.map(type => ({ id: `bird-${nextBirdId++}`, type }))
      }));
    }

    function branchExtent(branch) {
      const xs = branch.slots.map(slot => slot[0]);
      const spacing = xs.length > 1 ? Math.abs(xs[1] - xs[0]) : data.width * 0.08;
      return [Math.max(0, Math.min(...xs) - spacing * 0.55), Math.min(data.width, Math.max(...xs) + spacing * 0.55)];
    }

    function createBoardStructure() {
      branchLayer.replaceChildren();
      branchElements = [];
      data.branches.forEach((branch, index) => {
        const group = svgElement("g", { class: "branch", "data-index": index });
        const [startX, endX] = branchExtent(branch);
        const wood = svgElement("line", {
          class: "branch-line",
          x1: startX,
          y1: branch.branchY,
          x2: endX,
          y2: branch.branchY,
          "stroke-width": branchStroke
        });
        const highlight = svgElement("line", {
          class: "branch-highlight",
          x1: startX,
          y1: branch.branchY,
          x2: endX,
          y2: branch.branchY,
          "stroke-width": branchStroke + 5
        });
        group.append(highlight, wood);
        branch.slots.forEach(([x, y]) => {
          group.append(svgElement("circle", {
            class: "slot-guide", cx: x, cy: y, r: tokenRadius
          }));
        });
        branchLayer.append(group);
        branchElements.push(group);
      });
    }

    function createBirdElement(bird, point) {
      const group = svgElement("g", {
        class: "bird",
        "data-id": bird.id,
        transform: `translate(${point[0]} ${point[1]})`
      });
      const circle = svgElement("circle", { r: tokenRadius, fill: birdColor(bird.type) });
      const text = svgElement("text", {
        y: tokenRadius * 0.03,
        "font-size": tokenRadius * 1.12,
        "aria-hidden": "true"
      });
      text.textContent = symbol(bird.type);
      const title = svgElement("title");
      title.textContent = `类型 ${symbol(bird.type)}`;
      group.append(title, circle, text);
      birdLayer.append(group);
      birdElements.set(bird.id, group);
      return group;
    }

    function resetBoard(targetStep = 0) {
      generation += 1;
      playing = false;
      animating = false;
      playButton.textContent = "播放";
      birdLayer.replaceChildren();
      state = buildInitialState();
      birdElements = new Map();
      branchElements.forEach(element => {
        element.style.opacity = "1";
        element.classList.remove("active");
      });
      data.branches.forEach((branch, branchIndex) => {
        state[branchIndex].birds.forEach((bird, slotIndex) => {
          createBirdElement(bird, branch.slots[slotIndex]);
        });
      });
      stepIndex = 0;
      for (let index = 0; index < targetStep; index += 1) {
        applyMoveInstant(data.moves[index]);
        stepIndex += 1;
      }
      updateStatus();
    }

    function applyMoveInstant(move) {
      const source = state[move.source];
      const destination = state[move.destination];
      const moving = source.birds.splice(source.birds.length - move.count, move.count);
      const destinationStart = destination.birds.length;
      destination.birds.push(...moving);
      moving.forEach((bird, offset) => {
        const point = data.branches[move.destination].slots[destinationStart + offset];
        birdElements.get(bird.id)?.setAttribute("transform", `translate(${point[0]} ${point[1]})`);
      });
      if (move.completesBranch) {
        destination.removed = true;
        branchElements[move.destination].style.opacity = "0";
        destination.birds.forEach(bird => birdElements.get(bird.id)?.remove());
        destination.birds = [];
      }
    }

    function pointAt(branchIndex, slotIndex) {
      return data.branches[branchIndex].slots[slotIndex];
    }

    function tweenBird(element, start, end, duration, runGeneration) {
      if (duration <= 0) {
        element.setAttribute("transform", `translate(${end[0]} ${end[1]})`);
        return Promise.resolve();
      }
      const lift = Math.max(46, data.height * 0.038);
      const waypoints = [
        start,
        [start[0], start[1] - lift],
        [end[0], end[1] - lift],
        end
      ];
      return new Promise(resolve => {
        const started = performance.now();
        const frame = now => {
          if (runGeneration !== generation) {
            resolve();
            return;
          }
          // Some browsers may provide a frame timestamp fractionally earlier
          // than performance.now() captured when the tween was scheduled.
          const progressValue = Math.max(
            0,
            Math.min(1, (now - started) / duration)
          );
          const scaled = progressValue * (waypoints.length - 1);
          const segment = Math.min(waypoints.length - 2, Math.floor(scaled));
          const local = scaled - segment;
          const eased = local < 0.5 ? 2 * local * local : 1 - Math.pow(-2 * local + 2, 2) / 2;
          const from = waypoints[segment];
          const to = waypoints[segment + 1];
          const x = from[0] + (to[0] - from[0]) * eased;
          const y = from[1] + (to[1] - from[1]) * eased;
          element.setAttribute("transform", `translate(${x} ${y})`);
          if (progressValue < 1) requestAnimationFrame(frame);
          else resolve();
        };
        requestAnimationFrame(frame);
      });
    }

    function wait(milliseconds) {
      return new Promise(resolve => setTimeout(resolve, milliseconds));
    }

    async function animateMove(move) {
      if (animating) return;
      animating = true;
      updateControls();
      const runGeneration = generation;
      const source = state[move.source];
      const destination = state[move.destination];
      const sourceStart = source.birds.length - move.count;
      const destinationStart = destination.birds.length;
      const moving = source.birds.slice(sourceStart);
      branchElements[move.source].classList.add("active");
      branchElements[move.destination].classList.add("active");
      const speed = Number(speedSelect.value);
      const duration = reducedMotion.matches ? 0 : 920 / speed;

      await Promise.all(moving.map((bird, offset) => {
        const element = birdElements.get(bird.id);
        return tweenBird(
          element,
          pointAt(move.source, sourceStart + offset),
          pointAt(move.destination, destinationStart + offset),
          duration,
          runGeneration
        );
      }));

      if (runGeneration !== generation) return;
      source.birds.splice(sourceStart, move.count);
      destination.birds.push(...moving);

      if (move.completesBranch) {
        await wait(reducedMotion.matches ? 0 : 180 / speed);
        const fading = destination.birds
          .map(bird => birdElements.get(bird.id))
          .filter(Boolean);
        branchElements[move.destination].style.transition = `opacity ${360 / speed}ms ease`;
        branchElements[move.destination].style.opacity = "0";
        fading.forEach(element => {
          element.style.transition = `opacity ${360 / speed}ms ease`;
          element.style.opacity = "0";
        });
        await wait(reducedMotion.matches ? 0 : 380 / speed);
        if (runGeneration !== generation) return;
        destination.removed = true;
        fading.forEach(element => element.remove());
        destination.birds = [];
      }

      branchElements[move.source].classList.remove("active");
      branchElements[move.destination].classList.remove("active");
      stepIndex += 1;
      animating = false;
      updateStatus();
    }

    function completedCount() {
      return data.moves.slice(0, stepIndex).filter(move => move.completesBranch).length;
    }

    function updateStatus() {
      const total = data.moves.length;
      const eliminated = completedCount();
      if (stepIndex === 0) {
        status.innerHTML = total
          ? `准备开始，共 <strong>${total}</strong> 步，预计消除 <strong>${data.solution.eliminated}/${data.solution.target}</strong> 根树枝。`
          : "当前没有可展示的移动步骤。";
      } else if (stepIndex >= total) {
        status.innerHTML = data.solution.solved
          ? `播放完成：已消除 <strong>${eliminated}</strong> 根树枝，棋盘已完成。`
          : `最佳路径播放完成：已消除 <strong>${eliminated}/${data.solution.target}</strong> 根树枝。`;
      } else {
        const move = data.moves[stepIndex];
        status.innerHTML = `第 <strong>${stepIndex}/${total}</strong> 步完成；下一步 #${move.source} → #${move.destination}，移动 ${move.count} 只。`;
      }
      progress.style.width = `${total ? (stepIndex / total) * 100 : 0}%`;
      updateControls();
    }

    function updateControls() {
      previousButton.disabled = animating || stepIndex === 0;
      nextButton.disabled = animating || stepIndex >= data.moves.length;
      resetButton.disabled = animating || stepIndex === 0;
      playButton.disabled = data.moves.length === 0;
      playButton.textContent = playing ? "暂停" : (stepIndex >= data.moves.length ? "重播" : "播放");
    }

    async function play() {
      if (playing) {
        playing = false;
        updateControls();
        return;
      }
      if (stepIndex >= data.moves.length) resetBoard(0);
      playing = true;
      updateControls();
      while (playing && stepIndex < data.moves.length) {
        await animateMove(data.moves[stepIndex]);
        if (playing && stepIndex < data.moves.length) {
          await wait(reducedMotion.matches ? 0 : 260 / Number(speedSelect.value));
        }
      }
      playing = false;
      updateControls();
    }

    previousButton.addEventListener("click", () => resetBoard(Math.max(0, stepIndex - 1)));
    nextButton.addEventListener("click", async () => {
      if (stepIndex < data.moves.length) await animateMove(data.moves[stepIndex]);
    });
    resetButton.addEventListener("click", () => resetBoard(0));
    playButton.addEventListener("click", play);

    summary.textContent = `${data.branches.length} 根树枝 · ${data.typeCount} 类鸟 · `
      + `${data.solution.solved ? "完整解" : "当前最佳解"} · 搜索 ${data.solution.exploredStates} 个状态`;
    createBoardStructure();
    resetBoard(0);
  </script>
</body>
</html>
"""
