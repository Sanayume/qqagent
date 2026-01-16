// QQ 沙盒前端逻辑

// 状态
let state = {
    users: [],
    groups: [],
    presets: [],
    currentPreset: null,
    currentUserQQ: null,
    currentChat: null, // { type: 'group'|'private', id: number }
    replyTo: null,     // 回复的消息 ID
    atUsers: [],       // @ 的用户列表
    messages: [],
};

let ws = null;

// ==================== 初始化 ====================

async function init() {
    // 加载状态
    await loadState();
    await loadPresets();

    // 连接 WebSocket
    connectWebSocket();

    // 默认选择第一个非机器人用户
    const nonBotUser = state.users.find(u => !u.is_bot);
    if (nonBotUser) {
        state.currentUserQQ = nonBotUser.qq;
        document.getElementById('currentUser').value = nonBotUser.qq;
    }

    // 默认选择第一个群
    if (state.groups.length > 0) {
        selectChat('group', state.groups[0].group_id);
    }
}

async function loadState() {
    const res = await fetch('/api/state');
    const data = await res.json();
    state.users = data.users;
    state.groups = data.groups;
    state.currentPreset = data.current_preset;
    renderSidebar();
    renderUserManagement();
}

async function loadPresets() {
    const res = await fetch('/api/presets');
    const data = await res.json();
    state.presets = data.presets;
    state.currentPreset = data.current;
    renderPresetSelect();
}

// ==================== WebSocket ====================

