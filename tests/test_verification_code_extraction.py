"""ZER-90：统一验证码提取模块测试。"""

from __future__ import annotations

import unittest

from outlook_web.services.verification_code_extraction import (
    VerificationInput,
    VerificationPolicy,
    apply_confidence_gate,
    extract_verification,
    extract_verification_from_email_dict,
)


class VerificationCodeExtractionModuleTests(unittest.TestCase):
    def test_extract_lowercase_alphanumeric_code_with_policy_length(self):
        email = VerificationInput(subject="Your verification code", body="Your verification code is ab12cd")
        policy = VerificationPolicy(code_length="6-6", code_source="all")

        result = extract_verification(email, policy)

        self.assertEqual(result.get("verification_code"), "ab12cd")
        self.assertEqual(result.get("code_confidence"), "high")

    def test_extract_preserves_mixed_case(self):
        email = VerificationInput(body="Your verification code is Ab12Cd")
        policy = VerificationPolicy(code_length="6-6")

        result = extract_verification(email, policy)

        self.assertEqual(result.get("verification_code"), "Ab12Cd")

    def test_extract_html_ignores_css_color_and_keeps_hyphen_code(self):
        email = VerificationInput(
            subject="Verification",
            body_html=(
                "<html><head><style>.title { color: #333333; }</style></head><body>"
                "<p>Your verification code is 84A-KMN</p>"
                "</body></html>"
            ),
        )
        policy = VerificationPolicy(code_length="6-6", code_source="all")

        result = extract_verification(email, policy)

        self.assertEqual(result.get("verification_code"), "84A-KMN")
        self.assertEqual(result.get("code_confidence"), "high")

    def test_apply_confidence_gate_strips_low_confidence_code(self):
        raw = {
            "verification_code": "123456",
            "verification_link": None,
            "code_confidence": "low",
            "link_confidence": "low",
        }
        gated = apply_confidence_gate(raw, enforce_mutual_exclusion=False)
        self.assertIsNone(gated.get("verification_code"))

    def test_expected_field_code_filters_link(self):
        email = VerificationInput(
            body="Your verification code is 123456 https://example.com/verify",
        )
        policy = VerificationPolicy(code_length="6-6", expected_field="code")

        result = extract_verification(email, policy)

        self.assertEqual(result.get("verification_code"), "123456")
        self.assertIsNone(result.get("verification_link"))
        self.assertEqual(result.get("formatted"), "123456")

    def test_legacy_wrapper_matches_unified_extractor(self):
        email = {
            "subject": "Validate your email",
            "body": "Please use the code below to validate your email address.\n\n84A-KMN",
        }

        unified = extract_verification(VerificationInput.from_email_dict(email), VerificationPolicy())
        legacy = extract_verification_from_email_dict(email)

        self.assertEqual(legacy.get("verification_code"), unified.get("verification_code"))
        self.assertEqual(legacy.get("code_confidence"), unified.get("code_confidence"))


if __name__ == "__main__":
    unittest.main()


class VerificationExtractionAccuracyTests(unittest.TestCase):
    """验证码提取精进：候选评分 / 文本归一化 / 结构信号 / 词表扩充"""

    def test_standalone_line_code_preferred_over_inline_number(self):
        """独立成行的候选优先于行内普通数字（如订单号）"""
        email = VerificationInput(
            subject="Your order confirmation",
            body="Order 90812 has been received.\n\n736452\n\nUse this code to log in.",
        )
        result = extract_verification(email, VerificationPolicy())
        self.assertEqual(result.get("verification_code"), "736452")

    def test_labeled_code_beats_earlier_random_number(self):
        """紧跟标签（code: / 验证码是）的候选优先于更早出现的无关数字"""
        email = VerificationInput(body="Invoice 55123 was paid. Your login code: 482913")
        result = extract_verification(email, VerificationPolicy())
        self.assertEqual(result.get("verification_code"), "482913")

    def test_zero_width_chars_do_not_break_code(self):
        """零宽字符不会拆断验证码"""
        email = VerificationInput(subject="Code", body="Your code is 12\u200b3456 today")
        result = extract_verification(email, VerificationPolicy(code_length="6-6"))
        self.assertEqual(result.get("verification_code"), "123456")

    def test_fullwidth_digits_normalized(self):
        """全角数字归一化为半角"""
        email = VerificationInput(subject="验证", body="您的验证码是１２３４５６，请勿泄露。")
        result = extract_verification(email, VerificationPolicy())
        self.assertEqual(result.get("verification_code"), "123456")

    def test_common_tech_tokens_not_misdetected(self):
        """含数字的常见技术词不被误判为验证码"""
        email = VerificationInput(
            subject="Release notes",
            body="Now supports BASE64 and SHA256 hashing. Your verification code is 654987.",
        )
        result = extract_verification(email, VerificationPolicy())
        self.assertEqual(result.get("verification_code"), "654987")

    def test_expanded_keywords_passcode_and_one_time(self):
        """扩充关键词：passcode / one-time code 可命中"""
        r1 = extract_verification(
            VerificationInput(subject="Sign in", body="Your passcode is 882211 and expires soon."),
            VerificationPolicy(),
        )
        self.assertEqual(r1.get("verification_code"), "882211")

        r2 = extract_verification(
            VerificationInput(subject="Login", body="Use the one-time code 553321 to continue."),
            VerificationPolicy(),
        )
        self.assertEqual(r2.get("verification_code"), "553321")

    def test_low_entropy_penalty_prefers_real_code(self):
        """低熵惩罚：示例码 123456 与真实码并存时优先真实码"""
        email = VerificationInput(
            subject="Demo",
            body="Example: 123456. Your actual verification code is 719384.",
        )
        result = extract_verification(email, VerificationPolicy())
        self.assertEqual(result.get("verification_code"), "719384")

    def test_code_after_newline_label_window(self):
        """标签后换行再跟验证码（窗口放宽到 ±100 字符）仍可命中"""
        email = VerificationInput(
            subject="Verify",
            body="To finish, enter the verification code:\n\n      628411\n\nThank you.",
        )
        result = extract_verification(email, VerificationPolicy())
        self.assertEqual(result.get("verification_code"), "628411")


if __name__ == "__main__":
    unittest.main()
