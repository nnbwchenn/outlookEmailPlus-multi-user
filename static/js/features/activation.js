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

// ---------- 用户端：兑换弹窗 ----------
function showRedeemModal() {
    closeRedeemModal();
    const modal = document.createElement("div");
    modal.className = "modal-overlay show";
    modal.id = "acRedeemModal";
    modal.innerHTML = `
        <div class="modal-content" style="max-width:420px;">
            <div class="modal-header">
                <h3>使用激活码</h3>
                <button class="modal-close" onclick="closeRedeemModal()">&times;</button>
            </div>
            <div class="modal-body" style="padding:1rem 1.25rem;display:flex;flex-direction:column;gap:12px;">
                <div class="form-group" style="margin:0;">
                    <label class="form-label">激活码</label>
                    <input type="text" class="form-input" id="acRedeemInput"
                           placeholder="例如：A3B4-C5D6-E7F8"
                           autocomplete="off" spellcheck="false"
                           style="text-transform:uppercase;font-family:var(--font-mono, monospace);letter-spacing:1px;">
                    <div class="form-hint">激活后会将未分配的邮箱绑定到你的账号（数量由激活码决定）</div>
                </div>
                <div id="acRedeemStatus" class="token-status hidden"></div>
                <div id="acRedeemResult" style="display:none;"></div>
            </div>
            <div class="modal-footer" style="display:flex;justify-content:flex-end;gap:8px;padding:0.75rem 1.25rem;border-top:1px solid var(--border-light);">
                <button class="btn btn-sm" onclick="closeRedeemModal()">关闭</button>
                <button class="btn btn-sm btn-primary" id="acRedeemBtn" onclick="acRedeemSubmit()">立即激活</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    setTimeout(() => document.getElementById("acRedeemInput")?.focus(), 50);
}

function closeRedeemModal() {
    document.getElementById("acRedeemModal")?.remove();
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
            const rows = (data.bound || [])
                .map(
                    (b) =>
                        `<li style="font-family:var(--font-mono, monospace);font-size:0.78rem;">${_acEsc(b.email)}</li>`,
                )
                .join("");
            resultEl.innerHTML = `<div style="margin-top:4px;font-size:0.8rem;color:var(--text-secondary);">已绑定的邮箱：</div><ul style="margin:4px 0 0 1.2rem;padding:0;">${rows}</ul>`;
            resultEl.style.display = "block";
            input.value = "";
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
    try {
        const res = await fetch("/api/admin/activation-codes");
        const data = await res.json();
        const codes = data.codes || [];
        if (!codes.length) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align:center;color:var(--text-muted);">暂无激活码，先用上方表单生成</td></tr>`;
            return;
        }
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
