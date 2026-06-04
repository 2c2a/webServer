import pytest
from django.test import RequestFactory
from config.views import static_fallback_view


@pytest.mark.django_db
class TestStaticFallbackView:
    def setup_method(self):
        self.factory = RequestFactory()

    def test_path_traversal_blocked(self):
        request = self.factory.get("/static/../../etc/passwd")
        response = static_fallback_view(request, "../../etc/passwd")
        assert response.status_code == 400

    def test_absolute_url_scheme_blocked(self):
        request = self.factory.get("/static/https://evil.com")
        response = static_fallback_view(request, "https://evil.com")
        assert response.status_code == 400

    def test_absolute_url_netloc_blocked(self):
        request = self.factory.get("/static//evil.com/path")
        response = static_fallback_view(request, "//evil.com/path")
        assert response.status_code == 400

    def test_backslash_url_blocked(self):
        request = self.factory.get("/static/\\\\evil.com/path")
        response = static_fallback_view(request, "\\\\evil.com/path")
        assert response.status_code == 400

    def test_normal_path_served_or_redirected(self):
        request = self.factory.get("/static/css/base.css")
        response = static_fallback_view(request, "css/base.css")
        assert response.status_code in (200, 302)

    def test_normal_js_path_served_or_redirected(self):
        request = self.factory.get("/static/js/base.js")
        response = static_fallback_view(request, "js/base.js")
        assert response.status_code in (200, 302)

    def test_nonexistent_path_redirects_to_cdn(self):
        request = self.factory.get("/static/nonexistent/file.xyz")
        response = static_fallback_view(request, "nonexistent/file.xyz")
        assert response.status_code == 302
        assert "static.2c2a.cc.cd" in response.url
