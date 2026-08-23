"""
统一验证码提取模块（ZER-90）

将验证码候选生成、评分、门控收敛为单一服务，供 Web API、External API、
简洁模式摘要及旧版 verification_extractor 兼容层共用。
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

# 验证码关键词列表（支持中英文；评分制下顺序不再敏感）
VERIFICATION_KEYWORDS = [
    "验证码",
    "code",
    "验证",
    "verification",
    "OTP",
    "动态码",
    "校验码",
    "verify code",
    "confirmation code",
    "security code",
    "验证码是",
    "your code",
    "code is",
    "激活码",
    "短信验证码",
    # 扩充：常见英文变体
    "one-time password",
    "one-time code",
    "one time code",
    "passcode",
    "login code",
    "access code",
    "auth code",
    "authentication code",
    "pin code",
    "verification code",
    # 扩充：繁体与其他中文变体
    "安全代码",
    "驗證碼",
    "驗證",
    "認證碼",
    "動態碼",
    "认证码",
    "动态密码",
]

VERIFICATION_PATTERN = r"(?<![A-Za-z0-9])[A-Z0-9]{4,8}(?![A-Za-z0-9])"
VERIFICATION_PATTERN_RE = re.compile(VERIFICATION_PATTERN, re.IGNORECASE)

# 带连字符字母数字验证码，例如 x.ai 的 84A-KMN
HYPHENATED_VERIFICATION_PATTERN = r"(?<![A-Z0-9])([A-Z0-9]{2,4}-[A-Z0-9]{2,4})(?=$|[^A-Z0-9-]|[A-Z][a-z])"

# 关键词窗口半径（字符数）：验证码通常出现在关键词附近
KEYWORD_WINDOW_RADIUS = 100

# 常见非验证码字母数字词（含数字的技术词汇等），直接排除
COMMON_NON_CODE_TOKENS = {
    "HTML5", "CSS3", "UTF8", "BASE64", "IPV4", "IPV6", "COVID19",
    "GPT3", "GPT4", "GPT5", "WIN10", "WIN11", "HTTP2", "HTTP3",
    "OAUTH2", "WEB3", "SHA256", "SHA512", "X86", "USB30", "TYPEC",
    "MD5", "CRC32", "PNG24", "H264", "H265", "OPUS", "MP3",
}

# 候选值紧邻其前的“标签”模式（如 “code:” “验证码是”），强结构信号
LABEL_BEFORE_CODE_RE = re.compile(
    r"(?:code|passcode|otp|pin|password|token|验证码|校验码|动态码|激活码|认证码|码|驗證碼)\s*"
    r"(?:is|are|为|是|=|:|：)?\s*$",
    re.IGNORECASE,
)

CODE_CONTEXT_PHRASES = [
    "validate your email",
    "validate your email address",
    "code below",
    "xai account",
    "x.ai",
    "support@x.ai",
    "verification code",
    "confirm your email",
    "verify your email",
    "your code",
    "the code below",
]

LINK_PATTERN = r'https?://[^\s<>"{}|\\^`\[\]]+'

# 邮件点击追踪/安全包装域名：这些链接不是真正的验证动作链接（真实链接被编码在查询参数里）
EMAIL_TRACKING_LINK_PATTERNS = (
    "awstrack.me",
    "protection.outlook.com",
    "safelinks",
    "/l0/https",          # AWS 追踪包装路径特征
    "click.track",
    "mailtrack",
    "canva.com/r/",
)

DEFAULT_LINK_KEYWORDS = [
    "verify",
    "confirmation",
    "confirm",
    "activate",
    "validation",
]

LINK_CONTEXT_PHRASES = [
    "verify your email",
    "verify your account",
    "verify your address",
    "confirm your email",
    "confirm your account",
    "confirm your address",
    "activate your email",
    "activate your account",
    "email verification",
    "account verification",
    "验证您的邮箱",
    "验证你的邮箱",
    "验证您的账户",
    "验证你的账户",
    "验证您的账号",
    "验证你的账号",
    "确认您的邮箱",
    "确认你的邮箱",
    "确认您的账户",
    "确认你的账户",
    "激活您的账户",
    "激活你的账户",
    "激活您的邮箱",
    "激活你的邮箱",
    "邮箱验证",
    "账号验证",
    "账户验证",
]


@dataclass
class VerificationPolicy:
    """验证码提取策略。"""

    code_regex: str | None = None
    code_length: str | None = None
    code_source: str = "all"
    prefer_link_keywords: list[str] = field(default_factory=lambda: list(DEFAULT_LINK_KEYWORDS))
    enforce_mutual_exclusion: bool = True
    apply_confidence_gate: bool = False
    expected_field: str | None = None  # code | link | any


@dataclass
class VerificationInput:
    """统一邮件输入：subject / 正文 / HTML 分离，避免直接扫描原始 HTML 样式。"""

    subject: str = ""
    body: str = ""
    body_preview: str = ""
    body_html: str = ""
    html_content: str = ""
    body_content: str = ""
    body_content_type: str = ""

    @classmethod
    def from_email_dict(cls, email: dict[str, Any]) -> VerificationInput:
        payload = email or {}
        return cls(
            subject=str(payload.get("subject") or "").strip(),
            body=str(payload.get("body") or "").strip(),
            body_preview=str(payload.get("body_preview") or "").strip(),
            body_html=str(payload.get("body_html") or payload.get("html_content") or "").strip(),
            html_content=str(payload.get("html_content") or "").strip(),
            body_content=str(payload.get("bodyContent") or "").strip(),
            body_content_type=str(payload.get("bodyContentType") or "").strip(),
        )

    def as_legacy_email_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "body": self.body,
            "body_preview": self.body_preview,
            "body_html": self.body_html or self.html_content,
            "html_content": self.html_content,
            "bodyContent": self.body_content,
            "bodyContentType": self.body_content_type,
        }


class HTMLTextExtractor(HTMLParser):
    """HTML 转纯文本提取器（跳过 style/script 等不可见节点）。"""

    def __init__(self) -> None:
        super().__init__()
        self.text_parts: list[str] = []
        self._skip_tags = {"style", "script", "head", "meta", "link"}
        self._current_skip = False

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag.lower() in self._skip_tags:
            self._current_skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._skip_tags:
            self._current_skip = False

    def handle_data(self, data: str) -> None:
        if not self._current_skip and data.strip():
            self.text_parts.append(data.strip())

    def get_text(self) -> str:
        return " ".join(self.text_parts)


def html_to_visible_text(html_content: str) -> str:
    if not html_content:
        return ""
    parser = HTMLTextExtractor()
    try:
        parser.feed(html_content)
        return html.unescape(parser.get_text() or "").strip()
    except Exception:
        return html_content.strip()


def extract_content_text_without_subject(email_input: VerificationInput) -> str:
    if email_input.body:
        return _normalize_text(email_input.body)

    html_raw = email_input.body_html or email_input.html_content
    if html_raw:
        return _normalize_text(html_to_visible_text(html_raw))

    if email_input.body_content:
        if email_input.body_content_type.lower() == "html":
            return _normalize_text(html_to_visible_text(email_input.body_content))
        return _normalize_text(email_input.body_content)

    if email_input.body_preview:
        return _normalize_text(email_input.body_preview)

    return ""


def extract_email_text(email: dict[str, Any]) -> str:
    email_input = VerificationInput.from_email_dict(email)
    content = extract_content_text_without_subject(email_input)
    if content:
        return content
    if email_input.subject:
        return email_input.subject
    return ""


def _parse_code_length(code_length: str) -> tuple[int, int]:
    m = re.match(r"^(\d+)-(\d+)$", str(code_length or "").strip())
    if not m:
        raise ValueError("code_length 参数无效")
    try:
        min_len = int(m.group(1))
        max_len = int(m.group(2))
    except (TypeError, ValueError) as exc:
        raise ValueError("code_length 参数无效") from exc
    if min_len <= 0 or max_len <= 0 or min_len > max_len:
        raise ValueError("code_length 参数无效")
    return min_len, max_len


def build_code_regex(*, code_regex: str | None, code_length: str | None) -> re.Pattern[str]:
    if code_regex:
        try:
            return re.compile(code_regex)
        except re.error as exc:
            raise ValueError("code_regex 参数无效") from exc

    if code_length:
        min_len, max_len = _parse_code_length(code_length)
        return re.compile(rf"(?<![A-Za-z0-9])[A-Za-z0-9]{{{min_len},{max_len}}}(?![A-Za-z0-9])")

    return re.compile(r"(?<!\d)\d{4,8}(?!\d)")


def _is_valid_hyphenated_code(code: str) -> bool:
    if not code or "-" not in code:
        return False

    parts = code.split("-")
    if len(parts) != 2:
        return False
    if not all(part.isalnum() for part in parts):
        return False

    alnum = "".join(parts)
    if not (4 <= len(alnum) <= 10):
        return False
    if any(c.isdigit() for c in alnum):
        return True
    return len(alnum) >= 6 and all(len(part) >= 3 for part in parts) and alnum.isalpha()


def _has_code_context(email_content: str) -> bool:
    content_lower = email_content.lower()
    return any(phrase.lower() in content_lower for phrase in CODE_CONTEXT_PHRASES)


# ==================== 候选评分机制（提高多候选场景准确率） ====================


def _normalize_text(text: str) -> str:
    """归一化干扰字符：零宽字符、NBSP、全角数字/冒号，避免验证码被拆断或漏匹配。"""
    if not text:
        return text or ""
    cleaned = text.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "").replace("\ufeff", "")
    cleaned = cleaned.replace("\u00a0", " ")
    for i, digit in enumerate("０１２３４５６７８９"):
        cleaned = cleaned.replace(digit, str(i))
    return cleaned.replace("：", ":")


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_year_like(value: str) -> bool:
    if not value.isdigit() or len(value) != 4:
        return False
    try:
        return 1900 <= int(value) <= 2100
    except ValueError:
        return False


def _is_hhmm_like(value: str) -> bool:
    if not value.isdigit() or len(value) != 4:
        return False
    try:
        hour, minute = int(value[:2]), int(value[2:])
    except ValueError:
        return False
    return 0 <= hour <= 23 and 0 <= minute <= 59


def _is_low_entropy_digits(value: str) -> bool:
    """低熵数字串：全同位或 ≥5 位连续递增/递减（如 000000 / 123456 / 654321），多为示例。"""
    if not value.isdigit() or len(value) < 5:
        return False
    if len(set(value)) == 1:
        return True
    try:
        digits = [int(c) for c in value]
    except ValueError:
        return False
    asc = all(digits[i + 1] - digits[i] == 1 for i in range(len(digits) - 1))
    desc = all(digits[i] - digits[i + 1] == 1 for i in range(len(digits) - 1))
    return asc or desc


def _score_candidate(
    value: str,
    *,
    standalone: bool,
    after_label: bool,
    in_keyword_window: bool,
) -> int | None:
    """给候选验证码打分；返回 None 表示直接排除。

    结构信号强于内容信号：独立成行 > 紧跟标签 > 关键词附近 > 内容特征。
    """
    if not any(c.isdigit() for c in value):
        return None
    if value.upper() in COMMON_NON_CODE_TOKENS:
        return None

    score = 0
    if standalone:
        score += 30
    if after_label:
        score += 25
    if in_keyword_window:
        score += 20

    if value.isdigit():
        length = len(value)
        if 4 <= length <= 8:
            score += 10
        if length == 6:
            score += 8
        elif length in (4, 8):
            score += 4
        if _is_year_like(value):
            score -= 30
        if _is_hhmm_like(value):
            score -= 25
    else:
        score += 6
        if "-" in value and _is_valid_hyphenated_code(value):
            score += 6

    if _is_low_entropy_digits(value):
        score -= 12
    return score


def _line_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for line in text.splitlines(True):
        spans.append((start, start + len(line)))
        start += len(line)
    if not spans:
        spans.append((0, len(text)))
    return spans


def _collect_scored_candidates(
    text: str,
    pattern: re.Pattern[str],
    *,
    use_keyword_windows: bool,
    require_keyword_window: bool,
) -> dict[str, dict[str, Any]]:
    """收集所有候选并评分，同值取最高分与最早出现位置。"""
    candidates: dict[str, dict[str, Any]] = {}
    spans = _line_spans(text)
    lowered_keywords = [k.lower() for k in VERIFICATION_KEYWORDS]

    for match in pattern.finditer(text):
        value = match.group(0) or ""
        pos = match.start()

        line_span = next(((s, e) for s, e in spans if s <= pos < e), (0, len(text)))
        line_text = text[line_span[0]:line_span[1]]
        standalone = line_text.strip() == value
        after_label = bool(LABEL_BEFORE_CODE_RE.search(text[line_span[0]:pos]))

        in_window = False
        if use_keyword_windows:
            window = text[max(0, pos - KEYWORD_WINDOW_RADIUS): min(len(text), pos + KEYWORD_WINDOW_RADIUS)]
            window_lower = window.lower()
            in_window = any(k in window_lower for k in lowered_keywords)
            if require_keyword_window and not in_window:
                continue

        score = _score_candidate(
            value,
            standalone=standalone,
            after_label=after_label,
            in_keyword_window=in_window,
        )
        if score is None or score <= 0:
            continue

        existing = candidates.get(value)
        if existing is None:
            candidates[value] = {"score": score, "pos": pos}
        else:
            existing["score"] = max(existing["score"], score)
            existing["pos"] = min(existing["pos"], pos)
    return candidates


def _best_scored_candidate(
    text: str,
    pattern: re.Pattern[str],
    *,
    use_keyword_windows: bool,
    require_keyword_window: bool = False,
) -> str | None:
    """取最高分候选；同分取最早出现的（邮件正文中先出现的通常是有效码）。"""
    if not text:
        return None
    candidates = _collect_scored_candidates(
        text,
        pattern,
        use_keyword_windows=use_keyword_windows,
        require_keyword_window=require_keyword_window,
    )
    if not candidates:
        return None
    best = max(candidates.items(), key=lambda item: (item[1]["score"], -item[1]["pos"]))
    return best[0]


def _find_hyphenated_code_in_text(text: str) -> str | None:
    if not text:
        return None

    for match in re.finditer(HYPHENATED_VERIFICATION_PATTERN, text, re.IGNORECASE):
        code = match.group(1)
        if _is_valid_hyphenated_code(code):
            return code
    return None


def smart_extract_hyphenated_verification_code(email_content: str) -> str | None:
    if not email_content:
        return None

    content_lower = email_content.lower()
    for keyword in VERIFICATION_KEYWORDS:
        keyword_lower = keyword.lower()
        pos = content_lower.find(keyword_lower)
        if pos == -1:
            continue

        start = max(0, pos - 50)
        end = min(len(email_content), pos + len(keyword) + 50)
        code = _find_hyphenated_code_in_text(email_content[start:end])
        if code:
            return code
    return None


def fallback_extract_hyphenated_verification_code(email_content: str) -> str | None:
    if not email_content or not _has_code_context(email_content):
        return None
    return _find_hyphenated_code_in_text(email_content)


def smart_extract_verification_code(email_content: str) -> str | None:
    if not email_content:
        return None

    code = _best_scored_candidate(email_content, VERIFICATION_PATTERN_RE, use_keyword_windows=True)
    if code:
        return code

    return smart_extract_hyphenated_verification_code(email_content)


def fallback_extract_verification_code(email_content: str) -> str | None:
    if not email_content:
        return None

    code = _best_scored_candidate(email_content, VERIFICATION_PATTERN_RE, use_keyword_windows=False)
    if code:
        return code

    return fallback_extract_hyphenated_verification_code(email_content)


def smart_extract_code_by_keywords(email_content: str, code_re: re.Pattern[str]) -> str | None:
    if not email_content:
        return None

    # 调用方指定 regex 时保持原语义：必须出现在关键词附近才采信
    return _best_scored_candidate(
        email_content,
        code_re,
        use_keyword_windows=True,
        require_keyword_window=True,
    )


def fallback_extract_code(email_content: str, code_re: re.Pattern[str]) -> str | None:
    if not email_content:
        return None

    return _best_scored_candidate(email_content, code_re, use_keyword_windows=False)


def extract_links(email_content: str) -> list[str]:
    if not email_content:
        return []

    cleaned_links = [link.rstrip(".,;:!?)>'\"") for link in re.findall(LINK_PATTERN, email_content, re.IGNORECASE)]
    cleaned_links = [
        link
        for link in cleaned_links
        if not any(pat in link.lower() for pat in EMAIL_TRACKING_LINK_PATTERNS)
    ]
    seen: set[str] = set()
    unique_links: list[str] = []
    for link in cleaned_links:
        if link not in seen:
            seen.add(link)
            unique_links.append(link)
    return unique_links


def pick_preferred_link(links: list[str], prefer_link_keywords: list[str]) -> str | None:
    if not links:
        return None

    keywords = [keyword.lower() for keyword in (prefer_link_keywords or []) if keyword]
    if keywords:
        for keyword in keywords:
            for link in links:
                if keyword in (link or "").lower():
                    return link
    return links[0]


def build_source_text(email_input: VerificationInput, *, code_source: str) -> tuple[str, str]:
    subject = _normalize_text(email_input.subject)
    content = extract_content_text_without_subject(email_input)
    html_raw = email_input.body_html or email_input.html_content

    source = str(code_source or "all").strip().lower()
    if source == "subject":
        return subject, "subject"
    if source == "content":
        return content, "content"
    if source == "html":
        return (_normalize_text(html_to_visible_text(html_raw)) if html_raw else ""), "html"
    return f"{subject} {content}".strip(), "all"


def extract_verification_code_from_text(
    source_text: str,
    *,
    code_regex: str | None,
    code_length: str | None,
) -> tuple[str | None, str]:
    code_re = build_code_regex(code_regex=code_regex, code_length=code_length)
    caller_directed_code = bool(code_regex)

    verification_code = smart_extract_code_by_keywords(source_text, code_re)
    code_confidence = "high" if verification_code else "low"

    if not verification_code:
        verification_code = fallback_extract_code(source_text, code_re)
        if verification_code and caller_directed_code:
            code_confidence = "high"

    if not verification_code:
        verification_code = smart_extract_hyphenated_verification_code(source_text)
        if verification_code:
            code_confidence = "high"

    if not verification_code:
        verification_code = fallback_extract_hyphenated_verification_code(source_text)
        if verification_code:
            code_confidence = "high"

    return verification_code, code_confidence


def extract_verification(
    email_input: VerificationInput,
    policy: VerificationPolicy | None = None,
) -> dict[str, Any]:
    """
    统一验证码/链接提取入口。

    返回字段与 extract_verification_info_with_options 兼容。
    """
    active_policy = policy or VerificationPolicy()
    source_text, match_source = build_source_text(email_input, code_source=active_policy.code_source)
    subject = email_input.subject
    content = extract_content_text_without_subject(email_input)
    html_raw = email_input.body_html or email_input.html_content

    verification_code, code_confidence = extract_verification_code_from_text(
        source_text,
        code_regex=active_policy.code_regex,
        code_length=active_policy.code_length,
    )

    links = extract_links(f"{subject} {content} {html_raw}".strip())
    prefer_keywords = active_policy.prefer_link_keywords or DEFAULT_LINK_KEYWORDS

    verification_link = None
    link_confidence = "low"
    should_pick_link = (not active_policy.enforce_mutual_exclusion) or (not verification_code)
    if should_pick_link:
        verification_link = pick_preferred_link(links, prefer_keywords)
        if verification_link:
            for keyword in prefer_keywords:
                if keyword and keyword.lower() in verification_link.lower():
                    link_confidence = "high"
                    break
            if link_confidence != "high":
                full_text_lower = f"{subject} {content}".lower()
                for phrase in LINK_CONTEXT_PHRASES:
                    if phrase.lower() in full_text_lower:
                        link_confidence = "high"
                        break

    confidence = "high" if code_confidence == "high" or link_confidence == "high" else "low"

    parts: list[str] = []
    if verification_code:
        parts.append(verification_code)
    if verification_link:
        parts.append(verification_link)
    formatted = " ".join(parts) if parts else None

    result = {
        "verification_code": verification_code,
        "verification_link": verification_link,
        "links": links,
        "formatted": formatted,
        "match_source": match_source,
        "confidence": confidence,
        "code_confidence": code_confidence,
        "link_confidence": link_confidence,
    }

    if active_policy.apply_confidence_gate:
        result = apply_confidence_gate(result, enforce_mutual_exclusion=active_policy.enforce_mutual_exclusion)

    expected_field = str(active_policy.expected_field or "").strip().lower()
    if expected_field == "code":
        result["verification_link"] = None
        result["link_confidence"] = "low"
        result["formatted"] = result.get("verification_code") or None
    elif expected_field == "link":
        result["verification_code"] = None
        result["code_confidence"] = "low"
        result["formatted"] = result.get("verification_link") or None

    return result


def apply_confidence_gate(extracted: dict[str, Any], *, enforce_mutual_exclusion: bool = True) -> dict[str, Any]:
    result = dict(extracted)

    if result.get("code_confidence") != "high":
        result["verification_code"] = None
    if result.get("link_confidence") != "high":
        result["verification_link"] = None

    if enforce_mutual_exclusion and result.get("verification_code"):
        result["verification_link"] = None
        result["link_confidence"] = "low"

    parts = [value for value in (result.get("verification_code"), result.get("verification_link")) if value]
    result["formatted"] = " ".join(parts) if parts else None
    result["confidence"] = (
        "high" if result.get("code_confidence") == "high" or result.get("link_confidence") == "high" else "low"
    )
    return result


def policy_from_resolved(
    resolved: dict[str, Any] | None,
    *,
    code_source: str = "all",
    enforce_mutual_exclusion: bool = True,
    apply_confidence_gate: bool = False,
    expected_field: str | None = None,
) -> VerificationPolicy:
    payload = resolved or {}
    return VerificationPolicy(
        code_regex=payload.get("code_regex"),
        code_length=payload.get("code_length"),
        code_source=code_source,
        enforce_mutual_exclusion=enforce_mutual_exclusion,
        apply_confidence_gate=apply_confidence_gate,
        expected_field=expected_field,
    )


def extract_verification_from_email_dict(
    email: dict[str, Any],
    *,
    code_regex: str | None = None,
    code_length: str | None = None,
    code_source: str = "all",
    prefer_link_keywords: list[str] | None = None,
    enforce_mutual_exclusion: bool = True,
    apply_confidence_gate_after: bool = False,
) -> dict[str, Any]:
    """兼容旧 extract_verification_info_with_options 签名的薄封装。"""
    policy = VerificationPolicy(
        code_regex=code_regex,
        code_length=code_length,
        code_source=code_source,
        prefer_link_keywords=list(prefer_link_keywords or DEFAULT_LINK_KEYWORDS),
        enforce_mutual_exclusion=enforce_mutual_exclusion,
        apply_confidence_gate=apply_confidence_gate_after,
    )
    return extract_verification(VerificationInput.from_email_dict(email), policy)
