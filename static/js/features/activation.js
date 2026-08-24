// ==================== 激活码（管理员生成管理 + 用户端兑换） ====================

function _acEsc(text) {
    return String(text == null ? "" : text).replace(
        /[&<>"']/g,
        (c) =>
            ({
                "&": "&amp;",
                "<": "&lt;",
                ">": "&gt;",
                '"': "&quot;",
                "'": "&#39;",
            })[c],
    );
}

function _acCopyText(text, btn) {
    const done = () => {
        if (!btn) return;
        const old = btn.textContent;
        btn.textContent = "已复制";
        setTimeout(() => (btn.textContent = old), 1200);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard
            .writeText(text)
            .then(done)
            .catch(() => {});
    } else {
        const ta = document.createElement("textarea");
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        ta.remove();
        done();
    }
}

// ---------- 页面渲染：按角色切换管理/兑换视图 ----------
function renderActivationPage() {
    const isAdmin = typeof isAdminUser === "function" && isAdminUser();
    const adminView = document.getElementById("acAdminView");
    const memberView = document.getElementById("acMemberView");
    if (!adminView || !memberView) return;
    adminView.style.display = isAdmin ? "" : "none";
    memberView.style.display = isAdmin ? "none" : "";
    if (isAdmin) {
        acLoadCodes();
    } else {
        _acLoadMyBindings();
    }
}

function _acSetStatus(text, kind) {
    const el = document.getElementById("acRedeemStatus");
    if (!el) return;
    el.textContent = text;
    el.className =
        "token-status " +
        (kind === "error" ? "error" : kind === "success" ? "success" : "");
    el.classList.remove("hidden");
}

async function acRedeemSubmit() {
    const input = document.getElementById("acRedeemInput");
    const btn = document.getElementById("acRedeemBtn");
    const resultEl = document.getElementById("acRedeemResult");
    const code = (input?.value || "").trim().toUpperCase();
    if (!code) {
        _acSetStatus("请输入激活码", "error");
        return;
    }
    if (btn) {
        btn.disabled = true;
        btn.textContent = "激活中…";
    }
    resultEl.style.display = "none";
    try {
        const res = await fetch("/api/activation/redeem", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ code }),
        });
        const data = await res.json();
        if (data.success) {
            _acSetStatus(data.message || "激活成功", "success");
            const box = document.createElement("div");
            box.style.cssText =
                "margin-top:4px;font-size:0.8rem;color:var(--text-secondary);";
            box.textContent = "已绑定的邮箱：";
            const ul = document.createElement("ul");
            ul.style.cssText = "margin:4px 0 0 1.2rem;padding:0;";
            for (const b of data.bound || []) {
                const li = document.createElement("li");
                li.style.cssText =
                    "font-family:var(--font-mono, monospace);font-size:0.78rem;";
                li.textContent = b.email; // textContent 天然防 XSS
                ul.appendChild(li);
            }
            resultEl.replaceChildren(box, ul);
            resultEl.style.display = "block";
            input.value = "";
            _acLoadMyBindings(); // 刷新已激活清单
            // 刷新邮箱列表与总览（新邮箱已归属当前用户）
            try {
                if (
                    typeof currentGroupId !== "undefined" &&
                    typeof loadAccountsByGroup === "function"
                ) {
                    await loadAccountsByGroup(currentGroupId, true, 1);
                }
                if (typeof window.notifyOverviewDataChanged === "function") {
                    window.notifyOverviewDataChanged(
                        ["summary"],
                        "activation-redeemed",
                    );
                }
            } catch (_e) {}
        } else {
            _acSetStatus(
                (data.error && data.error.message) || "激活失败",
                "error",
            );
        }
    } catch (_e) {
        _acSetStatus("网络错误，请重试", "error");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = "立即激活";
        }
    }
}

async function _acLoadMyBindings() {
    const listEl = document.getElementById("acMyBindingsList");
    if (!listEl) return;
    try {
        const res = await fetch("/api/activation/my");
        const data = await res.json();
        const rows = data.bindings || [];
        if (!rows.length) {
            listEl.textContent = "还没有通过激活码绑定的邮箱";
            return;
        }
        listEl.innerHTML = rows
            .map((r) => `<div style="display:flex;justify-content:space-between;gap:8px;padding:2px 0;">` +
                        `<span style="font-family:var(--font-mono, monospace);">${_acEsc(r.email)}</span>` +
                        `<span style="color:var(--text-muted);white-space:nowrap;">${_acEsc(String(r.created_at || "").slice(0, 10))}</span></div>`)
            .join("");
    } catch (_e) {
        listEl.textContent = "加载失败";
    }
}

