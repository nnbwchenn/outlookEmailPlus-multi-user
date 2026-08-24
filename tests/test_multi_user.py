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


class MemberSettingsTests(MultiUserBase):
    """成员端系统设置：修改自身密码 / 个人轮询偏好 / Telegram 测试 / 权限边界"""

    def test_member_change_own_password(self):
        with self.app.test_client() as admin_client:
            self._login(admin_client)
            self._create_member(admin_client, "pw_member", "memberpass1")

        with self.app.test_client() as member_client:
            self._login(member_client, "pw_member", "memberpass1")

            # 旧密码错误
            resp = member_client.put("/api/me/password", json={"old_password": "wrongpass1", "new_password": "newpass123"})
            self.assertEqual(resp.status_code, 400)

            # 新密码过短
            resp = member_client.put("/api/me/password", json={"old_password": "memberpass1", "new_password": "short"})
            self.assertEqual(resp.status_code, 400)

            # 正常修改
            resp = member_client.put("/api/me/password", json={"old_password": "memberpass1", "new_password": "newpass123"})
            self.assertEqual(resp.status_code, 200, resp.get_json())

        # 新密码可登录，旧密码不可登录
        with self.app.test_client() as c:
            resp = c.post("/login", json={"username": "pw_member", "password": "newpass123"})
            self.assertEqual(resp.status_code, 200)
            resp = c.post("/login", json={"username": "pw_member", "password": "memberpass1"})
            self.assertNotEqual(resp.status_code, 200)

    def test_member_polling_prefs(self):
        with self.app.test_client() as admin_client:
            self._login(admin_client)
            self._create_member(admin_client, "poll_member", "memberpass1")

        with self.app.test_client() as member_client:
            self._login(member_client, "poll_member", "memberpass1")

            # 默认值
            resp = member_client.get("/api/me/polling")
            polling = resp.get_json()["polling"]
            self.assertFalse(polling["enabled"])
            self.assertEqual(polling["interval"], 10)
            self.assertEqual(polling["max_count"], 5)

            # 非法值被拒绝
            resp = member_client.put("/api/me/polling", json={"enabled": True, "interval": 1, "max_count": 5})
            self.assertEqual(resp.status_code, 400)
            resp = member_client.put("/api/me/polling", json={"enabled": True, "interval": 30, "max_count": 999})
            self.assertEqual(resp.status_code, 400)

            # 正常保存 + 回读
            resp = member_client.put("/api/me/polling", json={"enabled": True, "interval": 30, "max_count": 8})
            self.assertEqual(resp.status_code, 200)
            polling = member_client.get("/api/me/polling").get_json()["polling"]
            self.assertTrue(polling["enabled"])
            self.assertEqual(polling["interval"], 30)
            self.assertEqual(polling["max_count"], 8)

        # bootstrap 对 member 返回个人轮询偏好（而非全局）
        with self.app.test_client() as member_client:
            self._login(member_client, "poll_member", "memberpass1")
            cookie = "; ".join(f"{k}={v}" for k, v in member_client._cookies.items())
            resp = member_client.get("/api/bootstrap", headers={"Cookie": cookie})
            bootstrap = resp.get_json()["bootstrap"]
            self.assertTrue(bootstrap["enable_auto_polling"])
            self.assertEqual(bootstrap["polling_interval"], 30)
            self.assertEqual(bootstrap["polling_count"], 8)

        # admin 的 bootstrap 使用全局轮询配置（不受 member 偏好影响）：
        # 全局值可能被其它测试修改过，这里只校验"与全局 settings 一致"而非固定 10
        with self.app.app_context():
            from outlook_web.repositories import settings as settings_repo

            expected_global_interval = int(settings_repo.get_setting("polling_interval", "10") or 10)
        with self.app.test_client() as admin_client:
            self._login(admin_client)
            cookie = "; ".join(f"{k}={v}" for k, v in admin_client._cookies.items())
            resp = admin_client.get("/api/bootstrap", headers={"Cookie": cookie})
            bootstrap = resp.get_json()["bootstrap"]
            self.assertEqual(bootstrap["polling_interval"], expected_global_interval)
        self.assertNotEqual(expected_global_interval, 30)

    def test_member_telegram_test_requires_config(self):
        with self.app.test_client() as admin_client:
            self._login(admin_client)
            self._create_member(admin_client, "tg_member", "memberpass1")

        with self.app.test_client() as member_client:
            self._login(member_client, "tg_member", "memberpass1")
            # 未配置时返回明确错误（不发起外部请求）
            resp = member_client.post("/api/me/notifications/telegram-test")
            self.assertEqual(resp.status_code, 400)
            self.assertEqual(resp.get_json()["error"]["code"], "TELEGRAM_NOT_CONFIGURED")

    def test_member_cannot_touch_admin_settings(self):
        with self.app.test_client() as admin_client:
            self._login(admin_client)
            self._create_member(admin_client, "iso_member", "memberpass1")

        with self.app.test_client() as member_client:
            self._login(member_client, "iso_member", "memberpass1")
            resp = member_client.get("/api/settings")
            self.assertEqual(resp.status_code, 403)
            resp = member_client.put("/api/settings", json={"external_api_key": "hack"})
            self.assertEqual(resp.status_code, 403)


