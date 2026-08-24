// ==================== 多用户管理（admin 专属） ====================

function muT(text) {
    if (typeof translateAppTextLocal === 'function') return translateAppTextLocal(text);
    return text;
}

function muEscape(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}

// 加载用户列表页
async function loadUsersPage() {
    const container = document.getElementById('usersContainer');
    if (!container) return;
    container.innerHTML = `<div class="loading-overlay"><span class="spinner"></span> ${muT('加载中…')}</div>`;

    try {
        const response = await fetch('/api/users');
        const data = await response.json();
        if (!data.success) {
            container.innerHTML = `<div class="empty-state"><p>${muT('加载失败')}</p></div>`;
            return;
        }

        const users = data.users || [];
        container.innerHTML = `
            <div style="overflow-x:auto;">
                <table class="data-table data-table--admin" style="width:100%;">
                    <thead>
                        <tr>
                            <th>用户名</th>
                            <th>昵称</th>
                            <th>角色</th>
                            <th>状态</th>
                            <th>邮箱数</th>
                            <th>创建时间</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${users.map(u => `
                            <tr>
                                <td><strong>${muEscape(u.username)}</strong></td>
                                <td>${muEscape(u.display_name || '-')}</td>
                                <td>${u.role === 'admin' ? '<span class="badge" style="background:var(--clr-primary);color:#fff;">管理员</span>' : '<span class="badge" style="background:var(--clr-jade);color:#fff;">成员</span>'}</td>
                                <td>${u.status === 'active' ? '<span style="color:var(--clr-success);">正常</span>' : '<span style="color:var(--clr-danger);">禁用</span>'}</td>
                                <td>${u.account_count}</td>
                                <td style="font-size:0.75rem;color:var(--text-muted);">${u.created_at ? String(u.created_at).slice(0, 16).replace('T', ' ') : '-'}</td>
                                <td style="white-space:nowrap;">
                                    <button class="btn btn-sm btn-ghost" onclick="showAssignAccountsModal(${u.id}, '${muEscape(u.username)}')">分配邮箱</button>
                                    <button class="btn btn-sm btn-ghost" onclick="showEditUserModal(${u.id}, '${muEscape(u.username)}', '${u.role}', ${u.external_api_enabled ? 1 : 0}, ${u.external_api_rate_limit || ''})">编辑</button>
                                    ${u.username !== 'admin' ? `<button class="btn btn-sm btn-danger" onclick="deleteUser(${u.id}, '${muEscape(u.username)}')">删除</button>` : ''}
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    } catch (error) {
        container.innerHTML = `<div class="empty-state"><p>${muT('加载失败')}</p></div>`;
    }
}

