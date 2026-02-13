/**
 * QN Code Assistant v1.3.2 - Client
 * Features: Terminal tabs, persistent chat, usage tracking, auth, themes,
 *           keyboard shortcuts, file browser, git integration, notifications,
 *           session search, export, multi-user, PWA
 */

class ClaudeCodeWeb {
    constructor() {
        // State
        this.socket = null;
        this.selectedProject = null;
        this.selectedRemoteHostId = null;
        this.currentSession = null;
        this.currentRoot = null;
        this._currentParent = null;
        this.config = {};
        this._currentUser = null;

        // Terminal tabs: {id: {terminal, fitAddon, container, project, remoteHostId, closed}}
        this.terminals = {};
        this.activeTerminalId = null;

        // Stream buffering to prevent UI freezing on verbose output
        this._streamBuffer = '';
        this._streamFlushTimer = null;
        this._scrollTimer = null;
        this._streamFlushInterval = 50;

        // Auto-follow state
        this._autoFollow = true;
        this._scrollLock = false;

        // Usage tracking
        this._usage = { weekly: { input_tokens: 0, output_tokens: 0 }, total: { input_tokens: 0, output_tokens: 0 } };
        this._usagePollTimer = null;

        // Notification sounds
        this._soundEnabled = localStorage.getItem('soundEnabled') === 'true';
        this._audioCtx = null;

        // Search state
        this._searchDebounce = null;

        // File browser state
        this._filesCurrentPath = null;

        // Wizard state
        this._wizardStep = 1;
        this._wizardMaxSteps = 5;
        this._wizardDetectedData = null;
        this._wizardTargetPath = null;

        // Remote wizard state
        this._rwStep = 1;
        this._rwMethod = null;
        this._rwImportedHost = null;
        this._rwSshConfig = [];
        this._rwSshSetup = null;
        this._rwKeyStatus = null;
        this._rwVerifyResults = {};
        this._rwBusy = false;
        this._lastAction = {};  // debounce guard: { actionName: timestamp }
        this._editingFile = null;  // path of file being edited, or null
        this._editDirty = false;   // whether editor content has been modified
        this._aceEditor = null;    // Ace Editor instance for edit mode
        this._aceLoadPromise = null; // lazy-load promise for ace.js
        this._viewerMode = 'view'; // 'view', 'edit', or 'diff'
        this._viewerTransition = false; // guard against overlapping mode switches

        // Agent management state
        this._agentLibrary = [];
        this._activeAgents = [];
        this._customAgents = [];
        this._agentCategoryFilter = 'all';

        // DOM Elements
        this.elements = {
            connectionStatus: document.getElementById('connection-status'),
            projectsList: document.getElementById('projects-list'),
            terminalContainer: document.getElementById('terminal-container'),
            terminalProject: document.getElementById('terminal-project'),
            terminalTabsList: document.getElementById('terminal-tabs-list'),
            chatMessages: document.getElementById('chat-messages'),
            chatInput: document.getElementById('chat-input'),
            chatStatus: document.getElementById('chat-status'),
            currentPath: document.getElementById('current-path'),
            autoFollow: document.getElementById('auto-follow'),
            soundToggle: document.getElementById('sound-toggle'),
        };

        // Flags
        this.flags = {
            resume: document.getElementById('flag-resume'),
            continue: document.getElementById('flag-continue'),
            verbose: document.getElementById('flag-verbose'),
            printMode: document.getElementById('flag-print-mode'),
            printPrompt: document.getElementById('flag-print-prompt'),
            permissionMode: document.getElementById('flag-permission-mode'),
            model: document.getElementById('model-select'),
            effortLevel: document.getElementById('flag-effort-level'),
            extendedThinking: document.getElementById('flag-extended-thinking'),
            thinkingTokens: document.getElementById('flag-thinking-tokens'),
            systemPrompt: document.getElementById('flag-system-prompt'),
            fallbackModel: document.getElementById('flag-fallback-model'),
            autocompactThreshold: document.getElementById('flag-autocompact-threshold'),
            allowedTools: document.getElementById('flag-allowed-tools'),
            disallowedTools: document.getElementById('flag-disallowed-tools'),
            addDirs: document.getElementById('flag-add-dirs'),
            mcpConfig: document.getElementById('flag-mcp-config'),
            agentTeams: document.getElementById('flag-agent-teams'),
        };

        this.init();
    }

    async init() {
        // Check auth status first
        try {
            const authStatus = await fetch('/api/auth/status').then(r => r.json());
            if (authStatus.auth_enabled && !authStatus.authenticated) {
                window.location.href = '/login';
                return;
            }
            // Show logout button if auth is enabled
            if (authStatus.auth_enabled) {
                const logoutBtn = document.getElementById('btn-logout');
                if (logoutBtn) logoutBtn.style.display = '';
            }
        } catch (e) {
            console.error('Auth check failed:', e);
        }

        this.connectSocket();
        this.setupEventListeners();
        this.setupKeyboardShortcuts();
        this.loadConfig().then(() => {
            this.loadProjects();
            this.applyTheme(this.config.theme || 'dark');
            this.loadAgentLibrary();
        });
        this.initTerminalWelcome();
        this.restorePersistentSession();
        this.checkServerStatus();
        this.loadUsage();
        this.loadCurrentUser();
        this._usagePollTimer = setInterval(() => this.loadUsage(), 300000); // 5 min

        // Restore sound toggle state
        if (this.elements.soundToggle) {
            this.elements.soundToggle.checked = this._soundEnabled;
        }
    }

    async checkServerStatus() {
        try {
            const response = await fetch('/api/status');
            const status = await response.json();

            const header = document.querySelector('.sidebar-header h1');
            if (header && status.version) {
                header.innerHTML = `QN Code Assistant <a href="#" id="version-link" class="version-link">v${this._escapeHtml(status.version)}</a>`;
            }

            if (!status.claude_version) {
                console.warn('Claude CLI not found or version check failed');
            }
        } catch (error) {
            console.error('Failed to check server status:', error);
        }
    }

    // ============== Config & Settings ==============

    async loadConfig() {
        try {
            const response = await fetch('/api/config');
            this.config = await response.json();
            this.renderFavoritesSidebar();
            this.renderRemoteHostsSidebar();
        } catch (error) {
            console.error('Failed to load config:', error);
        }
    }

    openSettings() {
        const overlay = document.getElementById('settings-overlay');
        overlay.classList.remove('hidden');
        this.populateSettingsForm();
    }

    closeSettings() {
        document.getElementById('settings-overlay').classList.add('hidden');
        const addFavForm = document.getElementById('add-favorite-form');
        const addRemoteForm = document.getElementById('add-remote-form');
        if (addFavForm) addFavForm.style.display = 'none';
        if (addRemoteForm) addRemoteForm.style.display = 'none';
    }

    async openChangelog() {
        const overlay = document.getElementById('changelog-overlay');
        const body = document.getElementById('changelog-body');
        overlay.classList.remove('hidden');
        // Use cached content if available
        if (this._changelogHtml) {
            body.innerHTML = this._changelogHtml;
            return;
        }
        body.innerHTML = '<div style="color:var(--text-secondary);padding:20px;text-align:center;">Loading...</div>';
        try {
            const response = await fetch('/api/changelog');
            const data = await response.json();
            this._changelogHtml = '<div class="changelog-content">' +
                this.renderMarkdown(data.content || '# Changelog\n\nNo content.') + '</div>';
            body.innerHTML = this._changelogHtml;
        } catch (error) {
            body.innerHTML = '<div style="color:var(--error);padding:20px;">Failed to load changelog.</div>';
        }
    }

    populateSettingsForm() {
        document.getElementById('setting-projects-root').value = this.config.projects_root || '';
        document.getElementById('setting-timeout').value = this.config.process_timeout_minutes || 60;
        document.getElementById('setting-max-terminals').value = this.config.max_concurrent_terminals || 5;
        document.getElementById('setting-max-chats').value = this.config.max_concurrent_chats || 10;
        document.getElementById('setting-chat-cwd').value = this.config.chat_cwd || '/opt/claude';
        document.getElementById('setting-theme').value = this.config.theme || 'dark';
        document.getElementById('setting-allowed-paths').value = (this.config.allowed_paths || ['/opt']).join(', ');
        document.getElementById('setting-allow-full-browsing').checked = this.config.allow_full_browsing || false;
        this.renderFavoritesSettings();
        this.renderRemotesSettings();
        this.populateAuthSettings();
        this.renderUsersSettings();
        this.renderCustomAgentsList();
    }

    async populateAuthSettings() {
        try {
            const status = await fetch('/api/auth/status').then(r => r.json());
            const display = document.getElementById('auth-status-display');
            if (status.auth_enabled) {
                display.innerHTML = 'Status: <span style="color:var(--success);">Enabled</span>';
            } else {
                display.innerHTML = 'Status: <span style="color:var(--warning);">Disabled</span> - Set username and password to enable.';
            }

            // Populate SSL fields
            document.getElementById('setting-ssl-enabled').checked = this.config.ssl_enabled || false;
            document.getElementById('setting-ssl-cert').value = this.config.ssl_cert || '';
            document.getElementById('setting-ssl-key').value = this.config.ssl_key || '';
        } catch (e) {
            console.error('Failed to load auth settings:', e);
        }
    }

    async saveGeneralSettings() {
        const allowedPathsRaw = document.getElementById('setting-allowed-paths').value.trim();
        const allowedPaths = allowedPathsRaw ? allowedPathsRaw.split(',').map(p => p.trim()).filter(Boolean) : ['/opt'];

        const data = {
            projects_root: document.getElementById('setting-projects-root').value.trim(),
            process_timeout_minutes: parseInt(document.getElementById('setting-timeout').value) || 60,
            max_concurrent_terminals: parseInt(document.getElementById('setting-max-terminals').value) || 5,
            max_concurrent_chats: parseInt(document.getElementById('setting-max-chats').value) || 10,
            chat_cwd: document.getElementById('setting-chat-cwd').value.trim() || '/opt/claude',
            theme: document.getElementById('setting-theme').value || 'dark',
            allowed_paths: allowedPaths,
            allow_full_browsing: document.getElementById('setting-allow-full-browsing').checked,
        };

        try {
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const result = await response.json();
            if (result.success) {
                this.config = { ...this.config, ...data };
                this.applyTheme(data.theme);
                this.loadProjects();
                this.showToast('Settings saved', 'success');
            } else {
                this.showToast('Error: ' + (result.error || 'Failed to save'), 'error');
            }
        } catch (error) {
            console.error('Failed to save settings:', error);
            this.showToast('Failed to save settings', 'error');
        }
    }