// ---------- 管理端：生成 + 列表管理 ----------
async function acGenerate() {
    const countEl = document.getElementById("acGenCount");
    const bindEl = document.getElementById("acGenBindings");
    const resultEl = document.getElementById("acGenResult");
    const copyWrap = document.getElementById("acGenCopyWrap");
    const statusEl = document.getElementById("acGenStatus");
    const count = parseInt(countEl?.value || "0", 10);
    const maxBindings = parseInt(bindEl?.value || "0", 10);

    const showStatus = (text, ok) => {
        if (!statusEl) return;
        statusEl.textContent = text;
        statusEl.style.color = ok
            ? "var(--clr-success, #2e9e5b)"
            : "var(--clr-danger, #d64545)";
    };

    if (!(count >= 1 && count <= 200)) {
        showStatus("生成数量需在 1-200 之间", false);
        return;
    }
    if (!(maxBindings >= 1 && maxBindings <= 100)) {
        showStatus("绑定邮箱数需在 1-100 之间", false);
        return;
    }

    showStatus("生成中…", true);
    try {
        const res = await fetch("/api/admin/activation-codes/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ count, max_bindings: maxBindings }),
        });
        const data = await res.json();
        if (!data.success) {
            showStatus((data.error && data.error.message) || "生成失败", false);
            return;
        }
        const joined = (data.codes || []).join("\n");
        if (resultEl) {
            resultEl.value = joined;
            resultEl.hidden = false;
        }
        if (copyWrap) copyWrap.hidden = false;
        showStatus(
            `已生成 ${data.codes.length} 个激活码（每个可绑 ${data.max_bindings} 个邮箱），请复制保存`,
            true,
        );
        acLoadCodes();
    } catch (_e) {
        showStatus("网络错误，请重试", false);
    }
}

function acCopyGenerated() {
    const resultEl = document.getElementById("acGenResult");
    if (resultEl && resultEl.value)
        _acCopyText(resultEl.value, document.getElementById("acGenCopyBtn"));
}

async function acLoadCodes() {
    const tbody = document.getElementById("acCodesBody");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--text-muted);">加载中…</td></tr>`;
    // 额度台账（不能超开：剩余可发名额与未分配邮箱一一对应）
    try {
        const sumRes = await fetch("/api/admin/activation-codes/summary");
        const sum = await sumRes.json();
        const info = document.getElementById("acQuotaInfo");
        if (info && sum.success) {
            info.textContent = `未分配邮箱 ${sum.available_mailboxes} · 未兑换码占额 ${sum.outstanding_quota} · 还可签发 ${sum.remaining_capacity}`;
        }
    } catch (_e) {}
    try {
        const res = await fetch("/api/admin/activation-codes");
        const data = await res.json();
        const codes = data.codes || [];
        if (!codes.length) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--text-muted);">暂无激活码，先用上方表单生成</td></tr>`;
            return;
        }
        // pi-lens-ignore: no-inner-html-js
        tbody.innerHTML = codes
            .map((c) => {
                const statusBadge =
                    c.status === "active"
                        ? '<span class="tag" style="background:#2e9e5b;color:#fff;">可用</span>'
                        : c.redeemed_by
                          ? '<span class="tag" style="background:#8a8f98;color:#fff;">已兑换</span>'
                          : '<span class="tag" style="background:#d64545;color:#fff;">停用</span>';
                const toggleLabel = c.status === "active" ? "停用" : "启用";
                return `
                <tr>
                    <td style="font-family:var(--font-mono, monospace);">${_acEsc(c.code)}
                        <button class="btn-icon" title="复制" onclick='acCopyOne("${_acEsc(c.code)}", this)'><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="emoji-svg"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg></button>
                    </td>
                    <td>${Number(c.max_bindings)}</td>
                    <td>${Number(c.bound_count)} / ${Number(c.max_bindings)}</td>
                    <td>${statusBadge}</td>
                    <td>${c.redeemed_by_username ? _acEsc(c.redeemed_by_username) : "-"}</td>
                    <td style="white-space:nowrap;">${_acEsc(String(c.created_at || "").slice(0, 16))}</td>
                    <td style="white-space:nowrap;">
                        ${c.redeemed_by ? "" : `<button class="btn btn-sm btn-ghost" onclick="acToggle(${Number(c.id)}, '${c.status === "active" ? "disabled" : "active"}')">${toggleLabel}</button>`}
                        <button class="btn btn-sm btn-danger" onclick="acDeleteCode(${Number(c.id)})">删除</button>
                    </td>
                </tr>`;
            })
            .join("");
    } catch (_e) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--clr-danger);">加载失败</td></tr>`;
    }
}

function acCopyOne(code, btn) {
    _acCopyText(code, btn);
}

async function acToggle(id, nextStatus) {
    try {
        await fetch(`/api/admin/activation-codes/${id}/status`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status: nextStatus }),
        });
    } catch (_e) {}
    acLoadCodes();
}

async function acDeleteCode(id) {
    if (!confirm("确定删除该激活码？删除后无法恢复。")) return;
    try {
        await fetch(`/api/admin/activation-codes/${id}`, { method: "DELETE" });
    } catch (_e) {}
    acLoadCodes();
}
