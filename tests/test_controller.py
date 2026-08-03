import base64
import io
import unittest
from unittest.mock import patch

from PIL import Image

from suanniao.controller import StableCaptureMixin, WdaController, WdaError


def png_base64(width: int, height: int) -> str:
    output = io.BytesIO()
    Image.new("RGB", (width, height), (120, 180, 220)).save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


class WdaControllerTests(unittest.TestCase):
    def test_stable_capture_can_reuse_an_existing_first_frame(self) -> None:
        first = Image.new("RGB", (20, 40), "white")
        second = Image.new("RGB", (20, 40), "white")

        class SequenceController(StableCaptureMixin):
            def __init__(self) -> None:
                self.capture_calls = 0

            def capture(self) -> Image.Image:
                self.capture_calls += 1
                return second

        controller = SequenceController()

        result = controller.capture_stable(initial=first, interval=0, attempts=2)

        self.assertIs(result, second)
        self.assertEqual(controller.capture_calls, 1)

    def test_session_sets_bounded_quiescence_timeouts_once(self) -> None:
        screenshot = png_base64(300, 600)
        requests: list[tuple[str, str, object]] = []

        def fake_request(
            _controller: WdaController,
            method: str,
            path: str,
            payload: object = None,
        ) -> dict[str, object]:
            requests.append((method, path, payload))
            if path == "/session/session-1/appium/settings":
                return {"value": payload}
            if path == "/session/session-1/screenshot":
                return {"value": screenshot}
            raise AssertionError(f"Unexpected WDA request: {method} {path}")

        with patch.object(WdaController, "_request_json", new=fake_request):
            controller = WdaController(
                session_id="session-1",
                default_active_application="com.tencent.xin",
                quiescence_timeout=0.2,
            )
            controller.capture()
            controller.capture()

        self.assertEqual(
            requests[0],
            (
                "POST",
                "/session/session-1/appium/settings",
                {
                    "settings": {
                        "defaultActiveApplication": "com.tencent.xin",
                        "waitForIdleTimeout": 0.2,
                        "animationCoolOffTimeout": 0.2,
                    }
                },
            ),
        )
        self.assertEqual(
            sum(path.endswith("/appium/settings") for _, path, _ in requests),
            1,
        )

    def test_new_session_sets_default_active_application_once(self) -> None:
        screenshot = png_base64(300, 600)
        requests: list[tuple[str, str, object]] = []

        def fake_request(
            _controller: WdaController,
            method: str,
            path: str,
            payload: object = None,
        ) -> dict[str, object]:
            requests.append((method, path, payload))
            if method == "POST" and path == "/session":
                return {"value": {"sessionId": "session-1"}}
            if path == "/session/session-1/appium/settings":
                return {"value": payload}
            if path == "/session/session-1/screenshot":
                return {"value": screenshot}
            raise AssertionError(f"Unexpected WDA request: {method} {path}")

        with patch.object(WdaController, "_request_json", new=fake_request):
            controller = WdaController(
                default_active_application="com.tencent.xin"
            )
            controller.capture()
            controller.capture()

        self.assertEqual(
            requests[:3],
            [
                (
                    "POST",
                    "/session",
                    {
                        "capabilities": {
                            "alwaysMatch": {"platformName": "iOS"},
                            "firstMatch": [{}],
                        }
                    },
                ),
                (
                    "POST",
                    "/session/session-1/appium/settings",
                    {
                        "settings": {
                            "defaultActiveApplication": "com.tencent.xin"
                        }
                    },
                ),
                ("GET", "/session/session-1/screenshot", None),
            ],
        )
        self.assertEqual(
            sum(path.endswith("/appium/settings") for _, path, _ in requests),
            1,
        )

    def test_existing_session_sets_default_active_application_once(self) -> None:
        screenshot = png_base64(300, 600)
        requests: list[tuple[str, str, object]] = []

        def fake_request(
            _controller: WdaController,
            method: str,
            path: str,
            payload: object = None,
        ) -> dict[str, object]:
            requests.append((method, path, payload))
            if path == "/session/existing-session/appium/settings":
                return {"value": payload}
            if path == "/session/existing-session/screenshot":
                return {"value": screenshot}
            raise AssertionError(f"Unexpected WDA request: {method} {path}")

        with patch.object(WdaController, "_request_json", new=fake_request):
            controller = WdaController(
                session_id="existing-session",
                default_active_application="com.tencent.xin",
            )
            controller.capture()
            controller.capture()

        self.assertEqual(
            requests[0],
            (
                "POST",
                "/session/existing-session/appium/settings",
                {
                    "settings": {
                        "defaultActiveApplication": "com.tencent.xin"
                    }
                },
            ),
        )
        self.assertEqual(
            sum(path.endswith("/appium/settings") for _, path, _ in requests),
            1,
        )

    def test_screenshot_and_retina_tap_scaling(self) -> None:
        screenshot = png_base64(300, 600)
        requests: list[tuple[str, str, object]] = []

        def fake_request(
            _controller: WdaController,
            method: str,
            path: str,
            payload: object = None,
        ) -> dict[str, object]:
            requests.append((method, path, payload))
            if method == "POST" and path == "/session":
                return {"value": {"sessionId": "session-1"}}
            if method == "GET" and path == "/session/session-1/screenshot":
                return {"value": screenshot}
            if method == "GET" and path == "/session/session-1/window/rect":
                return {"value": {"x": 0, "y": 0, "width": 100, "height": 200}}
            if method == "POST" and path == "/session/session-1/wda/tap/0":
                return {"value": None}
            if method == "DELETE" and path == "/session/session-1":
                return {"value": None}
            raise AssertionError(f"Unexpected WDA request: {method} {path}")

        with patch.object(WdaController, "_request_json", new=fake_request):
            controller = WdaController()
            image = controller.capture()
            controller.tap(150, 300)
            controller.close()

        self.assertEqual(image.size, (300, 600))
        tap_request = next(
            request for request in requests if request[1].endswith("/wda/tap/0")
        )
        self.assertEqual(tap_request[2], {"x": 50, "y": 100})
        self.assertIn(("DELETE", "/session/session-1", None), requests)

    def test_external_session_is_not_deleted(self) -> None:
        requests: list[tuple[str, str, object]] = []

        def fake_request(
            _controller: WdaController,
            method: str,
            path: str,
            payload: object = None,
        ) -> dict[str, object]:
            requests.append((method, path, payload))
            return {"value": None}

        with patch.object(WdaController, "_request_json", new=fake_request):
            controller = WdaController(session_id="existing-session")
            controller.close()

        self.assertEqual(requests, [])

    def test_tap_pair_uses_two_scaled_wda_tap_requests(self) -> None:
        screenshot = png_base64(300, 600)
        requests: list[tuple[str, str, object]] = []

        def fake_request(
            _controller: WdaController,
            method: str,
            path: str,
            payload: object = None,
        ) -> dict[str, object]:
            requests.append((method, path, payload))
            if method == "GET" and path == "/session/session-1/screenshot":
                return {"value": screenshot}
            if method == "GET" and path == "/session/session-1/window/rect":
                return {"value": {"width": 100, "height": 200}}
            if method == "POST" and path == "/session/session-1/wda/tap/0":
                return {"value": None}
            raise AssertionError(f"Unexpected WDA request: {method} {path}")

        with patch.object(WdaController, "_request_json", new=fake_request):
            controller = WdaController(session_id="session-1")
            controller.capture()
            controller.tap_pair((150, 300), (75, 150), 0.06)

        tap_requests = [
            request for request in requests if request[1].endswith("/wda/tap/0")
        ]
        self.assertEqual(
            [request[2] for request in tap_requests],
            [{"x": 50, "y": 100}, {"x": 25, "y": 50}],
        )

    def test_window_size_is_reused_while_screenshot_size_is_unchanged(self) -> None:
        screenshot = png_base64(300, 600)
        requests: list[tuple[str, str, object]] = []

        def fake_request(
            _controller: WdaController,
            method: str,
            path: str,
            payload: object = None,
        ) -> dict[str, object]:
            requests.append((method, path, payload))
            if path == "/session/session-1/screenshot":
                return {"value": screenshot}
            if path == "/session/session-1/window/rect":
                return {"value": {"width": 100, "height": 200}}
            if path == "/session/session-1/wda/tap/0":
                return {"value": None}
            raise AssertionError(f"Unexpected WDA request: {method} {path}")

        with patch.object(WdaController, "_request_json", new=fake_request):
            controller = WdaController(session_id="session-1")
            controller.capture()
            controller.tap(150, 300)
            controller.capture()
            controller.tap(150, 300)

        window_requests = [
            request for request in requests if request[1].endswith("/window/rect")
        ]
        self.assertEqual(len(window_requests), 1)

    def test_screenshot_fallback_endpoint_is_cached(self) -> None:
        screenshot = png_base64(300, 600)
        requests: list[tuple[str, str, object]] = []

        def fake_request(
            _controller: WdaController,
            method: str,
            path: str,
            payload: object = None,
        ) -> dict[str, object]:
            requests.append((method, path, payload))
            if path == "/session/session-1/screenshot":
                raise WdaError("session screenshot unavailable")
            if path == "/screenshot":
                return {"value": screenshot}
            raise AssertionError(f"Unexpected WDA request: {method} {path}")

        with patch.object(WdaController, "_request_json", new=fake_request):
            controller = WdaController(session_id="session-1")
            controller.capture()
            controller.capture()

        self.assertEqual(
            [path for _method, path, _payload in requests],
            ["/session/session-1/screenshot", "/screenshot", "/screenshot"],
        )

    def test_tap_fallback_strategy_is_cached(self) -> None:
        requests: list[tuple[str, str, object]] = []

        def fake_request(
            _controller: WdaController,
            method: str,
            path: str,
            payload: object = None,
        ) -> dict[str, object]:
            requests.append((method, path, payload))
            if path == "/session/session-1/window/rect":
                return {"value": {"width": 100, "height": 200}}
            if path == "/session/session-1/wda/tap/0":
                raise WdaError("WDA tap unavailable")
            if path == "/session/session-1/actions":
                return {"value": None}
            raise AssertionError(f"Unexpected WDA request: {method} {path}")

        with patch.object(WdaController, "_request_json", new=fake_request):
            controller = WdaController(session_id="session-1")
            controller.tap(10, 20)
            controller.tap(30, 40)

        failed_primary = [
            request
            for request in requests
            if request[1] == "/session/session-1/wda/tap/0"
        ]
        action_requests = [
            request
            for request in requests
            if request[1] == "/session/session-1/actions"
        ]
        self.assertEqual(len(failed_primary), 1)
        self.assertEqual(len(action_requests), 2)

    def test_invalid_wda_url_is_rejected(self) -> None:
        with self.assertRaises(WdaError):
            WdaController(base_url="127.0.0.1:8100")

    def test_negative_quiescence_timeout_is_rejected(self) -> None:
        with self.assertRaises(WdaError):
            WdaController(quiescence_timeout=-0.01)

    def test_dismiss_interruption_uses_labelled_json_button_center(self) -> None:
        requests: list[tuple[str, str, object]] = []

        def fake_request(
            _controller: WdaController,
            method: str,
            path: str,
            payload: object = None,
        ) -> dict[str, object]:
            requests.append((method, path, payload))
            if path == "/session/session-1/window/rect":
                return {"value": {"width": 390, "height": 844}}
            if path == "/session/session-1/source?format=json":
                return {
                    "value": {
                        "type": "XCUIElementTypeApplication",
                        "children": [
                            {
                                "type": "XCUIElementTypeButton",
                                "label": "Close Ad",
                                "isEnabled": "true",
                                "isVisible": "true",
                                "rect": {
                                    "x": 344,
                                    "y": 42,
                                    "width": 40,
                                    "height": 40,
                                },
                            }
                        ],
                    }
                }
            if path == "/session/session-1/wda/tap/0":
                return {"value": None}
            raise AssertionError(f"Unexpected WDA request: {method} {path}")

        with patch.object(WdaController, "_request_json", new=fake_request):
            controller = WdaController(session_id="session-1")
            dismissed = controller.dismiss_interruption()

        self.assertTrue(dismissed)
        self.assertIn(
            (
                "POST",
                "/session/session-1/wda/tap/0",
                {"x": 364.0, "y": 62.0},
            ),
            requests,
        )
        self.assertFalse(any(path.endswith("/source") for _, path, _ in requests))

    def test_dismiss_interruption_falls_back_to_xml_source(self) -> None:
        requests: list[tuple[str, str, object]] = []

        def fake_request(
            _controller: WdaController,
            method: str,
            path: str,
            payload: object = None,
        ) -> dict[str, object]:
            requests.append((method, path, payload))
            if path == "/session/session-1/window/rect":
                return {"value": {"width": 390, "height": 844}}
            if path.endswith("source?format=json"):
                raise WdaError("JSON source is unavailable")
            if path == "/session/session-1/source":
                return {
                    "value": (
                        '<XCUIElementTypeApplication x="0" y="0" width="390" '
                        'height="844"><XCUIElementTypeButton label="关闭按钮" '
                        'x="330" y="70" width="44" height="44" enabled="true" '
                        'visible="true"/></XCUIElementTypeApplication>'
                    )
                }
            if path == "/session/session-1/wda/tap/0":
                return {"value": None}
            raise AssertionError(f"Unexpected WDA request: {method} {path}")

        with patch.object(WdaController, "_request_json", new=fake_request):
            controller = WdaController(session_id="session-1")
            dismissed = controller.dismiss_interruption()

        self.assertTrue(dismissed)
        self.assertIn(
            (
                "POST",
                "/session/session-1/wda/tap/0",
                {"x": 352.0, "y": 92.0},
            ),
            requests,
        )

    def test_dismiss_interruption_ignores_unrelated_or_disabled_buttons(self) -> None:
        requests: list[tuple[str, str, object]] = []

        def fake_request(
            _controller: WdaController,
            method: str,
            path: str,
            payload: object = None,
        ) -> dict[str, object]:
            requests.append((method, path, payload))
            if path == "/session/session-1/window/rect":
                return {"value": {"width": 390, "height": 844}}
            if path.endswith("source?format=json"):
                return {
                    "value": {
                        "children": [
                            {
                                "type": "XCUIElementTypeButton",
                                "label": "设置",
                                "rect": {"x": 20, "y": 40, "width": 40, "height": 40},
                            },
                            {
                                "type": "XCUIElementTypeButton",
                                "label": "Close Ad",
                                "isEnabled": " false ",
                                "rect": {
                                    "x": 330,
                                    "y": 40,
                                    "width": 40,
                                    "height": 40,
                                },
                            },
                        ]
                    }
                }
            if path.endswith("/source"):
                return {"value": '<XCUIElementTypeButton label="取消"/>'}
            raise AssertionError(f"Unexpected WDA request: {method} {path}")

        with patch.object(WdaController, "_request_json", new=fake_request):
            controller = WdaController(session_id="session-1")
            dismissed = controller.dismiss_interruption()

        self.assertFalse(dismissed)
        self.assertFalse(any(method == "POST" for method, _, _ in requests))


if __name__ == "__main__":
    unittest.main()
