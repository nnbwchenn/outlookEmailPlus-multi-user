from __future__ import annotations

"""用户端不暴露邮箱池功能的前端回归契约。"""

import unittest

from tests._import_app import import_web_app_module


class PoolAdminFrontendContractBase(unittest.TestCase):
    """前端契约测试基类"""

    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app
        cls.client = cls.app.test_client()

    def _get_text(self, path):
        resp = self.client.get(path)
        try:
            return resp.data.decode("utf-8")
        finally:
            resp.close()

    def _login(self):
        resp = self.client.post("/login", json={"username": "admin", "password": "testpass123"})
        if resp.status_code != 200:
            raise RuntimeError(f"测试用户登录失败 ({resp.status_code})")


class PoolAdminUiRemovalTests(PoolAdminFrontendContractBase):
    """邮箱池后端兼容保留，但用户端不得加载或展示其管理能力。"""

    def test_index_has_no_pool_admin_navigation_or_controls(self):
        self._login()
        html = self._get_text("/")
        forbidden = [
            "pool-admin",
            "poolAdmin",
            "pool_admin",
            "号池管理",
            "addToPoolCheckbox",
            "poolExternalEnabled",
            "externalApiDisablePool",
            "邮箱池",
        ]
        for marker in forbidden:
            self.assertNotIn(marker, html, f"用户端不应暴露邮箱池标识: {marker}")

    def test_pool_admin_script_is_not_served(self):
        response = self.client.get("/static/js/features/pool_admin.js")
        self.assertEqual(response.status_code, 404)

    def test_main_client_does_not_request_or_manage_pool(self):
        main_js = self._get_text("/static/js/main.js")
        overview_js = self._get_text("/static/js/features/overview.js")
        forbidden = [
            "loadPoolAdmin",
            "pool-admin",
            "/api/overview/pool",
            "poolExternalEnabled",
            "add_to_pool",
        ]
        for marker in forbidden:
            self.assertNotIn(marker, main_js + overview_js, f"客户端不应保留邮箱池逻辑: {marker}")


if __name__ == "__main__":
    unittest.main()
