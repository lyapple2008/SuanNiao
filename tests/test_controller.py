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


if __name__ == "__main__":
    unittest.main()
