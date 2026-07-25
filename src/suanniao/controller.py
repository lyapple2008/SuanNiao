from __future__ import annotations

import base64
import io
import json
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image


class DeviceError(RuntimeError):
    pass


class AdbError(DeviceError):
    pass


class WdaError(DeviceError):
    pass


class DeviceController(Protocol):
    def capture_stable(
        self,
        *,
        interval: float = 0.25,
        attempts: int = 8,
        difference_threshold: float = 1.5,
    ) -> Image.Image: ...

    def tap(self, x: int, y: int) -> None: ...

    def close(self) -> None: ...


class StableCaptureMixin:
    def capture(self) -> Image.Image:
        raise NotImplementedError

    def capture_stable(
        self,
        *,
        interval: float = 0.25,
        attempts: int = 8,
        difference_threshold: float = 1.5,
    ) -> Image.Image:
        previous = self.capture()
        for _ in range(attempts - 1):
            time.sleep(interval)
            current = self.capture()
            before = np.asarray(previous)
            after = np.asarray(current)
            if before.shape != after.shape:
                previous = current
                continue

            height = before.shape[0]
            game_before = before[round(0.25 * height) : round(0.84 * height)]
            game_after = after[round(0.25 * height) : round(0.84 * height)]
            difference = np.abs(
                game_before.astype(float) - game_after.astype(float)
            ).mean()
            if difference <= difference_threshold:
                return current
            previous = current
        return previous