function connectWebSocket() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.host}/ws`);

    ws.onopen = () => {
        console.log('WebSocket 已连接');
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
    };

    ws.onclose = () => {
        console.log('WebSocket 断开，3秒后重连...');
        setTimeout(connectWebSocket, 3000);
    };
}

function handleWebSocketMessage(data) {
    switch (data.type) {
        case 'new_message':
            handleNewMessage(data.message, data.sender);
            break;
        case 'user_added':
            state.users.push(data.user);
            renderSidebar();
            renderUserManagement();
            break;
        case 'user_removed':
            state.users = state.users.filter(u => u.qq !== data.qq);
            renderSidebar();
            renderUserManagement();
            break;
        case 'group_added':
            state.groups.push(data.group);
            renderSidebar();
            break;
        case 'group_removed':
            state.groups = state.groups.filter(g => g.group_id !== data.group_id);
            renderSidebar();
            break;
        case 'preset_changed':
            state.currentPreset = data.preset;
            renderPresetSelect();
            break;
        case 'messages_cleared':
        case 'reset':
            state.messages = [];
            renderMessages();
            break;
        case 'session_cleared':
        case 'all_sessions_cleared':
            // 会话清空，可能需要刷新
            break;
    }
}

function handleNewMessage(message, sender) {
    // 检查是否是当前聊天的消息
    if (state.currentChat) {
        if (state.currentChat.type === 'group' && message.chat_type === 'group' && message.group_id === state.currentChat.id) {
            state.messages.push({ ...message, sender });
            renderMessages();
            scrollToBottom();
        } else if (state.currentChat.type === 'private' && message.chat_type === 'private') {
            // 私聊：检查是否涉及当前选择的用户
            const botQQ = state.users.find(u => u.is_bot)?.qq;
            if ((message.sender_qq === state.currentChat.id && message.target_qq === botQQ) ||
                (message.sender_qq === botQQ && message.target_qq === state.currentChat.id)) {
                state.messages.push({ ...message, sender });
                renderMessages();
                scrollToBottom();
            }
        }
    }
}

// ==================== 渲染函数 ====================

function renderPresetSelect() {
    const select = document.getElementById('presetSelect');
    select.innerHTML = state.presets.map(p =>
        `<option value="${p.name}" ${p.name === state.currentPreset ? 'selected' : ''}>${p.name}</option>`
    ).join('');
}

function renderSidebar() {
    // 用户选择
    const userSelect = document.getElementById('currentUser');
    userSelect.innerHTML = state.users
        .filter(u => !u.is_bot)
        .map(u => `<option value="${u.qq}">${u.nickname} (${u.qq})</option>`)
        .join('');
    if (state.currentUserQQ) {
        userSelect.value = state.currentUserQQ;
    }
    userSelect.onchange = () => {
        state.currentUserQQ = parseInt(userSelect.value);
    };

    // 群列表
    const groupList = document.getElementById('groupList');
    groupList.innerHTML = state.groups.map(g => `
        <div class="list-item ${state.currentChat?.type === 'group' && state.currentChat?.id === g.group_id ? 'active' : ''}"
             onclick="selectChat('group', ${g.group_id})">
            <img class="avatar" src="https://p.qlogo.cn/gh/${g.group_id}/${g.group_id}/100" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect fill=%22%235c6370%22 width=%22100%22 height=%22100%22/><text x=%2250%22 y=%2250%22 dominant-baseline=%22middle%22 text-anchor=%22middle%22 fill=%22white%22 font-size=%2240%22>群</text></svg>'">
            <span class="name">${g.name}</span>
        </div>
    `).join('');

    // 私聊列表（非机器人用户，用于和 Bot 私聊）
    const botQQ = state.users.find(u => u.is_bot)?.qq;
    const privateList = document.getElementById('privateList');
    privateList.innerHTML = state.users
        .filter(u => !u.is_bot)
        .map(u => `
            <div class="list-item ${state.currentChat?.type === 'private' && state.currentChat?.id === u.qq ? 'active' : ''}"
                 onclick="selectChat('private', ${u.qq})">
                <img class="avatar" src="${u.avatar}" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect fill=%22%235c6370%22 width=%22100%22 height=%22100%22/></svg>'">
                <span class="name">${u.nickname} → Bot</span>
            </div>
        `).join('');
}

function renderUserManagement() {
    const container = document.getElementById('userManagement');
    container.innerHTML = state.users.map(u => `
        <div class="user-item">
            <img class="avatar" src="${u.avatar}" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect fill=%22%235c6370%22 width=%22100%22 height=%22100%22/></svg>'">
            <div class="info">
                <div class="nickname">${u.nickname} ${u.is_bot ? '<span class="bot-tag">BOT</span>' : ''}</div>
                <div class="qq">${u.qq}</div>
            </div>
            ${!u.is_bot ? `<button class="delete-btn" onclick="deleteUser(${u.qq})">×</button>` : ''}
        </div>
    `).join('');
}

function renderGroupMembers() {
    const container = document.getElementById('groupMembers');

    if (!state.currentChat || state.currentChat.type !== 'group') {
        container.innerHTML = '<div class="empty-state">选择一个群查看成员</div>';
        return;
    }

    const group = state.groups.find(g => g.group_id === state.currentChat.id);
    if (!group) return;

    container.innerHTML = group.members.map(qq => {
        const user = state.users.find(u => u.qq === qq);
        if (!user) return '';
        return `
            <div class="member-item">
                <img class="avatar" src="${user.avatar}" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect fill=%22%235c6370%22 width=%22100%22 height=%22100%22/></svg>'">
                <div class="info">
                    <div class="nickname">${user.nickname} ${user.is_bot ? '<span class="bot-tag">BOT</span>' : ''}</div>
                    <div class="qq">${user.qq}</div>
                </div>
                ${!user.is_bot ? `<button class="delete-btn" onclick="removeFromGroup(${group.group_id}, ${qq})">×</button>` : ''}
            </div>
        `;
    }).join('');
}

function renderMessages() {
    const container = document.getElementById('messages');
    const botQQ = state.users.find(u => u.is_bot)?.qq;

    if (state.messages.length === 0) {
        container.innerHTML = '<div class="empty-state">暂无消息</div>';
        return;
    }

    container.innerHTML = state.messages.map(msg => {
        const sender = msg.sender || state.users.find(u => u.qq === msg.sender_qq);
        const isSelf = msg.sender_qq === state.currentUserQQ;
        const isBot = msg.sender_qq === botQQ;

        // 回复引用
        let replyHtml = '';
        if (msg.reply_to) {
            const replyMsg = state.messages.find(m => m.message_id === msg.reply_to);
            if (replyMsg) {
                const replySender = state.users.find(u => u.qq === replyMsg.sender_qq);
                replyHtml = `<div class="reply-quote">${replySender?.nickname || '某人'}: ${replyMsg.content.slice(0, 50)}</div>`;
            }
        }

        // @ 标签
        let atHtml = '';
        if (msg.at_users && msg.at_users.length > 0) {
            atHtml = msg.at_users.map(qq => {
                const atUser = state.users.find(u => u.qq === qq);
                return `<span class="at-tag">@${atUser?.nickname || qq}</span>`;
            }).join(' ') + ' ';
        }

        // 图片
        let imageHtml = '';
        if (msg.image) {
            imageHtml = `<img class="image" src="${msg.image}" onerror="this.style.display='none'">`;
        }

        return `
            <div class="message ${isSelf ? 'self' : ''} ${isBot ? 'bot' : ''}" data-id="${msg.message_id}">
                <img class="avatar" src="${sender?.avatar || ''}" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect fill=%22%235c6370%22 width=%22100%22 height=%22100%22/></svg>'">
                <div class="content">
                    <div class="sender-name">${sender?.nickname || '未知'}</div>
                    ${replyHtml}
                    <div class="bubble" onclick="setReply(${msg.message_id}, '${(sender?.nickname || '').replace(/'/g, "\\'")}', '${msg.content.slice(0, 30).replace(/'/g, "\\'")}')">
                        ${atHtml}${escapeHtml(msg.content)}
                        ${imageHtml}
                    </div>
                    <div class="msg-id">ID: ${msg.message_id}</div>
                </div>
            </div>
        `;
    }).join('');
}

function scrollToBottom() {
    const container = document.getElementById('messages');
    container.scrollTop = container.scrollHeight;
}

// ==================== 聊天操作 ====================

async function selectChat(type, id) {
    state.currentChat = { type, id };
    state.replyTo = null;
    state.atUsers = [];

    // 更新标题
    let title = '';
    let info = '';
    if (type === 'group') {
        const group = state.groups.find(g => g.group_id === id);
        title = group?.name || '群聊';
        info = `群号: ${id} | ${group?.members.length || 0} 人`;
    } else {
        const user = state.users.find(u => u.qq === id);
        title = `${user?.nickname || '私聊'} → Bot`;
        info = `QQ: ${id}`;
    }
    document.getElementById('chatTitle').textContent = title;
    document.getElementById('chatInfo').textContent = info;

    // 加载消息
    const botQQ = state.users.find(u => u.is_bot)?.qq;
    const params = new URLSearchParams({ chat_type: type });
    if (type === 'group') {
        params.set('group_id', id);
    } else {
        params.set('user_qq', id);
    }

    const res = await fetch(`/api/messages?${params}`);
    const messages = await res.json();

    // 补充 sender 信息
    state.messages = messages.map(msg => ({
        ...msg,
        sender: state.users.find(u => u.qq === msg.sender_qq)
    }));

    renderSidebar();
    renderGroupMembers();
    renderMessages();
    scrollToBottom();

    // 清理输入状态
    cancelReply();
    cancelAt();
}

function sendMessage() {
    const input = document.getElementById('messageInput');
    const content = input.value.trim();

    if (!content && !state.imageData) return;
    if (!state.currentChat) return;
    if (!state.currentUserQQ) {
        alert('请先选择发送身份');
        return;
    }

    const botQQ = state.users.find(u => u.is_bot)?.qq;

    const message = {
        type: 'send_message',
        sender_qq: state.currentUserQQ,
        content: content,
        image: state.imageData || '',
        at_users: state.atUsers.map(u => u.qq),
        reply_to: state.replyTo || 0,
        chat_type: state.currentChat.type,
        group_id: state.currentChat.type === 'group' ? state.currentChat.id : null,
        target_qq: state.currentChat.type === 'private' ? botQQ : null,
    };

    ws.send(JSON.stringify(message));

    // 清理
    input.value = '';
    state.imageData = null;
    cancelReply();
    cancelAt();
}

function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

// ==================== 回复功能 ====================

function setReply(messageId, senderName, content) {
    state.replyTo = messageId;
    document.getElementById('replyPreview').style.display = 'flex';
    document.getElementById('replyText').textContent = `回复 ${senderName}: ${content}...`;
    document.getElementById('replyBtn').classList.add('active');
}

function cancelReply() {
    state.replyTo = null;
    document.getElementById('replyPreview').style.display = 'none';
    document.getElementById('replyBtn').classList.remove('active');
}

function toggleReply() {
    if (state.replyTo) {
        cancelReply();
    }
}

// ==================== @ 功能 ====================

function toggleAtPicker() {
    if (state.currentChat?.type !== 'group') {
        alert('只能在群聊中 @ 人');
        return;
    }

    const group = state.groups.find(g => g.group_id === state.currentChat.id);
    if (!group) return;

    const container = document.getElementById('atUserList');
    container.innerHTML = group.members.map(qq => {
        const user = state.users.find(u => u.qq === qq);
        if (!user || user.qq === state.currentUserQQ) return '';
        const isSelected = state.atUsers.some(u => u.qq === qq);
        return `
            <div class="at-user-item ${isSelected ? 'selected' : ''}" onclick="toggleAtUser(${qq})">
                <img class="avatar" src="${user.avatar}" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect fill=%22%235c6370%22 width=%22100%22 height=%22100%22/></svg>'">
                <span>${user.nickname} (${qq})</span>
            </div>
        `;
    }).join('');

    showModal('atModal');
}

function toggleAtUser(qq) {
    const user = state.users.find(u => u.qq === qq);
    if (!user) return;

    const index = state.atUsers.findIndex(u => u.qq === qq);
    if (index >= 0) {
        state.atUsers.splice(index, 1);
    } else {
        state.atUsers.push(user);
    }

    updateAtPreview();
    toggleAtPicker(); // 刷新列表
}

function updateAtPreview() {
    const preview = document.getElementById('atPreview');
    const text = document.getElementById('atText');

    if (state.atUsers.length > 0) {
        preview.style.display = 'flex';
        text.textContent = state.atUsers.map(u => `@${u.nickname}`).join(' ');
    } else {
        preview.style.display = 'none';
    }
}

function cancelAt() {
    state.atUsers = [];
    updateAtPreview();
}

// ==================== 图片功能 ====================

function handleImageSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
        state.imageData = e.target.result;
        alert('图片已选择，发送消息时会一并发送');
    };
    reader.readAsDataURL(file);
}

// ==================== 用户/群管理 ====================

async function createUser() {
    const qq = parseInt(document.getElementById('newUserQQ').value);
    const nickname = document.getElementById('newUserNickname').value.trim();

    if (!qq || !nickname) {
        alert('请填写完整信息');
        return;
    }

    await fetch('/api/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ qq, nickname })
    });

    hideModal('userModal');
    document.getElementById('newUserQQ').value = '';
    document.getElementById('newUserNickname').value = '';
}

async function deleteUser(qq) {
    if (!confirm('确定删除此用户？')) return;
    await fetch(`/api/users/${qq}`, { method: 'DELETE' });
}

async function createGroup() {
    const group_id = parseInt(document.getElementById('newGroupId').value);
    const name = document.getElementById('newGroupName').value.trim();

    if (!group_id || !name) {
        alert('请填写完整信息');
        return;
    }

    // 添加所有用户到群
    const members = state.users.map(u => u.qq);

    await fetch('/api/groups', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ group_id, name, members })
    });

    hideModal('groupModal');
    document.getElementById('newGroupId').value = '';
    document.getElementById('newGroupName').value = '';
}

async function removeFromGroup(groupId, qq) {
    await fetch(`/api/groups/${groupId}/members/${qq}`, { method: 'DELETE' });
    // 刷新成员列表
    const group = state.groups.find(g => g.group_id === groupId);
    if (group) {
        group.members = group.members.filter(m => m !== qq);
        renderGroupMembers();
    }
}

// ==================== 弹窗 ====================

function showModal(id) {
    document.getElementById(id).classList.add('show');
}

function hideModal(id) {
    document.getElementById(id).classList.remove('show');
}

// ==================== 工具函数 ====================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ==================== 预设和会话管理 ====================

async function switchPreset() {
    const select = document.getElementById('presetSelect');
    const name = select.value;

    const res = await fetch(`/api/presets/${encodeURIComponent(name)}`, { method: 'POST' });
    const data = await res.json();

    if (data.success) {
        state.currentPreset = data.preset;
        alert(`已切换到预设: ${data.preset}`);
    } else {
        alert(`切换失败: ${data.error}`);
        renderPresetSelect(); // 恢复选择
    }
}

async function clearMessages() {
    if (!confirm('确定清空所有消息？（不会清空 Agent 记忆）')) return;

    await fetch('/api/simulator/messages', { method: 'DELETE' });
    state.messages = [];
    renderMessages();
}

async function resetAll() {
    if (!confirm('确定完全重置？\n\n这将清空：\n- 所有消息\n- Agent 会话记忆')) return;

    await fetch('/api/reset', { method: 'POST' });
    state.messages = [];
    renderMessages();
    alert('已完全重置');
}

// 初始化
document.addEventListener('DOMContentLoaded', init);
