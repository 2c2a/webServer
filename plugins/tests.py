import pytest
from django.test import RequestFactory
from django.contrib.auth import get_user_model
from unittest.mock import MagicMock, patch

User = get_user_model()


@pytest.mark.django_db
class TestPluginApiViewNoInfoLeak:
    def setup_method(self):
        self.factory = RequestFactory()

    def test_exception_returns_generic_error(self):
        from plugins.django_integration import plugin_api_view

        plugin = MagicMock()
        plugin.enabled = True
        plugin.some_action.side_effect = RuntimeError("secret internal error")

        with patch("plugins.django_integration.get_plugin", return_value=plugin):
            request = self.factory.post(
                "/api/plugins/test/some_action",
                data="{}",
                content_type="application/json",
            )
            response = plugin_api_view(request, "test", "some_action")

        assert response.status_code == 500
        assert b"Internal server error" in response.content
        assert b"secret internal error" not in response.content


@pytest.mark.django_db
class TestPluginManagementApiNoInfoLeak:
    def setup_method(self):
        self.factory = RequestFactory()

    def test_exception_returns_generic_error(self):
        from plugins.django_integration import plugin_management_api

        user = User.objects.create_user("testuser", password="testpass")
        request = self.factory.post(
            "/api/plugins/manage",
            data='{"action":"enable","plugin_id":"nonexist"}',
            content_type="application/json",
        )
        request.user = user

        with patch(
            "plugins.plugin_manager.PluginManager.enable_plugin",
            side_effect=RuntimeError("db connection lost"),
        ):
            response = plugin_management_api(request)

        assert response.status_code == 500
        assert b"Internal server error" in response.content
        assert b"db connection lost" not in response.content
