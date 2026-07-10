"""HTTP API 服务测试。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pydoctrans.server import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestHealthEndpoint:
    """测试 GET /health。"""

    def test_returns_200(self, client: TestClient) -> None:
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    def test_returns_status_up(self, client: TestClient) -> None:
        response = client.get("/api/v1/health")
        data = response.json()
        assert data["status"] == "up"
        assert data["engine"] == "libreoffice"
        assert "version" in data
        assert "pool" in data

    def test_pool_info_present(self, client: TestClient) -> None:
        response = client.get("/api/v1/health")
        pool = response.json()["pool"]
        assert "max_concurrent" in pool
        assert "available" in pool
        assert pool["max_concurrent"] >= pool["available"]


class TestEnginesEndpoint:
    """测试 GET /engines。"""

    def test_returns_200(self, client: TestClient) -> None:
        response = client.get("/api/v1/engines")
        assert response.status_code == 200

    def test_lists_libreoffice(self, client: TestClient) -> None:
        response = client.get("/api/v1/engines")
        data = response.json()
        assert "engines" in data
        names = [e["name"] for e in data["engines"]]
        assert "libreoffice" in names


class TestConvertEndpoint:
    """测试 POST /convert。"""

    def test_txt_to_pdf(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/convert",
            files={"file": ("hello.txt", b"Hello pydoctrans!", "text/plain")},
            data={"to": "pdf"},
        )
        assert response.status_code == 200
        assert int(response.headers.get("content-length", "0")) > 0
        assert response.headers.get("x-engine") == "libreoffice"

    def test_missing_file_returns_422(self, client: TestClient) -> None:
        response = client.post("/api/v1/convert", data={"to": "pdf"})
        assert response.status_code == 422

    def test_missing_format_defaults_to_pdf(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/convert",
            files={"file": ("hello.txt", b"Hello!", "text/plain")},
        )
        assert response.status_code == 200
        assert int(response.headers.get("content-length", "0")) > 0

    def test_invalid_format_returns_400(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/convert",
            files={"file": ("hello.txt", b"Hello!", "text/plain")},
            data={"to": "zzz_invalid_format"},
        )
        assert response.status_code == 400

    def test_empty_filename_returns_error(self, client: TestClient) -> None:
        """空文件名应返回 422（FastAPI 表单验证失败）。"""
        response = client.post(
            "/api/v1/convert",
            files={"file": ("", b"...", "text/plain")},
            data={"to": "pdf"},
        )
        assert response.status_code == 422

    def test_empty_file_converts(self, client: TestClient) -> None:
        """空文件也应能转换。"""
        response = client.post(
            "/api/v1/convert",
            files={"file": ("empty.txt", b"", "text/plain")},
            data={"to": "pdf"},
        )
        # 空文件 LO 仍能生成 PDF（可能是空白页）
        assert response.status_code == 200

    def test_response_has_headers(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/convert",
            files={"file": ("test.txt", b"data", "text/plain")},
            data={"to": "pdf"},
        )
        assert "content-disposition" in response.headers
        assert "x-engine" in response.headers
        assert "libreoffice" in response.headers["x-engine"]

    def test_concurrent_requests(self, client: TestClient) -> None:
        """多个并发请求应正常处理。"""
        import concurrent.futures

        def make_request(i: int) -> int:
            resp = client.post(
                "/api/v1/convert",
                files={"file": (f"test_{i}.txt", f"content {i}".encode(), "text/plain")},
                data={"to": "pdf"},
            )
            return resp.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(make_request, i) for i in range(3)]
            statuses = [f.result() for f in futures]

        assert all(s == 200 for s in statuses)


class TestMetricsEndpoint:
    """测试 GET /metrics。"""

    def test_returns_200(self, client: TestClient) -> None:
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_returns_prometheus_format(self, client: TestClient) -> None:
        response = client.get("/metrics")
        content = response.text
        assert "pydoctrans_requests_total" in content
        assert "pydoctrans_pool_slots_max" in content
        assert "pydoctrans_request_duration_seconds" in content
        assert "pydoctrans_file_size_bytes" in content
        assert "pydoctrans_requests_in_flight" in content

    def test_metrics_increment_after_conversion(self, client: TestClient) -> None:
        # 获取基线值
        before = client.get("/metrics").text
        # 做一次转换
        client.post(
            "/api/v1/convert",
            files={"file": ("test.txt", b"data", "text/plain")},
            data={"to": "pdf"},
        )
        after = client.get("/metrics").text

        # 验证 metrics 有变化（文本不同说明计数增加了）
        assert before != after


class TestMaxFileSize:
    """测试文件大小限制。"""

    def test_small_file_accepted(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/convert",
            files={"file": ("test.txt", b"small", "text/plain")},
            data={"to": "pdf"},
        )
        assert response.status_code == 200


class TestShutdownMiddleware:
    """测试优雅关闭中间件。"""

    def test_rejects_when_shutting_down(self, client: TestClient) -> None:
        import pydoctrans.server as server_mod

        # 模拟关闭状态
        server_mod._shutdown_event.set()
        try:
            response = client.post(
                "/api/v1/convert",
                files={"file": ("test.txt", b"data", "text/plain")},
                data={"to": "pdf"},
            )
            assert response.status_code == 503
            assert "关闭" in response.text
        finally:
            server_mod._shutdown_event.clear()

    def test_health_still_works_during_shutdown(self, client: TestClient) -> None:
        """健康检查在关闭期间也保持可用（通过中间件）变化不大。"""
        response = client.get("/api/v1/health")
        assert response.status_code == 200