    async saveAuthSettings() {
        const username = document.getElementById('setting-auth-username').value.trim();
        const password = document.getElementById('setting-auth-password').value;

        if (!username) {
            this.showToast('Username is required', 'error');
            return;
        }
        if (!password) {
            this.showToast('Password is required to enable/update auth', 'warning');
            return;
        }

        try {
            const res = await fetch('/api/auth/setup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            const data = await res.json();
            if (data.success) {
                this.showToast('Authentication configured', 'success');
                document.getElementById('setting-auth-password').value = '';
                this.populateAuthSettings();
                document.getElementById('btn-logout').style.display = '';
            } else {
                this.showToast(data.error || 'Failed', 'error');
            }
        } catch (e) {
            this.showToast('Failed to save auth', 'error');
        }
    }

    async saveSslSettings() {
        const data = {
            ssl_enabled: document.getElementById('setting-ssl-enabled').checked,
            ssl_cert: document.getElementById('setting-ssl-cert').value.trim(),
            ssl_key: document.getElementById('setting-ssl-key').value.trim(),
        };

        try {
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const result = await response.json();
            if (result.success) {
                this.config = { ...this.config, ...data };
                this.showToast('SSL settings saved. Restart server to apply.', 'success', 6000);
            } else {
                this.showToast('Error: ' + (result.error || 'Failed'), 'error');
            }
        } catch (e) {
            this.showToast('Failed to save SSL settings', 'error');
        }
    }

    // ============== Favorites ==============

    renderFavoritesSidebar() {
        const section = document.getElementById('favorites-section');
        const list = document.getElementById('favorites-list');
        const favorites = this.config.favorites || [];

        if (favorites.length === 0) {
            section.style.display = 'none';
            return;
        }

        section.style.display = 'block';
        list.innerHTML = favorites.map(fav => {
            const remoteHost = fav.remote_host_id
                ? (this.config.remote_hosts || []).find(h => h.id === fav.remote_host_id)
                : null;
            const badges = [];
            if (remoteHost) {
                badges.push(remoteHost.mode === 'ssh'
                    ? '<span class="badge ssh">SSH</span>'
                    : '<span class="badge mount">Mount</span>');
            }
            return `
                <div class="project-item" data-path="${this._escapeHtml(fav.path)}" data-remote-host-id="${this._escapeHtml(fav.remote_host_id || '')}">
                    <div class="project-name">
                        <span class="badge fav">&#9733;</span>
                        ${this._escapeHtml(fav.name)}
                        <div class="project-badges">${badges.join('')}</div>
                    </div>
                    <div class="project-path">${this._escapeHtml(fav.path)}</div>
                </div>
            `;
        }).join('');
    }

    renderFavoritesSettings() {
        const list = document.getElementById('favorites-settings-list');
        const favorites = this.config.favorites || [];

        if (favorites.length === 0) {
            list.innerHTML = '<div style="color: var(--text-secondary); font-size: 0.85rem;">No favorites yet</div>';
            return;
        }

        list.innerHTML = favorites.map((fav, idx) => `
            <div class="settings-item" data-index="${idx}">
                <div class="settings-item-info">
                    <div class="settings-item-name">${this._escapeHtml(fav.name)}</div>
                    <div class="settings-item-detail">${this._escapeHtml(fav.path)}</div>
                </div>
                <div class="settings-item-actions">
                    <button class="btn-sm danger" onclick="app.removeFavorite(${idx})">Remove</button>
                </div>
            </div>
        `).join('');
    }

    async addFavorite() {
        const name = document.getElementById('fav-name').value.trim();
        const path = document.getElementById('fav-path').value.trim();
        const remoteHostId = document.getElementById('fav-remote-host').value || null;

        if (!name || !path) {
            this.showToast('Name and path are required', 'warning');
            return;
        }

        const favorites = this.config.favorites || [];
        favorites.push({ name, path, remote_host_id: remoteHostId });

        try {
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ favorites })
            });
            const result = await response.json();
            if (result.success) {
                this.config.favorites = favorites;
                this.renderFavoritesSettings();
                this.renderFavoritesSidebar();
                document.getElementById('add-favorite-form').style.display = 'none';
                document.getElementById('fav-name').value = '';
                document.getElementById('fav-path').value = '';
            }
        } catch (error) {
            console.error('Failed to add favorite:', error);
        }
    }

    async removeFavorite(index) {
        const favorites = this.config.favorites || [];
        const fav = favorites[index];
        const ok = await this.confirm('Remove Favorite', `Remove "${fav?.name || 'this favorite'}" from favorites?`);
        if (!ok) return;
        favorites.splice(index, 1);

        try {
            await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ favorites })
            });
            this.config.favorites = favorites;
            this.renderFavoritesSettings();
            this.renderFavoritesSidebar();
        } catch (error) {
            console.error('Failed to remove favorite:', error);
        }
    }

    populateFavoriteRemoteSelect() {
        const select = document.getElementById('fav-remote-host');
        select.innerHTML = '<option value="">Local</option>';
        (this.config.remote_hosts || []).forEach(host => {
            select.innerHTML += `<option value="${this._escapeHtml(host.id)}">${this._escapeHtml(host.name)} (${this._escapeHtml(host.mode)})</option>`;
        });
    }

    // ============== Remote Hosts ==============

    renderRemoteHostsSidebar() {
        const section = document.getElementById('remote-hosts-section');
        const list = document.getElementById('remote-hosts-list');
        const hosts = this.config.remote_hosts || [];

        if (hosts.length === 0) {
            section.style.display = 'none';
            return;
        }

        section.style.display = 'block';
        list.innerHTML = hosts.map(host => `
            <div class="project-item" data-host-id="${this._escapeHtml(host.id)}">
                <div class="project-name">
                    ${this._escapeHtml(host.name)}
                    <div class="project-badges">
                        <span class="badge ${host.mode === 'ssh' ? 'ssh' : 'mount'}">${host.mode === 'ssh' ? 'SSH' : 'Mount'}</span>
                    </div>
                </div>
                <div class="project-path">${host.mode === 'ssh'
                    ? this._escapeHtml(host.username + '@' + host.hostname)
                    : this._escapeHtml(host.mount_path || '')}</div>
            </div>
        `).join('');
    }

    renderRemotesSettings() {
        const list = document.getElementById('remotes-settings-list');
        const hosts = this.config.remote_hosts || [];

        if (hosts.length === 0) {
            list.innerHTML = '<div style="color: var(--text-secondary); font-size: 0.85rem;">No remote hosts yet</div>';
            return;
        }

        list.innerHTML = hosts.map((host, idx) => `
            <div class="settings-item" data-index="${idx}">
                <div class="settings-item-info">
                    <div class="settings-item-name">
                        ${this._escapeHtml(host.name)}
                        <span class="badge ${host.mode === 'ssh' ? 'ssh' : 'mount'}" style="margin-left: 6px;">${host.mode === 'ssh' ? 'SSH - runs on remote' : 'Mount - runs locally'}</span>
                    </div>
                    <div class="settings-item-detail">${host.mode === 'ssh'
                        ? this._escapeHtml(host.username + '@' + host.hostname + ':' + host.port)
                        : this._escapeHtml(host.mount_path || '')}</div>
                </div>
                <div class="settings-item-actions">
                    <button class="btn-sm danger" onclick="app.removeRemoteHost(${idx})">Remove</button>
                </div>
            </div>
        `).join('');
    }

    async removeRemoteHost(index) {
        const remoteHosts = this.config.remote_hosts || [];
        const host = remoteHosts[index];
        const ok = await this.confirm('Remove Remote Host', `Remove "${host?.name || 'this host'}" from remote hosts?`);
        if (!ok) return;
        remoteHosts.splice(index, 1);

        try {
            await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ remote_hosts: remoteHosts })
            });
            this.config.remote_hosts = remoteHosts;
            this.renderRemotesSettings();
            this.renderRemoteHostsSidebar();
        } catch (error) {
            console.error('Failed to remove remote host:', error);
        }
    }



    async browseRemoteHost(hostId) {
        const host = (this.config.remote_hosts || []).find(h => h.id === hostId);
        if (!host) return;

        this.elements.projectsList.innerHTML = '<div class="empty-state"><div class="loading"></div><p>Loading remote projects...</p></div>';

        try {
            const response = await fetch(`/api/remote/${hostId}/projects`);
            const data = await response.json();

            if (data.error) {
                this.elements.projectsList.innerHTML = `<div class="empty-state"><p style="color: var(--error);">${this._escapeHtml(data.error)}</p></div>`;
                return;
            }

            this.currentRoot = data.root;
            this.elements.currentPath.value = `[${host.name}] ${data.root}`;
            this.selectedRemoteHostId = hostId;

            // Update section label to show remote context
            const label = document.getElementById('projects-section-label');
            label.innerHTML = `<span style="cursor:pointer;color:var(--accent);font-weight:bold;margin-right:6px;font-size:1.1rem;" title="Back to local projects" id="back-to-local">&larr;</span>${this._escapeHtml(host.name)} Projects`;
            document.getElementById('back-to-local').addEventListener('click', (e) => {
                e.stopPropagation();
                this.selectedRemoteHostId = null;
                label.textContent = 'Local Projects';
                document.querySelectorAll('#remote-hosts-list .project-item').forEach(i => i.classList.remove('active'));
                this.loadProjects();
            });

            this.renderProjects(data.projects);
        } catch (error) {
            console.error('Failed to browse remote host:', error);
            this.elements.projectsList.innerHTML = `<div class="empty-state"><p style="color: var(--error);">Failed to connect</p></div>`;
        }
    }

    // ============== Persistent Chat Session ==============

    async restorePersistentSession() {
        try {
            const response = await fetch('/api/session/persistent');
            if (response.ok) {
                this.currentSession = await response.json();
                this.renderChatMessages();
            }
        } catch (e) {
            console.error('Failed to restore persistent session:', e);
        }
    }

    // ============== Socket Connection ==============

    connectSocket() {
        this.socket = io({
            reconnection: true,
            reconnectionAttempts: Infinity,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 10000
        });

        this._wasConnected = false;

        this.socket.on('connect', () => {
            this.elements.connectionStatus.classList.add('connected');
            document.getElementById('connection-banner').classList.remove('visible');

            if (this._wasConnected) {
                this.showToast('Connection restored', 'success');
                document.getElementById('btn-send-chat').disabled = false;
            }
            this._wasConnected = true;

            // Check for detached tmux sessions to reconnect
            this._checkDetachedSessions();
        });

        this.socket.on('disconnect', (reason) => {
            this.elements.connectionStatus.classList.remove('connected');
            document.getElementById('connection-banner').classList.add('visible');
            this.showToast('Connection lost - reconnecting...', 'error', 6000);
        });

        this.socket.on('reconnect_attempt', () => {});

        // Terminal events
        this.socket.on('terminal_created', (data) => {
            this._addTerminalTab(data.id, data.project, data.tmux_session);
        });

        this.socket.on('terminal_output', (data) => {
            const term = this.terminals[data.id];
            if (term) {
                term.terminal.write(data.data);
            }
        });

        this.socket.on('terminal_closed', (data) => {
            const term = this.terminals[data.id];
            if (term) {
                if (data.tmux_alive && !data.tmux_killed) {
                    const tmuxName = data.tmux_session || term.tmux_session || '';
                    term.terminal.write('\r\n\x1b[36m[Detached from tmux session: ' + tmuxName + ']\x1b[0m\r\n');
                    term.terminal.write('\x1b[36m[Session is still running — reconnect anytime]\x1b[0m\r\n');
                } else {
                    term.terminal.write('\r\n\x1b[33m[Terminal session ended]\x1b[0m\r\n');
                }
                term.closed = true;
                this.renderTerminalTabs();
            }
            // Show reconnect banner if tmux session persists (outside if-term since closeTerminalTab may have already removed it)
            if (data.tmux_alive && !data.tmux_killed) {
                this._checkDetachedSessions();
            }
        });

        this.socket.on('tmux_session_killed', (data) => {
            this.showToast(`tmux session ${data.tmux_session} terminated`, 'info');
            this._checkDetachedSessions();
        });

        // Chat events
        this.socket.on('chat_status', (data) => {
            if (data.session_id === this.currentSession?.id) {
                this.elements.chatStatus.textContent = data.status === 'running' ? 'Claude is thinking...' : '';
            }
        });

        this.socket.on('chat_stream', (data) => {
            if (data.session_id === this.currentSession?.id) {
                this.appendStreamChunk(data.chunk);
            }
        });

        this.socket.on('chat_complete', (data) => {
            if (data.session_id === this.currentSession?.id) {
                this.finishStreamMessage();
                this.elements.chatStatus.textContent = '';
                document.getElementById('btn-send-chat').disabled = false;
                if (document.hidden) this._playNotificationSound('complete');
            }
        });

        this.socket.on('chat_error', (data) => {
            if (data.session_id === this.currentSession?.id) {
                this.elements.chatStatus.textContent = 'Error: ' + data.error;
                document.getElementById('btn-send-chat').disabled = false;
                if (document.hidden) this._playNotificationSound('error');
            }
        });

        // Usage events
        this.socket.on('usage_update', (data) => {
            this._usage.weekly.input_tokens += data.input_tokens || 0;
            this._usage.weekly.output_tokens += data.output_tokens || 0;
            this._usage.total.input_tokens += data.input_tokens || 0;
            this._usage.total.output_tokens += data.output_tokens || 0;
            this.renderUsage();
        });
    }

    // ============== Event Listeners ==============

    setupEventListeners() {
        // Mode tabs
        document.querySelectorAll('.mode-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.sidebar-panel').forEach(p => p.classList.remove('active'));
                tab.classList.add('active');
                document.getElementById(`${tab.dataset.mode}-panel`).classList.add('active');
            });
        });

        // View tabs (Terminal/Chat)
        document.querySelectorAll('.view-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.view-tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.view-content').forEach(v => v.classList.remove('active'));
                tab.classList.add('active');
                document.getElementById(`${tab.dataset.view}-view`).classList.add('active');

                if (tab.dataset.view === 'terminal' && this.activeTerminalId) {
                    const term = this.terminals[this.activeTerminalId];
                    if (term) {
                        term.fitAddon.fit();
                        term.terminal.focus();
                    }
                }
                if (tab.dataset.view === 'files' && this.selectedProject) {
                    this.loadFiles(this._filesCurrentPath || this.selectedProject);
                }
            });
        });

        // Path navigation
        document.getElementById('nav-up').addEventListener('click', () => {
            if (this.currentRoot && this.currentRoot !== '/' && this._currentParent) {
                this.loadProjects(this._currentParent);
            }
        });

        document.getElementById('nav-go').addEventListener('click', () => {
            const path = this.elements.currentPath.value.trim();
            if (path) this.loadProjects(path);
        });

        this.elements.currentPath.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') document.getElementById('nav-go').click();
        });

        // Launch option controls
        document.getElementById('flag-effort-level').addEventListener('click', (e) => {
            const btn = e.target.closest('.toggle-btn');
            if (!btn) return;
            document.querySelectorAll('#flag-effort-level .toggle-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
        });

        document.getElementById('flag-extended-thinking').addEventListener('change', (e) => {
            document.getElementById('thinking-tokens-wrap').classList.toggle('hidden', !e.target.checked);
        });

        document.getElementById('flag-print-mode').addEventListener('change', (e) => {
            document.getElementById('print-prompt-wrap').classList.toggle('hidden', !e.target.checked);
        });

        document.getElementById('launch-options-toggle').addEventListener('click', () => {
            const body = document.getElementById('launch-options-body');
            const arrow = document.querySelector('#launch-options-toggle .toggle-arrow');
            body.classList.toggle('hidden');
            arrow.textContent = body.classList.contains('hidden') ? '\u25B6' : '\u25BC';
        });

        document.getElementById('advanced-options-toggle').addEventListener('click', () => {
            const panel = document.getElementById('advanced-options');
            const arrow = document.querySelector('#advanced-options-toggle .toggle-arrow');
            panel.classList.toggle('hidden');
            arrow.textContent = panel.classList.contains('hidden') ? '\u25B6' : '\u25BC';
        });

        // Terminal buttons
        document.getElementById('btn-new-terminal').addEventListener('click', () => {
            this.createTerminal();
        });

        document.getElementById('btn-kill-terminal').addEventListener('click', async () => {
            if (!this.activeTerminalId) return;
            const ok = await this.confirm('Kill Terminal', 'Are you sure you want to kill this terminal session?');
            if (ok) this.killTerminal();
        });

        document.getElementById('btn-compact').addEventListener('click', () => {
            if (this.activeTerminalId && this.terminals[this.activeTerminalId] && !this.terminals[this.activeTerminalId].closed) {
                this.socket.emit('terminal_input', { id: this.activeTerminalId, data: '/compact\n' });
                this.showToast('Sent /compact to terminal', 'info');
            }
        });

        // Chat
        document.getElementById('btn-send-chat').addEventListener('click', () => {
            this.sendChatMessage();
        });

        this.elements.chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.altKey && !e.shiftKey) {
                e.preventDefault();
                this.sendChatMessage();
            }
        });

        // Logout
        document.getElementById('btn-logout').addEventListener('click', () => {
            window.location.href = '/logout';
        });

        // Settings modal
        document.getElementById('btn-settings').addEventListener('click', () => this.openSettings());
        document.getElementById('settings-close').addEventListener('click', () => this.closeSettings());
        document.getElementById('settings-overlay').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) this.closeSettings();
        });

        // Settings tabs
        document.querySelectorAll('.settings-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.settings-tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.settings-panel').forEach(p => p.classList.remove('active'));
                tab.classList.add('active');
                document.getElementById(`settings-${tab.dataset.settingsTab}`).classList.add('active');
            });
        });

        // General settings save
        document.getElementById('btn-save-general').addEventListener('click', () => this.saveGeneralSettings());

        // Auth save
        document.getElementById('btn-save-auth').addEventListener('click', () => this.saveAuthSettings());
        document.getElementById('btn-save-ssl').addEventListener('click', () => this.saveSslSettings());

        // Favorites
        document.getElementById('btn-add-favorite').addEventListener('click', () => {
            this.populateFavoriteRemoteSelect();
            document.getElementById('add-favorite-form').style.display = 'block';
        });
        document.getElementById('btn-cancel-favorite').addEventListener('click', () => {
            document.getElementById('add-favorite-form').style.display = 'none';
        });
        document.getElementById('btn-save-favorite').addEventListener('click', () => this.addFavorite());

        // Refresh projects
        document.getElementById('btn-refresh-projects').addEventListener('click', () => {
            this.loadProjects(this.currentRoot);
        });

        // Remote hosts - open wizard instead of inline form
        document.getElementById('btn-add-remote').addEventListener('click', () => this.openRemoteWizard());

        // Remote wizard controls
        document.getElementById('remote-wizard-close').addEventListener('click', () => this.closeRemoteWizard());
        document.getElementById('remote-wizard-overlay').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) this.closeRemoteWizard();
        });
        document.getElementById('rw-next').addEventListener('click', () => this._rwNext());
        document.getElementById('rw-prev').addEventListener('click', () => this._rwPrev());
        document.getElementById('rw-save').addEventListener('click', () => this._rwSave());
        document.getElementById('rw-manual-copy').addEventListener('click', () => {
            const cmd = document.getElementById('rw-manual-cmd').textContent;
            navigator.clipboard.writeText(cmd).then(() => this.showToast('Copied to clipboard', 'success'));
        });
        document.getElementById('rw-manual-retry').addEventListener('click', () => this._rwVerifyKeyAuth());

        // Users management
        document.getElementById('btn-add-user').addEventListener('click', () => {
            document.getElementById('add-user-form').style.display = 'block';
        });
        document.getElementById('btn-cancel-user').addEventListener('click', () => {
            document.getElementById('add-user-form').style.display = 'none';
        });
        document.getElementById('btn-save-user').addEventListener('click', () => this.addUser());

        // Agent Teams checkbox toggles sidebar summary
        document.getElementById('flag-agent-teams').addEventListener('change', (e) => {
            const summary = document.getElementById('sidebar-agents-summary');
            if (summary) summary.classList.toggle('hidden', !e.target.checked);
        });

        // Open agents modal from sidebar
        document.getElementById('btn-open-agents-modal').addEventListener('click', () => this.openAgentsModal());

        // Agents modal close
        document.getElementById('agents-modal-close').addEventListener('click', () => this.closeAgentsModal());
        document.getElementById('agents-overlay').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) this.closeAgentsModal();
        });

        // Agents modal filter (delegated)
        document.getElementById('agents-modal-filter').addEventListener('click', (e) => {
            const btn = e.target.closest('.btn-sm');
            if (!btn || !btn.dataset.category) return;
            document.querySelectorAll('#agents-modal-filter .btn-sm').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            this._agentCategoryFilter = btn.dataset.category;
            this.renderAgentModalGrid();
        });

        // Agents modal grid (delegated) — toggle active class directly
        // to avoid innerHTML replacement during click event processing
        document.getElementById('agents-modal-grid').addEventListener('click', (e) => {
            const card = e.target.closest('.agent-card');
            if (!card || card.classList.contains('locked')) return;
            const agentId = card.dataset.agentId;
            if (!agentId) return;
            const idx = this._activeAgents.indexOf(agentId);
            if (idx >= 0) {
                this._activeAgents.splice(idx, 1);
                card.classList.remove('active');
            } else if (this._activeAgents.length < 5) {
                this._activeAgents.push(agentId);
                card.classList.add('active');
            } else {
                this.showToast('Maximum 5 agents allowed (+ Sentinel)', 'warning');
                return;
            }
            this.updateAgentCount();
        });

        // Save & Close in agents modal
        document.getElementById('btn-save-agents-modal').addEventListener('click', () => {
            this.saveAgentConfig().then(() => this.closeAgentsModal());
        });

        // Custom agents (in settings modal)
        document.getElementById('btn-add-custom-agent').addEventListener('click', () => {
            const form = document.getElementById('add-custom-agent-form');
            form.style.display = form.style.display === 'none' ? 'block' : 'none';
            form.dataset.editIndex = '';
            document.getElementById('custom-agent-name').value = '';
            document.getElementById('custom-agent-description').value = '';
            document.getElementById('custom-agent-content').value = '';
        });
        document.getElementById('btn-cancel-custom-agent').addEventListener('click', () => {
            document.getElementById('add-custom-agent-form').style.display = 'none';
        });
        document.getElementById('btn-save-custom-agent').addEventListener('click', () => this.saveCustomAgent());
        document.getElementById('btn-save-agents').addEventListener('click', () => this.saveAgentConfig());

        // Export chat
        document.getElementById('btn-export-chat').addEventListener('click', () => this.exportChat());

        // Search sessions
        const searchInput = document.getElementById('chat-search-input');
        if (searchInput) {
            searchInput.addEventListener('input', () => {
                clearTimeout(this._searchDebounce);
                this._searchDebounce = setTimeout(() => this.searchSessions(searchInput.value), 300);
            });
            searchInput.addEventListener('focus', () => {
                if (searchInput.value.trim().length >= 2) this.searchSessions(searchInput.value);
            });
            document.addEventListener('click', (e) => {
                if (!e.target.closest('#chat-search-wrap')) {
                    document.getElementById('chat-search-results').classList.add('hidden');
                }
            });
        }

        // Sound toggle
        if (this.elements.soundToggle) {
            this.elements.soundToggle.addEventListener('change', () => {
                this._soundEnabled = this.elements.soundToggle.checked;
                localStorage.setItem('soundEnabled', this._soundEnabled);
                if (this._soundEnabled) this._playNotificationSound('complete');
            });
        }

        // Tooltips — prevent tip clicks from toggling parent checkboxes
        document.addEventListener('click', (e) => {
            if (e.target.closest('.tip')) e.preventDefault();
        }, true);

        // Tooltips (global delegated handler)
        let tipPopup = null;
        document.addEventListener('mouseenter', (e) => {
            if (!e.target.closest) return;
            const tip = e.target.closest('.tip');
            if (!tip || !tip.dataset.tip) return;
            if (tipPopup) tipPopup.remove();
            tipPopup = document.createElement('div');
            tipPopup.className = 'tip-popup';
            tipPopup.textContent = tip.dataset.tip;
            document.body.appendChild(tipPopup);
            const rect = tip.getBoundingClientRect();
            // Position to the right of the icon, vertically centered
            let top = rect.top + rect.height / 2 - tipPopup.offsetHeight / 2;
            let left = rect.right + 10;
            // If it overflows right, show to the left
            if (left + tipPopup.offsetWidth > window.innerWidth - 10) {
                left = rect.left - tipPopup.offsetWidth - 10;
            }
            // Keep within viewport vertically
            if (top < 10) top = 10;
            if (top + tipPopup.offsetHeight > window.innerHeight - 10) {
                top = window.innerHeight - tipPopup.offsetHeight - 10;
            }
            tipPopup.style.top = top + 'px';
            tipPopup.style.left = left + 'px';
        }, true);
        document.addEventListener('mouseleave', (e) => {
            if (e.target.closest && e.target.closest('.tip') && tipPopup) {
                tipPopup.remove();
                tipPopup = null;
            }
        }, true);

        // Shortcuts overlay
        document.getElementById('shortcuts-close').addEventListener('click', () => {
            document.getElementById('shortcuts-overlay').classList.add('hidden');
        });
        document.getElementById('shortcuts-overlay').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) e.currentTarget.classList.add('hidden');
        });

        // Changelog modal
        document.getElementById('changelog-close').addEventListener('click', () => {
            document.getElementById('changelog-overlay').classList.add('hidden');
        });
        document.getElementById('changelog-overlay').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) e.currentTarget.classList.add('hidden');
        });
        // Version link (delegated since it's created dynamically)
        document.querySelector('.sidebar-header').addEventListener('click', (e) => {
            const link = e.target.closest('#version-link');
            if (!link) return;
            e.preventDefault();
            this.openChangelog();
        });

        // Auto-follow toggle
        if (this.elements.autoFollow) {
            this.elements.autoFollow.addEventListener('change', () => {
                this._autoFollow = this.elements.autoFollow.checked;
                if (this._autoFollow) {
                    this.scrollChatToBottom(true);
                }
            });
        }

        // Scroll detection
        this.elements.chatMessages.addEventListener('scroll', () => {
            this._checkScrollPosition();
        });

        // Window resize - fit active terminal
        window.addEventListener('resize', () => {
            if (this.activeTerminalId) {
                const term = this.terminals[this.activeTerminalId];
                if (term) term.fitAddon.fit();
            }
        });

        // Wizard
        document.getElementById('btn-init-wizard').addEventListener('click', () => {
            if (this.selectedProject) this.openWizard(this.selectedProject);
        });
        document.getElementById('wizard-close').addEventListener('click', () => this.closeWizard());
        document.getElementById('wizard-overlay').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) this.closeWizard();
        });
        document.getElementById('wiz-next').addEventListener('click', () => this._wizardNext());
        document.getElementById('wiz-prev').addEventListener('click', () => this._wizardPrev());
        document.getElementById('wiz-create').addEventListener('click', () => this._wizardCreate());
        document.getElementById('wiz-view-preview').addEventListener('click', () => this._wizardToggleView('preview'));
        document.getElementById('wiz-view-source').addEventListener('click', () => this._wizardToggleView('source'));
        document.getElementById('wiz-create-settings').addEventListener('change', (e) => {
            document.getElementById('wiz-settings-options').style.display = e.target.checked ? 'block' : 'none';
        });
        // Allow clicking step indicators to jump
        document.querySelectorAll('.wizard-step').forEach(step => {
            step.addEventListener('click', () => {
                const target = parseInt(step.dataset.step);
                if (target <= this._wizardStep || step.classList.contains('completed')) {
                    this._wizardStep = target;
                    this._renderWizardStep();
                }
            });
        });

        // Delegated event listeners for dynamically rendered lists (prevents listener leaks)
        // Projects list (click = select, dblclick = select + open terminal)
        this.elements.projectsList.addEventListener('click', (e) => {
            const item = e.target.closest('.project-item');
            if (!item) return;
            const remoteHostId = item.dataset.remoteHostId || this.selectedRemoteHostId || null;
            this.selectProject(item.dataset.path, remoteHostId);
        });
        this.elements.projectsList.addEventListener('dblclick', (e) => {
            const item = e.target.closest('.project-item');
            if (!item) return;
            const remoteHostId = item.dataset.remoteHostId || this.selectedRemoteHostId || null;
            this.selectProject(item.dataset.path, remoteHostId);
            this.createTerminal();
        });

        // Favorites sidebar list
        const favList = document.getElementById('favorites-list');
        if (favList) {
            favList.addEventListener('click', (e) => {
                const item = e.target.closest('.project-item');
                if (!item) return;
                this.selectProject(item.dataset.path, item.dataset.remoteHostId || null);
            });
            favList.addEventListener('dblclick', (e) => {
                const item = e.target.closest('.project-item');
                if (!item) return;
                this.selectProject(item.dataset.path, item.dataset.remoteHostId || null);
                this.createTerminal();
            });
        }

        // Remote hosts sidebar list
        const remoteList = document.getElementById('remote-hosts-list');
        if (remoteList) {
            remoteList.addEventListener('click', (e) => {
                const item = e.target.closest('.project-item');
                if (!item) return;
                remoteList.querySelectorAll('.project-item').forEach(i => i.classList.remove('active'));
                item.classList.add('active');
                this.browseRemoteHost(item.dataset.hostId);
            });
        }

        // File tree (click on dir = navigate, click on file = view)
        const fileTree = document.getElementById('file-tree');
        if (fileTree) {
            fileTree.addEventListener('click', (e) => {
                const item = e.target.closest('.file-item');
                if (!item) return;
                if (item.dataset.isDir === 'true') {
                    this.loadFiles(item.dataset.path);
                } else {
                    this.viewFile(item.dataset.path);
                    fileTree.querySelectorAll('.file-item').forEach(f => f.classList.remove('selected'));
                    item.classList.add('selected');
                }
            });
        }

        // Search results
        const searchResults = document.getElementById('search-results');
        if (searchResults) {
            searchResults.addEventListener('click', (e) => {
                const item = e.target.closest('.search-result-item');
                if (!item) return;
                this.loadSessionById(item.dataset.sessionId);
                searchResults.classList.add('hidden');
                document.getElementById('chat-search-input').value = '';
            });
        }
    }

    _checkScrollPosition() {
        if (this._scrollLock) return;

        const el = this.elements.chatMessages;
        const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
        const isAtBottom = distFromBottom < 150;

        if (!isAtBottom && this._autoFollow) {
            this._autoFollow = false;
            if (this.elements.autoFollow) this.elements.autoFollow.checked = false;
        } else if (isAtBottom && !this._autoFollow) {
            this._autoFollow = true;
            if (this.elements.autoFollow) this.elements.autoFollow.checked = true;
        }
    }

    // ============== Projects ==============

    async loadProjects(root = null) {
        const url = root ? `/api/projects?root=${encodeURIComponent(root)}` : '/api/projects';
        this.selectedRemoteHostId = null;
        document.getElementById('projects-section-label').textContent = 'Local Projects';

        try {
            const response = await fetch(url);
            const data = await response.json();
            this.currentRoot = data.root;
            this._currentParent = data.parent;
            this.elements.currentPath.value = data.root;
            this.renderProjects(data.projects);
        } catch (error) {
            console.error('Failed to load projects:', error);
            this.elements.projectsList.innerHTML = '<div class="empty-state">Failed to load projects</div>';
        }
    }

    renderProjects(projects) {
        if (projects.length === 0) {
            this.elements.projectsList.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">&#128193;</div>
                    <p>No projects found in this directory</p>
                </div>
            `;
            return;
        }

        this.elements.projectsList.innerHTML = projects.map(project => `
            <div class="project-item ${project.type === 'current' ? 'current-dir' : ''}" data-path="${this._escapeHtml(project.path)}">
                <div class="project-name">
                    ${this._escapeHtml(project.name)}
                    <div class="project-badges">
                        ${project.type === 'current' ? '<span class="badge current">USE THIS</span>' : ''}
                        ${project.indicators.claude ? '<span class="badge claude">Claude</span>' : ''}
                        ${project.indicators.git ? '<span class="badge git">Git</span>' : ''}
                        ${project.indicators.node ? '<span class="badge node">Node</span>' : ''}
                        ${project.indicators.python ? '<span class="badge python">Python</span>' : ''}
                        ${project.indicators.rust ? '<span class="badge rust">Rust</span>' : ''}
                    </div>
                </div>
                <div class="project-path">${this._escapeHtml(project.path)}</div>
            </div>
        `).join('');
    }

    selectProject(path, remoteHostId = null) {
        this.selectedProject = path;
        this.selectedRemoteHostId = remoteHostId || null;

        document.querySelectorAll('.project-item').forEach(item => {
            item.classList.toggle('selected', item.dataset.path === path);
        });

        let label = path;
        if (remoteHostId) {
            const host = (this.config.remote_hosts || []).find(h => h.id === remoteHostId);
            if (host) {
                label = `[${host.mode === 'ssh' ? 'SSH' : 'Mounted'}: ${host.name}] ${path}`;
            }
        }
        this.elements.terminalProject.textContent = label;
        this._filesCurrentPath = path;
        this.fetchGitStatus(path);

        // Show/hide wizard button (hidden for remote hosts)
        const wizBtn = document.getElementById('btn-init-wizard');
        if (wizBtn) wizBtn.style.display = remoteHostId ? 'none' : '';
    }

    // ============== Terminal Tabs ==============

    _terminalTheme() {
        return {
            background: '#0f0f1a',
            foreground: '#eaeaea',
            cursor: '#e94560',
            selection: 'rgba(233, 69, 96, 0.3)',
            black: '#1a1a2e',
            red: '#f87171',
            green: '#4ade80',
            yellow: '#fbbf24',
            blue: '#60a5fa',
            magenta: '#c084fc',
            cyan: '#22d3ee',
            white: '#eaeaea',
        };
    }

    initTerminalWelcome() {
        // Show a static welcome message, no xterm instance yet
        this.elements.terminalContainer.innerHTML = `
            <div class="terminal-welcome">
                <div style="color: #fbbf24; white-space: pre; font-size: 0.85rem; line-height: 1.4;">
+------------------------------------------+
|     Welcome to QN Code Assistant           |
+------------------------------------------+</div>
                <p style="margin-top: 12px; color: var(--text-secondary);">Select a project and click <span style="color: var(--success);">[+]</span> to start a terminal session.</p>
                <p style="color: var(--text-secondary);">Or double-click a project to launch immediately.</p>
            </div>
        `;
    }

    _createTerminalInstance(terminalId, project) {
        const container = document.createElement('div');
        container.className = 'terminal-instance';
        container.id = `term-${terminalId}`;
        container.style.display = 'none';
        this.elements.terminalContainer.appendChild(container);

        const terminal = new Terminal({
            cursorBlink: true,
            fontSize: 14,
            fontFamily: "'SF Mono', 'Fira Code', 'Consolas', monospace",
            theme: this._terminalTheme()
        });

        const fitAddon = new FitAddon.FitAddon();
        const webLinksAddon = new WebLinksAddon.WebLinksAddon();
        terminal.loadAddon(fitAddon);
        terminal.loadAddon(webLinksAddon);

        terminal.open(container);

        // Let browser handle copy/paste shortcuts instead of sending to PTY
        terminal.attachCustomKeyEventHandler((e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'v') return false;
            if ((e.ctrlKey || e.metaKey) && e.key === 'c' && terminal.hasSelection()) return false;
            return true;
        });

        // Handle input
        terminal.onData(data => {
            if (this.terminals[terminalId] && !this.terminals[terminalId].closed) {
                this.socket.emit('terminal_input', { id: terminalId, data: data });
            }
        });

        // Handle resize
        terminal.onResize(({ cols, rows }) => {
            if (this.terminals[terminalId] && !this.terminals[terminalId].closed) {
                this.socket.emit('terminal_resize', { id: terminalId, cols, rows });
            }
        });

        return { terminal, fitAddon, container, project, closed: false, tmux_session: null };
    }

    _addTerminalTab(terminalId, project, tmuxSession) {
        // Remove welcome message if present
        const welcome = this.elements.terminalContainer.querySelector('.terminal-welcome');
        if (welcome) welcome.remove();

        const termData = this._createTerminalInstance(terminalId, project);
        termData.tmux_session = tmuxSession || null;
        this.terminals[terminalId] = termData;
        this.switchTerminalTab(terminalId);
        this.renderTerminalTabs();

        const projectName = project.split('/').pop() || project;
        if (tmuxSession) {
            termData.terminal.write(`\x1b[36mConnected: ${projectName} [tmux: ${tmuxSession}]\x1b[0m\r\n`);
        } else {
            termData.terminal.write(`\x1b[36mConnected: ${projectName}\x1b[0m\r\n`);
        }
    }

    switchTerminalTab(terminalId) {
        // Hide all terminal instances
        Object.values(this.terminals).forEach(t => {
            t.container.style.display = 'none';
        });

        const term = this.terminals[terminalId];
        if (term) {
            term.container.style.display = '';
            this.activeTerminalId = terminalId;

            // Update toolbar label
            const projectName = term.project.split('/').pop() || term.project;
            this.elements.terminalProject.textContent = term.project;

            // Fit after display
            requestAnimationFrame(() => {
                term.fitAddon.fit();
                term.terminal.focus();
            });
        }

        this.renderTerminalTabs();
    }

    async closeTerminalTab(terminalId) {
        const term = this.terminals[terminalId];
        if (!term) return;

        // If still running and has a tmux session, offer detach vs kill
        if (!term.closed && term.tmux_session) {
            const choice = await this.confirm(
                'Close Terminal',
                'Detach (keep session running for reconnect) or Kill (terminate session)?',
                'Kill', 'danger', 'Detach'
            );
            if (choice) {
                // Kill = terminate tmux session
                this.socket.emit('terminal_kill', { id: terminalId, kill_tmux: true });
            } else {
                // Detach = keep tmux alive
                this.socket.emit('terminal_detach', { id: terminalId });
            }
        } else if (!term.closed) {
            this.socket.emit('terminal_kill', { id: terminalId, kill_tmux: true });
        }

        // Dispose xterm and remove container
        term.terminal.dispose();
        term.container.remove();
        delete this.terminals[terminalId];

        // Switch to another tab or show welcome
        const remainingIds = Object.keys(this.terminals);
        if (remainingIds.length > 0) {
            this.switchTerminalTab(remainingIds[remainingIds.length - 1]);
        } else {
            this.activeTerminalId = null;
            this.initTerminalWelcome();
        }

        this.renderTerminalTabs();
    }

    renderTerminalTabs() {
        const tabsList = this.elements.terminalTabsList;
        if (!tabsList) return;

        const ids = Object.keys(this.terminals);
        if (ids.length === 0) {
            tabsList.innerHTML = '';
            return;
        }

        tabsList.innerHTML = ids.map(id => {
            const t = this.terminals[id];
            const projectName = t.project.split('/').pop() || 'Terminal';
            const isActive = id === this.activeTerminalId;
            const isClosed = t.closed;
            return `
                <div class="terminal-tab ${isActive ? 'active' : ''} ${isClosed ? 'closed' : ''}" data-id="${id}">
                    ${!isClosed ? '<span class="terminal-tab-dot"></span>' : ''}
                    <span class="terminal-tab-name">${projectName}</span>
                    <button class="terminal-tab-close" data-id="${id}" title="Close">&times;</button>
                </div>
            `;
        }).join('');

        // Tab click handlers
        tabsList.querySelectorAll('.terminal-tab').forEach(tab => {
            tab.addEventListener('click', (e) => {
                if (!e.target.classList.contains('terminal-tab-close')) {
                    this.switchTerminalTab(tab.dataset.id);
                }
            });
        });

        // Close button handlers
        tabsList.querySelectorAll('.terminal-tab-close').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.closeTerminalTab(btn.dataset.id);
            });
        });
    }

    createTerminal() {
        // Debounce rapid clicks (1s cooldown)
        const now = Date.now();
        if (now - (this._lastAction.createTerminal || 0) < 1000) return;
        this._lastAction.createTerminal = now;

        if (!this.selectedProject) {
            this.showToast('Please select a project first', 'warning');
            return;
        }

        const flags = this.getFlags();

        this.socket.emit('terminal_create', {
            project: this.selectedProject,
            flags: flags,
            remote_host_id: this.selectedRemoteHostId || undefined
        });
    }

    killTerminal(terminalId = null) {
        const id = terminalId || this.activeTerminalId;
        if (id && this.terminals[id] && !this.terminals[id].closed) {
            this.socket.emit('terminal_kill', { id: id, kill_tmux: true });
        }
    }

    async _checkDetachedSessions() {
        /**Check for detached tmux sessions and offer reconnection.*/
        try {
            const resp = await fetch('/api/tmux/sessions');
            if (!resp.ok) return;
            const data = await resp.json();
            const detached = (data.sessions || []).filter(s => !s.attached);
            if (detached.length === 0) return;

            // Show reconnect banner
            this._showTmuxReconnectBanner(detached);
        } catch (e) {
            // Silently fail — not critical
        }
    }

    _showTmuxReconnectBanner(sessions) {
        /**Show a banner with detached tmux sessions available for reconnect.*/
        // Remove existing banner if any
        const existing = document.getElementById('tmux-reconnect-banner');
        if (existing) existing.remove();

        const banner = document.createElement('div');
        banner.id = 'tmux-reconnect-banner';
        banner.className = 'tmux-reconnect-banner';

        const count = sessions.length;
        const label = count === 1 ? '1 persistent session' : `${count} persistent sessions`;

        banner.innerHTML = `
            <div class="tmux-banner-content">
                <span class="tmux-banner-icon">&#9654;</span>
                <span class="tmux-banner-text">${label} available for reconnect</span>
                <div class="tmux-banner-sessions">
                    ${sessions.map(s => `
                        <button class="tmux-reconnect-btn" data-tmux="${s.name}" title="Created: ${s.created || 'unknown'}">
                            ${s.name}
                        </button>
                    `).join('')}
                </div>
                <button class="tmux-banner-dismiss" title="Dismiss">&times;</button>
            </div>
        `;

        // Insert at top of terminal container area
        const termArea = document.querySelector('.terminal-area') || document.getElementById('terminal-container');
        if (termArea && termArea.parentNode) {
            termArea.parentNode.insertBefore(banner, termArea);
        }

        // Event delegation for reconnect buttons
        banner.addEventListener('click', (e) => {
            const reconnectBtn = e.target.closest('.tmux-reconnect-btn');
            if (reconnectBtn) {
                const tmuxName = reconnectBtn.dataset.tmux;
                this.reconnectTmuxSession(tmuxName);
                reconnectBtn.disabled = true;
                reconnectBtn.textContent = 'Connecting...';
                return;
            }
            if (e.target.classList.contains('tmux-banner-dismiss')) {
                banner.remove();
            }
        });
    }

    reconnectTmuxSession(tmuxName) {
        /**Reconnect to a detached tmux session.*/
        this.socket.emit('terminal_reconnect', {
            tmux_session: tmuxName,
            project: this.selectedProject || '/opt/claude-web',
        });

        // Remove from banner
        setTimeout(() => {
            const banner = document.getElementById('tmux-reconnect-banner');
            if (banner) {
                const btn = banner.querySelector(`[data-tmux="${tmuxName}"]`);
                if (btn) btn.remove();
                // Remove banner if no more sessions
                const remaining = banner.querySelectorAll('.tmux-reconnect-btn');
                if (remaining.length === 0) banner.remove();
            }
        }, 1000);
    }

    killTmuxSession(tmuxName) {
        /**Kill a detached tmux session without reconnecting.*/
        this.socket.emit('terminal_kill_tmux', { tmux_session: tmuxName });
    }

    // ============== Chat ==============

    renderChatMessages() {
        if (!this.currentSession) {
            this.elements.chatMessages.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">&#128172;</div>
                    <p>Chat session loading...</p>
                </div>
            `;
            return;
        }

        const messages = this.currentSession.messages || [];

        if (messages.length === 0) {
            this.elements.chatMessages.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">&#128640;</div>
                    <p>Ready to chat with Claude Code</p>
                    <p style="font-size: 0.8rem; margin-top: 8px;">Working directory: ${this.currentSession.project || '/opt/claude'}</p>
                </div>
            `;
            return;
        }

        this.elements.chatMessages.innerHTML = messages.map(msg => `
            <div class="message ${msg.role}">
                <div class="message-content">${this.renderMarkdown(msg.content)}</div>
                <div class="message-time">${this.formatDate(msg.timestamp)}</div>
            </div>
        `).join('');

        this.addCopyButtons(this.elements.chatMessages);

        const anchor = document.createElement('div');
        anchor.className = 'scroll-anchor';
        this.elements.chatMessages.appendChild(anchor);

        this._autoFollow = true;
        if (this.elements.autoFollow) this.elements.autoFollow.checked = true;
        this.scrollChatToBottom(true);
    }

    async sendChatMessage() {
        const message = this.elements.chatInput.value.trim();
        if (!message) return;

        // Ensure persistent session exists
        if (!this.currentSession) {
            await this.restorePersistentSession();
            if (!this.currentSession) {
                this.showToast('Failed to create chat session', 'error');
                return;
            }
        }

        this.addMessageToUI('user', message);
        this.elements.chatInput.value = '';

        document.getElementById('btn-send-chat').disabled = true;

        this.createStreamPlaceholder();

        this.socket.emit('chat_message', {
            session_id: this.currentSession.id,
            message: message
        });
    }

    addMessageToUI(role, content) {
        if (this.currentSession) {
            if (!this.currentSession.messages) this.currentSession.messages = [];
            this.currentSession.messages.push({
                role,
                content,
                timestamp: new Date().toISOString()
            });
        }

        this._scrollLock = true;

        const existingAnchor = this.elements.chatMessages.querySelector('.scroll-anchor');
        if (existingAnchor) existingAnchor.remove();

        // Remove empty state if present
        const emptyState = this.elements.chatMessages.querySelector('.empty-state');
        if (emptyState) emptyState.remove();

        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        messageDiv.innerHTML = `
            <div class="message-content">${this.renderMarkdown(content)}</div>
            <div class="message-time">${this.formatDate(new Date().toISOString())}</div>
        `;
        this.elements.chatMessages.appendChild(messageDiv);
        this.addCopyButtons(messageDiv);

        const anchor = document.createElement('div');
        anchor.className = 'scroll-anchor';
        this.elements.chatMessages.appendChild(anchor);

        this._autoFollow = true;
        if (this.elements.autoFollow) this.elements.autoFollow.checked = true;
        this.scrollChatToBottom(true);
    }

    createStreamPlaceholder() {
        const existingAnchor = this.elements.chatMessages.querySelector('.scroll-anchor');
        if (existingAnchor) existingAnchor.remove();

        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant';
        messageDiv.id = 'streaming-message';
        messageDiv.innerHTML = `<div class="message-content streaming"></div>`;
        this.elements.chatMessages.appendChild(messageDiv);

        const anchor = document.createElement('div');
        anchor.className = 'scroll-anchor';
        this.elements.chatMessages.appendChild(anchor);

        this.scrollChatToBottom(true);
    }

    appendStreamChunk(chunk) {
        this._streamBuffer += chunk;

        if (!this._streamFlushTimer) {
            this._streamFlushTimer = setTimeout(() => {
                this._flushStreamBuffer();
            }, this._streamFlushInterval);
        }
    }

    _flushStreamBuffer() {
        this._streamFlushTimer = null;

        if (!this._streamBuffer) return;

        const streamingMessage = document.getElementById('streaming-message');
        if (streamingMessage) {
            const content = streamingMessage.querySelector('.message-content');
            this._scrollLock = true;
            content.textContent += this._streamBuffer;
            this._streamBuffer = '';
            this.scrollChatToBottom();
        }
    }

    finishStreamMessage() {
        // Flush any remaining buffer first
        if (this._streamFlushTimer) {
            clearTimeout(this._streamFlushTimer);
            this._streamFlushTimer = null;
        }
        this._flushStreamBuffer();

        const streamingMessage = document.getElementById('streaming-message');
        if (!streamingMessage) return;

        const content = streamingMessage.querySelector('.message-content');
        const container = this.elements.chatMessages;

        // Persist assistant response to session object
        if (this.currentSession) {
            if (!this.currentSession.messages) this.currentSession.messages = [];
            this.currentSession.messages.push({
                role: 'assistant',
                content: content.textContent,
                timestamp: new Date().toISOString()
            });
        }

        // Lock scroll detection for the entire reflow
        this._scrollLock = true;
        const shouldFollow = this._autoFollow;

        // SCROLL FIX: Lock the message height during the reflow to prevent collapse
        const currentHeight = streamingMessage.getBoundingClientRect().height;
        streamingMessage.style.minHeight = currentHeight + 'px';

        streamingMessage.classList.add('stream-complete');
        content.classList.remove('streaming');

        // This is the line that causes reflow - replace raw text with rendered markdown
        content.innerHTML = this.renderMarkdown(content.textContent);
        this.addCopyButtons(streamingMessage);
        streamingMessage.removeAttribute('id');

        // Add timestamp
        const timeDiv = document.createElement('div');
        timeDiv.className = 'message-time';
        timeDiv.textContent = this.formatDate(new Date().toISOString());
        streamingMessage.appendChild(timeDiv);

        // Release height lock and scroll in next frame
        requestAnimationFrame(() => {
            streamingMessage.style.minHeight = '';

            if (shouldFollow) {
                container.scrollTop = container.scrollHeight;
            }

            requestAnimationFrame(() => {
                this._scrollLock = false;
            });
        });
    }

    scrollChatToBottom(force = false) {
        if (!force && !this._autoFollow) return;

        if (this._scrollTimer) {
            cancelAnimationFrame(this._scrollTimer);
            this._scrollTimer = null;
        }

        this._scrollLock = true;

        this._scrollTimer = requestAnimationFrame(() => {
            this._scrollTimer = requestAnimationFrame(() => {
                this.elements.chatMessages.scrollTop = this.elements.chatMessages.scrollHeight;
                this._scrollTimer = null;
                requestAnimationFrame(() => {
                    this._scrollLock = false;
                });
            });
        });
    }

    // ============== Usage Tracking ==============

    async loadUsage() {
        try {
            const response = await fetch('/api/usage');
            if (response.ok) {
                const data = await response.json();
                this._usage = data;
                this.renderUsage();
            }
        } catch (e) {
            console.error('Failed to load usage:', e);
        }
    }

    renderUsage() {
        const display = document.getElementById('usage-display');
        const textEl = document.getElementById('usage-text');
        const resetEl = document.getElementById('usage-reset');
        if (!display || !textEl) return;

        display.style.display = 'flex';

        const weekly = this._usage.weekly || { input_tokens: 0, output_tokens: 0 };
        const fmtTokens = (n) => {
            if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
            if (n >= 1000) return (n / 1000).toFixed(1) + 'k';
            return n.toString();
        };

        textEl.textContent = `Week: ${fmtTokens(weekly.input_tokens)} in / ${fmtTokens(weekly.output_tokens)} out`;

        if (this._usage.reset_time && resetEl) {
            const reset = new Date(this._usage.reset_time);
            const now = new Date();
            const diffMs = reset - now;
            if (diffMs > 0) {
                const days = Math.floor(diffMs / 86400000);
                const hours = Math.floor((diffMs % 86400000) / 3600000);
                resetEl.textContent = `Resets: ${days}d ${hours}h`;
            }
        }
    }

    // ============== Toast Notifications ==============

    showToast(message, type = 'info', duration = 4000) {
        const container = document.getElementById('toast-container');
        const icons = { success: '\u2713', error: '\u2717', warning: '\u26A0', info: '\u2139' };
        const safeType = ['success', 'error', 'warning', 'info'].includes(type) ? type : 'info';

        const toast = document.createElement('div');
        toast.className = `toast ${safeType}`;
        toast.innerHTML = `
            <span class="toast-icon">${icons[safeType] || icons.info}</span>
            <span class="toast-body">${this._escapeHtml(message)}</span>
            <button class="toast-close">\u00D7</button>
        `;

        toast.querySelector('.toast-close').addEventListener('click', () => this._dismissToast(toast));
        container.appendChild(toast);

        if (duration > 0) {
            setTimeout(() => this._dismissToast(toast), duration);
        }

        return toast;
    }

    _dismissToast(toast) {
        if (!toast || !toast.parentNode) return;
        toast.classList.add('toast-out');
        toast.addEventListener('animationend', () => toast.remove());
    }

    // ============== Confirm Dialog ==============

    confirm(title, message, confirmLabel = 'Confirm', type = 'danger', cancelLabel = 'Cancel') {
        return new Promise((resolve) => {
            const safeType = ['danger', 'warning', 'info', 'success'].includes(type) ? type : 'danger';
            const overlay = document.createElement('div');
            overlay.className = 'confirm-overlay';
            overlay.innerHTML = `
                <div class="confirm-modal">
                    <div class="confirm-title">${this._escapeHtml(title)}</div>
                    <div class="confirm-message">${this._escapeHtml(message)}</div>
                    <div class="confirm-actions">
                        <button class="confirm-btn cancel">${this._escapeHtml(cancelLabel)}</button>
                        <button class="confirm-btn ${safeType}">${this._escapeHtml(confirmLabel)}</button>
                    </div>
                </div>
            `;

            const cancel = overlay.querySelector('.confirm-btn.cancel');
            const confirmBtn = overlay.querySelector(`.confirm-btn.${type}`);

            const close = (result) => {
                overlay.remove();
                resolve(result);
            };

            cancel.addEventListener('click', () => close(false));
            confirmBtn.addEventListener('click', () => close(true));
            overlay.addEventListener('click', (e) => {
                if (e.target === overlay) close(false);
            });

            const onKey = (e) => {
                if (e.key === 'Escape') {
                    document.removeEventListener('keydown', onKey);
                    close(false);
                }
            };
            document.addEventListener('keydown', onKey);

            document.body.appendChild(overlay);
            confirmBtn.focus();
        });
    }

    // ============== Code Copy Buttons ==============

    addCopyButtons(container) {
        container.querySelectorAll('pre').forEach(pre => {
            if (pre.querySelector('.code-copy-btn')) return;
            const btn = document.createElement('button');
            btn.className = 'code-copy-btn';
            btn.textContent = 'Copy';
            btn.addEventListener('click', async () => {
                const code = pre.querySelector('code');
                const text = code ? code.textContent : pre.textContent;
                try {
                    await navigator.clipboard.writeText(text);
                    btn.textContent = 'Copied!';
                    btn.classList.add('copied');
                    setTimeout(() => {
                        btn.textContent = 'Copy';
                        btn.classList.remove('copied');
                    }, 2000);
                } catch {
                    this.showToast('Failed to copy to clipboard', 'error');
                }
            });
            pre.appendChild(btn);
        });
    }

    // ============== Keyboard Shortcuts ==============

    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Don't capture when typing in inputs (except specific combos)
            const inInput = e.target.matches('input, textarea, select');
            const inTerminal = e.target.closest('.xterm');

            // Ctrl+ combos work everywhere except terminal
            if (e.ctrlKey && !inTerminal) {
                switch (e.key) {
                    case '1':
                        e.preventDefault();
                        this._switchView('terminal');
                        return;
                    case '2':
                        e.preventDefault();
                        this._switchView('chat');
                        return;
                    case '3':
                        e.preventDefault();
                        this._switchView('files');
                        return;
                    case 't':
                        e.preventDefault();
                        this.createTerminal();
                        return;
                    case 'w':
                        e.preventDefault();
                        if (this.activeTerminalId) this.closeTerminalTab(this.activeTerminalId);
                        return;
                    case 'k':
                        e.preventDefault();
                        this._switchView('chat');
                        this.elements.chatInput.focus();
                        return;
                    case ',':
                        e.preventDefault();
                        this.openSettings();
                        return;
                    case '/':
                        e.preventDefault();
                        this._switchView('chat');
                        const searchInput = document.getElementById('chat-search-input');
                        if (searchInput) searchInput.focus();
                        return;
                }

                // Ctrl+Shift+Arrow for terminal tab switching
                if (e.shiftKey && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
                    e.preventDefault();
                    this._switchTerminalTabDirection(e.key === 'ArrowRight' ? 1 : -1);
                    return;
                }
            }

            // Escape: close modals
            if (e.key === 'Escape') {
                const wizard = document.getElementById('wizard-overlay');
                if (wizard && !wizard.classList.contains('hidden')) {
                    this.closeWizard();
                    return;
                }
                const shortcuts = document.getElementById('shortcuts-overlay');
                if (!shortcuts.classList.contains('hidden')) {
                    shortcuts.classList.add('hidden');
                    return;
                }
                const settings = document.getElementById('settings-overlay');
                if (!settings.classList.contains('hidden')) {
                    this.closeSettings();
                    return;
                }
                const searchResults = document.getElementById('chat-search-results');
                if (searchResults && !searchResults.classList.contains('hidden')) {
                    searchResults.classList.add('hidden');
                    return;
                }
            }

            // ? shows shortcuts help (only when not in input)
            if (e.key === '?' && !inInput && !inTerminal) {
                document.getElementById('shortcuts-overlay').classList.remove('hidden');
            }
        });
    }

    _switchView(viewName) {
        document.querySelectorAll('.view-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.view-content').forEach(v => v.classList.remove('active'));
        const tab = document.querySelector(`.view-tab[data-view="${viewName}"]`);
        if (tab) tab.classList.add('active');
        const view = document.getElementById(`${viewName}-view`);
        if (view) view.classList.add('active');

        if (viewName === 'terminal' && this.activeTerminalId) {
            const term = this.terminals[this.activeTerminalId];
            if (term) { term.fitAddon.fit(); term.terminal.focus(); }
        }
        if (viewName === 'files' && this.selectedProject) {
            this.loadFiles(this._filesCurrentPath || this.selectedProject);
        }
    }

    _switchTerminalTabDirection(dir) {
        const ids = Object.keys(this.terminals);
        if (ids.length < 2) return;
        const idx = ids.indexOf(this.activeTerminalId);
        const next = (idx + dir + ids.length) % ids.length;
        this.switchTerminalTab(ids[next]);
    }

    // ============== Themes ==============

    applyTheme(themeName) {
        const themes = {
            dark: {
                '--bg-primary': '#1a1a2e',
                '--bg-secondary': '#16213e',
                '--bg-tertiary': '#0f0f1a',
                '--accent': '#e94560',
                '--accent-hover': '#ff6b6b',
                '--text-primary': '#eaeaea',
                '--text-secondary': '#a0a0a0',
                '--border-color': '#2d2d44',
            },
            midnight: {
                '--bg-primary': '#0d1b2a',
                '--bg-secondary': '#1b2838',
                '--bg-tertiary': '#070d15',
                '--accent': '#3a86ff',
                '--accent-hover': '#5da0ff',
                '--text-primary': '#e0e1dd',
                '--text-secondary': '#8d99ae',
                '--border-color': '#233345',
            },
            solarized: {
                '--bg-primary': '#002b36',
                '--bg-secondary': '#073642',
                '--bg-tertiary': '#001e26',
                '--accent': '#b58900',
                '--accent-hover': '#d4a017',
                '--text-primary': '#fdf6e3',
                '--text-secondary': '#93a1a1',
                '--border-color': '#0a4a5a',
            },
            light: {
                '--bg-primary': '#f5f5f5',
                '--bg-secondary': '#ffffff',
                '--bg-tertiary': '#e8e8e8',
                '--accent': '#d63384',
                '--accent-hover': '#e75aaa',
                '--text-primary': '#212529',
                '--text-secondary': '#6c757d',
                '--border-color': '#dee2e6',
            },
        };

        const vars = themes[themeName] || themes.dark;
        const root = document.documentElement;
        Object.entries(vars).forEach(([prop, val]) => {
            root.style.setProperty(prop, val);
        });

        // Update terminal themes if any exist
        Object.values(this.terminals).forEach(t => {
            if (t.terminal) {
                t.terminal.options.theme = this._terminalTheme();
            }
        });
    }

    // ============== Notification Sounds ==============

    _playNotificationSound(type) {
        if (!this._soundEnabled) return;
        try {
            if (!this._audioCtx) this._audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            const ctx = this._audioCtx;

            if (type === 'complete') {
                // Pleasant two-tone chime
                [523.25, 659.25].forEach((freq, i) => {
                    const osc = ctx.createOscillator();
                    const gain = ctx.createGain();
                    osc.type = 'sine';
                    osc.frequency.value = freq;
                    gain.gain.setValueAtTime(0.15, ctx.currentTime + i * 0.15);
                    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + i * 0.15 + 0.4);
                    osc.connect(gain);
                    gain.connect(ctx.destination);
                    osc.start(ctx.currentTime + i * 0.15);
                    osc.stop(ctx.currentTime + i * 0.15 + 0.4);
                });
            } else if (type === 'error') {
                // Low buzz
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = 'sawtooth';
                osc.frequency.value = 220;
                gain.gain.setValueAtTime(0.1, ctx.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.5);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start();
                osc.stop(ctx.currentTime + 0.5);
            }
        } catch (e) {
            // Web Audio not available
        }
    }

    // ============== Export ==============

    async exportChat() {
        if (!this.currentSession?.id) {
            this.showToast('No session to export', 'warning');
            return;
        }
        try {
            const response = await fetch(`/api/session/${this.currentSession.id}/export`);
            if (!response.ok) throw new Error('Export failed');
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `chat-${this.currentSession.id.slice(0, 8)}.md`;
            a.click();
            URL.revokeObjectURL(url);
            this.showToast('Chat exported', 'success');
        } catch (e) {
            this.showToast('Export failed: ' + e.message, 'error');
        }
    }

    // ============== Session Search ==============

    async searchSessions(query) {
        const resultsDiv = document.getElementById('chat-search-results');
        if (!resultsDiv) return;

        query = query.trim();
        if (query.length < 2) {
            resultsDiv.classList.add('hidden');
            return;
        }

        try {
            const response = await fetch(`/api/sessions/search?q=${encodeURIComponent(query)}`);
            const data = await response.json();

            if (data.results.length === 0) {
                resultsDiv.innerHTML = '<div class="search-no-results">No results found</div>';
            } else {
                resultsDiv.innerHTML = data.results.map(r => `
                    <div class="search-result-item" data-session-id="${this._escapeHtml(r.session_id)}">
                        <div class="search-result-name">${this._escapeHtml(r.project_name)} <span class="search-result-role">${this._escapeHtml(r.role)}</span></div>
                        <div class="search-result-snippet">${this._escapeHtml(r.snippet)}</div>
                    </div>
                `).join('');

            }
            resultsDiv.classList.remove('hidden');
        } catch (e) {
            console.error('Search failed:', e);
        }
    }

    async loadSessionById(sessionId) {
        try {
            const response = await fetch(`/api/session/${sessionId}`);
            if (response.ok) {
                this.currentSession = await response.json();
                this.renderChatMessages();
                this._switchView('chat');
                this.showToast('Session loaded', 'success');
            }
        } catch (e) {
            this.showToast('Failed to load session', 'error');
        }
    }

    _escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // ============== Git Integration ==============

    async fetchGitStatus(path) {
        const badge = document.getElementById('git-status-badge');
        if (!badge) return;

        try {
            const response = await fetch(`/api/git/status?path=${encodeURIComponent(path)}`);
            const data = await response.json();

            if (!data.is_git) {
                badge.classList.add('hidden');
                return;
            }

            const dirtyIcon = data.dirty ? ' *' : '';
            badge.textContent = `${data.branch}${dirtyIcon}`;
            badge.className = `git-badge ${data.dirty ? 'dirty' : 'clean'}`;
            badge.title = data.dirty
                ? `Branch: ${data.branch} | ${data.modified_count} changed file(s)`
                : `Branch: ${data.branch} | Clean`;
        } catch (e) {
            badge.classList.add('hidden');
        }
    }

    // ============== File Browser ==============

    async loadFiles(path) {
        if (this._editDirty && !confirm('You have unsaved changes. Discard?')) return;
        this._editingFile = null;
        this._editDirty = false;

        const tree = document.getElementById('files-tree');
        const viewer = document.getElementById('files-viewer');
        if (!tree) return;

        if (!path) {
            tree.innerHTML = '<div class="empty-state"><p>Select a project to browse files</p></div>';
            return;
        }

        this._filesCurrentPath = path;

        try {
            const response = await fetch(`/api/files?path=${encodeURIComponent(path)}`);
            const data = await response.json();

            if (data.error) {
                tree.innerHTML = `<div class="empty-state"><p style="color:var(--error)">${this._escapeHtml(data.error)}</p></div>`;
                return;
            }

            // Breadcrumb
            this._renderFilesBreadcrumb(data.path, data.parent);

            // File listing - escape names and paths to prevent XSS from malicious filenames
            tree.innerHTML = data.items.map(item => {
                const icon = item.is_dir ? '&#128193;' : this._fileIcon(item.name);
                const size = item.size !== null ? this._formatSize(item.size) : '';
                const safeName = this._escapeHtml(item.name);
                const safePath = this._escapeHtml(item.path);
                return `
                    <div class="file-item ${item.is_dir ? 'dir' : 'file'}" data-path="${safePath}" data-is-dir="${item.is_dir}">
                        <span class="file-icon">${icon}</span>
                        <span class="file-name">${safeName}</span>
                        <span class="file-size">${size}</span>
                    </div>
                `;
            }).join('');

        } catch (e) {
            tree.innerHTML = `<div class="empty-state"><p style="color:var(--error)">Failed to load files</p></div>`;
        }
    }

    _renderFilesBreadcrumb(path, parent) {
        const bc = document.getElementById('files-breadcrumb');
        if (!bc) return;

        const parts = path.split('/').filter(Boolean);
        let html = '';
        let accumulated = '';

        parts.forEach((part, i) => {
            accumulated += '/' + part;
            const isLast = i === parts.length - 1;
            const safePart = this._escapeHtml(part);
            const safePath = this._escapeHtml(accumulated);
            html += isLast
                ? `<span class="bc-current">${safePart}</span>`
                : `<span class="bc-link" data-path="${safePath}">${safePart}</span><span class="bc-sep">/</span>`;
        });

        bc.innerHTML = html;
        bc.querySelectorAll('.bc-link').forEach(link => {
            link.addEventListener('click', () => this.loadFiles(link.dataset.path));
        });
    }

    async viewFile(path) {
        // Debounce rapid clicks (300ms cooldown)
        const now = Date.now();
        if (now - (this._lastAction.viewFile || 0) < 300) return;
        this._lastAction.viewFile = now;

        // Dirty guard: confirm before leaving unsaved edits
        if (this._editDirty && path !== this._editingFile) {
            if (!confirm('You have unsaved changes. Discard?')) return;
        }
        this._destroyAceEditor();
        this._editingFile = null;
        this._editDirty = false;
        this._viewerMode = 'view';

        const viewer = document.getElementById('files-viewer');
        if (!viewer) return;

        viewer.innerHTML = '<div class="empty-state"><div class="loading"></div><p>Loading...</p></div>';

        try {
            const response = await fetch(`/api/files/read?path=${encodeURIComponent(path)}`);
            const data = await response.json();

            if (data.error) {
                viewer.innerHTML = `<div class="empty-state"><p style="color:var(--error)">${this._escapeHtml(data.error)}</p></div>`;
                return;
            }

            // Determine project path for diff button (backend walks up to find git root)
            const projectPath = this.selectedProject || this._filesCurrentPath || '';
            const relativePath = path.startsWith(projectPath) ? path.slice(projectPath.length + 1) : data.name;

            // Sanitize language class to prevent injection
            const safeLang = data.language ? data.language.replace(/[^a-zA-Z0-9_-]/g, '') : '';
            const langClass = safeLang ? ` class="language-${safeLang}"` : '';
            viewer.innerHTML = `
                <div class="file-viewer-header">
                    <span class="file-viewer-name">${this._escapeHtml(data.name)}</span>
                    <span class="file-viewer-meta">${parseInt(data.lines) || 0} lines | ${this._formatSize(data.size)}</span>
                    <div class="file-viewer-actions">
                        <button class="btn-diff" data-path="${this._escapeHtml(path)}" data-project="${this._escapeHtml(projectPath)}" data-rel="${this._escapeHtml(relativePath)}" title="Show git diff" style="display:none">Diff</button>
                        <button class="btn-edit" data-path="${this._escapeHtml(data.path)}">Edit</button>
                    </div>
                </div>
                <pre class="file-viewer-code"><code${langClass}>${this._escapeHtml(data.content)}</code></pre>
            `;

            // Store raw content for edit mode
            viewer.dataset.filePath = data.path;

            // Edit button handler
            viewer.querySelector('.btn-edit').addEventListener('click', () => {
                this._enterEditMode(data.path, data.content, data.language);
            });

            // Diff button: show only if file is in a git repo (async check)
            const diffBtn = viewer.querySelector('.btn-diff');
            diffBtn.addEventListener('click', () => {
                this._showDiffView(diffBtn.dataset.project, diffBtn.dataset.rel, data.path);
            });
            fetch(`/api/git/status?path=${encodeURIComponent(projectPath)}`)
                .then(r => r.json())
                .then(s => { if (s.is_git) diffBtn.style.display = ''; })
                .catch(() => {});

            // Syntax highlighting
            viewer.querySelectorAll('pre code').forEach(block => {
                try { hljs.highlightElement(block); } catch {}
            });
            this.addCopyButtons(viewer);
        } catch (e) {
            viewer.innerHTML = `<div class="empty-state"><p style="color:var(--error)">Failed to read file</p></div>`;
        }
    }

    _getAceMode(language) {
        const modeMap = {
            'python': 'python', 'javascript': 'javascript', 'json': 'json',
            'html': 'html', 'css': 'css', 'markdown': 'markdown',
            'bash': 'sh', 'shell': 'sh', 'yaml': 'yaml', 'xml': 'xml',
            'sql': 'sql', 'rust': 'rust', 'go': 'golang', 'java': 'java',
            'c': 'c_cpp', 'cpp': 'c_cpp', 'ruby': 'ruby', 'php': 'php',
            'typescript': 'typescript', 'toml': 'toml', 'dockerfile': 'dockerfile',
            'makefile': 'makefile', 'lua': 'lua', 'perl': 'perl'
        };
        return modeMap[language] || 'text';
    }

    _loadAce() {
        if (typeof ace !== 'undefined') return Promise.resolve();
        if (this._aceLoadPromise) return this._aceLoadPromise;
        this._aceLoadPromise = new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = '/static/js/ace/ace.js';
            script.onload = resolve;
            script.onerror = () => { this._aceLoadPromise = null; reject(new Error('Failed to load Ace Editor')); };
            document.head.appendChild(script);
        });
        return this._aceLoadPromise;
    }

    async _enterEditMode(path, content, language) {
        if (this._viewerTransition) return;
        this._viewerTransition = true;
        const viewer = document.getElementById('files-viewer');
        if (!viewer) { this._viewerTransition = false; return; }

        this._destroyAceEditor();
        this._editingFile = path;
        this._editDirty = false;
        this._viewerMode = 'edit';

        const name = path.split('/').pop();
        viewer.innerHTML = `
            <div class="file-viewer-header">
                <span class="file-viewer-name">${this._escapeHtml(name)}</span>
                <span class="file-edit-indicator">Editing</span>
                <div class="file-viewer-actions">
                    <button class="btn-save">Save</button>
                    <button class="btn-cancel">Cancel</button>
                </div>
            </div>
            <div id="ace-editor-container" class="ace-editor-container"></div>
        `;

        // Lazy-load Ace Editor on first use
        try { await this._loadAce(); } catch {}

        // Initialize Ace Editor
        if (typeof ace !== 'undefined') {
            ace.config.set('basePath', '/static/js/ace');
            this._aceEditor = ace.edit('ace-editor-container');
            this._aceEditor.setTheme('ace/theme/one_dark');
            const mode = this._getAceMode(language);
            this._aceEditor.session.setMode(`ace/mode/${mode}`);
            this._aceEditor.setValue(content, -1);
            this._aceEditor.setOptions({
                fontSize: '13px',
                showPrintMargin: false,
                tabSize: 4,
                useSoftTabs: true,
                wrap: false
            });

            // Track dirty state
            this._aceEditor.session.on('change', () => {
                this._editDirty = true;
            });

            // Ctrl+S to save
            this._aceEditor.commands.addCommand({
                name: 'save',
                bindKey: { win: 'Ctrl-S', mac: 'Cmd-S' },
                exec: () => this._saveFile(path)
            });

            // Resize handler for window/container changes
            this._aceResizeHandler = () => this._aceEditor?.resize();
            window.addEventListener('resize', this._aceResizeHandler);

            this._aceEditor.focus();
        } else {
            // Fallback to textarea if Ace isn't loaded
            const container = document.getElementById('ace-editor-container');
            container.outerHTML = `<textarea class="file-editor-textarea" spellcheck="false">${this._escapeHtml(content)}</textarea>`;
            const textarea = viewer.querySelector('.file-editor-textarea');
            textarea.addEventListener('input', () => { this._editDirty = true; });
            textarea.addEventListener('keydown', (e) => {
                if (e.key === 's' && (e.ctrlKey || e.metaKey)) {
                    e.preventDefault();
                    this._saveFile(path);
                }
            });
            textarea.focus();
        }

        viewer.querySelector('.btn-save').addEventListener('click', () => this._saveFile(path));
        viewer.querySelector('.btn-cancel').addEventListener('click', () => this._exitEditMode());

        // beforeunload guard
        this._beforeUnloadHandler = (e) => {
            if (this._editDirty) {
                e.preventDefault();
                e.returnValue = '';
            }
        };
        window.addEventListener('beforeunload', this._beforeUnloadHandler);
        this._viewerTransition = false;
    }

    _destroyAceEditor() {
        if (this._aceResizeHandler) {
            window.removeEventListener('resize', this._aceResizeHandler);
            this._aceResizeHandler = null;
        }
        if (this._aceEditor) {
            this._aceEditor.destroy();
            this._aceEditor = null;
        }
    }

    _exitEditMode() {
        if (this._editDirty) {
            if (!confirm('You have unsaved changes. Discard?')) return;
        }
        if (this._beforeUnloadHandler) {
            window.removeEventListener('beforeunload', this._beforeUnloadHandler);
            this._beforeUnloadHandler = null;
        }
        this._destroyAceEditor();
        const path = this._editingFile;
        this._editingFile = null;
        this._editDirty = false;
        this._viewerMode = 'view';
        if (path) this.viewFile(path);
    }

    async _saveFile(path) {
        const viewer = document.getElementById('files-viewer');
        let content;

        if (this._aceEditor) {
            content = this._aceEditor.getValue();
        } else {
            const textarea = viewer?.querySelector('.file-editor-textarea');
            if (!textarea) return;
            content = textarea.value;
        }

        const saveBtn = viewer?.querySelector('.btn-save');
        if (saveBtn) {
            saveBtn.disabled = true;
            saveBtn.textContent = 'Saving...';
        }

        try {
            const response = await fetch('/api/files/write', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path, content })
            });
            const data = await response.json();

            if (data.error) {
                alert('Save failed: ' + data.error);
                if (saveBtn) {
                    saveBtn.disabled = false;
                    saveBtn.textContent = 'Save';
                }
                return;
            }

            this._editDirty = false;
            this._exitEditMode();
        } catch (e) {
            alert('Save failed: network error');
            if (saveBtn) {
                saveBtn.disabled = false;
                saveBtn.textContent = 'Save';
            }
        }
    }

    async _showDiffView(projectPath, relativePath, fullPath) {
        if (this._viewerTransition) return;
        this._viewerTransition = true;
        const viewer = document.getElementById('files-viewer');
        if (!viewer) { this._viewerTransition = false; return; }

        this._destroyAceEditor();
        this._viewerMode = 'diff';
        const name = fullPath.split('/').pop();

        viewer.innerHTML = '<div class="empty-state"><div class="loading"></div><p>Loading diff...</p></div>';

        try {
            const response = await fetch(`/api/git/diff?path=${encodeURIComponent(projectPath)}&file=${encodeURIComponent(relativePath)}`);
            if (this._viewerMode !== 'diff') { this._viewerTransition = false; return; } // mode changed during fetch
            const data = await response.json();

            if (data.error) {
                viewer.innerHTML = `<div class="empty-state"><p style="color:var(--error)">${this._escapeHtml(data.error)}</p></div>`;
                this._viewerTransition = false;
                return;
            }

            if (!data.diffs || data.diffs.length === 0) {
                viewer.innerHTML = `
                    <div class="file-viewer-header">
                        <span class="file-viewer-name">${this._escapeHtml(name)}</span>
                        <span class="file-viewer-meta">Diff</span>
                        <div class="file-viewer-actions">
                            <button class="btn-cancel">Back</button>
                        </div>
                    </div>
                    <div class="diff-empty-state">No changes detected for this file</div>
                `;
                viewer.querySelector('.btn-cancel').addEventListener('click', () => this.viewFile(fullPath));
                this._viewerTransition = false;
                return;
            }

            const stats = data.stats || {};
            let html = `
                <div class="file-viewer-header">
                    <span class="file-viewer-name">${this._escapeHtml(name)}</span>
                    <span class="file-viewer-meta">Diff</span>
                    <div class="file-viewer-actions">
                        <button class="btn-edit" data-path="${this._escapeHtml(fullPath)}">Edit</button>
                        <button class="btn-cancel">Back</button>
                    </div>
                </div>
                <div class="diff-summary">
                    <span class="badge badge-files">${stats.files_changed || 0} file${(stats.files_changed || 0) !== 1 ? 's' : ''}</span>
                    <span class="badge badge-add">+${stats.insertions || 0}</span>
                    <span class="badge badge-del">-${stats.deletions || 0}</span>
                </div>
                <div class="diff-view">
            `;

            let oldLineNum = 0;
            let newLineNum = 0;

            for (const diff of data.diffs) {
                html += `<div class="diff-file-header">${this._escapeHtml(diff.file)}</div>`;

                if (diff.binary) {
                    html += '<div class="diff-binary-notice">Binary file changed</div>';
                    continue;
                }

                for (const hunk of diff.hunks) {
                    // Parse hunk header for line numbers: @@ -old,count +new,count @@
                    const match = hunk.header.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
                    if (match) {
                        oldLineNum = parseInt(match[1]);
                        newLineNum = parseInt(match[2]);
                    }
                    html += `<div class="diff-hunk-header">${this._escapeHtml(hunk.header)}</div>`;

                    for (const line of hunk.lines) {
                        const safeContent = this._escapeHtml(line.content);
                        if (line.type === 'add') {
                            html += `<div class="diff-line add"><span class="diff-line-num"></span><span class="diff-line-num">${newLineNum}</span><span class="diff-line-content">${safeContent}</span></div>`;
                            newLineNum++;
                        } else if (line.type === 'remove') {
                            html += `<div class="diff-line remove"><span class="diff-line-num">${oldLineNum}</span><span class="diff-line-num"></span><span class="diff-line-content">${safeContent}</span></div>`;
                            oldLineNum++;
                        } else {
                            html += `<div class="diff-line context"><span class="diff-line-num">${oldLineNum}</span><span class="diff-line-num">${newLineNum}</span><span class="diff-line-content">${safeContent}</span></div>`;
                            oldLineNum++;
                            newLineNum++;
                        }
                    }
                }
            }

            html += '</div>';
            viewer.innerHTML = html;

            // Wire up buttons
            viewer.querySelector('.btn-cancel').addEventListener('click', () => this.viewFile(fullPath));
            const editBtn = viewer.querySelector('.btn-edit');
            if (editBtn) {
                editBtn.addEventListener('click', async () => {
                    const resp = await fetch(`/api/files/read?path=${encodeURIComponent(fullPath)}`);
                    const fileData = await resp.json();
                    if (!fileData.error) this._enterEditMode(fullPath, fileData.content, fileData.language);
                });
            }

            this._viewerTransition = false;
        } catch (e) {
            viewer.innerHTML = `<div class="empty-state"><p style="color:var(--error)">Failed to load diff</p></div>`;
            this._viewerTransition = false;
        }
    }

    _fileIcon(name) {
        const ext = name.split('.').pop().toLowerCase();
        const icons = {
            js: '&#128312;', ts: '&#128309;', py: '&#128013;', rs: '&#9881;',
            json: '&#123;&#125;', md: '&#128196;', html: '&#127760;', css: '&#127912;',
            sh: '&#9002;', yml: '&#128220;', yaml: '&#128220;', toml: '&#128220;',
            txt: '&#128196;', log: '&#128196;', svg: '&#128444;', png: '&#128444;',
            jpg: '&#128444;', gif: '&#128444;',
        };
        return icons[ext] || '&#128196;';
    }

    _formatSize(bytes) {
        if (bytes === null || bytes === undefined) return '';
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
        return (bytes / 1048576).toFixed(1) + ' MB';
    }

    // ============== Multi-User ==============

    async loadCurrentUser() {
        try {
            const response = await fetch('/api/auth/whoami');
            if (response.ok) {
                this._currentUser = await response.json();
                // Show username in sidebar
                const header = document.querySelector('.sidebar-header h1');
                if (header && this._currentUser.username && this._currentUser.username !== 'anonymous') {
                    // Don't overwrite - append username
                }
                // Hide settings for non-admin
                if (this._currentUser.role !== 'admin') {
                    const settingsBtn = document.getElementById('btn-settings');
                    if (settingsBtn) settingsBtn.style.display = 'none';
                }
            }
        } catch (e) {
            // Not critical
        }
    }

    async renderUsersSettings() {
        const list = document.getElementById('users-settings-list');
        if (!list) return;

        try {
            const response = await fetch('/api/users');
            if (!response.ok) {
                list.innerHTML = '<div style="color:var(--text-secondary); font-size:0.85rem;">Admin access required to manage users</div>';
                return;
            }
            const data = await response.json();
            const users = data.users || [];

            if (users.length === 0) {
                list.innerHTML = '<div style="color:var(--text-secondary); font-size:0.85rem;">No multi-user accounts configured</div>';
                return;
            }

            list.innerHTML = users.map(u => `
                <div class="settings-item">
                    <div class="settings-item-info">
                        <div class="settings-item-name">${this._escapeHtml(u.username)} <span class="badge ${u.role === 'admin' ? 'git' : 'mount'}">${this._escapeHtml(u.role)}</span></div>
                    </div>
                    <div class="settings-item-actions">
                        ${u.username !== this._currentUser?.username ? `<button class="btn-sm danger" data-delete-user="${this._escapeHtml(u.username)}">Remove</button>` : '<span style="font-size:0.75rem;color:var(--text-secondary)">(you)</span>'}
                    </div>
                </div>
            `).join('');

            // Attach event handlers for delete buttons (avoids inline onclick with unescaped data)
            list.querySelectorAll('[data-delete-user]').forEach(btn => {
                btn.addEventListener('click', () => {
                    this.deleteUser(btn.dataset.deleteUser);
                });
            });
        } catch (e) {
            list.innerHTML = '<div style="color:var(--text-secondary); font-size:0.85rem;">Failed to load users</div>';
        }
    }

    async addUser() {
        const username = document.getElementById('new-user-username').value.trim();
        const password = document.getElementById('new-user-password').value;
        const role = document.getElementById('new-user-role').value;

        if (!username || !password) {
            this.showToast('Username and password required', 'warning');
            return;
        }

        try {
            const response = await fetch('/api/users', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password, role })
            });
            const data = await response.json();
            if (data.success) {
                this.showToast(`User "${username}" created`, 'success');
                document.getElementById('add-user-form').style.display = 'none';
                document.getElementById('new-user-username').value = '';
                document.getElementById('new-user-password').value = '';
                this.renderUsersSettings();
            } else {
                this.showToast(data.error || 'Failed', 'error');
            }
        } catch (e) {
            this.showToast('Failed to create user', 'error');
        }
    }

    async deleteUser(username) {
        const ok = await this.confirm('Delete User', `Remove user "${username}"? This cannot be undone.`);
        if (!ok) return;

        try {
            const response = await fetch(`/api/users/${username}`, { method: 'DELETE' });
            const data = await response.json();
            if (data.success) {
                this.showToast(`User "${username}" deleted`, 'success');
                this.renderUsersSettings();
            } else {
                this.showToast(data.error || 'Failed', 'error');
            }
        } catch (e) {
            this.showToast('Failed to delete user', 'error');
        }
    }

    // ============== Project Instructions Wizard ==============

    async openWizard(projectPath) {
        this._wizardTargetPath = projectPath;
        this._wizardStep = 1;

        // Show modal
        document.getElementById('wizard-overlay').classList.remove('hidden');

        // Reset form
        document.querySelectorAll('.wizard-panel').forEach(p => p.classList.remove('active'));
        document.querySelector('.wizard-panel[data-wizard-step="1"]').classList.add('active');

        // Call detect API
        try {
            const res = await fetch(`/api/project/detect?path=${encodeURIComponent(projectPath)}`);
            if (!res.ok) throw new Error('Detection failed');
            this._wizardDetectedData = await res.json();

            // Check if CLAUDE.md already exists
            if (this._wizardDetectedData.has_claude_md) {
                const overwrite = await this.confirm(
                    'CLAUDE.md Exists',
                    'This project already has a CLAUDE.md file. Do you want to overwrite it?',
                    'Overwrite', 'warning'
                );
                if (!overwrite) {
                    this.closeWizard();
                    return;
                }
            }

            this._prefillWizard(this._wizardDetectedData);
        } catch (e) {
            console.error('Wizard detect failed:', e);
            this._wizardDetectedData = {};
        }

        this._renderWizardStep();
    }

    _prefillWizard(data) {
        document.getElementById('wiz-name').value = data.name || '';
        document.getElementById('wiz-description').value = data.description || '';

        if (data.language) {
            const langSelect = document.getElementById('wiz-language');
            for (const opt of langSelect.options) {
                if (opt.value === data.language) {
                    langSelect.value = data.language;
                    break;
                }
            }
        }

        document.getElementById('wiz-framework').value = (data.framework_hints || []).join(', ');
        document.getElementById('wiz-dirs').value = (data.top_dirs || []).map(d => d + '/').join('\n');
        document.getElementById('wiz-files').value = (data.key_files || []).join('\n');
        document.getElementById('wiz-build-cmd').value = data.build_command || '';
        document.getElementById('wiz-test-cmd').value = data.test_command || '';
        document.getElementById('wiz-dev-cmd').value = data.dev_command || '';
        document.getElementById('wiz-lint-cmd').value = data.lint_command || '';

        // Set naming convention
        if (data.naming_convention) {
            const namingSelect = document.getElementById('wiz-naming');
            for (const opt of namingSelect.options) {
                if (opt.value === data.naming_convention) {
                    namingSelect.value = data.naming_convention;
                    break;
                }
            }
        }

        // Default indent based on language
        const indentSelect = document.getElementById('wiz-indent');
        if (data.language === 'Python') {
            indentSelect.value = '4 spaces';
        } else if (data.language === 'Go') {
            indentSelect.value = 'tabs';
        } else {
            indentSelect.value = '2 spaces';
        }
    }

    _renderWizardStep() {
        const step = this._wizardStep;

        // Update panels
        document.querySelectorAll('.wizard-panel').forEach(p => {
            p.classList.toggle('active', parseInt(p.dataset.wizardStep) === step);
        });

        // Update step indicators
        document.querySelectorAll('.wizard-step').forEach(s => {
            const sNum = parseInt(s.dataset.step);
            s.classList.toggle('active', sNum === step);
            s.classList.toggle('completed', sNum < step);
        });

        // Navigation buttons
        document.getElementById('wiz-prev').style.visibility = step > 1 ? 'visible' : 'hidden';
        document.getElementById('wiz-next').style.display = step < this._wizardMaxSteps ? '' : 'none';
        document.getElementById('wiz-create').style.display = step === this._wizardMaxSteps ? '' : 'none';

        // Generate preview on step 5
        if (step === this._wizardMaxSteps) {
            this._generatePreview();
        }
    }

    _wizardNext() {
        if (this._wizardStep < this._wizardMaxSteps) {
            this._wizardStep++;
            this._renderWizardStep();
        }
    }

    _wizardPrev() {
        if (this._wizardStep > 1) {
            this._wizardStep--;
            this._renderWizardStep();
        }
    }

    _generateClaudeMd() {
        const name = document.getElementById('wiz-name').value.trim();
        const desc = document.getElementById('wiz-description').value.trim();
        const lang = document.getElementById('wiz-language').value;
        const framework = document.getElementById('wiz-framework').value.trim();
        const dirs = document.getElementById('wiz-dirs').value.trim();
        const files = document.getElementById('wiz-files').value.trim();
        const archNotes = document.getElementById('wiz-arch-notes').value.trim();
        const indent = document.getElementById('wiz-indent').value;
        const lineLength = document.getElementById('wiz-line-length').value;
        const naming = document.getElementById('wiz-naming').value;
        const styleRules = document.getElementById('wiz-style-rules').value.trim();
        const buildCmd = document.getElementById('wiz-build-cmd').value.trim();
        const testCmd = document.getElementById('wiz-test-cmd').value.trim();
        const devCmd = document.getElementById('wiz-dev-cmd').value.trim();
        const lintCmd = document.getElementById('wiz-lint-cmd').value.trim();
        const setupSteps = document.getElementById('wiz-setup-steps').value.trim();
        const gitNotes = document.getElementById('wiz-git-notes').value.trim();

        let md = `# ${name || 'Project'}\n\n`;

        // Overview
        if (desc) {
            md += `${desc}\n\n`;
        }
        if (lang || framework) {
            md += `**Language:** ${lang || 'Not specified'}`;
            if (framework) md += ` | **Framework:** ${framework}`;
            md += '\n\n';
        }

        // Project Structure
        if (dirs) {
            md += `## Project Structure\n\n`;
            md += '```\n';
            dirs.split('\n').filter(Boolean).forEach(d => {
                md += `${d.trim()}\n`;
            });
            md += '```\n\n';
        }

        // Important Files
        if (files) {
            md += `## Important Files\n\n`;
            files.split('\n').filter(Boolean).forEach(f => {
                md += `- \`${f.trim()}\`\n`;
            });
            md += '\n';
        }

        // Architecture
        if (archNotes) {
            md += `## Architecture\n\n${archNotes}\n\n`;
        }

        // Code Style
        md += `## Code Style\n\n`;
        md += `- **Indentation:** ${indent}\n`;
        md += `- **Max line length:** ${lineLength}\n`;
        md += `- **Naming convention:** ${naming}\n`;
        if (styleRules) {
            styleRules.split('\n').filter(Boolean).forEach(rule => {
                md += `- ${rule.trim()}\n`;
            });
        }
        md += '\n';

        // Key Commands
        if (buildCmd || testCmd || devCmd || lintCmd) {
            md += `## Key Commands\n\n`;
            if (buildCmd) md += `- **Build:** \`${buildCmd}\`\n`;
            if (testCmd) md += `- **Test:** \`${testCmd}\`\n`;
            if (devCmd) md += `- **Dev:** \`${devCmd}\`\n`;
            if (lintCmd) md += `- **Lint:** \`${lintCmd}\`\n`;
            md += '\n';
        }

        // Development Process
        if (setupSteps || gitNotes) {
            md += `## Development Process\n\n`;
            if (setupSteps) {
                md += `### Setup\n\n`;
                setupSteps.split('\n').filter(Boolean).forEach(s => {
                    md += `${s.trim()}\n`;
                });
                md += '\n';
            }
            if (gitNotes) {
                md += `### Git Workflow\n\n${gitNotes}\n\n`;
            }
        }

        return md;
    }

    _generatePreview() {
        const md = this._generateClaudeMd();
        const previewEl = document.getElementById('wiz-preview');
        const sourceEl = document.getElementById('wiz-source');

        previewEl.innerHTML = this.renderMarkdown(md);
        sourceEl.value = md;

        // Reset to preview view
        this._wizardToggleView('preview');
    }

    _wizardToggleView(view) {
        const previewEl = document.getElementById('wiz-preview');
        const sourceEl = document.getElementById('wiz-source');
        const btnPreview = document.getElementById('wiz-view-preview');
        const btnSource = document.getElementById('wiz-view-source');

        if (view === 'source') {
            previewEl.classList.add('hidden');
            sourceEl.classList.remove('hidden');
            btnPreview.classList.remove('active');
            btnSource.classList.add('active');
        } else {
            // Update preview from source if it was edited
            const sourceContent = sourceEl.value;
            previewEl.innerHTML = this.renderMarkdown(sourceContent);
            previewEl.classList.remove('hidden');
            sourceEl.classList.add('hidden');
            btnPreview.classList.add('active');
            btnSource.classList.remove('active');
        }
    }

    async _wizardCreate() {
        // Get content - prefer source textarea if it was edited on step 5
        const sourceEl = document.getElementById('wiz-source');
        const content = sourceEl.value.trim() || this._generateClaudeMd();

        if (!content) {
            this.showToast('No content to write', 'warning');
            return;
        }

        const body = {
            path: this._wizardTargetPath,
            claude_md_content: content,
            overwrite: this._wizardDetectedData?.has_claude_md || false,
        };

        // Settings
        if (document.getElementById('wiz-create-settings').checked) {
            const level = document.getElementById('wiz-permissions-level').value;
            let permissions = {};
            if (level === 'permissive') {
                permissions = {
                    permissions: {
                        allow: ['Edit', 'Write', 'Bash'],
                        deny: []
                    }
                };
            } else if (level === 'strict') {
                permissions = {
                    permissions: {
                        allow: [],
                        deny: ['Edit', 'Write', 'Bash', 'NotebookEdit']
                    }
                };
            } else {
                permissions = { permissions: {} };
            }
            body.create_settings = true;
            body.settings = permissions;
        }

        try {
            const res = await fetch('/api/project/init', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (res.ok && data.success) {
                this.showToast('CLAUDE.md created successfully!', 'success');
                this.closeWizard();
                // Refresh projects to show updated indicators
                this.loadProjects(this.currentRoot);
            } else {
                this.showToast(data.error || 'Failed to create CLAUDE.md', 'error');
            }
        } catch (e) {
            this.showToast('Failed to create CLAUDE.md: ' + e.message, 'error');
        }
    }

    closeWizard() {
        document.getElementById('wizard-overlay').classList.add('hidden');
        this._wizardStep = 1;
        this._wizardDetectedData = null;
        this._wizardTargetPath = null;
    }

    // ============== Remote Server Setup Wizard ==============

    async openRemoteWizard() {
        this._rwStep = 1;
        this._rwMethod = null;
        this._rwImportedHost = null;
        this._rwKeyStatus = null;
        this._rwVerifyResults = {};
        this._rwBusy = false;

        document.getElementById('remote-wizard-overlay').classList.remove('hidden');
        document.getElementById('rw-hostname').value = '';
        document.getElementById('rw-username').value = '';
        document.getElementById('rw-port').value = '22';
        document.getElementById('rw-password').value = '';
        document.getElementById('rw-name').value = '';
        document.getElementById('rw-default-path').value = '~';

        // Fetch SSH config and key info in parallel
        const [configRes, setupRes] = await Promise.all([
            fetch('/api/remote/ssh-config').then(r => r.json()).catch(() => ({ hosts: [] })),
            fetch('/api/remote/ssh-setup').then(r => r.json()).catch(() => ({ has_key: false })),
        ]);

        this._rwSshConfig = configRes.hosts || [];
        this._rwSshSetup = setupRes;

        this._renderRwStep();
        this._renderRwMethodCards();
    }

    closeRemoteWizard() {
        document.getElementById('remote-wizard-overlay').classList.add('hidden');
        this._rwStep = 1;
        this._rwMethod = null;
        this._rwBusy = false;
    }

    _renderRwMethodCards() {
        const container = document.getElementById('rw-method-cards');
        const sshHosts = this._rwSshConfig || [];
        const importable = sshHosts.filter(h => !h.already_imported);

        container.innerHTML = `
            <div class="rw-method-card ${importable.length === 0 ? 'disabled' : ''}" data-method="import">
                <div class="rw-method-icon">&#128196;</div>
                <div>
                    <div class="rw-method-title">Import from SSH Config</div>
                    <div class="rw-method-desc">${importable.length > 0 ? importable.length + ' host' + (importable.length !== 1 ? 's' : '') + ' found in ~/.ssh/config' : 'No importable hosts found in ~/.ssh/config'}</div>
                </div>
            </div>
            <div class="rw-method-card" data-method="new">
                <div class="rw-method-icon">&#127760;</div>
                <div>
                    <div class="rw-method-title">Add New Server</div>
                    <div class="rw-method-desc">Enter hostname + password, auto-setup SSH key auth</div>
                </div>
            </div>
            <div class="rw-method-card" data-method="mount">
                <div class="rw-method-icon">&#128193;</div>
                <div>
                    <div class="rw-method-title">Mount Local Path</div>
                    <div class="rw-method-desc">Use an already-mounted network path (NFS, SSHFS, etc.)</div>
                </div>
            </div>
            ${importable.length > 0 ? `
                <div id="rw-ssh-host-list" class="rw-ssh-host-list" style="display:none">
                    ${sshHosts.map((h, i) => `
                        <div class="rw-ssh-host-item ${h.already_imported ? 'imported' : ''}" data-index="${i}">
                            <div class="rw-ssh-host-name">${this._escapeHtml(h.alias)}</div>
                            <div class="rw-ssh-host-detail">${this._escapeHtml(h.username ? h.username + '@' : '')}${this._escapeHtml(h.hostname)}:${h.port}${h.already_imported ? ' (imported)' : ''}</div>
                        </div>
                    `).join('')}
                </div>
            ` : ''}
        `;

        // Method card click handlers
        container.querySelectorAll('.rw-method-card').forEach(card => {
            card.addEventListener('click', () => {
                if (card.classList.contains('disabled')) return;
                const method = card.dataset.method;
                this._rwMethod = method;
                container.querySelectorAll('.rw-method-card').forEach(c => c.classList.remove('selected'));
                card.classList.add('selected');

                const hostList = document.getElementById('rw-ssh-host-list');
                if (hostList) hostList.style.display = method === 'import' ? 'block' : 'none';
                this._rwImportedHost = null;
                if (hostList) hostList.querySelectorAll('.rw-ssh-host-item').forEach(i => i.classList.remove('selected'));
            });
        });

        // SSH host item click handlers
        const hostList = document.getElementById('rw-ssh-host-list');
        if (hostList) {
            hostList.querySelectorAll('.rw-ssh-host-item:not(.imported)').forEach(item => {
                item.addEventListener('click', () => {
                    this._rwImportedHost = parseInt(item.dataset.index);
                    hostList.querySelectorAll('.rw-ssh-host-item').forEach(i => i.classList.remove('selected'));
                    item.classList.add('selected');
                });
            });
        }
    }

    _renderRwStep() {
        const step = this._rwStep;

        // Update panels
        document.querySelectorAll('[data-rw-step]').forEach(p => {
            p.classList.toggle('active', parseInt(p.dataset.rwStep) === step);
        });

        // Update step indicators (scope to remote wizard only)
        document.querySelectorAll('#remote-wizard-steps .wizard-step').forEach(s => {
            const sNum = parseInt(s.dataset.step);
            s.classList.toggle('active', sNum === step);
            s.classList.toggle('completed', sNum < step);
        });

        // Navigation buttons
        document.getElementById('rw-prev').style.visibility = step > 1 ? 'visible' : 'hidden';
        document.getElementById('rw-next').style.display = step < 5 ? '' : 'none';
        document.getElementById('rw-save').style.display = step === 5 ? '' : 'none';

        // Step-specific rendering
        if (step === 5) this._renderRwSaveStep();
    }

    async _rwNext() {
        if (this._rwBusy) return;

        if (this._rwStep === 1) {
            if (!this._rwMethod) { this.showToast('Please choose a method', 'warning'); return; }
            if (this._rwMethod === 'import' && this._rwImportedHost === null) {
                this.showToast('Please select a host to import', 'warning'); return;
            }
            if (this._rwMethod === 'mount') {
                this._rwStep = 5;
                this._renderRwStep();
                return;
            }
            // Pre-fill from SSH config import
            if (this._rwMethod === 'import') {
                const h = this._rwSshConfig[this._rwImportedHost];
                document.getElementById('rw-hostname').value = h.hostname || '';
                document.getElementById('rw-port').value = h.port || 22;
                document.getElementById('rw-username').value = h.username || '';
            }
            this._rwStep = 2;
            this._renderRwStep();
            return;
        }

        if (this._rwStep === 2) {
            const hostname = document.getElementById('rw-hostname').value.trim();
            const username = document.getElementById('rw-username').value.trim();
            if (!hostname) { this.showToast('Hostname is required', 'warning'); return; }
            if (!username) { this.showToast('Username is required', 'warning'); return; }

            // Move to step 3 and run autonomous setup
            this._rwStep = 3;
            this._renderRwStep();
            await this._rwRunAutoSetup();
            return;
        }

        if (this._rwStep === 3) {
            // Step 4: Verification
            this._rwStep = 4;
            this._renderRwStep();
            await this._runRwVerification();
            return;
        }

        if (this._rwStep === 4) {
            this._rwStep = 5;
            this._renderRwStep();
            return;
        }
    }

    _rwPrev() {
        if (this._rwBusy) return;
        if (this._rwStep === 5 && this._rwMethod === 'mount') {
            this._rwStep = 1;
        } else if (this._rwStep > 1) {
            this._rwStep--;
        }
        this._renderRwStep();
        if (this._rwStep === 1) this._renderRwMethodCards();
    }

    _rwSetProgress(containerId, items) {
        const el = document.getElementById(containerId);
        el.innerHTML = items.map(item => `
            <div class="rw-progress-item ${item.status}">
                <span class="rw-progress-icon">${
                    item.status === 'active' ? '<span class="rw-spinner"></span>' :
                    item.status === 'success' ? '&#10003;' :
                    item.status === 'error' ? '&#10007;' :
                    item.status === 'warning' ? '&#9888;' :
                    '&#8226;'
                }</span>
                <span>${item.text}</span>
            </div>
        `).join('');
    }

    async _rwRunAutoSetup() {
        this._rwBusy = true;
        const nextBtn = document.getElementById('rw-next');
        nextBtn.disabled = true;
        document.getElementById('rw-manual-section').style.display = 'none';

        const hostname = document.getElementById('rw-hostname').value.trim();
        const username = document.getElementById('rw-username').value.trim();
        const port = parseInt(document.getElementById('rw-port').value) || 22;
        const password = document.getElementById('rw-password').value;

        const steps = [
            { id: 'key', text: 'Checking for SSH key...', status: 'active' },
            { id: 'test', text: 'Testing key authentication...', status: 'pending' },
            { id: 'push', text: 'Pushing key to remote...', status: 'pending' },
            { id: 'verify', text: 'Verifying key-based access...', status: 'pending' },
        ];

        const update = (id, status, text) => {
            const s = steps.find(s => s.id === id);
            if (s) { s.status = status; if (text) s.text = text; }
            this._rwSetProgress('rw-auth-progress', steps);
        };

        // Step 1: Check/generate SSH key
        try {
            let setupRes = this._rwSshSetup;
            if (!setupRes?.has_key) {
                update('key', 'active', 'Generating SSH key (ed25519)...');
                const res = await fetch('/api/remote/ssh-setup', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({}),
                });
                const data = await res.json();
                if (data.success) {
                    this._rwSshSetup = { has_key: true, key_path: data.key_path, public_key: data.public_key };
                    update('key', 'success', data.already_existed ? 'SSH key found: ' + data.key_path.split('/').pop() : 'SSH key generated: ' + data.key_path.split('/').pop());
                } else {
                    update('key', 'error', 'Failed to generate SSH key: ' + (data.error || 'unknown error'));
                    this._rwBusy = false; nextBtn.disabled = false; return;
                }
            } else {
                update('key', 'success', 'SSH key found: ' + (setupRes.key_path || '').split('/').pop());
            }
        } catch (e) {
            update('key', 'error', 'SSH key check failed: ' + e.message);
            this._rwBusy = false; nextBtn.disabled = false; return;
        }

        // Step 2: Test if key already authorized
        update('test', 'active', 'Testing key authentication...');
        try {
            const testRes = await fetch('/api/remote/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    mode: 'ssh', hostname, port, username,
                    ssh_key_path: this._rwSshSetup.key_path || '',
                }),
            });
            const testData = await testRes.json();

            if (testData.success) {
                update('test', 'success', 'Key already authorized on remote');
                update('push', 'success', 'Key push not needed');
                update('verify', 'success', 'Connection verified');
                this._rwKeyStatus = 'existing_works';
                this._rwVerifyResults = testData;
                this._rwBusy = false; nextBtn.disabled = false; return;
            }
            update('test', 'warning', 'Key not yet authorized on remote');
        } catch (e) {
            update('test', 'warning', 'Connection test failed: ' + e.message);
        }

        // Step 3: Push key using password
        if (!password) {
            update('push', 'warning', 'No password provided - manual key setup needed');
            update('verify', 'pending', 'Waiting for manual key setup...');
            const manualCmd = `ssh-copy-id -p ${port} ${username}@${hostname}`;
            document.getElementById('rw-manual-cmd').textContent = manualCmd;
            document.getElementById('rw-manual-section').style.display = 'block';
            this._rwKeyStatus = 'manual_needed';
            this._rwBusy = false; nextBtn.disabled = false; return;
        }

        update('push', 'active', 'Pushing SSH key to remote...');
        try {
            const pushRes = await fetch('/api/remote/push-key', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    hostname, port, username, password,
                }),
            });
            const pushData = await pushRes.json();

            if (pushData.success) {
                update('push', 'success', 'SSH key installed on remote');
            } else if (pushData.error && pushData.error.includes('sshpass')) {
                update('push', 'warning', 'sshpass not installed - manual key setup needed');
                const manualCmd = `ssh-copy-id -p ${port} ${username}@${hostname}`;
                document.getElementById('rw-manual-cmd').textContent = manualCmd;
                document.getElementById('rw-manual-section').style.display = 'block';
                this._rwKeyStatus = 'manual_needed';
                this._rwBusy = false; nextBtn.disabled = false; return;
            } else {
                update('push', 'error', 'Key push failed: ' + (pushData.error || 'Unknown error'));
                this._rwBusy = false; nextBtn.disabled = false; return;
            }
        } catch (e) {
            update('push', 'error', 'Key push failed: ' + e.message);
            this._rwBusy = false; nextBtn.disabled = false; return;
        }

        // Step 4: Verify key-based auth works
        update('verify', 'active', 'Verifying key-based authentication...');
        await this._rwVerifyKeyAuth();
    }

    async _rwVerifyKeyAuth() {
        const hostname = document.getElementById('rw-hostname').value.trim();
        const username = document.getElementById('rw-username').value.trim();
        const port = parseInt(document.getElementById('rw-port').value) || 22;
        const nextBtn = document.getElementById('rw-next');

        try {
            const res = await fetch('/api/remote/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    mode: 'ssh', hostname, port, username,
                    ssh_key_path: this._rwSshSetup?.key_path || '',
                }),
            });
            const data = await res.json();

            const steps = Array.from(document.querySelectorAll('#rw-auth-progress .rw-progress-item'));
            const verifyItem = steps[steps.length - 1];

            if (data.success) {
                if (verifyItem) {
                    verifyItem.className = 'rw-progress-item success';
                    verifyItem.querySelector('.rw-progress-icon').innerHTML = '&#10003;';
                    verifyItem.querySelector('span:last-child').textContent = 'Key-based authentication verified';
                }
                document.getElementById('rw-manual-section').style.display = 'none';
                this._rwKeyStatus = 'setup_complete';
                this._rwVerifyResults = data;
            } else {
                if (verifyItem) {
                    verifyItem.className = 'rw-progress-item error';
                    verifyItem.querySelector('.rw-progress-icon').innerHTML = '&#10007;';
                    verifyItem.querySelector('span:last-child').textContent = 'Verification failed: ' + (data.message || 'Could not connect');
                }
                this._rwKeyStatus = 'verify_failed';
            }
        } catch (e) {
            this._rwKeyStatus = 'verify_failed';
        }

        this._rwBusy = false;
        nextBtn.disabled = false;
    }

    async _runRwVerification() {
        const resultsEl = document.getElementById('rw-verify-results');

        // If we already have results from the auto-setup
        if (this._rwVerifyResults?.success) {
            const r = this._rwVerifyResults;
            this._rwSetProgress('rw-verify-results', [
                { status: 'success', text: 'SSH connection successful' },
                { status: r.claude_available ? 'success' : 'warning',
                  text: r.claude_available ? 'Claude CLI found' + (r.claude_path ? ': ' + r.claude_path : '') : 'Claude CLI not found on remote (install it before using)' },
            ]);
            return;
        }

        // Run fresh test
        this._rwSetProgress('rw-verify-results', [
            { status: 'active', text: 'Testing connection...' },
        ]);

        const hostname = document.getElementById('rw-hostname').value.trim();
        const username = document.getElementById('rw-username').value.trim();
        const port = parseInt(document.getElementById('rw-port').value) || 22;

        try {
            const res = await fetch('/api/remote/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    mode: 'ssh', hostname, port, username,
                    ssh_key_path: this._rwSshSetup?.key_path || '',
                }),
            });
            const data = await res.json();
            this._rwVerifyResults = data;

            this._rwSetProgress('rw-verify-results', [
                { status: data.success ? 'success' : 'error',
                  text: data.success ? 'SSH connection successful' : 'Connection failed: ' + (data.message || 'Unknown error') },
                ...(data.success ? [{
                    status: data.claude_available ? 'success' : 'warning',
                    text: data.claude_available ? 'Claude CLI found' + (data.claude_path ? ': ' + data.claude_path : '') : 'Claude CLI not found on remote (install it before using)',
                }] : []),
            ]);
        } catch (e) {
            this._rwSetProgress('rw-verify-results', [
                { status: 'error', text: 'Connection test failed: ' + e.message },
            ]);
        }
    }

    _renderRwSaveStep() {
        const isMount = this._rwMethod === 'mount';
        document.getElementById('rw-mount-section').style.display = isMount ? 'block' : 'none';
        document.getElementById('rw-default-path-field').style.display = isMount ? 'none' : '';

        // Auto-suggest name from hostname
        const nameEl = document.getElementById('rw-name');
        if (!nameEl.value) {
            if (isMount) {
                const mp = document.getElementById('rw-mount-path')?.value || '';
                nameEl.value = mp.split('/').filter(Boolean).pop() || 'Mount';
            } else {
                const hostname = document.getElementById('rw-hostname').value.trim();
                nameEl.value = hostname.replace(/\.\w+$/, '').replace(/[^a-zA-Z0-9.-]/g, '') || hostname;
            }
        }

        // Show summary for SSH
        const summaryEl = document.getElementById('rw-summary');
        if (!isMount) {
            const hostname = document.getElementById('rw-hostname').value.trim();
            const username = document.getElementById('rw-username').value.trim();
            const port = document.getElementById('rw-port').value;
            const keyPath = this._rwSshSetup?.key_path || 'auto-detected';
            const claude = this._rwVerifyResults?.claude_available ? 'Available' : 'Not found';

            summaryEl.style.display = 'block';
            summaryEl.innerHTML = `
                <div class="rw-summary-row"><span class="rw-summary-label">Host:</span><span class="rw-summary-value">${this._escapeHtml(username)}@${this._escapeHtml(hostname)}:${port}</span></div>
                <div class="rw-summary-row"><span class="rw-summary-label">SSH Key:</span><span class="rw-summary-value">${this._escapeHtml(keyPath)}</span></div>
                <div class="rw-summary-row"><span class="rw-summary-label">Key Status:</span><span class="rw-summary-value">${this._rwKeyStatus === 'existing_works' || this._rwKeyStatus === 'setup_complete' ? 'Authorized' : 'Needs setup'}</span></div>
                <div class="rw-summary-row"><span class="rw-summary-label">Claude CLI:</span><span class="rw-summary-value">${claude}</span></div>
            `;
        } else {
            summaryEl.style.display = 'none';
        }
    }

    async _rwSave() {
        const name = document.getElementById('rw-name').value.trim();
        if (!name) { this.showToast('Please enter a name for this server', 'warning'); return; }

        const isMount = this._rwMethod === 'mount';

        if (isMount) {
            const mountPath = document.getElementById('rw-mount-path').value.trim();
            if (!mountPath) { this.showToast('Please enter a mount path', 'warning'); return; }
        }

        const host = {
            id: crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2),
            name,
            mode: isMount ? 'mount' : 'ssh',
        };

        if (isMount) {
            host.mount_path = document.getElementById('rw-mount-path').value.trim();
        } else {
            host.hostname = document.getElementById('rw-hostname').value.trim();
            host.port = parseInt(document.getElementById('rw-port').value) || 22;
            host.username = document.getElementById('rw-username').value.trim();
            host.ssh_key_path = this._rwSshSetup?.key_path || '';
            host.default_path = document.getElementById('rw-default-path').value.trim() || '~';
        }

        const remoteHosts = [...(this.config.remote_hosts || []), host];

        try {
            const res = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ remote_hosts: remoteHosts }),
            });
            const result = await res.json();
            if (result.success) {
                this.config.remote_hosts = remoteHosts;
                this.renderRemotesSettings();
                this.renderRemoteHostsSidebar();
                this.closeRemoteWizard();
                this.showToast(`Server "${name}" added successfully`, 'success');
            } else {
                this.showToast('Failed to save: ' + (result.error || 'Unknown error'), 'error');
            }
        } catch (e) {
            this.showToast('Failed to save: ' + e.message, 'error');
        }
    }

    // ============== Utilities ==============

    getFlags() {
        const effortBtn = this.flags.effortLevel?.querySelector('.toggle-btn.active');
        const effortLevel = effortBtn ? effortBtn.dataset.value : 'high';

        return {
            resume: this.flags.resume.checked,
            continue: this.flags.continue.checked,
            verbose: this.flags.verbose.checked,
            print_mode: this.flags.printMode.checked,
            print_prompt: this.flags.printMode.checked
                ? (this.flags.printPrompt.value.trim() || null)
                : null,
            permission_mode: this.flags.permissionMode.value || null,
            model: this.flags.model.value || null,
            effort_level: effortLevel !== 'high' ? effortLevel : null,
            extended_thinking: this.flags.extendedThinking.checked,
            thinking_tokens: this.flags.extendedThinking.checked
                ? (parseInt(this.flags.thinkingTokens.value) || 31999)
                : null,
            system_prompt: this.flags.systemPrompt.value.trim() || null,
            fallback_model: this.flags.fallbackModel.value || null,
            autocompact_threshold: this.flags.autocompactThreshold.value
                ? parseInt(this.flags.autocompactThreshold.value) || null
                : null,
            allowed_tools: this.flags.allowedTools.value.trim() || null,
            disallowed_tools: this.flags.disallowedTools.value.trim() || null,
            add_dirs: this.flags.addDirs.value.trim() || null,
            mcp_config: this.flags.mcpConfig.value.trim() || null,
            agent_teams: this.flags.agentTeams?.checked || false,
        };
    }

    renderMarkdown(text) {
        if (!text) return '';
        try {
            // Configure marked to NOT allow raw HTML in markdown output.
            // This prevents XSS from markdown content containing <script>, <img onerror>, etc.
            const renderer = new marked.Renderer();
            const sanitizedHtml = marked.parse(text, {
                renderer: renderer,
                breaks: true,
            });
            // Strip any raw HTML tags that could execute scripts.
            // Allow safe formatting tags only.
            return this._sanitizeHtml(sanitizedHtml);
        } catch {
            return this._escapeHtml(text);
        }
    }

    _sanitizeHtml(html) {
        // Allow only safe HTML tags from markdown rendering.
        // Remove event handlers (onerror, onclick, etc.) and dangerous tags (script, iframe, etc.)
        const ALLOWED_TAGS = /^(p|br|strong|b|em|i|u|s|del|code|pre|blockquote|ul|ol|li|h[1-6]|a|table|thead|tbody|tr|th|td|hr|div|span|sub|sup|kbd|details|summary)$/i;
        const doc = new DOMParser().parseFromString(html, 'text/html');

        function cleanNode(node) {
            const children = Array.from(node.childNodes);
            for (const child of children) {
                if (child.nodeType === Node.ELEMENT_NODE) {
                    const tagName = child.tagName.toLowerCase();
                    // Remove dangerous elements entirely
                    if (['script', 'iframe', 'object', 'embed', 'form', 'input', 'textarea', 'button', 'select', 'style', 'link', 'meta', 'base', 'svg', 'math'].includes(tagName)) {
                        child.remove();
                        continue;
                    }
                    // For img tags, only allow src with data: or http(s): protocols and remove event handlers
                    if (tagName === 'img') {
                        const src = child.getAttribute('src') || '';
                        if (!src.match(/^(https?:\/\/|data:image\/)/i)) {
                            child.remove();
                            continue;
                        }
                    }
                    // Remove all event handler attributes (on*)
                    const attrs = Array.from(child.attributes);
                    for (const attr of attrs) {
                        if (attr.name.toLowerCase().startsWith('on') ||
                            attr.name.toLowerCase() === 'style' && /expression|javascript|vbscript/i.test(attr.value) ||
                            ['href', 'src', 'action', 'formaction', 'xlink:href'].includes(attr.name.toLowerCase()) &&
                            /^\s*(javascript|vbscript|data:text)/i.test(attr.value)) {
                            child.removeAttribute(attr.name);
                        }
                    }
                    // For anchor tags, ensure safe href
                    if (tagName === 'a') {
                        const href = child.getAttribute('href') || '';
                        if (/^\s*(javascript|vbscript|data:)/i.test(href)) {
                            child.removeAttribute('href');
                        }
                        // Open external links in new tab safely
                        child.setAttribute('rel', 'noopener noreferrer');
                    }
                    cleanNode(child);
                }
            }
        }
        cleanNode(doc.body);
        return doc.body.innerHTML;
    }

    // ============== Agent Management ==============

    async loadAgentLibrary() {
        try {
            const response = await fetch('/api/agents/library');
            const data = await response.json();
            this._agentLibrary = Array.isArray(data) ? data : (data.agents || []);
            this._activeAgents = (this.config.active_agents || []).filter(
                id => this._agentLibrary.some(a => a.id === id)
            );
            this._customAgents = this.config.custom_agents || [];
            this.renderSidebarAgentSummary();
            this.updateAgentCount();
            this.renderCustomAgentsList();
            // Auto-show summary if agents were previously configured
            if (this._activeAgents.length > 0 && this.flags.agentTeams) {
                this.flags.agentTeams.checked = true;
                const summary = document.getElementById('sidebar-agents-summary');
                if (summary) summary.classList.remove('hidden');
            }
        } catch (error) {
            console.error('Failed to load agent library:', error);
        }
    }

    openAgentsModal() {
        this._agentCategoryFilter = 'all';
        document.querySelectorAll('#agents-modal-filter .btn-sm').forEach(b => b.classList.remove('active'));
        const allBtn = document.querySelector('#agents-modal-filter .btn-sm[data-category="all"]');
        if (allBtn) allBtn.classList.add('active');
        document.getElementById('agents-overlay').classList.remove('hidden');
        this.renderAgentModalGrid();
        this.updateAgentCount();
    }

    closeAgentsModal() {
        document.getElementById('agents-overlay').classList.add('hidden');
        this.renderSidebarAgentSummary();
    }

    renderAgentModalGrid() {
        const grid = document.getElementById('agents-modal-grid');
        if (!grid) return;

        const filter = this._agentCategoryFilter;
        const agents = filter === 'all'
            ? this._agentLibrary
            : this._agentLibrary.filter(a => a.category === filter);

        if (agents.length === 0) {
            grid.innerHTML = '<div style="color:var(--text-secondary);padding:12px;">No agents in this category</div>';
            return;
        }

        grid.innerHTML = agents.map(agent => {
            const isActive = this._activeAgents.includes(agent.id);
            const isLocked = agent.locked;
            const classes = ['agent-card'];
            if (isActive) classes.push('active');
            if (isLocked) classes.push('locked');
            return `<div class="${classes.join(' ')}" data-agent-id="${agent.id}">
                <div class="agent-card-header">
                    <span class="agent-icon">${agent.icon || '&#129302;'}</span>
                    <span class="agent-name">${this._escapeHtml(agent.name)}</span>
                </div>
                <div class="agent-description">${this._escapeHtml(agent.description)}</div>
                <div class="agent-card-footer">
                    <span class="badge badge-${agent.category}">${agent.category}</span>
                    ${isLocked ? '<span class="badge badge-locked">Always On</span>' : ''}
                </div>
            </div>`;
        }).join('');
    }

    renderSidebarAgentSummary() {
        const list = document.getElementById('sidebar-agents-list');
        if (!list) return;

        // Always show Sentinel tag
        let tags = '<span class="sidebar-agent-tag sentinel"><span class="tag-icon">&#128737;</span> Sentinel</span>';

        // Add active agent tags
        for (const agentId of this._activeAgents) {
            const agent = this._agentLibrary.find(a => a.id === agentId);
            if (agent) {
                tags += `<span class="sidebar-agent-tag"><span class="tag-icon">${agent.icon || '&#129302;'}</span> ${this._escapeHtml(agent.name)}</span>`;
            }
        }

        if (this._activeAgents.length === 0) {
            tags += '<span style="color:var(--text-secondary);font-size:0.7rem;margin-left:4px;">+ 0 agents</span>';
        }

        list.innerHTML = tags;
    }

    updateAgentCount() {
        const countEl = document.getElementById('agents-modal-count');
        if (countEl) countEl.textContent = this._activeAgents.length;
    }

    renderCustomAgentsList() {
        const list = document.getElementById('custom-agents-list');
        if (!list) return;

        if (this._customAgents.length === 0) {
            list.innerHTML = '<div style="color:var(--text-secondary);font-size:0.85rem;">No custom agents</div>';
            return;
        }

        list.innerHTML = this._customAgents.map((agent, idx) => `
            <div class="settings-item" data-index="${idx}">
                <div class="settings-item-info">
                    <div class="settings-item-name">${this._escapeHtml(agent.name)}</div>
                    <div class="settings-item-detail">${this._escapeHtml(agent.description || '')}</div>
                </div>
                <div class="settings-item-actions">
                    <button class="btn-sm" data-action="edit-agent" data-agent-index="${idx}">Edit</button>
                    <button class="btn-sm danger" data-action="remove-agent" data-agent-index="${idx}">Remove</button>
                </div>
            </div>
        `).join('');

        list.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-action]');
            if (!btn) return;
            const idx = parseInt(btn.dataset.agentIndex);
            if (btn.dataset.action === 'edit-agent') this.editCustomAgent(idx);
            else if (btn.dataset.action === 'remove-agent') this.removeCustomAgent(idx);
        });
    }

    saveCustomAgent() {
        const name = document.getElementById('custom-agent-name').value.trim();
        const description = document.getElementById('custom-agent-description').value.trim();
        const content = document.getElementById('custom-agent-content').value.trim();

        if (!name || !content) {
            this.showToast('Name and definition are required', 'warning');
            return;
        }

        const form = document.getElementById('add-custom-agent-form');
        const editIndex = form.dataset.editIndex;

        if (editIndex !== '' && editIndex !== undefined) {
            this._customAgents[parseInt(editIndex)] = { name, description, content };
        } else {
            if (this._customAgents.length >= 2) {
                this.showToast('Maximum 2 custom agents allowed', 'warning');
                return;
            }
            this._customAgents.push({ name, description, content });
        }

        form.style.display = 'none';
        form.dataset.editIndex = '';
        document.getElementById('custom-agent-name').value = '';
        document.getElementById('custom-agent-description').value = '';
        document.getElementById('custom-agent-content').value = '';
        this.renderCustomAgentsList();
        this.showToast('Custom agent saved (click Save Agent Configuration to persist)', 'info');
    }

    editCustomAgent(index) {
        const agent = this._customAgents[index];
        if (!agent) return;
        const form = document.getElementById('add-custom-agent-form');
        form.style.display = 'block';
        form.dataset.editIndex = index;
        document.getElementById('custom-agent-name').value = agent.name;
        document.getElementById('custom-agent-description').value = agent.description || '';
        document.getElementById('custom-agent-content').value = agent.content || '';
    }

    async removeCustomAgent(index) {
        const agent = this._customAgents[index];
        const ok = await this.confirm('Remove Custom Agent', `Remove "${agent?.name || 'this agent'}"?`);
        if (!ok) return;
        this._customAgents.splice(index, 1);
        this.renderCustomAgentsList();
        this.showToast('Custom agent removed (click Save Agent Configuration to persist)', 'info');
    }

    async saveAgentConfig() {
        const data = {
            active_agents: this._activeAgents,
            custom_agents: this._customAgents,
        };

        try {
            const response = await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            });
            const result = await response.json();
            if (result.success) {
                this.config.active_agents = this._activeAgents;
                this.config.custom_agents = this._customAgents;
                this.showToast('Agent configuration saved', 'success');
            } else {
                this.showToast('Error: ' + (result.error || 'Failed to save'), 'error');
            }
        } catch (error) {
            console.error('Failed to save agent config:', error);
            this.showToast('Failed to save agent configuration', 'error');
        }
    }

    formatDate(isoString) {
        if (!isoString) return '';
        try {
            return new Date(isoString).toLocaleString();
        } catch {
            return isoString;
        }
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.app = new ClaudeCodeWeb();
});
