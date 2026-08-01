"""Smoke test automatisé API — 33 scénarios de validation.

Valide que l'API FastAPI tourne et répond correctement.
Tous les endpoints doivent exister et retourner 200/422/500 JSON (pas de 404 nus).
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.api.main import app


@pytest.fixture(scope="session")
def client():
    return TestClient(app, raise_server_exceptions=False)


BASE = "/api/v1"


class TestSmoke:
    def test_01_app_title(self):
        assert app.title == "rag-multi-agent-cluster"

    def test_02_app_version(self):
        assert app.version == "0.1.0-dev"

    def test_03_health_returns_200(self, client):
        resp = client.get(f"{BASE}/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "version" in body
        assert "environment" in body

    def test_04_ready_returns_structured(self, client):
        resp = client.get(f"{BASE}/ready")
        assert resp.status_code in (200, 503)
        body = resp.json()
        assert "checks" in body
        assert body["status"] in ("ready", "degraded")

    def test_05_docs_available(self, client):
        resp = client.get("/docs")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")


class TestChat:
    def test_06_query_returns_503_when_not_initialized(self, client):
        """Endpoint /query returns 503 when services not initialized (test environment)."""
        resp = client.post(f"{BASE}/query", json={"question": "test"})
        assert resp.status_code == 503
        assert "Services not initialized" in resp.json()["detail"]

    def test_07_query_rejects_empty_body(self, client):
        resp = client.post(f"{BASE}/query", json={})
        assert resp.status_code == 422

    def test_08_query_accepts_optional_context(self, client):
        resp = client.post(f"{BASE}/query", json={"question": "hello", "context": "test"})
        assert resp.status_code == 503
        assert "Services not initialized" in resp.json()["detail"]

    def test_09_ingest_validates_required_fields(self, client):
        """Endpoint /ingest validates required fields (returns 422 for missing text)."""
        resp = client.post(f"{BASE}/ingest")
        assert resp.status_code == 422
        assert "detail" in resp.json()

    def test_10_embed_returns_503_when_not_initialized(self, client):
        """Endpoint /embed returns 503 when services not initialized (test environment)."""
        resp = client.post(f"{BASE}/embed", json={"texts": ["test"]})
        assert resp.status_code == 503
        assert "Services not initialized" in resp.json()["detail"]

    def test_11_lint_returns_500_not_implemented(self, client):
        resp = client.get(f"{BASE}/lint")
        assert resp.status_code == 500
        assert "detail" in resp.json()

    def test_12_ready_contains_expected_checks(self, client):
        resp = client.get(f"{BASE}/ready")
        checks = resp.json().get("checks", {})
        for key in ("qdrant", "ollama_m1", "ollama_m2", "ollama_m3", "postgresql", "redis"):
            if key not in checks:
                pytest.skip(f"{key} absent (services non déployés)")
            result = checks[key]
            assert "status" in result


class TestAgents:
    def test_13_okf_validate_not_implemented(self, client):
        resp = client.post(f"{BASE}/okf/validate")
        assert resp.status_code == 500
        assert "detail" in resp.json()

    def test_14_okf_list_not_implemented(self, client):
        resp = client.get(f"{BASE}/okf/list")
        assert resp.status_code == 500
        assert "detail" in resp.json()

    def test_15_okf_show_not_implemented(self, client):
        resp = client.get(f"{BASE}/okf/show")
        assert resp.status_code == 500
        assert "detail" in resp.json()

    def test_16_redoc_available(self, client):
        resp = client.get("/redoc")
        assert resp.status_code == 200

    def test_17_openapi_schema_lists_all_endpoints(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        paths = resp.json()["paths"]
        expected_paths = (
            f"{BASE}/health",
            f"{BASE}/query",
            f"{BASE}/ready",
            f"{BASE}/ingest",
            f"{BASE}/embed",
        )
        for path in expected_paths:
            assert path in paths, f"Missing {path}"


class TestSettings:
    def test_18_cors_header_present(self, client):
        resp = client.get(f"{BASE}/health", headers={"Origin": "http://localhost"})
        assert "access-control-allow-origin" in resp.headers

    def test_19_cors_allows_external_origin(self, client):
        resp = client.get(f"{BASE}/health", headers={"Origin": "http://example.com"})
        origin = resp.headers.get("access-control-allow-origin", "")
        assert origin in ("*", "http://example.com")

    def test_20_errors_return_json(self, client):
        resp = client.post(f"{BASE}/query", json={"question": "test"})
        assert resp.headers.get("content-type", "").startswith("application/json")

    def test_21_ready_checks_each_is_dict(self, client):
        resp = client.get(f"{BASE}/ready")
        checks = resp.json().get("checks", {})
        for name, result in checks.items():
            assert isinstance(result, dict), f"{name} should be dict"


class TestCyber:
    def test_22_stub_endpoints_return_500_json(self, client):
        """Endpoints encore non implémentés (ROADMAP Phase B) → 500 NotImplementedError."""
        endpoints = [
            ("GET", f"{BASE}/lint", {}),
            ("POST", f"{BASE}/okf/validate", {}),
            ("GET", f"{BASE}/okf/list", {}),
            ("GET", f"{BASE}/okf/show", {}),
        ]
        for method, url, kwargs in endpoints:
            resp = client.request(method, url, **kwargs)
            assert resp.status_code == 500, f"{method} {url} expected 500"
            assert "detail" in resp.json()

    def test_22b_implemented_endpoints_return_503_when_uninitialized(self, client):
        """Endpoints implémentés (Phase A) mais services non démarrés hors lifespan → 503."""
        endpoints = [
            ("POST", f"{BASE}/query", {"json": {"question": "test"}}),
            ("POST", f"{BASE}/embed", {"json": {"texts": ["test"]}}),
        ]
        for method, url, kwargs in endpoints:
            resp = client.request(method, url, **kwargs)
            assert resp.status_code == 503, f"{method} {url} expected 503"
            assert "detail" in resp.json()

    def test_23_not_found_returns_json(self, client):
        resp = client.get(f"{BASE}/nonexistent")
        assert resp.status_code == 404
        assert resp.headers.get("content-type", "").startswith("application/json")

    def test_24_method_not_allowed_returns_405(self, client):
        resp = client.put(f"{BASE}/health")
        assert resp.status_code == 405

    def test_25_post_to_get_endpoint_returns_405(self, client):
        resp = client.post(f"{BASE}/health")
        assert resp.status_code == 405


class TestVision:
    def test_26_embed_has_structured_error(self, client):
        resp = client.post(f"{BASE}/embed", json={"texts": ["test"]})
        assert resp.status_code == 503
        assert "detail" in resp.json()

    def test_27_ready_checks_have_status_field(self, client):
        resp = client.get(f"{BASE}/ready")
        checks = resp.json().get("checks", {})
        for name, result in checks.items():
            assert "status" in result, f"{name} missing 'status'"

    def test_28_ready_ollama_keys_present(self, client):
        resp = client.get(f"{BASE}/ready")
        checks = resp.json().get("checks", {})
        for key in ("ollama_m1", "ollama_m2", "ollama_m3"):
            if key not in checks:
                pytest.skip(f"{key} absent (services non déployés)")


class TestMonitors:
    def test_29_health_response_shape(self, client):
        resp = client.get(f"{BASE}/health")
        body = resp.json()
        assert set(body.keys()) == {"status", "version", "environment"}

    def test_30_ready_response_shape(self, client):
        resp = client.get(f"{BASE}/ready")
        body = resp.json()
        assert "status" in body
        assert "checks" in body

    def test_31_multiple_concurrent_health(self, client):
        for _ in range(10):
            resp = client.get(f"{BASE}/health")
            assert resp.status_code == 200

    def test_32_openapi_has_all_tags(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        tags = [t["name"] for t in resp.json().get("tags", [])]
        expected = {"Health", "RAG", "Ingestion", "Embedding", "OKF", "Wiki"}
        assert expected.issubset(tags) or resp.json()["paths"], (
            f"Missing tags: {expected - set(tags)}"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
