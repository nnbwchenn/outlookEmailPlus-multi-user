"""激活码契约测试：生成校验 / 兑换绑定 / 防重复 / 越权 / 边界"""

from __future__ import annotations

import sqlite3
import unittest

from tests._import_app import import_web_app_module


class ActivationCodeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app
        from tests._import_app import _DB_PATH

        cls.db_path = str(_DB_PATH)

    def setUp(self):
        self.client = self.app.test_client()
        self._login("admin", "testpass123")

    def _login(self, username: str, password: str) -> None:
        resp = self.client.post("/login", data={"username": username, "password": password})
        assert resp.status_code in (200, 302), f"登录失败: {resp.status_code}"

    def _seed_accounts(self, emails: list[str]) -> None:
        conn = sqlite3.connect(self.db_path)
        for email in emails:
            conn.execute(
                "INSERT INTO accounts (email, password, client_id, refresh_token, group_id, status, account_type, provider) "
                "VALUES (?, '', 'cid', 'rt', 1, 'active', 'outlook', 'outlook')",
                (email,),
            )
        conn.commit()
        conn.close()

    def _unassigned_count(self) -> int:
        conn = sqlite3.connect(self.db_path)
        n = conn.execute("SELECT COUNT(*) FROM accounts WHERE owner_user_id IS NULL").fetchone()[0]
        conn.close()
        return int(n)

    # ---------- 管理端：生成与参数校验 ----------

    def test_generate_requires_admin(self):
        self.client.post("/logout") if False else None
        # 未登录客户端
        fresh = self.app.test_client()
        resp = fresh.post("/api/admin/activation-codes/generate", json={"count": 1, "max_bindings": 1})
        self.assertIn(resp.status_code, (302, 401, 403))

    def test_generate_rejects_invalid_bounds(self):
        for payload in (
            {"count": 0, "max_bindings": 1},
            {"count": 201, "max_bindings": 1},
            {"count": 5, "max_bindings": 0},
            {"count": 5, "max_bindings": 101},
            {"count": "abc", "max_bindings": 1},
        ):
            resp = self.client.post("/api/admin/activation-codes/generate", json=payload)
            self.assertEqual(resp.status_code, 400, f"payload={payload}")

    def test_generate_and_list(self):
        resp = self.client.post(
            "/api/admin/activation-codes/generate", json={"count": 3, "max_bindings": 2}
        )
        self.assertEqual(resp.status_code, 200)
        codes = resp.get_json()["codes"]
        self.assertEqual(len(codes), 3)
        self.assertTrue(all(c.count("-") == 2 for c in codes))

        listing = self.client.get("/api/admin/activation-codes")
        rows = listing.get_json()["codes"]
        mine = [r for r in rows if r["code"] in codes]
        self.assertEqual(len(mine), 3)
        self.assertTrue(all(r["max_bindings"] == 2 for r in mine))
        self.assertTrue(all(r["status"] == "active" for r in mine))

    # ---------- 用户端：兑换绑定 ----------

    def test_redeem_binds_unassigned_mailboxes(self):
        before = self._unassigned_count()
        if before < 3:
            self.skipTest(f"未分配邮箱不足（{before}），跳过")

        gen = self.client.post(
            "/api/admin/activation-codes/generate", json={"count": 1, "max_bindings": 2}
        ).get_json()
        code = gen["codes"][0]

        resp = self.client.post("/api/activation/redeem", json={"code": code})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["bound_count"], 2)
        self.assertEqual(len(body["bound"]), 2)

        # 绑定的邮箱归属当前用户（admin id=1）
        conn = sqlite3.connect(self.db_path)
        owner_ids = [
            conn.execute("SELECT owner_user_id FROM accounts WHERE email=?", (b["email"],)).fetchone()[0]
            for b in body["bound"]
        ]
        bindings = conn.execute(
            "SELECT COUNT(*) FROM activation_code_bindings WHERE user_id=1"
        ).fetchone()[0]
        conn.close()
        self.assertTrue(all(oid == 1 for oid in owner_ids))
        self.assertGreaterEqual(bindings, 2)

        # 同一码再次兑换 → 拒绝
        dup = self.client.post("/api/activation/redeem", json={"code": code})
        self.assertEqual(dup.status_code, 400)
        self.assertEqual(dup.get_json()["error"]["code"], "ACTIVATION_CODE_USED")

    def test_redeem_rejects_duplicate_binding_via_constraint(self):
        """UNIQUE(code_id, account_id) 约束存在且生效"""
        self._seed_accounts(["dedup-test@example.com"])
        gen = self.client.post(
            "/api/admin/activation-codes/generate", json={"count": 1, "max_bindings": 5}
        ).get_json()
        code = gen["codes"][0]

        conn = sqlite3.connect(self.db_path)
        cid = conn.execute("SELECT id FROM activation_codes WHERE code=?", (code,)).fetchone()[0]
        aid = conn.execute("SELECT id FROM accounts LIMIT 1").fetchone()[0]
        conn.execute("INSERT INTO activation_code_bindings (code_id, account_id, user_id) VALUES (?,?,1)", (cid, aid))
        conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO activation_code_bindings (code_id, account_id, user_id) VALUES (?,?,1)", (cid, aid)
            )
        conn.rollback()
        conn.close()

    def test_redeem_rejects_disabled_code(self):
        gen = self.client.post(
            "/api/admin/activation-codes/generate", json={"count": 1, "max_bindings": 1}
        ).get_json()
        code = gen["codes"][0]

        listing = self.client.get("/api/admin/activation-codes").get_json()["codes"]
        code_id = next(r["id"] for r in listing if r["code"] == code)

        toggle = self.client.post(f"/api/admin/activation-codes/{code_id}/status", json={"status": "disabled"})
        self.assertEqual(toggle.status_code, 200)

        resp = self.client.post("/api/activation/redeem", json={"code": code})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["error"]["code"], "ACTIVATION_CODE_DISABLED")

        # 启用恢复
        back = self.client.post(f"/api/admin/activation-codes/{code_id}/status", json={"status": "active"})
        self.assertEqual(back.status_code, 200)

    def test_redeem_rejects_unknown_code(self):
        resp = self.client.post("/api/activation/redeem", json={"code": "ZZZZ-ZZZZ-ZZZZ"})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_json()["error"]["code"], "ACTIVATION_CODE_INVALID")

    def test_redeem_empty_mailbox_pool(self):
        """无未分配邮箱时 → NO_AVAILABLE_MAILBOX"""
        # 先把所有账号分配掉
        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE accounts SET owner_user_id=1 WHERE owner_user_id IS NULL")
        conn.commit()
        conn.close()

        try:
            gen = self.client.post(
                "/api/admin/activation-codes/generate", json={"count": 1, "max_bindings": 5}
            ).get_json()
            resp = self.client.post("/api/activation/redeem", json={"code": gen["codes"][0]})
            self.assertEqual(resp.status_code, 400)
            self.assertEqual(resp.get_json()["error"]["code"], "NO_AVAILABLE_MAILBOX")
        finally:
            conn = sqlite3.connect(self.db_path)
            conn.execute("UPDATE accounts SET owner_user_id=NULL WHERE owner_user_id=1")
            conn.commit()
            conn.close()

    def test_my_activations_lists_bindings(self):
        before = self._unassigned_count()
        if before < 1:
            self.skipTest("无未分配邮箱，跳过")

        gen = self.client.post(
            "/api/admin/activation-codes/generate", json={"count": 1, "max_bindings": 1}
        ).get_json()
        self.client.post("/api/activation/redeem", json={"code": gen["codes"][0]})

        resp = self.client.get("/api/activation/my")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.get_json()["bindings"]), 1)


if __name__ == "__main__":
    unittest.main()