@dataclass(slots=True)
class AdbController(StableCaptureMixin):
    adb_path: str = "adb"
    serial: str | None = None

    def __post_init__(self) -> None:
        resolved = shutil.which(self.adb_path)
        if resolved is None:
            raise AdbError(
                f"Cannot find {self.adb_path!r}. Install Android platform-tools or pass "
                "--adb /absolute/path/to/adb."
            )
        self.adb_path = resolved

    def _command(self, *arguments: str) -> list[str]:
        command = [self.adb_path]
        if self.serial:
            command.extend(("-s", self.serial))
        command.extend(arguments)
        return command

    def capture(self) -> Image.Image:
        completed = subprocess.run(
            self._command("exec-out", "screencap", "-p"),
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            error = completed.stderr.decode(errors="replace").strip()
            raise AdbError(f"ADB screenshot failed: {error}")
        try:
            return Image.open(io.BytesIO(completed.stdout)).convert("RGB")
        except Exception as exc:  # pragma: no cover - depends on a real device
            raise AdbError("ADB returned an invalid screenshot") from exc

    def tap(self, x: int, y: int) -> None:
        completed = subprocess.run(
            self._command("shell", "input", "tap", str(x), str(y)),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise AdbError(f"ADB tap failed: {completed.stderr.strip()}")

    def close(self) -> None:
        return None


@dataclass(slots=True)
class WdaController(StableCaptureMixin):
    """Control an iPhone through a running WebDriverAgent HTTP server."""

    base_url: str = "http://127.0.0.1:8100"
    timeout: float = 10.0
    session_id: str | None = None
    _owns_session: bool = field(init=False, default=False)
    _last_screenshot_size: tuple[int, int] | None = field(init=False, default=None)
    _last_window_rect: tuple[float, float] | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise WdaError(
                "--wda-url must be an HTTP URL, for example http://127.0.0.1:8100"
            )
        self.base_url = self.base_url.rstrip("/")
        if self.timeout <= 0:
            raise WdaError("--wda-timeout must be positive")

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = urljoin(f"{self.base_url}/", path.lstrip("/"))
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace").strip()
            raise WdaError(
                f"WebDriverAgent returned HTTP {exc.code} for {path}: {details}"
            ) from exc
        except URLError as exc:
            raise WdaError(
                f"Cannot connect to WebDriverAgent at {self.base_url}: {exc.reason}. "
                "Start WDA and, for a physical iPhone, forward port 8100."
            ) from exc

        if not raw:
            return {}
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WdaError(f"WebDriverAgent returned invalid JSON for {path}") from exc
        if not isinstance(result, dict):
            raise WdaError(f"WebDriverAgent returned an unexpected response for {path}")

        value = result.get("value")
        if isinstance(value, dict) and value.get("error"):
            message = value.get("message") or value["error"]
            raise WdaError(f"WebDriverAgent command failed for {path}: {message}")
        return result

    def _ensure_session(self) -> str:
        if self.session_id:
            return self.session_id

        bodies = (
            {
                "capabilities": {
                    "alwaysMatch": {"platformName": "iOS"},
                    "firstMatch": [{}],
                }
            },
            {"desiredCapabilities": {}},
        )
        last_error: WdaError | None = None
        for body in bodies:
            try:
                result = self._request_json("POST", "/session", body)
            except WdaError as exc:
                last_error = exc
                continue
            value = result.get("value")
            session_id = result.get("sessionId")
            if not session_id and isinstance(value, dict):
                session_id = value.get("sessionId")
            if isinstance(session_id, str) and session_id:
                self.session_id = session_id
                self._owns_session = True
                return session_id

        if last_error is not None:
            raise last_error
        raise WdaError("WebDriverAgent did not return a session id")

    def capture(self) -> Image.Image:
        session_id = self._ensure_session()
        last_error: WdaError | None = None
        result: dict[str, Any] | None = None
        for path in (f"/session/{session_id}/screenshot", "/screenshot"):
            try:
                result = self._request_json("GET", path)
                break
            except WdaError as exc:
                last_error = exc
        if result is None:
            assert last_error is not None
            raise last_error

        encoded: Any = result.get("value")
        if isinstance(encoded, dict):
            encoded = encoded.get("screenshot")
        if not isinstance(encoded, str):
            raise WdaError("WebDriverAgent screenshot response did not contain image data")

        try:
            image_bytes = base64.b64decode(encoded, validate=True)
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception as exc:
            raise WdaError("WebDriverAgent returned an invalid screenshot") from exc
        self._last_screenshot_size = image.size
        self._last_window_rect = None
        return image

    def _window_size(self) -> tuple[float, float]:
        if self._last_window_rect is not None:
            return self._last_window_rect

        session_id = self._ensure_session()
        last_error: WdaError | None = None
        for path in (
            f"/session/{session_id}/window/rect",
            f"/session/{session_id}/window/size",
        ):
            try:
                result = self._request_json("GET", path)
            except WdaError as exc:
                last_error = exc
                continue
            value = result.get("value")
            if isinstance(value, dict):
                width = value.get("width")
                height = value.get("height")
                if isinstance(width, (int, float)) and isinstance(height, (int, float)):
                    self._last_window_rect = float(width), float(height)
                    return self._last_window_rect

        if last_error is not None:
            raise last_error
        raise WdaError("WebDriverAgent did not return the iPhone window size")

    def tap(self, x: int, y: int) -> None:
        session_id = self._ensure_session()
        screen_width, screen_height = self._window_size()
        if self._last_screenshot_size is None:
            tap_x, tap_y = x, y
        else:
            image_width, image_height = self._last_screenshot_size
            tap_x = round(x * screen_width / image_width)
            tap_y = round(y * screen_height / image_height)

        tap_payload = {"x": tap_x, "y": tap_y}
        try:
            self._request_json(
                "POST", f"/session/{session_id}/wda/tap/0", tap_payload
            )
            return
        except WdaError:
            pass

        actions = {
            "actions": [
                {
                    "type": "pointer",
                    "id": "finger1",
                    "parameters": {"pointerType": "touch"},
                    "actions": [
                        {
                            "type": "pointerMove",
                            "duration": 0,
                            "x": tap_x,
                            "y": tap_y,
                            "origin": "viewport",
                        },
                        {"type": "pointerDown", "button": 0},
                        {"type": "pause", "duration": 50},
                        {"type": "pointerUp", "button": 0},
                    ],
                }
            ]
        }
        try:
            self._request_json(
                "POST", f"/session/{session_id}/actions", actions
            )
            return
        except WdaError:
            self._request_json("POST", "/wda/tap/0", tap_payload)

    def close(self) -> None:
        if not self.session_id or not self._owns_session:
            return
        session_id = self.session_id
        self.session_id = None
        self._owns_session = False
        try:
            self._request_json("DELETE", f"/session/{session_id}")
        except WdaError:
            # Closing a best-effort automation session should not mask the
            # actual game result or a more useful earlier error.
            pass
