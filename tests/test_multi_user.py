"""多用户模式 — 用户管理 / 邮箱分配 / 权限隔离测试"""

import unittest

from tests._import_app import clear_login_attempts, import_web_app_module


class MultiUserBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def setUp(self):
        with self.app.app_context():
            from outlook_web.db import get_db
            from outlook_web.repositories import users as users_repo

            clear_login_attempts()
            # 清理账号（避免测试间统计累积）
            db = get_db()
            db.execute("DELETE FROM accounts")
            db.commit()
            # 确保 admin 存在且密码为 testpass123
            admin = users_repo.get_user_by_username("admin")
            if admin:
                users_repo.update_user(admin["id"], password="testpass123")
            # 清理测试用户
            for u in users_repo.list_users():
                if u["username"] != "admin":
                    users_repo.delete_user(u["id"])

    def _login(self, client, username="admin", password="testpass123"):
        resp = client.post("/login", json={"username": username, "password": password})
        self.assertEqual(resp.status_code, 200, resp.get_json())
        return resp

    def _create_member(self, client, username="member1", password="memberpass1"):
        resp = client.post(
            "/api/users",
            json={"username": username, "password": password, "role": "member", "display_name": "测试成员"},
        )
        self.assertEqual(resp.status_code, 200, resp.get_json())
        return resp.get_json().get("user")

    def _add_account(self, client, email):
        resp = client.post(
            "/api/accounts",
            json={"account_string": f"{email}----dummy-pass----dummy-cid----dummy-rt"},
        )
        self.assertEqual(resp.status_code, 200, resp.get_json())
        with self.app.app_context():
            from outlook_web.repositories import accounts as accounts_repo

            account = accounts_repo.get_account_by_email(email)
            return account["id"] if account else None


class UserManagementTests(MultiUserBase):
    def test_me_returns_role(self):
        with self.app.test_client() as client:
            self._login(client)
            resp = client.get("/api/me")
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertTrue(data["success"])
            self.assertEqual(data["user"]["username"], "admin")
            self.assertEqual(data["user"]["role"], "admin")

    def test_me_requires_login(self):
        with self.app.test_client() as client:
            resp = client.get("/api/me")
            self.assertEqual(resp.status_code, 401)

    def test_create_list_update_delete_user(self):
        with self.app.test_client() as client:
            self._login(client)
            user = self._create_member(client)

            # 列表
            resp = client.get("/api/users")
            self.assertEqual(resp.status_code, 200)
            users = resp.get_json()["users"]
            usernames = [u["username"] for u in users]
            self.assertIn("admin", usernames)
            self.assertIn("member1", usernames)

            # 更新：禁用 + 重置密码
            resp = client.put(
                f"/api/users/{user['id']}",
                json={"status": "disabled", "password": "newpass1234"},
            )
            self.assertEqual(resp.status_code, 200, resp.get_json())

            # 禁用后无法登录
            client2 = self.app.test_client()
            resp2 = client2.post("/login", json={"username": "member1", "password": "newpass1234"})
            self.assertEqual(resp2.status_code, 401)

            # 删除
            resp = client.delete(f"/api/users/{user['id']}")
            self.assertEqual(resp.status_code, 200, resp.get_json())

    def test_member_cannot_manage_users(self):
        with self.app.test_client() as admin_client:
            self._login(admin_client)
            self._create_member(admin_client)

        with self.app.test_client() as member_client:
            self._login(member_client, "member1", "memberpass1")
            resp = member_client.get("/api/users")
            self.assertEqual(resp.status_code, 403)
            resp2 = member_client.post("/api/users", json={"username": "x", "password": "12345678"})
            self.assertEqual(resp2.status_code, 403)