// 创建用户模态框
function showCreateUserModal() {
    const existing = document.getElementById('muCreateUserModal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.className = 'modal-overlay show';
    modal.id = 'muCreateUserModal';
    modal.innerHTML = `
        <div class="modal-content" style="max-width:420px;">
            <div class="modal-header">
                <h3>创建用户</h3>
                <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">&times;</button>
            </div>
            <div class="modal-body" style="display:flex;flex-direction:column;gap:12px;padding:1rem 1.25rem;">
                <div class="form-group">
                    <label class="form-label">用户名</label>
                    <input type="text" class="form-input" id="muNewUsername" placeholder="至少 2 个字符" autocomplete="off">
                </div>
                <div class="form-group">
                    <label class="form-label">昵称（可选）</label>
                    <input type="text" class="form-input" id="muNewDisplayName" placeholder="显示名称">
                </div>
                <div class="form-group">
                    <label class="form-label">密码</label>
                    <input type="password" class="form-input" id="muNewPassword" placeholder="至少 8 位" autocomplete="new-password">
                </div>
                <div class="form-group">
                    <label class="form-label">角色</label>
                    <select class="form-input" id="muNewRole">
                        <option value="member">成员（仅查看被分配邮箱）</option>
                        <option value="admin">管理员（全部权限）</option>
                    </select>
                </div>
                <div id="muCreateStatus" class="token-status hidden"></div>
            </div>
            <div class="modal-footer" style="display:flex;justify-content:flex-end;gap:8px;padding:0.75rem 1.25rem;border-top:1px solid var(--border-light);">
                <button class="btn btn-sm" onclick="this.closest('.modal-overlay').remove()">取消</button>
                <button class="btn btn-sm btn-primary" onclick="createUser()">创建</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

async function createUser() {
    const username = document.getElementById('muNewUsername').value.trim();
    const password = document.getElementById('muNewPassword').value;
    const role = document.getElementById('muNewRole').value;
    const display_name = document.getElementById('muNewDisplayName').value.trim();
    const statusEl = document.getElementById('muCreateStatus');

    if (!username || password.length < 8) {
        statusEl.className = 'token-status token-dialog-status error';
        statusEl.textContent = '用户名必填且密码至少 8 位';
        statusEl.style.display = 'block';
        return;
    }

    try {
        const response = await fetch('/api/users', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, role, display_name })
        });
        const data = await response.json();
        if (data.success) {
            document.getElementById('muCreateUserModal').remove();
            showToast('用户创建成功', 'success');
            loadUsersPage();
        } else {
            statusEl.className = 'token-status token-dialog-status error';
            statusEl.textContent = data.error?.message || '创建失败';
            statusEl.style.display = 'block';
        }
    } catch (error) {
        statusEl.className = 'token-status token-dialog-status error';
        statusEl.textContent = '请求失败';
        statusEl.style.display = 'block';
    }
}

// 编辑用户（重置密码 / 角色 / 状态）
function showEditUserModal(userId, username, role, extApiEnabled, extApiRateLimit) {
    const existing = document.getElementById('muEditUserModal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.className = 'modal-overlay show';
    modal.id = 'muEditUserModal';
    modal.innerHTML = `
        <div class="modal-content" style="max-width:420px;">
            <div class="modal-header">
                <h3>编辑用户：${muEscape(username)}</h3>
                <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">&times;</button>
            </div>
            <div class="modal-body" style="display:flex;flex-direction:column;gap:12px;padding:1rem 1.25rem;">
                <div class="form-group">
                    <label class="form-label">新密码（留空不修改）</label>
                    <input type="password" class="form-input" id="muEditPassword" placeholder="至少 8 位" autocomplete="new-password">
                </div>
                <div class="form-group">
                    <label class="form-label">角色</label>
                    <select class="form-input" id="muEditRole">
                        <option value="member" ${role === 'member' ? 'selected' : ''}>成员</option>
                        <option value="admin" ${role === 'admin' ? 'selected' : ''}>管理员</option>
                    </select>
                </div>
                <div class="form-group">
                    <label class="form-label">状态</label>
                    <select class="form-input" id="muEditStatus">
                        <option value="active">正常</option>
                        <option value="disabled">禁用</option>
                    </select>
                </div>
                <div style="border-top:1px solid var(--border-light);padding-top:12px;">
                    <div style="font-weight:600;margin-bottom:8px;font-size:0.9rem;">对外 API 权限</div>
                    <label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin-bottom:8px;">
                        <input type="checkbox" id="muEditExtApiEnabled" ${extApiEnabled ? 'checked' : ''}>
                        <span>允许使用成员 API Key 查询名下邮箱/验证码</span>
                    </label>
                    <div class="form-group" style="margin-bottom:0;">
                        <label class="form-label">每分钟限流 <span style="font-size:0.75rem;color:var(--text-muted);font-weight:400;">（留空 = 默认 60）</span></label>
                        <input type="number" class="form-input" id="muEditExtApiRateLimit" min="1" max="10000" placeholder="60" value="${extApiRateLimit || ''}" style="max-width:140px;">
                    </div>
                </div>
                <div id="muEditStatusMsg" class="token-status hidden"></div>
            </div>
            <div class="modal-footer" style="display:flex;justify-content:flex-end;gap:8px;padding:0.75rem 1.25rem;border-top:1px solid var(--border-light);">
                <button class="btn btn-sm" onclick="this.closest('.modal-overlay').remove()">取消</button>
                <button class="btn btn-sm btn-primary" onclick="updateUser(${userId})">保存</button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
}

async function updateUser(userId) {
    const password = document.getElementById('muEditPassword').value;
    const role = document.getElementById('muEditRole').value;
    const status = document.getElementById('muEditStatus').value;
    const statusEl = document.getElementById('muEditStatusMsg');

    if (password && password.length < 8) {
        statusEl.className = 'token-status token-dialog-status error';
        statusEl.textContent = '密码至少 8 位';
        statusEl.style.display = 'block';
        return;
    }

    try {
        const payload = { role, status };
        if (password) payload.password = password;
        payload.external_api_enabled = document.getElementById('muEditExtApiEnabled').checked;
        const rateRaw = document.getElementById('muEditExtApiRateLimit').value.trim();
        payload.external_api_rate_limit = rateRaw === '' ? null : parseInt(rateRaw, 10);
        if (rateRaw !== '' && (isNaN(payload.external_api_rate_limit) || payload.external_api_rate_limit < 1 || payload.external_api_rate_limit > 10000)) {
            statusEl.className = 'token-status token-dialog-status error';
            statusEl.textContent = '限流阈值必须是 1-10000 之间的数字';
            statusEl.style.display = 'block';
            return;
        }
        const response = await fetch(`/api/users/${userId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (data.success) {
            document.getElementById('muEditUserModal').remove();
            showToast('用户已更新', 'success');
            loadUsersPage();
        } else {
            statusEl.className = 'token-status token-dialog-status error';
            statusEl.textContent = data.error?.message || '更新失败';
            statusEl.style.display = 'block';
        }
    } catch (error) {
        statusEl.textContent = '请求失败';
        statusEl.style.display = 'block';
    }
}

async function deleteUser(userId, username) {
    if (!confirm(`确定删除用户「${username}」？其名下邮箱将归还管理员。`)) return;
    try {
        const response = await fetch(`/api/users/${userId}`, { method: 'DELETE' });
        const data = await response.json();
        if (data.success) {
            showToast('用户已删除', 'success');
            loadUsersPage();
        } else {
            showToast(data.error?.message || '删除失败', 'error');
        }
    } catch (error) {
        showToast('请求失败', 'error');
    }
}

// 分配邮箱
async function showAssignAccountsModal(userId, username) {
    const existing = document.getElementById('muAssignModal');
    if (existing) existing.remove();

    const modal = document.createElement('div');
    modal.className = 'modal-overlay show';
    modal.id = 'muAssignModal';
    modal.innerHTML = `
        <div class="modal-content" style="max-width:640px;">
            <div class="modal-header">
                <h3>分配邮箱给：${muEscape(username)}</h3>
                <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">&times;</button>
            </div>
            <div class="modal-body" style="padding:1rem 1.25rem;">
                <div style="display:flex;gap:12px;margin-bottom:12px;">
                    <button class="btn btn-sm btn-primary" id="muTabAssigned" onclick="muSwitchAssignTab('assigned', ${userId})">已分配</button>
                    <button class="btn btn-sm" id="muTabUnassigned" onclick="muSwitchAssignTab('unassigned', ${userId})">全部邮箱（标注归属）</button>
                </div>
                <div id="muAssignList" style="max-height:360px;overflow-y:auto;border:1px solid var(--border-light);border-radius:6px;">
                    <div class="loading-overlay"><span class="spinner"></span> 加载中…</div>
                </div>
                <div style="display:flex;gap:8px;margin-top:12px;align-items:center;">
                    <span id="muAssignCount" style="font-size:0.8rem;color:var(--text-muted);"></span>
                    <div style="flex:1;"></div>
                    <button class="btn btn-sm" onclick="this.closest('.modal-overlay').remove()">关闭</button>
                    <button class="btn btn-sm btn-primary" onclick="muConfirmAssign(${userId}, '${muEscape(username)}')">保存分配</button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    muSwitchAssignTab('assigned', userId);
}

let muAssignMode = 'assigned';
let muAssignSelected = new Set();

async function muSwitchAssignTab(mode, userId) {
    muAssignMode = mode;
    muAssignSelected = new Set();
    document.getElementById('muTabAssigned').className = mode === 'assigned' ? 'btn btn-sm btn-primary' : 'btn btn-sm';
    document.getElementById('muTabUnassigned').className = mode === 'unassigned' ? 'btn btn-sm btn-primary' : 'btn btn-sm';

    const listEl = document.getElementById('muAssignList');
    listEl.innerHTML = `<div class="loading-overlay"><span class="spinner"></span> 加载中…</div>`;

    try {
        const url = mode === 'assigned'
            ? `/api/users/${userId}/accounts`
            : '/api/users/unassigned-accounts';
        const response = await fetch(url);
        const data = await response.json();
        if (!data.success) {
            listEl.innerHTML = `<div class="empty-state"><p>加载失败</p></div>`;
            return;
        }
        const accounts = data.accounts || [];
        document.getElementById('muAssignCount').textContent = `共 ${accounts.length} 个邮箱`;

        if (accounts.length === 0) {
            listEl.innerHTML = `<div class="empty-state"><p>${mode === 'assigned' ? '该用户名下暂无邮箱' : '系统中还没有任何邮箱'}</p></div>`;
            return;
        }

        listEl.innerHTML = accounts.map(a => {
            const ownedByOther = a.owner_user_id && a.owner_user_id !== userId;
            const ownedBySelf = a.owner_user_id && a.owner_user_id === userId;
            const ownerChip = ownedByOther
                ? `<span style="margin-left:auto;font-size:0.72rem;background:#b45309;color:#fff;border-radius:999px;padding:1px 8px;white-space:nowrap;">归属: ${muEscape(a.owner_username || '其他用户')}</span>`
                : ownedBySelf
                  ? `<span style="margin-left:auto;font-size:0.72rem;background:#8a8f98;color:#fff;border-radius:999px;padding:1px 8px;white-space:nowrap;">已归属本人</span>`
                  : '';
            const rowTint = ownedByOther ? 'background:rgba(180,83,9,0.06);' : '';
            return `
            <label style="display:flex;align-items:center;gap:10px;padding:8px 12px;border-bottom:1px solid var(--border-light);cursor:pointer;${rowTint}">
                <input type="checkbox" class="mu-assign-check" value="${a.id}" onchange="muToggleAssign(${a.id}, this.checked)">
                <span style="font-size:0.85rem;">${muEscape(a.email)}</span>
                ${ownerChip}
                <span style="${ownedByOther ? '' : 'margin-left:auto;'}font-size:0.72rem;color:var(--text-muted);">${a.status === 'active' ? '正常' : '停用'}</span>
            </label>
        `;}).join('');
    } catch (error) {
        listEl.innerHTML = `<div class="empty-state"><p>加载失败</p></div>`;
    }
}

function muToggleAssign(accountId, checked) {
    if (checked) muAssignSelected.add(accountId);
    else muAssignSelected.delete(accountId);
}

async function muConfirmAssign(userId, username) {
    const accountIds = Array.from(muAssignSelected);
    if (accountIds.length === 0) {
        showToast(muAssignMode === 'assigned' ? '请选择要回收的邮箱' : '请选择要分配的邮箱', 'warning');
        return;
    }

    try {
        const url = muAssignMode === 'assigned' ? '/api/users/unassign' : '/api/users/assign';
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(muAssignMode === 'assigned' ? { account_ids: accountIds } : { owner_user_id: userId, account_ids: accountIds })
        });
        const data = await response.json();
        if (data.success) {
            showToast(data.message || '操作成功', 'success');
            muSwitchAssignTab(muAssignMode, userId);
            loadUsersPage();
        } else {
            showToast(data.error?.message || '操作失败', 'error');
        }
    } catch (error) {
        showToast('请求失败', 'error');
    }
}

// navigate 到用户管理页时加载
window.__origNavigate = window.__origNavigate || null;
document.addEventListener('DOMContentLoaded', function () {
    const origNav = window.navigate;
    if (origNav && !window.__muNavPatched) {
        window.navigate = function (page) {
            origNav(page);
            if (page === 'users') loadUsersPage();
        };
        window.__muNavPatched = true;
    }
});