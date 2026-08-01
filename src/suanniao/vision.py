from __future__ import annotations

import json
import os
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image, ImageDraw

# Prevent scikit-learn from probing CPU topology in restricted environments.
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")
from scipy import ndimage  # noqa: E402
from scipy.optimize import linear_sum_assignment  # noqa: E402
from sklearn.cluster import KMeans  # noqa: E402
from sklearn.metrics import silhouette_score  # noqa: E402

from .model import BoardState

Side = Literal["left", "right"]


class RecognitionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DetectedBranch:
    side: Side
    branch_y: int
    bird_y: int
    slots: tuple[tuple[int, int], ...]  # base toward movable end
    birds: tuple[int, ...]

    def click_point(self) -> tuple[int, int]:
        if self.birds:
            return self.slots[len(self.birds) - 1]
        # Empty destination: tap the exposed wood just above its center.
        xs = [point[0] for point in self.slots]
        return round(sum(xs) / len(xs)), self.branch_y - 2


@dataclass(frozen=True, slots=True)
class RecognitionResult:
    state: BoardState
    branches: tuple[DetectedBranch, ...]
    type_count: int
    cluster_sizes: tuple[int, ...]
    silhouette: float | None
    image_size: tuple[int, int]


@dataclass(frozen=True, slots=True)
class _ClusterCandidate:
    type_count: int
    labels: np.ndarray
    raw_sizes: tuple[int, ...]
    capacity_targets: tuple[int, ...]
    sizes: tuple[int, ...]
    silhouette: float | None
    invalid: int
    quality: float
    constrained_iterations: int

    @property
    def valid(self) -> bool:
        return self.invalid == 0


@dataclass(frozen=True, slots=True)
class _PresenceEvidence:
    score: float
    foreground_fraction: float
    bird_fraction: float
    largest_component_fraction: float
    largest_component_height: float
    largest_component_fill: float


@dataclass(frozen=True, slots=True)
class _OccupancySelection:
    occupancies: tuple[int, ...]
    slot_clusters: tuple[tuple[int, ...], ...]
    method: str
    empty_cluster: int | None
    centers: tuple[tuple[float, ...], ...]
    mean_scores: tuple[float, ...]
    sizes: tuple[int, ...]