class AccountAssignmentTests(MultiUserBase):
    def test_assign_and_isolate(self):
        with self.app.test_client() as admin_client:
            self._login(admin_client)
            user = self._create_member(admin_client)
            acc_id = self._add_account(admin_client, "assigned@test.com")
            acc2_id = self._add_account(admin_client, "other@test.com")

            # 分配一个邮箱给 member
            resp = admin_client.post("/api/users/assign", json={"owner_user_id": user["id"], "account_ids": [acc_id]})
            self.assertEqual(resp.status_code, 200, resp.get_json())

            # 查看该用户账号
            resp = admin_client.get(f"/api/users/{user['id']}/accounts")
            emails = [a["email"] for a in resp.get_json()["accounts"]]
            self.assertIn("assigned@test.com", emails)
            self.assertNotIn("other@test.com", emails)

        # member 登录：只能看到自己的邮箱
        with self.app.test_client() as member_client:
            self._login(member_client, "member1", "memberpass1")
            resp = member_client.get("/api/accounts")
            self.assertEqual(resp.status_code, 200)
            emails = [a["email"] for a in resp.get_json().get("accounts", [])]
            self.assertIn("assigned@test.com", emails)
            self.assertNotIn("other@test.com", emails)

            # member 访问他人账号详情 -> 404
            resp = member_client.get(f"/api/accounts/{acc2_id}")
            self.assertEqual(resp.status_code, 404)

            # member 访问自己账号详情 -> 200
            resp = member_client.get(f"/api/accounts/{acc_id}")
            self.assertEqual(resp.status_code, 200)

    def test_member_cannot_add_or_delete_accounts(self):
        with self.app.test_client() as admin_client:
            self._login(admin_client)
            user = self._create_member(admin_client)

        with self.app.test_client() as member_client:
            self._login(member_client, "member1", "memberpass1")
            # 添加账号 -> 403
            resp = member_client.post(
                "/api/accounts",
                json={"email": "hack@test.com", "password": "x", "client_id": "x", "refresh_token": "x"},
            )
            self.assertEqual(resp.status_code, 403)
            # 删除账号 -> 403
            resp = member_client.delete("/api/accounts/1")
            self.assertEqual(resp.status_code, 403)

    def test_member_cannot_access_admin_modules(self):
        with self.app.test_client() as admin_client:
            self._login(admin_client)
            self._create_member(admin_client)

        with self.app.test_client() as member_client:
            self._login(member_client, "member1", "memberpass1")
            # Token 工具 prepare -> 403
            resp = member_client.post("/api/token-tool/prepare", json={"client_id": "x"})
            self.assertEqual(resp.status_code, 403)
            # 系统设置 -> 403
            resp = member_client.get("/api/settings")
            self.assertEqual(resp.status_code, 403)
            # 审计日志 -> 403
            resp = member_client.get("/api/audit-logs")
            self.assertEqual(resp.status_code, 403)
            # 邮箱池 -> 403
            resp = member_client.get("/api/pool-admin/accounts")
            self.assertEqual(resp.status_code, 403)


class MemberEmailAccessTests(MultiUserBase):
    def test_member_reads_own_email_but_not_others(self):
        with self.app.test_client() as admin_client:
            self._login(admin_client)
            user = self._create_member(admin_client)
            acc_id = self._add_account(admin_client, "mine@test.com")
            acc2_id = self._add_account(admin_client, "notmine@test.com")
            admin_client.post("/api/users/assign", json={"owner_user_id": user["id"], "account_ids": [acc_id]})

        with self.app.test_client() as member_client:
            self._login(member_client, "member1", "memberpass1")
            # 自己邮箱 -> 可访问（200/404/502 均可：dummy token 无效属预期）
            resp = member_client.get("/api/emails/mine@test.com")
            self.assertIn(resp.status_code, (200, 404, 502))
            # 他人邮箱 -> 404（归属校验）
            resp = member_client.get("/api/emails/notmine@test.com")
            self.assertEqual(resp.status_code, 404)
            # 验证码提取他人邮箱 -> 404
            resp = member_client.get("/api/emails/notmine@test.com/verification")
            self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()


class MemberOverviewIsolationTests(MultiUserBase):
    """成员数据概览：只统计自己被分配的邮箱"""

    def test_member_summary_only_counts_own_accounts(self):
        with self.app.test_client() as admin_client:
            self._login(admin_client)
            user = self._create_member(admin_client, "ov_member", "memberpass1")
            # 添加 3 个邮箱：2 个给 member，1 个留在管理员全局
            acc_ids = []
            for i in range(3):
                email = f"ov{i}@test.com"
                self._add_account(admin_client, email)
                with self.app.app_context():
                    from outlook_web.repositories import accounts as accounts_repo

                    acc = accounts_repo.get_account_by_email(email)
                    if acc:
                        acc_ids.append(acc["id"])
            # 分配前 2 个给 member
            admin_client.post(
                "/api/users/assign",
                json={"owner_user_id": user["id"], "account_ids": acc_ids[:2]},
            )

        with self.app.test_client() as member_client:
            self._login(member_client, "ov_member", "memberpass1")
            # OverviewAwareFlaskClient 会清空 overview 请求的 cookie，需显式带上会话 Cookie
            cookie = "; ".join(f"{k}={v}" for k, v in member_client._cookies.items())
            resp = member_client.get("/api/overview/summary", headers={"Cookie": cookie})
            self.assertEqual(resp.status_code, 200)
            summary = resp.get_json()
            account_status = summary.get("account_status") or {}
            self.assertEqual(account_status.get("total"), 2, summary)

        with self.app.test_client() as admin_client2:
            self._login(admin_client2)
            cookie2 = "; ".join(f"{k}={v}" for k, v in admin_client2._cookies.items())
            resp = admin_client2.get("/api/overview/summary", headers={"Cookie": cookie2})
            summary = resp.get_json()
            account_status = summary.get("account_status") or {}
            self.assertEqual(account_status.get("total"), 3, summary)

    def test_member_pool_stats_empty(self):
        with self.app.test_client() as admin_client:
            self._login(admin_client)
            user = self._create_member(admin_client, "ov_member2", "memberpass1")

        with self.app.test_client() as member_client:
            self._login(member_client, "ov_member2", "memberpass1")
            cookie = "; ".join(f"{k}={v}" for k, v in member_client._cookies.items())
            resp = member_client.get("/api/overview/pool", headers={"Cookie": cookie})
            self.assertEqual(resp.status_code, 200)
            kpi = resp.get_json().get("kpi") or {}
            self.assertEqual(kpi.get("available"), 0)
            self.assertEqual(kpi.get("in_use"), 0)
