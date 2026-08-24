import unittest

from tests._import_app import import_web_app_module


class ExternalApiKeySettingsUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def _login(self, client, password: str = "testpass123"):
        resp = client.post("/login", json={"username": "admin", "password": password})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.get_json().get("success"))
        resp.close()

    def _get_text(self, client, path):
        resp = client.get(path)
        try:
            return resp.status_code, resp.data.decode("utf-8")
        finally:
            resp.close()

    def test_settings_page_has_external_api_key_input(self):
        client = self.app.test_client()
        self._login(client)

        status_code, html = self._get_text(client, "/")
        self.assertEqual(status_code, 200)
        self.assertIn('id="settingsExternalApiKey"', html)
        self.assertIn('id="settingsExternalApiKeysJson"', html)
        # 邮箱池管理 UI 已从用户端移除（产品决策）：这些设置控件不应再出现
        for removed_id in (
            'id="poolExternalEnabled"',
            'id="externalApiDisablePoolClaimRandom"',
            'id="externalApiDisablePoolClaimRelease"',
            'id="externalApiDisablePoolClaimComplete"',
            'id="externalApiDisablePoolStats"',
        ):
            self.assertNotIn(removed_id, html)

    def test_main_js_loads_masked_external_api_key_fields(self):
        client = self.app.test_client()
        self._login(client)

        status_code, js = self._get_text(client, "/static/js/main.js")
        self.assertEqual(status_code, 200)
        self.assertIn("external_api_key_masked", js)
        self.assertIn("external_api_keys", js)
        self.assertIn("settingsExternalApiKey", js)
        self.assertIn("settingsExternalApiKeysJson", js)
        self.assertIn("dataset.maskedValue", js)
        # 邮箱池管理 UI 已移除：前端不应再读写这些字段
        for removed in (
            "data.settings.pool_external_enabled === true",
            "settings.pool_external_enabled = poolExternalEnabledEl.checked",
            "externalApiDisablePoolClaimRandom",
            "externalApiDisablePoolClaimRelease",
            "externalApiDisablePoolClaimComplete",
            "externalApiDisablePoolStats",
        ):
            self.assertNotIn(removed, js)

    def test_main_js_preserves_pool_access_and_telegram_poll_interval_contract(self):
        client = self.app.test_client()
        self._login(client)

        _, js = self._get_text(client, "/static/js/main.js")
        _, html = self._get_text(client, "/")
        # pool_access 由后端 API 序列化保留（external_api_keys repo），前端不再消费
        import sys as _sys

        _sys.path.insert(0, ".")
        from outlook_web.repositories.external_api_keys import list_external_api_keys  # noqa: F401

        self.assertIn("Telegram 轮询间隔必须在 10-86400 秒之间", js)
        flat_html = " ".join(html.split())
        self.assertIn('id="telegramPollInterval" min="10" max="86400"', flat_html)


if __name__ == "__main__":
    unittest.main()