class BoardRecognizer:
    """Detect branches and cluster visually identical birds without training."""

    def __init__(
        self,
        *,
        capacity: int = 4,
        type_count: int | None = None,
        max_types: int = 10,
        presence_threshold: float = 0.20,
    ) -> None:
        self.capacity = capacity
        self.type_count = type_count
        self.max_types = max_types
        self.presence_threshold = presence_threshold

    def has_game_board(self, source: str | Path | Image.Image) -> bool:
        """Cheaply distinguish a normal board from a full-screen interruption."""

        image = (
            source.convert("RGB")
            if isinstance(source, Image.Image)
            else Image.open(source).convert("RGB")
        )
        rgb = np.asarray(image)
        if self._board_background_luminance(rgb) < 120.0:
            return False

        rows = self._detect_branch_rows(rgb)
        # Near the end of a level, all remaining branches can be on the same
        # side. Two detected branch rows are enough to distinguish that valid
        # late-game board from the branch-free interruption screens seen in
        # ads and level overlays.
        return sum(map(len, rows.values())) >= 2

    @staticmethod
    def _board_background_luminance(rgb: np.ndarray) -> float:
        """Sample sky-only areas that remain visible behind modal overlays."""

        height, width = rgb.shape[:2]
        regions = (
            rgb[
                round(0.12 * height) : round(0.22 * height),
                round(0.15 * width) : round(0.35 * width),
            ],
            rgb[
                round(0.12 * height) : round(0.22 * height),
                round(0.65 * width) : round(0.85 * width),
            ],
            rgb[
                round(0.22 * height) : round(0.30 * height),
                round(0.58 * width) : round(0.78 * width),
            ],
        )
        samples = [
            float(np.median(region.mean(axis=2)))
            for region in regions
            if region.size
        ]
        return float(np.median(samples)) if samples else 0.0

    def read(
        self,
        source: str | Path | Image.Image,
        *,
        debug_dir: str | Path | None = None,
    ) -> RecognitionResult:
        image = (
            source.convert("RGB")
            if isinstance(source, Image.Image)
            else Image.open(source).convert("RGB")
        )
        debug_path = Path(debug_dir) if debug_dir is not None else None
        if debug_path is not None:
            debug_path.mkdir(parents=True, exist_ok=True)

        rgb = np.asarray(image)
        height, width = rgb.shape[:2]
        background_color = self._background_color(rgb)
        rows = self._detect_branch_rows(rgb)
        layout_scale = self._layout_scale(rows, height)
        branch_bounds = {
            (side, branch_y): self._branch_x_bounds(rgb, side, branch_y)
            for side in ("left", "right")
            for branch_y in rows[side]
        }
        average_branch_length = self._average_branch_length(
            tuple(branch_bounds.values()),
            width,
            scale=layout_scale,
        )
        records: list[dict[str, object]] = []

        for side in ("left", "right"):
            for branch_y in rows[side]:
                bird_y = round(branch_y - 0.0195 * height * layout_scale)
                bounds = branch_bounds[(side, branch_y)]
                slots = self._slot_centers(
                    side,
                    bird_y,
                    width,
                    branch_bounds=bounds,
                    branch_length=average_branch_length,
                )
                presence_evidence = tuple(
                    self._presence_evidence(rgb, x, y, scale=layout_scale)
                    for x, y in slots
                )
                records.append(
                    {
                        "side": side,
                        "branch_y": branch_y,
                        "bird_y": bird_y,
                        "branch_bounds": bounds,
                        "branch_length": average_branch_length,
                        "slots": slots,
                        "layout_scale": layout_scale,
                        "presence_evidence": presence_evidence,
                    }
                )

        occupancy_selection = self._select_occupancies(
            tuple(
                record["presence_evidence"]  # type: ignore[misc]
                for record in records
            )
        )
        occupancies = occupancy_selection.occupancies
        for record, slot_clusters in zip(
            records, occupancy_selection.slot_clusters
        ):
            record["presence_clusters"] = slot_clusters
        features: list[np.ndarray] = []
        bird_crops: list[Image.Image] = []
        for record, occupied in zip(records, occupancies):
            evidence = record["presence_evidence"]
            raw_occupied = self._threshold_occupancy(
                tuple(item.score for item in evidence)  # type: ignore[union-attr]
            )
            feature_indexes: list[int] = []
            slots = record["slots"]
            side = record["side"]
            for slot_index, (x, y) in enumerate(slots[:occupied]):  # type: ignore[index]
                feature_indexes.append(len(features))
                crop = self._bird_crop(
                    image,
                    x,
                    y,
                    side,  # type: ignore[arg-type]
                    width,
                    height,
                    background_color,
                    has_outer_neighbor=slot_index < occupied - 1,
                    scale=layout_scale,
                )
                bird_crops.append(crop)
                features.append(
                    self._bird_feature_from_crop(crop, background_color)
                )
            record["raw_occupied"] = raw_occupied
            record["occupied"] = occupied
            record["features"] = feature_indexes

        if debug_path is not None:
            self._write_detection_debug(
                image,
                rows,
                records,
                bird_crops,
                background_color,
                debug_path,
            )

        if not records:
            if debug_path is not None:
                self._write_debug_report(
                    image,
                    rows,
                    records,
                    bird_crops,
                    occupancy_selection,
                    (),
                    None,
                    debug_path,
                )
            raise RecognitionError(
                self._with_debug_hint(
                    "No branches were detected in the screenshot", debug_path
                )
            )

        if not features:
            branches = tuple(
                DetectedBranch(
                    side=record["side"],  # type: ignore[arg-type]
                    branch_y=record["branch_y"],  # type: ignore[arg-type]
                    bird_y=record["bird_y"],  # type: ignore[arg-type]
                    slots=record["slots"],  # type: ignore[arg-type]
                    birds=(),
                )
                for record in records
            )
            result = RecognitionResult(
                BoardState(tuple(() for _ in branches), self.capacity),
                branches,
                0,
                (),
                None,
                image.size,
            )
            if debug_path is not None:
                self._write_debug_report(
                    image,
                    rows,
                    records,
                    bird_crops,
                    occupancy_selection,
                    (),
                    None,
                    debug_path,
                )
            return result

        if len(features) % self.capacity:
            if debug_path is not None:
                self._write_debug_report(
                    image,
                    rows,
                    records,
                    bird_crops,
                    occupancy_selection,
                    (),
                    None,
                    debug_path,
                )
            raise RecognitionError(
                self._with_debug_hint(
                    f"Detected {len(features)} birds, not a multiple of "
                    f"{self.capacity}",
                    debug_path,
                )
            )

        matrix = np.vstack(features)
        candidates = self._cluster_candidates(matrix)
        selected = self._select_cluster(candidates)
        if debug_path is not None:
            self._write_debug_report(
                image,
                rows,
                records,
                bird_crops,
                occupancy_selection,
                candidates,
                selected,
                debug_path,
            )

        if selected is None:
            raise RecognitionError(
                self._with_debug_hint(
                    "Could not split the detected birds into groups whose sizes are "
                    f"multiples of {self.capacity}; pass --types if automatic "
                    "clustering is ambiguous",
                    debug_path,
                )
            )
        if not selected.valid:
            raise RecognitionError(
                self._with_debug_hint(
                    f"Cluster sizes {selected.sizes} are inconsistent with capacity "
                    f"{self.capacity}",
                    debug_path,
                )
            )

        branches_list: list[DetectedBranch] = []
        for record in records:
            indexes = record["features"]
            birds = tuple(
                int(selected.labels[index]) for index in indexes
            )  # type: ignore[union-attr]
            branches_list.append(
                DetectedBranch(
                    side=record["side"],  # type: ignore[arg-type]
                    branch_y=record["branch_y"],  # type: ignore[arg-type]
                    bird_y=record["bird_y"],  # type: ignore[arg-type]
                    slots=record["slots"],  # type: ignore[arg-type]
                    birds=birds,
                )
            )

        state = BoardState(tuple(branch.birds for branch in branches_list), self.capacity)
        return RecognitionResult(
            state,
            tuple(branches_list),
            selected.type_count,
            selected.sizes,
            selected.silhouette,
            image.size,
        )

    @staticmethod
    def _wood_mask(rgb: np.ndarray) -> np.ndarray:
        red = rgb[:, :, 0].astype(np.int16)
        green = rgb[:, :, 1].astype(np.int16)
        blue = rgb[:, :, 2].astype(np.int16)
        return (
            (red > 55)
            & (red < 205)
            & (green > 22)
            & (green < 135)
            & (blue < 95)
            & ((red - green) > 22)
        )

    def _detect_branch_rows(self, rgb: np.ndarray) -> dict[Side, list[int]]:
        height, width = rgb.shape[:2]
        wood = self._wood_mask(rgb)

        result: dict[Side, list[int]] = {"left": [], "right": []}
        ranges = {
            "left": (0, round(0.38 * width)),
            "right": (round(0.65 * width), width),
        }
        kernel_size = max(3, round(height / 300))
        kernel = np.ones(kernel_size, dtype=float) / kernel_size
        min_y = round(0.24 * height)
        max_y = round(0.84 * height)
        threshold = 0.11 * width

        for side, (start_x, end_x) in ranges.items():
            score = wood[:, start_x:end_x].sum(axis=1)
            smooth = np.convolve(score, kernel, mode="same")
            candidates = np.where(
                (smooth > threshold)
                & (np.arange(height) >= min_y)
                & (np.arange(height) <= max_y)
            )[0]

            groups: list[list[int]] = []
            for y in candidates:
                if not groups or y > groups[-1][-1] + 1:
                    groups.append([int(y)])
                else:
                    groups[-1].append(int(y))

            rows = [max(group, key=lambda y: smooth[y]) for group in groups]
            min_spacing = round(0.03 * height)
            filtered: list[int] = []
            for row in rows:
                if not filtered or row - filtered[-1] >= min_spacing:
                    filtered.append(row)
                elif smooth[row] > smooth[filtered[-1]]:
                    filtered[-1] = row
            result[side] = filtered

        return result

    @staticmethod
    def _branch_x_bounds(
        rgb: np.ndarray,
        side: Side,
        branch_y: int,
    ) -> tuple[int, int]:
        height, width = rgb.shape[:2]
        midpoint = width // 2
        start_x, end_x = (0, midpoint) if side == "left" else (midpoint, width)
        y_radius = max(3, round(height * 0.003))
        top = max(0, branch_y - y_radius)
        bottom = min(height, branch_y + y_radius + 1)
        wood = BoardRecognizer._wood_mask(rgb[top:bottom, start_x:end_x])
        column_score = wood.sum(axis=0)
        threshold = max(1, round((bottom - top) * 0.25))
        columns = np.flatnonzero(column_score >= threshold)
        if len(columns) == 0:
            fallback_length = min(round(0.38 * width), midpoint - 1)
            return (
                (0, fallback_length)
                if side == "left"
                else (width - fallback_length - 1, width - 1)
            )

        max_gap = max(2, round(width * 0.008))
        groups: list[list[int]] = [[int(columns[0])]]
        for column in columns[1:]:
            value = int(column)
            if value - groups[-1][-1] <= max_gap:
                groups[-1].append(value)
            else:
                groups.append([value])

        edge_tolerance = max_gap * 2
        if side == "left":
            edge_groups = [group for group in groups if group[0] <= edge_tolerance]
        else:
            edge_groups = [
                group
                for group in groups
                if group[-1] >= (end_x - start_x - 1) - edge_tolerance
            ]
        branch_group = max(edge_groups or groups, key=len)
        first_x = start_x + branch_group[0]
        last_x = start_x + branch_group[-1]

        max_length = max(1, (width - 1) // 2)
        if last_x - first_x > max_length:
            if side == "left":
                last_x = first_x + max_length
            else:
                first_x = last_x - max_length
        return first_x, last_x

    def _slot_centers(
        self,
        side: Side,
        bird_y: int,
        width: int,
        *,
        branch_bounds: tuple[int, int],
        branch_length: float,
    ) -> tuple[tuple[int, int], ...]:
        base = branch_bounds[0] if side == "left" else branch_bounds[1]
        direction = 1 if side == "left" else -1
        segment_length = branch_length / self.capacity
        return tuple(
            (
                min(
                    max(
                        round(
                            base
                            + direction * segment_length * (index + 0.5)
                        ),
                        0,
                    ),
                    width - 1,
                ),
                bird_y,
            )
            for index in range(self.capacity)
        )

    @staticmethod
    def _average_branch_length(
        bounds: tuple[tuple[int, int], ...],
        width: int,
        *,
        scale: float = 1.0,
    ) -> float:
        lengths = tuple(
            end_x - start_x
            for start_x, end_x in bounds
            if end_x > start_x
        )
        if lengths:
            return float(np.mean(lengths))
        return 0.3292 * width * scale

    @staticmethod
    def _layout_scale(rows: dict[Side, list[int]], height: int) -> float:
        """Infer the game's discrete sprite zoom from same-side branch spacing."""

        spacings = [
            following - previous
            for side_rows in rows.values()
            for previous, following in zip(side_rows, side_rows[1:])
        ]
        if not spacings:
            return 1.0
        median_spacing = float(np.median(spacings))
        nominal_spacing = 0.0468 * height
        return min(1.35, max(0.90, median_spacing / nominal_spacing))

    def _presence_evidence(
        self,
        rgb: np.ndarray,
        x: int,
        y: int,
        *,
        scale: float = 1.0,
    ) -> _PresenceEvidence:
        height, width = rgb.shape[:2]
        half_width = max(12, round(width * 0.032 * scale))
        top = max(0, y - round(height * 0.022 * scale))
        bottom = min(height, y + round(height * 0.008 * scale))
        left = max(0, x - half_width)
        right = min(width, x + half_width + 1)
        crop_rgb = rgb[top:bottom, left:right]
        crop = crop_rgb.astype(float)

        bg_left = round(0.43 * width)
        bg_right = round(0.57 * width)
        bg_top = max(0, top)
        bg_bottom = min(height, bottom)
        background = np.median(
            rgb[bg_top:bg_bottom, bg_left:bg_right].astype(float), axis=(0, 1)
        )
        distance = np.linalg.norm(crop - background, axis=2)
        foreground = distance > 45.0
        bird_mask = foreground & ~self._wood_mask(crop_rgb)

        labels, component_count = ndimage.label(
            bird_mask,
            structure=np.ones((3, 3), dtype=int),
        )
        largest_area = 0
        largest_height = 0
        largest_fill = 0.0
        if component_count:
            component_sizes = np.bincount(labels.ravel())[1:]
            largest_label = int(component_sizes.argmax()) + 1
            largest_area = int(component_sizes[largest_label - 1])
            component_rows, component_columns = np.where(labels == largest_label)
            if len(component_rows):
                largest_height = int(component_rows.max() - component_rows.min() + 1)
                largest_width = int(
                    component_columns.max() - component_columns.min() + 1
                )
                largest_fill = largest_area / max(largest_width * largest_height, 1)

        area = max(int(bird_mask.size), 1)
        roi_height = max(int(bird_mask.shape[0]), 1)
        foreground_fraction = float(foreground.mean())
        bird_fraction = float(bird_mask.mean())
        largest_component_fraction = largest_area / area
        largest_component_height = largest_height / roi_height
        largest_component_shape = largest_component_height * largest_fill
        score = (
            0.55 * bird_fraction
            + 0.25 * largest_component_fraction
            + 0.20 * largest_component_shape
        )
        return _PresenceEvidence(
            score,
            foreground_fraction,
            bird_fraction,
            largest_component_fraction,
            largest_component_height,
            largest_fill,
        )

    def _threshold_occupancy(self, scores: tuple[float, ...]) -> int:
        occupied = 0
        for score in scores:
            if score < self.presence_threshold:
                break
            occupied += 1
        return occupied

    @staticmethod
    def _presence_vector(evidence: _PresenceEvidence) -> tuple[float, ...]:
        return (
            evidence.score,
            evidence.foreground_fraction,
            evidence.bird_fraction,
            evidence.largest_component_fraction,
            evidence.largest_component_height,
            evidence.largest_component_fill,
        )

    def _threshold_occupancy_selection(
        self,
        evidence_rows: tuple[tuple[_PresenceEvidence, ...], ...],
    ) -> _OccupancySelection:
        occupancies = tuple(
            self._threshold_occupancy(tuple(item.score for item in row))
            for row in evidence_rows
        )
        slot_clusters = tuple(
            tuple(1 if item.score >= self.presence_threshold else 0 for item in row)
            for row in evidence_rows
        )
        return _OccupancySelection(
            occupancies,
            slot_clusters,
            "threshold-fallback",
            0,
            (),
            (),
            (),
        )

    def _capacity_constrained_occupancies(
        self,
        cost_rows: list[list[float]],
    ) -> tuple[int, ...]:
        states: dict[int, tuple[float, tuple[int, ...]]] = {0: (0.0, ())}
        for costs in cost_rows:
            next_states: dict[int, tuple[float, tuple[int, ...]]] = {}
            for total, (previous_cost, previous_occupancies) in states.items():
                for occupied, row_cost in enumerate(costs):
                    next_total = total + occupied
                    candidate = (
                        previous_cost + row_cost,
                        previous_occupancies + (occupied,),
                    )
                    existing = next_states.get(next_total)
                    if existing is None or candidate[0] < existing[0]:
                        next_states[next_total] = candidate
            states = next_states

        capacity = max(self.capacity, 1)
        valid = [
            candidate
            for total, candidate in states.items()
            if total % capacity == 0
        ]
        return min(valid, key=lambda candidate: candidate[0])[1]

    def _select_occupancies(
        self,
        evidence_rows: tuple[tuple[_PresenceEvidence, ...], ...],
    ) -> _OccupancySelection:
        """Cluster slots, then choose capacity-valid occupied prefixes."""

        if not evidence_rows:
            return _OccupancySelection((), (), "no-slots", None, (), (), ())

        flat_evidence = tuple(item for row in evidence_rows for item in row)
        matrix = np.asarray(
            [self._presence_vector(item) for item in flat_evidence],
            dtype=float,
        )
        if len(matrix) < 2 or len(np.unique(matrix, axis=0)) < 2:
            return self._threshold_occupancy_selection(evidence_rows)

        model = KMeans(n_clusters=2, n_init=20, random_state=0)
        labels = model.fit_predict(matrix)
        centers = tuple(
            tuple(float(value) for value in center)
            for center in model.cluster_centers_
        )
        sizes = tuple(int((labels == cluster).sum()) for cluster in range(2))
        mean_scores = tuple(
            float(
                np.mean(
                    [
                        evidence.score
                        for evidence, label in zip(flat_evidence, labels)
                        if label == cluster
                    ]
                )
            )
            for cluster in range(2)
        )
        empty_cluster = int(np.argmin(mean_scores))
        occupied_cluster = 1 - empty_cluster
        separation = mean_scores[occupied_cluster] - mean_scores[empty_cluster]
        distinct_empty_cluster = (
            mean_scores[empty_cluster] < self.presence_threshold
            and mean_scores[occupied_cluster] >= self.presence_threshold + 0.15
            and separation >= 0.20
        )
        if not distinct_empty_cluster:
            return self._threshold_occupancy_selection(evidence_rows)

        label_rows: list[tuple[int, ...]] = []
        cost_rows: list[list[float]] = []
        cursor = 0
        for row in evidence_rows:
            row_length = len(row)
            row_matrix = matrix[cursor : cursor + row_length]
            row_labels = tuple(
                int(label) for label in labels[cursor : cursor + row_length]
            )
            label_rows.append(row_labels)
            cursor += row_length

            costs = []
            for occupied in range(row_length + 1):
                expected_clusters = (
                    (occupied_cluster,) * occupied
                    + (empty_cluster,) * (row_length - occupied)
                )
                cost = sum(
                    float(np.sum((vector - model.cluster_centers_[cluster]) ** 2))
                    for vector, cluster in zip(row_matrix, expected_clusters)
                )
                costs.append(cost)
            cost_rows.append(costs)

        occupancies = self._capacity_constrained_occupancies(cost_rows)

        return _OccupancySelection(
            occupancies,
            tuple(label_rows),
            "two-cluster-presence",
            empty_cluster,
            centers,
            mean_scores,
            sizes,
        )

    @staticmethod
    def _bird_crop_box(
        x: int,
        y: int,
        side: Side,
        width: int,
        height: int,
        *,
        has_outer_neighbor: bool,
        scale: float = 1.0,
    ) -> tuple[int, int, int, int]:
        # The detected slot point sits slightly toward the screen edge relative
        # to the most useful body region. Shift every crop toward the center of
        # the screen. Packed birds still need a smaller counter-shift toward the
        # fixed/base end so the outer neighbor does not dominate the crop.
        direction = 1 if side == "left" else -1
        inward_shift = 0.006 * width * scale
        overlap_compensation = (
            0.002 * width * scale if has_outer_neighbor else 0.0
        )
        center_x = round(x + direction * (inward_shift - overlap_compensation))
        half_width = round(0.040 * width * scale)
        half_height = round(0.021 * height * scale)
        # The fixed/base slot is close to the screen edge. Clamp the center so
        # the full crop remains inside the screenshot: left crops move right
        # and right crops move left by the minimum additional amount required.
        center_x = min(max(center_x, half_width), width - half_width - 1)
        return (
            center_x - half_width,
            y - half_height,
            center_x + half_width + 1,
            y + half_height + 1,
        )

    @staticmethod
    def _bird_crop(
        image: Image.Image,
        x: int,
        y: int,
        side: Side,
        width: int,
        height: int,
        background_color: np.ndarray,
        *,
        has_outer_neighbor: bool,
        scale: float = 1.0,
    ) -> Image.Image:
        crop_box = BoardRecognizer._bird_crop_box(
            x,
            y,
            side,
            width,
            height,
            has_outer_neighbor=has_outer_neighbor,
            scale=scale,
        )
        left, top, right, bottom = crop_box
        crop_width = right - left
        crop_height = bottom - top
        fill = tuple(int(round(channel * 255)) for channel in background_color)
        crop = Image.new("RGB", (crop_width, crop_height), fill)
        source_box = (
            max(0, left),
            max(0, top),
            min(width, right),
            min(height, bottom),
        )
        source_crop = image.crop(source_box)
        crop.paste(
            source_crop,
            (
                max(0, -left),
                max(0, -top),
            ),
        )
        crop = crop.resize((49, 62), Image.Resampling.BILINEAR)
        if side == "right":
            crop = crop.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        return crop

    @staticmethod
    def _background_color(rgb: np.ndarray) -> np.ndarray:
        height, width = rgb.shape[:2]
        sample = rgb[
            round(0.24 * height) : round(0.84 * height),
            round(0.43 * width) : round(0.57 * width),
        ]
        return np.median(sample.astype(float), axis=(0, 1)) / 255.0

    @staticmethod
    def _bird_feature_mask(
        crop: Image.Image, background_color: np.ndarray
    ) -> np.ndarray:
        pixels = np.asarray(crop).astype(float) / 255.0
        height, width = pixels.shape[:2]
        yy, xx = np.mgrid[0:height, 0:width]
        # _bird_crop() mirrors right-side branches, so the branch's fixed/base
        # end is always on the left of the normalized crop. Packed birds overlap
        # from the movable end on the right. Bias the feature region toward the
        # base-side body instead of centering it between two neighboring birds.
        # Besides reducing neighbor contamination, this retains the body pattern
        # that distinguishes visually similar sprites such as the cow and the
        # orange bird.
        central = (
            ((xx - width * 0.36) / (width * 0.25)) ** 2
            + ((yy - height * 0.40) / (height * 0.32)) ** 2
            < 1.0
        )
        foreground = np.linalg.norm(pixels - background_color, axis=2) > 0.10
        return central & foreground

    @staticmethod
    def _bird_feature_from_crop(
        crop: Image.Image, background_color: np.ndarray
    ) -> np.ndarray:
        pixels = np.asarray(crop).astype(float) / 255.0
        hsv = np.asarray(crop.convert("HSV")).astype(float) / 255.0
        mask = BoardRecognizer._bird_feature_mask(crop, background_color)
        denominator = max(int(mask.sum()), 1)

        hue = hsv[:, :, 0]
        saturation = hsv[:, :, 1]
        value = hsv[:, :, 2]

        def ratio(condition: np.ndarray) -> float:
            return float((condition & mask).sum() / denominator)

        # Semantic color proportions are robust to partial occlusion while
        # separating the sprites used by the game: cow/orange, parrot/green,
        # purple/pink, yellow, and dark gray.
        return np.asarray(
            [
                ratio(value < 0.32),
                ratio((saturation < 0.18) & (value > 0.75)),
                ratio(
                    (saturation < 0.28)
                    & (value >= 0.32)
                    & (value <= 0.75)
                ),
                ratio(((hue < 0.04) | (hue > 0.94)) & (saturation > 0.30)),
                ratio(
                    (hue >= 0.04) & (hue < 0.10) & (saturation > 0.30)
                ),
                ratio(
                    (hue >= 0.10) & (hue < 0.19) & (saturation > 0.30)
                ),
                ratio(
                    (hue >= 0.19) & (hue < 0.48) & (saturation > 0.30)
                ),
                ratio(
                    (hue >= 0.48) & (hue < 0.72) & (saturation > 0.30)
                ),
                ratio(
                    (hue >= 0.72) & (hue < 0.94) & (saturation > 0.30)
                ),
            ],
            dtype=float,
        )

    def _cluster_candidates(
        self, matrix: np.ndarray
    ) -> tuple[_ClusterCandidate, ...]:
        bird_count = len(matrix)
        if self.type_count is not None:
            type_counts = [self.type_count]
        else:
            minimum_types = 1 if bird_count <= self.capacity else 2
            type_counts = list(
                range(
                    minimum_types,
                    min(self.max_types, bird_count // self.capacity) + 1,
                )
            )

        candidates: list[_ClusterCandidate] = []
        for type_count in type_counts:
            if type_count < 1 or type_count * self.capacity > bird_count:
                continue
            if type_count == 1:
                raw_labels = np.zeros(bird_count, dtype=int)
                centers = matrix.mean(axis=0, keepdims=True)
            else:
                model = KMeans(n_clusters=type_count, n_init=20, random_state=0)
                raw_labels = model.fit_predict(matrix)
                centers = model.cluster_centers_

            raw_sizes = tuple(
                int(value)
                for value in np.bincount(raw_labels, minlength=type_count)
            )
            capacity_targets = self._capacity_targets(matrix, centers, raw_sizes)
            labels, constrained_iterations = self._constrained_assignment(
                matrix, centers, capacity_targets
            )
            sizes = tuple(
                int(value) for value in np.bincount(labels, minlength=type_count)
            )
            if type_count == 1:
                silhouette = None
            else:
                silhouette = float(silhouette_score(matrix, labels))

            invalid = sum(size % self.capacity for size in sizes)
            quality = (silhouette if silhouette is not None else 1.0) - 0.002 * type_count
            candidates.append(
                _ClusterCandidate(
                    type_count,
                    labels,
                    raw_sizes,
                    capacity_targets,
                    sizes,
                    silhouette,
                    invalid,
                    quality,
                    constrained_iterations,
                )
            )
        return tuple(candidates)

    def _capacity_target_candidates(
        self,
        raw_sizes: tuple[int, ...],
        *,
        limit: int = 32,
    ) -> tuple[tuple[int, ...], ...]:
        """Return the best size-based multiple-of-capacity target candidates."""

        total = sum(raw_sizes)
        total_units = total // self.capacity
        cluster_count = len(raw_sizes)
        # used units -> [(sum of squared changes, absolute changes, path), ...]
        states: dict[int, list[tuple[int, int, tuple[int, ...]]]] = {
            0: [(0, 0, ())]
        }
        for index, raw_size in enumerate(raw_sizes):
            remaining_clusters = cluster_count - index - 1
            next_states: dict[int, list[tuple[int, int, tuple[int, ...]]]] = {}
            for used_units, options in states.items():
                max_units = total_units - used_units - remaining_clusters
                for squared_cost, absolute_cost, path in options:
                    for units in range(1, max_units + 1):
                        size = units * self.capacity
                        difference = size - raw_size
                        new_used = used_units + units
                        next_states.setdefault(new_used, []).append(
                            (
                                squared_cost + difference * difference,
                                absolute_cost + abs(difference),
                                path + (size,),
                            )
                        )
            states = {
                used: sorted(options)[:limit]
                for used, options in next_states.items()
            }
        return tuple(option[2] for option in states[total_units])

    def _capacity_targets(
        self,
        matrix: np.ndarray,
        centers: np.ndarray,
        raw_sizes: tuple[int, ...],
    ) -> tuple[int, ...]:
        """Select target sizes using both raw counts and feature assignment cost."""

        distances = ((matrix[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        best: tuple[float, int, int, tuple[int, ...]] | None = None
        for capacities in self._capacity_target_candidates(raw_sizes):
            slot_clusters = np.repeat(np.arange(len(capacities)), capacities)
            row_indexes, slot_indexes = linear_sum_assignment(
                distances[:, slot_clusters]
            )
            assignment_cost = float(
                distances[row_indexes, slot_clusters[slot_indexes]].sum()
            )
            differences = tuple(
                capacity - raw
                for capacity, raw in zip(capacities, raw_sizes)
            )
            candidate = (
                assignment_cost,
                sum(difference * difference for difference in differences),
                sum(abs(difference) for difference in differences),
                capacities,
            )
            if best is None or candidate < best:
                best = candidate
        if best is None:
            raise ValueError("No valid capacity target allocation")
        return best[3]

    @staticmethod
    def _constrained_assignment(
        matrix: np.ndarray,
        initial_centers: np.ndarray,
        capacities: tuple[int, ...],
        max_iterations: int = 20,
    ) -> tuple[np.ndarray, int]:
        """Assign samples optimally while giving each center exactly its capacity."""
        centers = initial_centers.copy()
        slot_clusters = np.repeat(np.arange(len(capacities)), capacities)
        previous: np.ndarray | None = None

        for iteration in range(1, max_iterations + 1):
            distances = ((matrix[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
            row_indexes, slot_indexes = linear_sum_assignment(
                distances[:, slot_clusters]
            )
            labels = np.empty(len(matrix), dtype=int)
            labels[row_indexes] = slot_clusters[slot_indexes]
            if previous is not None and np.array_equal(labels, previous):
                return labels, iteration
            previous = labels
            centers = np.vstack(
                [
                    matrix[labels == cluster].mean(axis=0)
                    for cluster in range(len(capacities))
                ]
            )

        labels = (
            previous
            if previous is not None
            else np.zeros(len(matrix), dtype=int)
        )
        return labels, max_iterations

    def _select_cluster(
        self, candidates: tuple[_ClusterCandidate, ...]
    ) -> _ClusterCandidate | None:
        eligible = (
            candidates
            if self.type_count is not None
            else tuple(candidate for candidate in candidates if candidate.valid)
        )
        return max(eligible, key=lambda candidate: candidate.quality, default=None)

    @staticmethod
    def _with_debug_hint(message: str, debug_path: Path | None) -> str:
        if debug_path is None:
            return message
        return f"{message}; debug report: {debug_path / 'index.html'}"

    def _write_detection_debug(
        self,
        image: Image.Image,
        rows: dict[Side, list[int]],
        records: list[dict[str, object]],
        bird_crops: list[Image.Image],
        background_color: np.ndarray,
        debug_path: Path,
    ) -> None:
        annotated = image.copy()
        draw = ImageDraw.Draw(annotated)
        width, _height = image.size
        rgb = np.asarray(image)
        line_width = max(3, round(width * 0.003))
        radius = max(9, round(width * 0.009))

        for side, branch_rows in rows.items():
            for branch_y in branch_rows:
                start_x, end_x = self._branch_x_bounds(rgb, side, branch_y)
                draw.line(
                    (start_x, branch_y, end_x, branch_y),
                    fill=(0, 190, 255),
                    width=line_width,
                )

        for branch_index, record in enumerate(records):
            slots = record["slots"]
            occupied = int(record["occupied"])  # type: ignore[arg-type]
            feature_indexes = record["features"]
            for slot_index, (x, y) in enumerate(slots):  # type: ignore[union-attr]
                is_occupied = slot_index < occupied
                color = (25, 190, 80) if is_occupied else (235, 70, 70)
                draw.ellipse(
                    (x - radius, y - radius, x + radius, y + radius),
                    outline=color,
                    width=line_width,
                )
                label = (
                    f"B{feature_indexes[slot_index]}"  # type: ignore[index]
                    if is_occupied
                    else f"E{branch_index}:{slot_index}"
                )
                draw.text((x - radius, y + radius + 2), label, fill=color)
                if is_occupied:
                    crop_box = self._bird_crop_box(
                        x,
                        y,
                        record["side"],  # type: ignore[arg-type]
                        image.width,
                        image.height,
                        has_outer_neighbor=slot_index < occupied - 1,
                        scale=float(record["layout_scale"]),
                    )
                    draw.rectangle(crop_box, outline=(255, 190, 35), width=line_width)

        annotated.save(debug_path / "01-detection.png")
        birds_path = debug_path / "birds"
        birds_path.mkdir(parents=True, exist_ok=True)
        for index, crop in enumerate(bird_crops):
            crop.save(birds_path / f"bird-{index:03d}.png")
        masks_path = debug_path / "feature-masks"
        masks_path.mkdir(parents=True, exist_ok=True)
        fill = tuple(int(round(channel * 255)) for channel in background_color)
        for index, crop in enumerate(bird_crops):
            mask = self._bird_feature_mask(crop, background_color)
            masked = Image.new("RGB", crop.size, fill)
            masked.paste(crop, mask=Image.fromarray(mask.astype(np.uint8) * 255))
            masked.save(masks_path / f"bird-{index:03d}.png")

    def _write_debug_report(
        self,
        image: Image.Image,
        rows: dict[Side, list[int]],
        records: list[dict[str, object]],
        bird_crops: list[Image.Image],
        occupancy_selection: _OccupancySelection,
        candidates: tuple[_ClusterCandidate, ...],
        selected: _ClusterCandidate | None,
        debug_path: Path,
    ) -> None:
        background_color = self._background_color(np.asarray(image))
        fill = tuple(int(round(channel * 255)) for channel in background_color)
        feature_crops: list[Image.Image] = []
        for crop in bird_crops:
            mask = self._bird_feature_mask(crop, background_color)
            masked = Image.new("RGB", crop.size, fill)
            masked.paste(crop, mask=Image.fromarray(mask.astype(np.uint8) * 255))
            feature_crops.append(masked)

        candidate_files: dict[int, str] = {}
        for candidate in candidates:
            filename = f"clusters-k{candidate.type_count:02d}.png"
            candidate_files[candidate.type_count] = filename
            self._write_cluster_montage(candidate, feature_crops, debug_path / filename)

        branches_payload = []
        for index, record in enumerate(records):
            slots = record["slots"]
            evidence = record["presence_evidence"]
            presence_clusters = record["presence_clusters"]
            occupied = int(record["occupied"])  # type: ignore[arg-type]
            branches_payload.append(
                {
                    "index": index,
                    "side": record["side"],
                    "branch_y": record["branch_y"],
                    "bird_y": record["bird_y"],
                    "branch_bounds": record["branch_bounds"],
                    "branch_length": round(float(record["branch_length"]), 3),
                    "raw_occupied": record["raw_occupied"],
                    "occupied": occupied,
                    "slots": [
                        {
                            "index": slot_index,
                            "point": point,
                            "presence_cluster": int(
                                presence_clusters[slot_index]  # type: ignore[index]
                            ),
                            "presence_score": round(
                                float(evidence[slot_index].score), 6  # type: ignore[index]
                            ),
                            "foreground_fraction": round(
                                float(evidence[slot_index].foreground_fraction),  # type: ignore[index]
                                6,
                            ),
                            "bird_fraction": round(
                                float(evidence[slot_index].bird_fraction), 6  # type: ignore[index]
                            ),
                            "largest_component_fraction": round(
                                float(
                                    evidence[  # type: ignore[index]
                                        slot_index
                                    ].largest_component_fraction
                                ),
                                6,
                            ),
                            "largest_component_height": round(
                                float(
                                    evidence[  # type: ignore[index]
                                        slot_index
                                    ].largest_component_height
                                ),
                                6,
                            ),
                            "largest_component_fill": round(
                                float(
                                    evidence[  # type: ignore[index]
                                        slot_index
                                    ].largest_component_fill
                                ),
                                6,
                            ),
                            "crop_box": (
                                self._bird_crop_box(
                                    point[0],
                                    point[1],
                                    record["side"],  # type: ignore[arg-type]
                                    image.width,
                                    image.height,
                                    has_outer_neighbor=slot_index < occupied - 1,
                                    scale=float(record["layout_scale"]),
                                )
                                if slot_index < occupied
                                else None
                            ),
                            "present": slot_index < occupied,
                        }
                        for slot_index, point in enumerate(slots)  # type: ignore[arg-type]
                    ],
                }
            )

        report = {
            "clustering_algorithm": "capacity-constrained-kmeans",
            "image_size": image.size,
            "capacity": self.capacity,
            "layout_scale": (
                float(records[0]["layout_scale"]) if records else 1.0
            ),
            "average_branch_length": (
                round(float(records[0]["branch_length"]), 3)
                if records
                else None
            ),
            "presence_threshold": self.presence_threshold,
            "occupancy_constraint": (
                "two-cluster-presence,prefix-per-branch,total-capacity-multiple"
            ),
            "presence_clustering": {
                "method": occupancy_selection.method,
                "empty_cluster": occupancy_selection.empty_cluster,
                "centers": occupancy_selection.centers,
                "mean_scores": occupancy_selection.mean_scores,
                "sizes": occupancy_selection.sizes,
            },
            "branch_rows": rows,
            "detected_branches": len(records),
            "detected_birds": len(bird_crops),
            "selected_type_count": selected.type_count if selected is not None else None,
            "branches": branches_payload,
            "candidates": [
                {
                    "type_count": candidate.type_count,
                    "raw_cluster_sizes": candidate.raw_sizes,
                    "capacity_targets": candidate.capacity_targets,
                    "cluster_sizes": candidate.sizes,
                    "remainders": tuple(
                        size % self.capacity for size in candidate.sizes
                    ),
                    "valid": candidate.valid,
                    "invalid_score": candidate.invalid,
                    "silhouette": candidate.silhouette,
                    "quality": candidate.quality,
                    "constrained_iterations": candidate.constrained_iterations,
                    "selected": candidate is selected,
                    "image": candidate_files[candidate.type_count],
                }
                for candidate in candidates
            ],
        }
        (debug_path / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (debug_path / "index.html").write_text(
            self._debug_html(report, len(bird_crops)), encoding="utf-8"
        )

    def _write_cluster_montage(
        self,
        candidate: _ClusterCandidate,
        bird_crops: list[Image.Image],
        destination: Path,
    ) -> None:
        members = [
            [
                index
                for index, label in enumerate(candidate.labels)
                if int(label) == group
            ]
            for group in range(candidate.type_count)
        ]
        cell_width = 58
        row_height = 88
        label_width = 125
        width = max(
            620,
            label_width
            + max((len(group) for group in members), default=0) * cell_width
            + 20,
        )
        height = 48 + max(1, candidate.type_count) * row_height
        canvas = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(canvas)
        silhouette = (
            f"{candidate.silhouette:.4f}"
            if candidate.silhouette is not None
            else "n/a"
        )
        draw.text(
            (12, 12),
            f"k={candidate.type_count}  raw={candidate.raw_sizes}  "
            f"constrained={candidate.sizes}  "
            f"silhouette={silhouette}  valid={candidate.valid}",
            fill=(20, 20, 20),
        )
        for group, indexes in enumerate(members):
            top = 44 + group * row_height
            remainder = len(indexes) % self.capacity
            color = (20, 125, 55) if remainder == 0 else (190, 45, 45)
            draw.text(
                (12, top + 8),
                f"{self._cluster_name(group)} size={len(indexes)} r={remainder}",
                fill=color,
            )
            for column, bird_index in enumerate(indexes):
                left = label_width + column * cell_width
                canvas.paste(bird_crops[bird_index], (left, top))
                draw.text((left, top + 64), f"B{bird_index}", fill=(20, 20, 20))
        canvas.save(destination)

    @staticmethod
    def _cluster_name(index: int) -> str:
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        return alphabet[index] if index < len(alphabet) else str(index)

    @staticmethod
    def _debug_html(report: dict[str, object], bird_count: int) -> str:
        cards = []
        for candidate in report["candidates"]:  # type: ignore[union-attr]
            selected_class = " selected" if candidate["selected"] else ""
            selected_label = "（已选择）" if candidate["selected"] else ""
            cards.append(
                f'<section class="card{selected_class}">'
                f'<h2>k={candidate["type_count"]}{selected_label}</h2>'
                f'<p>raw={escape(str(candidate["raw_cluster_sizes"]))}；'
                f'target={escape(str(candidate["capacity_targets"]))}；'
                f'final={escape(str(candidate["cluster_sizes"]))}；'
                f'remainders={escape(str(candidate["remainders"]))}；'
                f'silhouette={escape(str(candidate["silhouette"]))}；'
                f'iterations={candidate["constrained_iterations"]}；'
                f'valid={candidate["valid"]}</p>'
                f'<a href="{candidate["image"]}">'
                f'<img src="{candidate["image"]}" '
                f'alt="k={candidate["type_count"]}"></a></section>'
            )
        bird_images = "".join(
            f'<figure><div class="bird-pair">'
            f'<img src="birds/bird-{index:03d}.png" alt="B{index} crop">'
            f'<img src="feature-masks/bird-{index:03d}.png" '
            f'alt="B{index} feature mask"></div>'
            f'<figcaption>B{index}</figcaption></figure>'
            for index in range(bird_count)
        )
        candidate_html = "".join(cards) if cards else "<p>没有可计算的聚类候选。</p>"
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>算鸟聚类调试报告</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:24px;background:#f5f6f8;color:#18212b}}
main{{max-width:1200px;margin:auto}} .card{{background:white;border-radius:12px;padding:16px;margin:18px 0;box-shadow:0 2px 10px #0001}}
.selected{{outline:3px solid #2ca96b}} img{{max-width:100%;height:auto}} .birds{{display:flex;flex-wrap:wrap;gap:8px}}
figure{{margin:0;padding:6px;background:white;border-radius:6px;text-align:center}} .bird-pair{{display:flex;gap:3px}}
.bird-pair img{{width:49px;height:62px;image-rendering:auto}} code{{background:#e9edf2;padding:2px 5px;border-radius:4px}}
</style>
</head>
<body><main>
<h1>算鸟聚类调试报告</h1>
<p>检测到 <strong>{report["detected_branches"]}</strong> 根树枝、<strong>{report["detected_birds"]}</strong> 只鸟；
占用阈值 <code>{report["presence_threshold"]}</code>，鸟总数使用容量倍数约束，聚类算法 <code>{report["clustering_algorithm"]}</code>。
绿色槽位为已识别鸟，红色槽位为空。</p>
<section class="card"><h2>树枝与槽位检测</h2><a href="01-detection.png"><img src="01-detection.png" alt="检测标注图"></a></section>
<h2>候选聚类</h2>{candidate_html}
<h2>标准化鸟裁剪与特征掩码</h2><p>每组左侧为标准化裁剪，右侧为实际送入颜色特征统计的区域。</p><div class="birds">{bird_images}</div>
<p>完整数值见 <a href="report.json">report.json</a>。</p>
</main></body></html>"""
