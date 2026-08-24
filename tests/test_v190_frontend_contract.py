from __future__ import annotations

import re
import unittest

from tests._import_app import import_web_app_module


class V190FrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = import_web_app_module()
        cls.app = cls.module.app

    def _login(self, client):
        resp = client.post("/login", json={"username": "admin", "password": "testpass123"})
        self.assertEqual(resp.status_code, 200)

    def _get_text(self, client, path):
        resp = client.get(path)
        try:
            return resp.data.decode("utf-8")
        finally:
            resp.close()

    def test_i18n_runtime_exposes_date_and_error_helpers(self):
        client = self.app.test_client()
        js = self._get_text(client, "/static/js/i18n.js")
        self.assertIn("window.formatUiDateTime", js)
        self.assertIn("window.formatUiRelativeTime", js)
        self.assertIn("window.resolveApiErrorMessage", js)
        self.assertIn("switcher-docked", js)
        self.assertIn("document.querySelector('.sidebar-bottom')", js)
        self.assertIn(
            "root.querySelectorAll('[placeholder],[title],[aria-label],input[type=\"button\"][value]')",
            js,
        )
        self.assertIn("const core = text.trim()", js)

    def test_i18n_skips_dynamic_business_scopes(self):
        client = self.app.test_client()
        js = self._get_text(client, "/static/js/i18n.js")

        self.assertIn("const I18N_SKIP_SELECTORS", js)
        self.assertIn("data-i18n-skip", js)
        for selector in [
            "#emailList",
            "#emailDetail",
            "#accountList",
            "#compactAccountList",
            "#refreshLogContainer",
            "#auditLogContainer",
        ]:
            self.assertIn(selector, js)

    @staticmethod
    def _norm(src: str) -> str:
        """压缩空白并把双引号归一为单引号，容忍格式化差异。"""
        return " ".join(src.split()).replace('"', "'")

    def test_main_js_does_not_override_i18n_runtime_helpers(self):
        client = self.app.test_client()
        main_js = self._get_text(client, "/static/js/main.js")
        norm = self._norm(main_js)
        self.assertIn("const pickApiMessage = (payload, fallbackZh, fallbackEn) =>", norm)
        self.assertIn("const formatUiDateTime = (dateStr, options = {}) =>", norm)
        # 格式化后参数拆行且委托 window.formatUiRelativeTime：只断言声明存在
        self.assertIn("const formatUiRelativeTime = (", norm)
        self.assertNotIn("function pickApiMessage(payload, fallbackZh, fallbackEn)", main_js)
        self.assertNotIn("function formatUiDateTime(dateStr, options = {})", main_js)
        self.assertNotIn(
            "function formatUiRelativeTime(dateStr, fallbackZh = '从未刷新', fallbackEn = 'Never refreshed')",
            main_js,
        )

    def test_frontend_no_longer_uses_raw_error_object_toasts_on_key_paths(self):
        client = self.app.test_client()
        main_js = self._get_text(client, "/static/js/main.js")
        accounts_js = self._get_text(client, "/static/js/features/accounts.js")
        self.assertNotIn("showToast(data.error || '创建失败'", main_js)
        self.assertNotIn("showToast(data.error || '删除失败'", main_js)
        self.assertNotIn("showToast(data.error || '操作失败'", main_js)
        self.assertNotIn("showToast(result.error, 'error')", accounts_js)

    def test_settings_and_login_pages_load_i18n_script(self):
        client = self.app.test_client()
        self._login(client)
        index_html = self._get_text(client, "/")
        login_html = self._get_text(client, "/login")
        self.assertIn("/static/js/i18n.js", index_html)
        self.assertIn("/static/js/i18n.js", login_html)
        # 格式化后属性分行：压缩空白再断言（语义不变）
        flat_index = " ".join(index_html.split())
        self.assertIn('id="telegramPollInterval" min="10" max="86400"', flat_index)
        for marker in (
            'id="webhookNotificationEnabled"',
            'id="webhookNotificationUrl"',
            'id="webhookNotificationToken"',
            'id="btnTestWebhookNotification"',
        ):
            self.assertIn(marker, index_html)

    def test_key_email_notification_translations_exist(self):
        client = self.app.test_client()
        js = self._get_text(client, "/static/js/i18n.js")
        for text in [
            "邮件通知",
            "启用邮件通知",
            "启用 Email 通知",
            "Email 通知",
            "Telegram 通知",
            "接收通知邮箱",
            "发送测试邮件",
            "导出",
            "全量刷新 Token",
            "＋ 添加账号",
            "验证码",
            "审计日志",
            "暂无审计记录",
            "加载审计日志失败",
            "手动",
            "定时",
            "邮件通知",
            "Email 通知",
            "Telegram 通知",
            "Telegram 推送",
            "这里只配置 Email 通知通道。普通邮箱需在账号列表开启通知后才会通过 Email 发送。启用后仅从新到达的邮件开始通知。",
            "这里只配置 Email 渠道的接收邮箱，不会让所有普通邮箱自动发送。",
            "这里只配置 Telegram 通知通道。普通邮箱需在账号列表开启通知后才会通过 Telegram 发送。",
            "验证当前 Telegram 通知通道是否配置正确",
            "通知",
            "该邮箱通知参与",
            "开启该邮箱通知参与",
            "该邮箱通知参与（已开启）",
            "该邮箱通知参与已开启",
            "该邮箱通知参与已关闭",
            "点击关闭该邮箱通知参与",
            "关闭时（默认）仅做 API Key 鉴权；开启后额外启用 IP 白名单、限流、高风险端点禁用等安全策略。",
            "建议设置为 30 天，防止 Token 因 90 天不使用而过期",
            "默认分组",
            "请从左侧选择一个邮箱账号",
            "表达式有效",
            "下次执行:",
            "验证失败:",
            "自动按类型分组",
            "请选择标签...",
            "请选择分组...",
            "轮询中",
            "输入新密码（留空则不修改）",
            "用于 /api/external/* 的 X-API-Key",
            "每行一个 IP 或 CIDR，如 192.168.1.0/24",
            "输入 Bot Token",
            "输入 Chat ID",
            "http://host:port 或 socks5://user:pass@host:port",
            "授权成功后，浏览器会跳转到一个空白页，请复制地址栏中的完整 URL 并粘贴到这里",
            "确定要刷新所有账号的 Token 吗？",
            "确定要删除这个标签吗？",
            "Cron 表达式",
            "收件箱",
            "垃圾邮件",
            "推送",
            "QQ邮箱",
            "163邮箱",
            "126邮箱",
            "阿里云邮箱",
            "自定义IMAP",
            "该分组暂无邮箱",
            "收件箱为空",
            "暂无邮件",
            "未知发件人",
            "勾选后，新导入的 Outlook/IMAP 账号会以 `available` 状态进入邮箱池；不勾选则保持池外。",
            "（每个邮箱刷新之间的等待时间）",
            "Webhook 通知",
            "启用 Webhook 通知",
            "Webhook URL",
            "Webhook Token（可选）",
            "测试 Webhook",
            "Webhook 测试成功",
            "Webhook 测试失败",
            "随机生成",
            "当前已存在 API Key，是否覆盖？",
        ]:
            self.assertIn(text, js)

    def test_frontend_success_toasts_use_pick_api_message_on_key_paths(self):
        client = self.app.test_client()
        accounts_js = self._get_text(client, "/static/js/features/accounts.js")
        groups_js = self._get_text(client, "/static/js/features/groups.js")
        main_js = self._get_text(client, "/static/js/main.js")
        self.assertIn("pickApiMessage(result, result.message", accounts_js)
        self.assertIn("pickApiMessage(data, data.message", groups_js)
        self.assertIn("pickApiMessage(data, data.message", main_js)

    def test_frontend_dynamic_options_and_placeholders_use_i18n_helpers(self):
        client = self.app.test_client()
        accounts_js = self._get_text(client, "/static/js/features/accounts.js")
        main_js = self._get_text(client, "/static/js/main.js")
        groups_js = self._get_text(client, "/static/js/features/groups.js")
        emails_js = self._get_text(client, "/static/js/features/emails.js")
        self.assertIn("translateAppTextLocal('自动按类型分组')", accounts_js)
        self.assertIn("translateAppTextLocal('支持混合格式，每行一个账号", accounts_js)
        norm_main_i18n = " ".join(main_js.split()).replace('"', "'")
        self.assertIn("translateAppTextLocal('请选择标签...')", norm_main_i18n)
        self.assertIn("translateAppTextLocal('请选择分组...')", norm_main_i18n)
        self.assertIn("translateAppTextLocal('通知')", groups_js)
        self.assertIn("translateAppTextLocal('点击关闭该邮箱通知参与')", groups_js)
        self.assertIn(
            "translateAppTextLocal(notificationEnabled ? '该邮箱通知参与（已开启）' : '开启该邮箱通知参与')",
            groups_js,
        )
        self.assertIn("translateAppTextLocal('收件箱为空')", emails_js)

    def test_frontend_email_list_sorting_fallback_is_present_on_all_key_paths(self):
        client = self.app.test_client()
        emails_js = self._get_text(client, "/static/js/features/emails.js")
        main_js = self._get_text(client, "/static/js/main.js")

        # helper contract: timestamp fallback chain + stable newest-first sort
        self.assertIn("function resolveEmailSortTimestamp(email)", emails_js)
        self.assertIn(
            "const rawDate = email && (email.receivedDateTime || email.date || email.created_at || email.received_at);",
            emails_js,
        )
        norm_emails = " ".join(emails_js.split()).replace('"', "'")
        norm_main = " ".join(main_js.split()).replace('"', "'")

        self.assertIn("return Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY;", norm_emails)
        self.assertIn("function sortEmailsByNewestFirst(list)", norm_emails)
        self.assertIn(".sort((a, b) => (b.timestamp - a.timestamp) || (a.index - b.index))", norm_emails)
        self.assertIn("window.sortEmailsByNewestFirst = sortEmailsByNewestFirst;", norm_emails)

        # loadEmails(): fetch path + cache recovery path
        self.assertIn("const sortedEmails = sortEmailsByNewestFirst(data.emails || []);", norm_emails)
        self.assertIn("currentEmails = sortEmailsByNewestFirst(cache.emails || []);", norm_emails)

        # loadMoreEmails(): merged pagination fallback in main.js（格式化后冗余括号被移除）
        self.assertIn("currentEmails = typeof sortEmailsByNewestFirst === 'function'", norm_main)
        self.assertIn("? sortEmailsByNewestFirst(mergedEmails)", norm_main)

        # switchFolder(): cache recovery fallback in main.js
        self.assertIn("? sortEmailsByNewestFirst(cache.emails || [])", norm_main)

        # selectAccount() in accounts.js: cache recovery must also sort
        accounts_js = self._get_text(client, "/static/js/features/accounts.js")
        self.assertIn("? sortEmailsByNewestFirst(cache.emails || [])", accounts_js)

    def test_notification_copy_matches_channel_vs_account_model(self):
        client = self.app.test_client()
        self._login(client)
        index_html = self._get_text(client, "/")
        groups_js = self._get_text(client, "/static/js/features/groups.js")

        # 格式化后长文案被换行拆开：压缩空白后匹配
        flat_html = " ".join(index_html.split())
        self.assertIn("Email 通知", flat_html)
        self.assertIn("Telegram 通知", flat_html)
        self.assertIn(
            "这里只配置 Email 通知通道。普通邮箱需在账号列表开启通知后才会通过 Email 发送。启用后仅从新到达的邮件开始通知。",
            flat_html,
        )
        self.assertIn("这里只配置 Email 渠道的接收邮箱，不会让所有普通邮箱自动发送。", flat_html)
        self.assertIn(
            "这里只配置 Telegram 通知通道。普通邮箱需在账号列表开启通知后才会通过 Telegram 发送。",
            flat_html,
        )
        self.assertNotIn(
            "全局生效，覆盖普通邮箱和临时邮箱；仅从启用后新到达的邮件开始通知。",
            index_html,
        )
        self.assertNotIn(
            "只需填写接收邮箱，不暴露复杂邮件网关配置。关闭通知后可保留该邮箱。",
            index_html,
        )
        self.assertIn("acc.notification_enabled !== undefined", groups_js)
        self.assertIn(
            "currentAccountSearchQuery = String(query || '').trim();",
            groups_js,
        )
        self.assertIn(
            "await loadAccountsByGroup(currentGroupId, true, 1);",
            groups_js,
        )

    def test_frontend_import_and_export_error_contract_helpers_are_consumed(self):
        client = self.app.test_client()
        accounts_js = self._get_text(client, "/static/js/features/accounts.js")
        main_js = self._get_text(client, "/static/js/main.js")
        self.assertIn("buildImportFailureToastMessage", accounts_js)
        self.assertIn("data.summary || Array.isArray(data.errors)", accounts_js)
        self.assertIn("if (verifyData.need_verify)", accounts_js)
        self.assertIn("if (data.need_verify)", accounts_js)
        norm_main_err = " ".join(main_js.split()).replace('"', "'")
        self.assertIn("translateAppTextLocal('【用户错误信息】')", norm_main_err)
        self.assertIn("translateAppTextLocal('【错误详情】')", norm_main_err)
        self.assertIn("translateAppTextLocal('【技术堆栈/细节】')", norm_main_err)

    def test_frontend_polling_settings_preserve_zero_value(self):
        client = self.app.test_client()
        self._login(client)
        main_js = self._get_text(client, "/static/js/main.js")
        index_html = self._get_text(client, "/")

        norm_main2 = " ".join(main_js.split()).replace('"', "'")
        self.assertIn("function parseIntegerSetting(value, fallback)", norm_main2)
        self.assertIn("let autoPollingEnabled = false;", norm_main2)
        self.assertIn("function applyPollingSettings(settings, { restart = false } = {}) {", norm_main2)
        # [Phase 3 兼容] 使用两个字段的或运算（格式化后可能换行）
        self.assertIn(
            "autoPollingEnabled = isAutoPollingEnabledSetting(settings.enable_auto_polling) || isAutoPollingEnabledSetting(settings.enable_compact_auto_poll);",
            norm_main2,
        )
        norm_main3 = " ".join(main_js.split()).replace('"', "'")
        flat_html = " ".join(index_html.split()).replace('"', "'")
        # 格式化后 String(...) 调用被拆行；压缩后应包含 parseIntegerSetting(data.settings.polling_count, 5) 且外层有 String(
        self.assertIn(
            "String( parseIntegerSetting(data.settings.polling_count, 5), )".replace(" ", ""), norm_main3.replace(" ", "")
        )
        self.assertIn("maxPollingCount = parseIntegerSetting(settings.polling_count, 5);", norm_main3)
        self.assertIn("applyPollingSettings(settings, { restart: true });", norm_main3)
        self.assertNotIn("data.settings.polling_count || '5'", norm_main3)
        self.assertNotIn("parseInt(data.settings.polling_count) || 5", norm_main3)
        self.assertIn("id='pollingCount' min='0' max='100' value='5'", flat_html)
        # 格式化后提示文本被换行拆开：压缩空白后匹配
        self.assertIn("范围：0-100 次，设置为 0 表示持续轮询", flat_html)

    def test_frontend_auto_polling_uses_shared_runtime_state_for_account_selection_and_email_load(
        self,
    ):
        """Phase 2: 轮询触发从'选中账号自动启动'改为'复制邮箱启动'，由统一引擎处理"""
        client = self.app.test_client()
        main_js = self._get_text(client, "/static/js/main.js")
        accounts_js = self._get_text(client, "/static/js/features/accounts.js")
        emails_js = self._get_text(client, "/static/js/features/emails.js")
        poll_engine_js = self._get_text(client, "/static/js/features/poll-engine.js")
        compact_js = self._get_text(client, "/static/js/features/mailbox_compact.js")

        # 统一引擎包含核心轮询逻辑
        self.assertIn("function startPoll(email, opts)", poll_engine_js)
        self.assertIn("function stopPoll(email, toastMsg, toastType)", poll_engine_js)
        self.assertIn("function stopAllPolls()", poll_engine_js)
        # email-copied 事件监听在 compact 适配层（现支持标准和简洁两种模式）
        self.assertIn("email-copied", compact_js)
        # 标准模式选中账号不再自动启动轮询（已删除 syncPollingForCurrentAccount）
        self.assertNotIn("syncPollingForCurrentAccount", accounts_js)
        self.assertNotIn("syncPollingForCurrentAccount", emails_js)
        # 临时邮箱切换使用统一引擎停止
        self.assertNotIn("fetch('/api/settings')", emails_js)

    def test_account_panel_density_sync_runs_on_init_and_mailbox_navigation(self):
        client = self.app.test_client()
        main_js = self._get_text(client, "/static/js/main.js")

        norm = self._norm(main_js)
        self.assertIn("let accountPanelDensitySyncHandle = null;", norm)
        self.assertIn("function syncAccountPanelDensityIfVisible()", norm)
        self.assertIn("function scheduleAccountPanelDensitySync()", norm)
        self.assertIn("syncAccountPanelDensityIfVisible();", norm)
        self.assertIn("scheduleAccountPanelDensitySync();", norm)
        self.assertRegex(
            norm.replace(", }", " }"),
            r"window\.addEventListener\('resize', scheduleAccountPanelDensitySync, \{ passive: true \}\);",
        )
        self.assertIn("if (page === 'mailbox') {", norm)

    def test_external_pool_settings_are_exposed_in_settings_page_and_saved_by_frontend(
        self,
    ):
        """邮箱池管理 UI 已从用户端移除（产品决策）：前端不再读写 pool_external_enabled 等字段。"""
        client = self.app.test_client()
        self._login(client)
        main_js = self._get_text(client, "/static/js/main.js")
        index_html = self._get_text(client, "/")

        for marker in (
            "poolExternalEnabledEl",
            "pool_external_enabled",
            "externalApiDisablePoolClaimRandom",
            'id="poolExternalEnabled"',
            'id="externalApiDisablePoolStats"',
        ):
            self.assertNotIn(marker, main_js)
            self.assertNotIn(marker, index_html)

    def test_account_edit_uses_conditional_outlook_credential_validation(self):
        client = self.app.test_client()
        accounts_js = self._get_text(client, "/static/js/features/accounts.js")
        self.assertIn("clientIdInput.dataset.originalValue = acc.client_id || '';", accounts_js)
        self.assertIn(
            "const wantsToUpdateOutlookCredentials = !isImap && (hasClientIdChanged || !!refreshToken);",
            accounts_js,
        )
        self.assertIn(
            "if (wantsToUpdateOutlookCredentials && (!data.client_id || !data.refresh_token))",
            accounts_js,
        )
        self.assertNotIn("if (!isImap && (!data.client_id || !data.refresh_token))", accounts_js)

    def test_collapsed_sidebar_hides_github_label_to_avoid_overlap(self):
        # GitHub 图标/按钮已从侧栏移除(用户需求),断言不再存在相关 CSS 与 i18n 键
        client = self.app.test_client()
        css = self._get_text(client, "/static/css/main.css")
        i18n_js = self._get_text(client, "/static/js/i18n.js")
        self.assertNotIn(".sidebar-collapsed .btn-github", css)
        self.assertNotIn("btn-github", css)
        self.assertNotIn("'GitHub'", i18n_js)
        self.assertNotIn("'☀ 浅色模式'", i18n_js)
        self.assertIn(".sidebar-collapsed #globalLanguageSwitcher.switcher-docked", i18n_js)

    def test_scroll_is_not_globally_locked_on_html_body(self):
        client = self.app.test_client()
        css = self._get_text(client, "/static/css/main.css")
        normalized = css.replace("\r\n", "\n")
        self.assertNotRegex(
            normalized,
            re.compile(r"html\\s*\\{[^}]*overflow:\\s*hidden;", re.MULTILINE),
        )
        self.assertNotRegex(
            normalized,
            re.compile(r"body\\s*\\{[^}]*overflow:\\s*hidden;", re.MULTILINE),
        )

    def test_watchtower_i18n_keys_removed(self):
        """一键更新功能已移除，相关 i18n 键不应存在；通用键保留"""
        client = self.app.test_client()
        i18n_js = self._get_text(client, "/static/js/i18n.js")
        main_js = self._get_text(client, "/static/js/main.js")

        # 一键更新相关键应已移除
        self.assertNotIn("Watchtower 检查完毕", i18n_js)
        self.assertNotIn("一键更新配置", i18n_js)
        self.assertNotIn("触发容器更新", i18n_js)
        self.assertNotIn("triggerUpdate", main_js)
        self.assertNotIn("testWatchtower", main_js)

        # 通用连通性测试键保留
        self.assertIn("'连通正常': 'Connection OK'", i18n_js)
        self.assertIn("'⏳ 测试中…': '⏳ Testing...'", i18n_js)
        self.assertIn("'基础': 'Basic'", i18n_js)
        self.assertIn("'API 安全': 'API Security'", i18n_js)
        self.assertIn("'自动化': 'Automation'", i18n_js)

        # main.js 中应使用 translateAppTextLocal 翻译连通性结果（格式化后引号可能为双引号）
        normalized_main = " ".join(main_js.split()).replace('"', "'")
        self.assertIn("translateAppTextLocal('⏳ 测试中…')", normalized_main)
