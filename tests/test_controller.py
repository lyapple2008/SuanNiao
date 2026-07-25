import base64
import io
import unittest
from unittest.mock import patch

from PIL import Image

from suanniao.controller import WdaController, WdaError


def png_base64(width: int, height: int) -> str:
    output = io.BytesIO()
    Image.new("RGB", (width, height), (120, 180, 220)).save(output, format="PNG")
    return base64.b64encode(output.getvalue()).decode("ascii")


class WdaControllerTests(unittest.TestCase):
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

    def test_invalid_wda_url_is_rejected(self) -> None:
        with self.assertRaises(WdaError):
            WdaController(base_url="127.0.0.1:8100")

    def test_dismiss_ad_uses_labelled_json_button_center(self) -> None:
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
                        "type": "Application",
                        "children": [
                            {
                                "type": "Button",
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
            dismissed = controller.dismiss_ad()

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

    def test_dismiss_ad_falls_back_to_xml_source(self) -> None:
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
                        'height="844"><XCUIElementTypeButton label="关闭广告" '
                        'x="330" y="70" width="44" height="44" enabled="true" '
                        'visible="true"/></XCUIElementTypeApplication>'
                    )
                }
            if path == "/session/session-1/wda/tap/0":
                return {"value": None}
            raise AssertionError(f"Unexpected WDA request: {method} {path}")

        with patch.object(WdaController, "_request_json", new=fake_request):
            controller = WdaController(session_id="session-1")
            dismissed = controller.dismiss_ad()

        self.assertTrue(dismissed)
        self.assertIn(
            (
                "POST",
                "/session/session-1/wda/tap/0",
                {"x": 352.0, "y": 92.0},
            ),
            requests,
        )

    def test_dismiss_ad_does_not_tap_unrelated_or_disabled_buttons(self) -> None:
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
                                "type": "Button",
                                "label": "设置",
                                "rect": {"x": 20, "y": 40, "width": 40, "height": 40},
                            },
                            {
                                "type": "Button",
                                "label": "Close Ad",
                                "isEnabled": "false",
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
            dismissed = controller.dismiss_ad()

        self.assertFalse(dismissed)
        self.assertFalse(any(method == "POST" for method, _, _ in requests))


if __name__ == "__main__":
    unittest.main()