class MemberExternalKeyTests(MultiUserBase):
    """成员级对外 API Key：创建/启停/删除/归属隔离/管理员替换不影响"""

    def _enable_external_api(self, client, user_id):
        resp = client.put(f"/api/users/{user_id}", json={"external_api_enabled": True})
        self.assertEqual(resp.status_code, 200, resp.get_json())

    def _assign_account_to_member(self, admin_client, member, email):
        acc_id = self._add_account(admin_client, email)
        resp = admin_client.post(
            "/api/users/assign",
            json={"owner_user_id": member["id"], "account_ids": [acc_id]},
        )
        self.assertEqual(resp.status_code, 200, resp.get_json())
        return acc_id

    def test_create_list_update_delete_key(self):
        with self.app.test_client() as admin_client:
            self._login(admin_client)
            member = self._create_member(admin_client, "key_member", "memberpass1")
            self._assign_account_to_member(admin_client, member, "own@test.com")
            self._enable_external_api(admin_client, member["id"])

        with self.app.test_client() as member_client:
            self._login(member_client, "key_member", "memberpass1")

            # 无名拒绝
            resp = member_client.post("/api/me/external-keys", json={"name": ""})
            self.assertEqual(resp.status_code, 400)

            # 创建：返回一次明文，范围锁定为自己邮箱，pool_access 关闭
            resp = member_client.post("/api/me/external-keys", json={"name": "my-script"})
            self.assertEqual(resp.status_code, 200, resp.get_json())
            key = resp.get_json()["key"]
            plain = key["api_key_plain"]
            self.assertTrue(plain.startswith("m_"))
            self.assertEqual(key["pool_access"], False)
            self.assertEqual(key["allowed_emails"], ["own@test.com"])
            self.assertNotEqual(key["api_key_masked"], plain)

            # 列表：只有脱敏值，无明文字段
            resp = member_client.get("/api/me/external-keys")
            keys = resp.get_json()["keys"]
            self.assertEqual(len(keys), 1)
            self.assertNotIn("api_key_plain", keys[0])
            self.assertEqual(keys[0]["api_key_masked"], key["api_key_masked"])

            # 明文查询
            resp = member_client.get(f"/api/me/external-keys/{key['id']}/plaintext")
            self.assertEqual(resp.get_json()["api_key"], plain)

            # 停用
            resp = member_client.put(f"/api/me/external-keys/{key['id']}", json={"enabled": False})
            self.assertEqual(resp.get_json()["key"]["enabled"], False)

            # 删除
            resp = member_client.delete(f"/api/me/external-keys/{key['id']}")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(len(member_client.get("/api/me/external-keys").get_json()["keys"]), 0)

    def test_member_without_accounts_cannot_create_key(self):
        with self.app.test_client() as admin_client:
            self._login(admin_client)
            member = self._create_member(admin_client, "noacc_member", "memberpass1")
            self._enable_external_api(admin_client, member["id"])

        with self.app.test_client() as member_client:
            self._login(member_client, "noacc_member", "memberpass1")
            resp = member_client.post("/api/me/external-keys", json={"name": "x"})
            self.assertEqual(resp.status_code, 400)
            self.assertEqual(resp.get_json()["error"]["code"], "NO_ASSIGNED_ACCOUNTS")

    def test_key_owner_isolation(self):
        with self.app.test_client() as admin_client:
            self._login(admin_client)
            member_a = self._create_member(admin_client, "iso_a", "memberpass1")
            member_b = self._create_member(admin_client, "iso_b", "memberpass1")
            self._assign_account_to_member(admin_client, member_a, "a-own@test.com")
            self._enable_external_api(admin_client, member_a["id"])
            self._enable_external_api(admin_client, member_b["id"])

        with self.app.test_client() as client_a:
            self._login(client_a, "iso_a", "memberpass1")
            resp = client_a.post("/api/me/external-keys", json={"name": "a-key"})
            key_id = resp.get_json()["key"]["id"]

        with self.app.test_client() as client_b:
            self._login(client_b, "iso_b", "memberpass1")
            # B 无法查看/启停/删除/取明文 A 的 Key
            resp = client_b.put(f"/api/me/external-keys/{key_id}", json={"enabled": False})
            self.assertEqual(resp.status_code, 404)
            resp = client_b.delete(f"/api/me/external-keys/{key_id}")
            self.assertEqual(resp.status_code, 404)
            resp = client_b.get(f"/api/me/external-keys/{key_id}/plaintext")
            self.assertEqual(resp.status_code, 404)
            self.assertEqual(len(client_b.get("/api/me/external-keys").get_json()["keys"]), 0)

    def test_admin_settings_hides_member_keys_and_replace_keeps_them(self):
        with self.app.test_client() as admin_client:
            self._login(admin_client)
            member = self._create_member(admin_client, "rp_member", "memberpass1")
            self._assign_account_to_member(admin_client, member, "rp@test.com")
            self._enable_external_api(admin_client, member["id"])

        with self.app.test_client() as member_client:
            self._login(member_client, "rp_member", "memberpass1")
            resp = member_client.post("/api/me/external-keys", json={"name": "member-key"})
            member_key_id = resp.get_json()["key"]["id"]

        with self.app.test_client() as admin_client:
            self._login(admin_client)
            # 管理员创建自己的全局 Key
            resp = admin_client.post("/api/users", json={"username": "nobody", "password": "nopass123"})
            admin_key_id = None
            # 通过 /api/settings 创建全局多 Key（走管理员保存接口）
            resp = admin_client.put(
                "/api/settings",
                json={"external_api_keys": [{"name": "global-a", "api_key": "global-key-plain-1", "enabled": True}]},
            )
            self.assertEqual(resp.status_code, 200, resp.get_json())

            # 管理员设置页看不到成员 Key
            settings = admin_client.get("/api/settings").get_json()["settings"]
            key_names = [k["name"] for k in settings["external_api_keys"]]
            self.assertIn("global-a", key_names)
            self.assertNotIn("member-key", key_names)

            # 管理员再次全量替换（删掉 global-a 换成 global-b），成员 Key 不受影响
            resp = admin_client.put(
                "/api/settings",
                json={"external_api_keys": [{"name": "global-b", "api_key": "global-key-plain-2", "enabled": True}]},
            )
            self.assertEqual(resp.status_code, 200)

        with self.app.test_client() as member_client:
            self._login(member_client, "rp_member", "memberpass1")
            keys = member_client.get("/api/me/external-keys").get_json()["keys"]
            self.assertEqual(len(keys), 1)
            self.assertEqual(keys[0]["name"], "member-key")
            self.assertEqual(keys[0]["id"], member_key_id)


