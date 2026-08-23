import sys, unittest
from unittest import mock
sys.path.insert(0, '.')
from tests._import_app import import_web_app_module

class EmailBoxEmptyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()

    def test_short_circuit_returns_box_empty(self):
        """全阶段成功读取但 0 封 → EMAIL_BOX_EMPTY，不再尝试后续渠道"""
        from outlook_web.services import verification_channel_routing as vcr

        calls = []

        def fake_fetch(*, account, channel, proxy_url="", folder="", top=3, **kw):
            calls.append(channel)
            return {"success": True, "emails": [], "channel": channel}

        with self.module.app.test_request_context():
            account = {
                "id": 1,
                "email": "empty@example.com",
                "client_id": "cid",
                "refresh_token": "rt",
                "preferred_verification_channel": "",
                "group_id": None,
            }
            cache_mock = mock.MagicMock()
            cache_mock.filter_channel_plan.side_effect = lambda email, plan: plan
            with mock.patch.object(vcr, "fetch_emails_for_channel", side_effect=fake_fetch), \
                 mock.patch.object(vcr, "channel_capability_cache", cache_mock), \
                 mock.patch.object(vcr.graph_service, "get_access_token_graph_result",
                              return_value={"success": True, "scope": "Mail.Read offline_access", "new_refresh_token": None}):
                result = vcr.extract_verification_for_outlook(
                    account=account,
                    resolved_policy={"code_length": "6-6", "code_regex": None},
                )

        self.assertFalse(result["success"])
        self.assertEqual(result["error_code"], "EMAIL_BOX_EMPTY")
        # graph 阶段（inbox+junk）读完即短路，不应再试 IMAP
        self.assertNotIn("imap_new", calls)

if __name__ == "__main__":
    unittest.main()