class MemberExternalApiPermissionTests(MultiUserBase):
    """管理员按用户控制对外 API 开关与限流"""

    def setUp(self):
        super().setUp()
        # 清空限流桶（内存态，避免测试间污染）
        from outlook_web.security import auth as auth_module

        auth_module._MEMBER_EXTERNAL_RATE_BUCKETS.clear()

    def _enable(self, client, user_id, enabled=True, rate_limit=None):
        payload = {"external_api_enabled": enabled}
        if rate_limit is not None:
            payload["external_api_rate_limit"] = rate_limit
        return client.put(f"/api/users/{user_id}", json=payload)

    def test_disabled_by_default_create_and_use_blocked(self):
        with self.app.test_client() as admin_client:
            self._login(admin_client)
            member = self._create_member(admin_client, "perm_member", "memberpass1")
            acc_id = self._add_account(admin_client, "perm@test.com")
            admin_client.post("/api/users/assign", json={"owner_user_id": member["id"], "account_ids": [acc_id]})

        with self.app.test_client() as member_client:
            self._login(member_client, "perm_member", "memberpass1")
            # 默认未开通：创建被拒
            resp = member_client.post("/api/me/external-keys", json={"name": "k"})
            self.assertEqual(resp.status_code, 403)
            self.assertEqual(resp.get_json()["error"]["code"], "MEMBER_EXTERNAL_API_DISABLED")

    def test_admin_enable_rate_limit_and_disable(self):
        with self.app.test_client() as admin_client:
            self._login(admin_client)
            member = self._create_member(admin_client, "flow_member", "memberpass1")
            acc_id = self._add_account(admin_client, "flow@test.com")
            admin_client.post("/api/users/assign", json={"owner_user_id": member["id"], "account_ids": [acc_id]})

            # 非法限流值
            resp = self._enable(admin_client, member["id"], rate_limit=0)
            self.assertEqual(resp.status_code, 400)

            # 开通 + 限流 1 次/分钟
            resp = self._enable(admin_client, member["id"], enabled=True, rate_limit=1)
            self.assertEqual(resp.status_code, 200, resp.get_json())
            users = admin_client.get("/api/users").get_json()["users"]
            target = next(u for u in users if u["id"] == member["id"])
            self.assertTrue(target["external_api_enabled"])
            self.assertEqual(target["external_api_rate_limit"], 1)

        with self.app.test_client() as member_client:
            self._login(member_client, "flow_member", "memberpass1")
            resp = member_client.post("/api/me/external-keys", json={"name": "k"})
            self.assertEqual(resp.status_code, 200)
            plain = resp.get_json()["key"]["api_key_plain"]

            headers = {"X-API-Key": plain}
            r1 = member_client.get("/api/external/health", headers=headers)
            self.assertEqual(r1.status_code, 200, r1.get_json())
            # 超出限流（1 次/分钟）
            r2 = member_client.get("/api/external/health", headers=headers)
            self.assertEqual(r2.status_code, 429)
            self.assertEqual(r2.get_json()["code"], "RATE_LIMITED")

            # 列表接口返回权限状态
            listing = member_client.get("/api/me/external-keys").get_json()
            self.assertTrue(listing["external_api_enabled"])
            self.assertEqual(listing["external_api_rate_limit"], 1)

        # 管理员关闭后立即失效
        with self.app.test_client() as admin_client:
            self._login(admin_client)
            self._enable(admin_client, member["id"], enabled=False)

        with self.app.test_client() as member_client:
            headers = {"X-API-Key": plain}
            resp = member_client.get("/api/external/health", headers=headers)
            self.assertEqual(resp.status_code, 403)
            self.assertEqual(resp.get_json()["code"], "MEMBER_EXTERNAL_API_DISABLED")

    def test_admin_global_key_unaffected_by_member_toggle(self):
        with self.app.test_client() as admin_client:
            self._login(admin_client)
            member = self._create_member(admin_client, "iso2_member", "memberpass1")
            # 关闭成员权限不影响管理员 legacy 全局 Key
            resp = self._enable(admin_client, member["id"], enabled=False)
            self.assertEqual(resp.status_code, 200)
            # 管理员设置全局 Key
            resp = admin_client.put("/api/settings", json={"external_api_key": "admin-global-key-123"})
            self.assertEqual(resp.status_code, 200, resp.get_json())

        with self.app.test_client() as any_client:
            resp = any_client.get("/api/external/health", headers={"X-API-Key": "admin-global-key-123"})
            self.assertEqual(resp.status_code, 200, resp.get_json())
