/**
 * Hybrid Navigation JavaScript
 * Technology-based navigation + Progressive disclosure
 */

class HybridNavigator {
    constructor() {
        this.currentTechnology = null;
        this.currentAction = null;
        this.currentCommand = null;
        this.builtTokens = [];
        this.currentMode = null;

        this.initializeEventListeners();
        this.loadTechnologies();
    }

    initializeEventListeners() {
        // Technology tab clicks
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('tech-tab')) {
                this.selectTechnology(e.target.dataset.technology);
            }
        });

        // Action filter clicks
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('action-filter')) {
                this.filterByAction(e.target.dataset.action);
            }
        });

        // Command template clicks
        document.addEventListener('click', (e) => {
            if (e.target.closest('.command-template')) {
                const commandElement = e.target.closest('.command-template');
                this.startBuildingCommand(
                    commandElement.dataset.commandText,
                    commandElement.dataset.modeName
                );
            }
        });

        // Token selection
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('token-option')) {
                this.selectToken(e.target.dataset.value);
            } else if (e.target.classList.contains('token-skip')) {
                // Skip optional token - just load next tokens without adding to built command
                this.loadNextTokens();
            }
        });

        // Reset button
        document.addEventListener('click', (e) => {
            if (e.target.id === 'reset-builder') {
                this.resetBuilder();
            }
        });

        // Insert/Copy buttons
        document.addEventListener('click', (e) => {
            if (e.target.id === 'insert-command') {
                this.insertCommand();
            } else if (e.target.id === 'copy-command') {
                this.copyCommand();
            }
        });

        // Show all keywords button
        document.addEventListener('click', (e) => {
            if (e.target.id === 'show-all-keywords') {
                this.showAllKeywords();
            }
        });

        // Keyword search input
        document.addEventListener('input', (e) => {
            if (e.target.id === 'keyword-search') {
                this.filterKeywords(e.target.value);
            }
        });

        // Semantic search input
        const searchInput = document.getElementById('semantic-search-input');
        if (searchInput) {
            let searchTimeout;
            searchInput.addEventListener('input', (e) => {
                clearTimeout(searchTimeout);
                const query = e.target.value.trim();

                if (query.length >= 2) {
                    // Debounce search by 300ms
                    searchTimeout = setTimeout(() => {
                        this.performSemanticSearch(query);
                    }, 300);
                } else {
                    this.clearSemanticSearch();
                }
            });

            // Handle Enter key
            searchInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    const query = e.target.value.trim();
                    if (query.length >= 2) {
                        this.performSemanticSearch(query);
                    }
                }
            });
        }

        // Clear search button
        document.addEventListener('click', (e) => {
            if (e.target.id === 'clear-search' || e.target.closest('#clear-search')) {
                this.clearSemanticSearch();
                const searchInput = document.getElementById('semantic-search-input');
                if (searchInput) {
                    searchInput.value = '';
                    searchInput.focus();
                }
            }
        });
    }

    async loadTechnologies() {
        try {
            const response = await fetch('/api/cli/technologies', {
                credentials: 'same-origin',
                headers: {
                    'Accept': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                throw new Error('Server returned HTML instead of JSON. Please refresh and log in again.');
            }

            const data = await response.json();
            this.renderTechnologyTabs(data.technologies);
        } catch (error) {
            console.error('Error loading technologies:', error);
            const container = document.getElementById('technology-tabs');
            if (container) {
                container.innerHTML = `
                    <div class="alert alert-warning">
                        <i class="bi bi-exclamation-triangle"></i>
                        <strong>Session Expired</strong>
                        <p class="mb-0">Please refresh the page and log in again.</p>
                        <button class="btn btn-sm btn-primary mt-2" onclick="location.reload()">
                            Refresh Page
                        </button>
                    </div>
                `;
            }
        }
    }

    renderTechnologyTabs(technologies) {
        const container = document.getElementById('technology-tabs');
        if (!container) return;

        // Top technologies get full tabs
        const topTechs = technologies.slice(0, 8);
        const otherTechs = technologies.slice(8);

        let html = '<div class="nav nav-pills mb-3" role="tablist">';

        // Render main technology tabs
        topTechs.forEach((tech, index) => {
            html += `
                <button class="nav-link tech-tab ${index === 0 ? 'active' : ''}"
                        data-technology="${tech.name}"
                        type="button"
                        role="tab">
                    ${this.getTechIcon(tech.name)} ${tech.name}
                    <span class="badge bg-secondary ms-2">${tech.count.toLocaleString()}</span>
                </button>
            `;
        });

        // "More" dropdown for other technologies
        if (otherTechs.length > 0) {
            html += `
                <div class="dropdown">
                    <button class="nav-link dropdown-toggle" type="button"
                            data-bs-toggle="dropdown">
                        More
                    </button>
                    <ul class="dropdown-menu">
            `;

            otherTechs.forEach(tech => {
                html += `
                    <li>
                        <a class="dropdown-item tech-tab" href="#"
                           data-technology="${tech.name}">
                            ${tech.name}
                            <span class="badge bg-secondary ms-2">${tech.count.toLocaleString()}</span>
                        </a>
                    </li>
                `;
            });

            html += `
                    </ul>
                </div>
            `;
        }

        html += '</div>';

        container.innerHTML = html;

        // Auto-select first technology
        if (topTechs.length > 0) {
            this.selectTechnology(topTechs[0].name);
        }
    }

    getTechIcon(technology) {
        const icons = {
            'BGP': '🌐',
            'OSPF': '🗺️',
            'Interfaces': '🔌',
            'VLANs': '🏷️',
            'ACLs': '🛡️',
            'QoS': '⚡',
            'Multicast': '📡',
            'MPLS': '🏷️',
            'VRF': '🔀',
            'Routing': '🧭',
            'System': '⚙️',
            'Monitoring': '📊',
            'Hardware': '🔧',
            'EVPN': '☁️'
        };
        return icons[technology] || '📋';
    }

    async selectTechnology(technology) {
        this.currentTechnology = technology;
        this.currentAction = null;

        // Update active state
        document.querySelectorAll('.tech-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.technology === technology);
        });

        // Load action filters
        await this.loadTechnologyStats(technology);

        // Load commands
        await this.loadCommands(technology);
    }

    async loadTechnologyStats(technology) {
        try {
            const response = await fetch(`/api/cli/technology/${encodeURIComponent(technology)}/stats`, {
                credentials: 'same-origin',
                headers: {
                    'Accept': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                console.warn('Could not load action filters - session may have expired');
                return;
            }

            const data = await response.json();
            this.renderActionFilters(data.actions);
        } catch (error) {
            console.error('Error loading technology stats:', error);
        }
    }

    renderActionFilters(actions) {
        const container = document.getElementById('action-filters');
        if (!container) return;

        let html = '<div class="btn-group" role="group">';

        // Action buttons - Show first as default!
        const actionOrder = ['Show', 'Configure', 'Remove', 'Clear', 'Debug'];
        const sortedActions = actionOrder.filter(action => actions[action]);

        sortedActions.forEach((action, index) => {
            const count = actions[action];
            const variant = this.getActionVariant(action);
            // Make "Show" active by default (first in list)
            const isActive = index === 0;

            html += `
                <button class="btn btn-sm btn-outline-${variant} action-filter ${isActive ? 'active' : ''}"
                        data-action="${action}">
                    ${action} (${count})
                </button>
            `;
        });

        html += '</div>';

        container.innerHTML = html;

        // Auto-select "Show" filter
        if (sortedActions.length > 0 && sortedActions[0] === 'Show') {
            // Trigger filter after a short delay to let UI render
            setTimeout(() => {
                this.filterByAction('Show');
            }, 100);
        }
    }

    getActionVariant(action) {
        const variants = {
            'Show': 'info',
            'Configure': 'success',
            'Remove': 'danger',
            'Clear': 'warning',
            'Debug': 'secondary',
            'Monitor': 'primary'
        };
        return variants[action] || 'secondary';
    }

    async filterByAction(action) {
        this.currentAction = action || null;

        // Update active state
        document.querySelectorAll('.action-filter').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.action === action);
        });

        // Reload commands with filter
        await this.loadCommands(this.currentTechnology, action);
    }

    shouldShowToken(token, index, allTokens) {
        // Logic to determine if token should be shown initially

        // Always show first required keyword
        if (token.token_type === 'keyword' && !token.is_optional) {
            return true;
        }

        // Show first variable (required parameter)
        if (token.token_type === 'variable' && !token.is_optional) {
            return true;
        }

        // Show first few choices
        if (token.token_type === 'choice' && index < 3) {
            return true;
        }

        // Hide optional tokens initially
        if (token.is_optional === 1 || token.is_optional === true) {
            return false;
        }

        // Show prefix only if it's the only token
        if (token.token_type === 'prefix') {
            return allTokens.length === 1;
        }

        return true;
    }

    groupTokens(tokens) {
        // Group tokens by type for better organization
        const groups = {
            required_keywords: [],
            required_variables: [],
            choices: [],
            optional: [],
            prefix: []
        };

        tokens.forEach(token => {
            const isOptional = token.is_optional === 1 || token.is_optional === true;

            if (token.token_type === 'prefix') {
                groups.prefix.push(token);
            } else if (token.token_type === 'keyword' && !isOptional) {
                groups.required_keywords.push(token);
            } else if (token.token_type === 'variable' && !isOptional) {
                groups.required_variables.push(token);
            } else if (token.token_type === 'choice') {
                groups.choices.push(token);
            } else {
                groups.optional.push(token);
            }
        });

        return groups;
    }

    async loadCommands(technology, action = null) {
        try {
            let url = `/api/cli/technology/${encodeURIComponent(technology)}?limit=50`;
            if (action) {
                url += `&action=${encodeURIComponent(action)}`;
            }

            const response = await fetch(url, {
                credentials: 'same-origin',
                headers: {
                    'Accept': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                throw new Error('Server returned HTML instead of JSON. Please refresh and log in again.');
            }

            const data = await response.json();
            this.renderCommandList(data.commands);
        } catch (error) {
            console.error('Error loading commands:', error);
            const container = document.getElementById('command-list');
            if (container) {
                container.innerHTML = `
                    <div class="alert alert-warning">
                        <i class="bi bi-exclamation-triangle"></i>
                        <strong>Error loading commands</strong>
                        <p class="mb-0">${error.message}</p>
                        <button class="btn btn-sm btn-primary mt-2" onclick="location.reload()">
                            Refresh Page
                        </button>
                    </div>
                `;
            }
        }
    }

    renderCommandList(commands) {
        const container = document.getElementById('command-list');
        if (!container) return;

        if (commands.length === 0) {
            container.innerHTML = `
                <div class="alert alert-info">
                    <i class="bi bi-info-circle"></i>
                    No commands found for this combination.
                </div>
            `;
            return;
        }

        let html = '';

        commands.forEach(cmd => {
            const hasParams = cmd.command_text.includes('<') || cmd.command_text.includes('[');
            const displayText = cmd.command_base || cmd.command_text;
            const isSimple = !hasParams;

            html += `
                <div class="command-template card mb-2 ${isSimple ? 'border-success' : ''}"
                     data-command-text="${this.escapeHtml(displayText)}"
                     data-mode-name="${cmd.mode_name}">
                    <div class="card-body p-3">
                        <div class="d-flex justify-content-between align-items-start">
                            <div class="flex-grow-1">
                                <div class="command-syntax">
                                    ${this.highlightSyntax(cmd.command_text)}
                                </div>
                                ${cmd.description ? `<small class="text-muted d-block mt-1">${this.escapeHtml(cmd.description)}</small>` :
                                  `<small class="text-muted d-block mt-1">${this.generateDescription(cmd)}</small>`}
                                <div class="mt-2">
                                    ${isSimple ? '<span class="badge bg-success-subtle text-success"><i class="bi bi-lightning-fill"></i> Ready to use</span> ' : ''}
                                    ${cmd.actions && cmd.actions.length > 0 ? cmd.actions.map(action => `
                                        <span class="badge bg-${this.getActionVariant(action)}">${this.escapeHtml(action)}</span>
                                    `).join(' ') : ''}
                                </div>
                            </div>
                            <div>
                                ${hasParams ?
                                    `<button class="btn btn-sm btn-primary">
                                        <i class="bi bi-wrench"></i> Build
                                    </button>` :
                                    `<button class="btn btn-sm btn-success">
                                        <i class="bi bi-plus-circle"></i> Use
                                    </button>`
                                }
                            </div>
                        </div>
                    </div>
                </div>
            `;
        });

        container.innerHTML = html;
    }

    getCommandIcon(cmd) {
        // Return emoji icon based on command type
        if (!cmd.actions || cmd.actions.length === 0) return '📝';

        const action = cmd.actions[0];
        const icons = {
            'Show': '👁️',
            'Configure': '⚙️',
            'Clear': '🗑️',
            'Debug': '🐛',
            'Monitor': '📊',
            'Remove': '❌'
        };
        return icons[action] || '📝';
    }

    generateDescription(cmd) {
        // Generate helpful description based on command
        const text = cmd.command_text.toLowerCase();

        if (text.includes('show') && text.includes('summary')) {
            return 'Display summary information';
        } else if (text.includes('show') && text.includes('neighbor')) {
            return 'View neighbor details';
        } else if (text.includes('show') && text.includes('status')) {
            return 'Check current status';
        } else if (text.includes('show')) {
            return 'Display information';
        } else if (text.includes('clear')) {
            return 'Clear/reset counters or state';
        } else if (text.includes('debug')) {
            return 'Enable debugging output';
        }

        return 'Run this command';
    }

    highlightSyntax(text) {
        // Escape HTML first to prevent XSS
        const escaped = this.escapeHtml(text);

        // Now apply syntax highlighting to the escaped text
        return escaped
            // Highlight [optional] parameters in gray
            .replace(/\[([^\]]+)\]/g, '<span class="text-muted">[$1]</span>')
            // Highlight <REQUIRED> parameters in blue
            .replace(/&lt;([^&]+)&gt;/g, '<span class="text-primary">&lt;$1&gt;</span>')
            // Highlight ( | ) choice indicators
            .replace(/\(([^)]+)\)/g, '<span class="text-success">($1)</span>')
            // Highlight ... ellipsis
            .replace(/\.\.\./g, '<span class="text-warning">...</span>');
    }

    startBuildingCommand(commandText, modeName) {
        this.currentCommand = { commandText, modeName };
        this.builtTokens = [];
        this.currentMode = modeName;

        // Show progressive builder panel
        document.getElementById('progressive-builder').style.display = 'block';
        document.getElementById('welcome-message').style.display = 'none';

        // Initialize with first token
        this.loadNextTokens();
    }

    async loadNextTokens() {
        try {
            const response = await fetch('/api/cli/next-tokens', {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify({
                    mode: this.currentMode,
                    tokens: this.builtTokens
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                throw new Error('Server returned HTML instead of JSON. Please refresh and log in again.');
            }

            const data = await response.json();
            this.renderProgressiveBuilder(data.next_tokens);
        } catch (error) {
            console.error('Error loading next tokens:', error);
            const container = document.getElementById('builder-tokens');
            if (container) {
                container.innerHTML = `
                    <div class="alert alert-warning">
                        <i class="bi bi-exclamation-triangle"></i>
                        <strong>Error</strong>
                        <p class="mb-0">${error.message}</p>
                        <button class="btn btn-sm btn-primary mt-2" onclick="location.reload()">
                            Refresh Page
                        </button>
                    </div>
                `;
            }
        }
    }

    renderProgressiveBuilder(tokens) {
        const container = document.getElementById('builder-tokens');
        if (!container) return;

        // Update built command display
        const builtCommand = this.builtTokens.join(' ');
        document.getElementById('built-command').textContent = builtCommand || '(building...)';

        if (tokens.length === 0) {
            // Command is complete!
            container.innerHTML = `
                <div class="alert alert-success">
                    <i class="bi bi-check-circle"></i> Command complete!
                </div>
            `;
            document.getElementById('command-actions').style.display = 'block';
            return;
        }

        // Group tokens for better organization
        const groups = this.groupTokens(tokens);

        let html = '<div class="mb-3"><strong>Next:</strong></div>';

        // Priority 1: Required keywords (like in CLI - you see the keyword first)
        if (groups.required_keywords.length > 0) {
            html += this.renderTokenGroup('Select command', groups.required_keywords, false);
        }

        // Priority 2: Required variables (parameters you must provide)
        if (groups.required_variables.length > 0) {
            groups.required_variables.forEach(token => {
                html += this.renderVariableInput(token);
            });
        }

        // Priority 3: Choices (when command has multiple paths)
        if (groups.choices.length > 0) {
            const choiceToken = groups.choices[0];
            if (choiceToken.choices && choiceToken.choices.length > 0) {
                html += this.renderChoices(choiceToken, 5); // Show first 5 choices
            }
        }

        // Priority 4: Prefix tokens (optional, collapse by default)
        if (groups.prefix.length > 0 && tokens.length < 3) {
            // Only show if we have few other options
            html += this.renderPrefixTokens(groups.prefix[0]);
        }

        // Priority 5: Optional tokens (collapsed by default)
        if (groups.optional.length > 0) {
            html += `
                <div class="mt-3">
                    <button class="btn btn-sm btn-outline-secondary" onclick="document.getElementById('optional-tokens').style.display='block'; this.style.display='none'">
                        <i class="bi bi-plus-circle"></i> Show ${groups.optional.length} optional parameter${groups.optional.length > 1 ? 's' : ''}
                    </button>
                    <div id="optional-tokens" style="display: none;" class="mt-2">
                        ${this.renderTokenGroup('Optional', groups.optional, true)}
                    </div>
                </div>
            `;
        }

        // If too many keywords, collapse them
        if (groups.required_keywords.length > 10) {
            html = this.renderManyKeywords(groups.required_keywords);
        }

        container.innerHTML = html;
        document.getElementById('command-actions').style.display = 'none';

        // Add event listener for variable inputs
        document.querySelectorAll('.variable-input').forEach(input => {
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    const value = e.target.value.trim();
                    if (value) {
                        this.selectToken(value);
                    }
                }
            });
        });
    }

    renderTokenGroup(label, tokens, isOptional) {
        let html = '';
        if (label) {
            html += `<div class="mb-2"><small class="text-muted">${label}</small></div>`;
        }

        tokens.forEach(token => {
            const tokenValue = token.token_value || token.value || 'unknown';
            const cssClass = this.getTokenClass(token.token_type);

            html += `
                <button class="btn ${cssClass} token-option mb-2 me-2"
                        data-value="${this.escapeHtml(tokenValue)}"
                        data-token-type="${token.token_type}">
                    ${tokenValue}
                    ${isOptional ? ' <small>(optional)</small>' : ''}
                </button>
            `;
        });

        return html;
    }

    renderVariableInput(token) {
        const tokenValue = token.token_value || token.value || 'unknown';
        const tokenLabel = token.description || `Enter ${tokenValue}`;

        return `
            <div class="mb-3">
                <label class="form-label"><strong>${tokenValue}</strong></label>
                <input type="text" class="form-control variable-input"
                       placeholder="${tokenValue}"
                       data-token-value="${this.escapeHtml(tokenValue)}"
                       data-token-type="variable">
                <small class="form-text text-muted">${tokenLabel}</small>
            </div>
        `;
    }

    renderChoices(choiceToken, maxShow = 5) {
        const choices = choiceToken.choices || [];
        const showChoices = choices.slice(0, maxShow);
        const hiddenChoices = choices.slice(maxShow);

        const cssClass = this.getTokenClass('choice');

        let html = `<div class="mb-2"><small class="text-muted">${choiceToken.description || 'Choose one'}:</small></div>`;

        showChoices.forEach(choice => {
            html += `
                <button class="btn ${cssClass} token-option mb-2 me-2"
                        data-value="${this.escapeHtml(choice)}"
                        data-token-type="choice">
                    ${choice}
                </button>
            `;
        });

        if (hiddenChoices.length > 0) {
            html += `
                <button class="btn btn-sm btn-outline-secondary mb-2 me-2"
                        onclick="document.getElementById('more-choices').style.display='inline'; this.style.display='none'">
                    +${hiddenChoices.length} more
                </button>
                <span id="more-choices" style="display: none;">
            `;

            hiddenChoices.forEach(choice => {
                html += `
                    <button class="btn ${cssClass} token-option mb-2 me-2"
                            data-value="${this.escapeHtml(choice)}"
                            data-token-type="choice">
                        ${choice}
                    </button>
                `;
            });

            html += '</span>';
        }

        return html;
    }

    renderPrefixTokens(token) {
        return `
            <div class="mb-3">
                <small class="text-muted">Optional prefix:</small>
                <div>
                    <button class="btn btn-outline-secondary token-option mb-2 me-2"
                            data-value="no"
                            data-token-type="prefix">
                        no
                    </button>
                    <button class="btn btn-outline-secondary token-option mb-2 me-2"
                            data-value="default"
                            data-token-type="prefix">
                        default
                    </button>
                    <button class="btn btn-outline-info token-skip mb-2 me-2"
                            data-skip="true">
                        <i class="bi bi-arrow-right"></i> Skip
                    </button>
                </div>
            </div>
        `;
    }

    renderManyKeywords(keywords) {
        // Store keywords for filtering
        this.allKeywords = keywords;

        // When there are many keywords, add search/filter
        let html = `
            <div class="mb-3">
                <input type="text" class="form-control mb-2" id="keyword-search"
                       placeholder="Type to filter commands...">
                <div id="keyword-list">
        `;

        keywords.slice(0, 10).forEach(token => {
            const tokenValue = token.token_value || token.value || 'unknown';
            html += `
                <button class="btn btn-primary token-option mb-2 me-2 keyword-btn"
                        data-value="${this.escapeHtml(tokenValue)}"
                        data-token-type="keyword">
                    ${tokenValue}
                </button>
            `;
        });

        html += `
                </div>
                <button class="btn btn-sm btn-outline-secondary" id="show-all-keywords">
                    Show all ${keywords.length} commands
                </button>
            </div>
        `;

        return html;
    }

    getTokenClass(tokenType) {
        const classes = {
            'literal': 'btn-primary',
            'keyword': 'btn-primary',
            'variable': 'btn-outline-warning',
            'optional': 'btn-outline-secondary',
            'prefix': 'btn-outline-secondary',
            'choice': 'btn-outline-info'
        };
        return classes[tokenType] || 'btn-outline-primary';
    }

    selectToken(value) {
        this.builtTokens.push(value);
        this.loadNextTokens();
    }

    resetBuilder() {
        this.builtTokens = [];
        this.currentCommand = null;
        this.currentMode = null;

        document.getElementById('progressive-builder').style.display = 'none';
        document.getElementById('welcome-message').style.display = 'block';
    }

    insertCommand() {
        const command = this.builtTokens.join(' ');
        // TODO: Integrate with configlet editor
        alert(`Inserting command:\n\n${command}\n\nConfiglet integration coming soon!`);
    }

    copyCommand() {
        const command = this.builtTokens.join(' ');
        navigator.clipboard.writeText(command).then(() => {
            this.showSuccess('Command copied to clipboard!');
        });
    }

    showAllKeywords() {
        // Get all keywords from current state
        if (!this.allKeywords || this.allKeywords.length === 0) {
            return;
        }

        const keywordList = document.getElementById('keyword-list');
        if (!keywordList) return;

        // Clear and show all keywords
        keywordList.innerHTML = '';
        this.allKeywords.forEach(token => {
            const tokenValue = token.token_value || token.value || 'unknown';
            const button = document.createElement('button');
            button.className = 'btn btn-primary token-option mb-2 me-2 keyword-btn';
            button.dataset.value = tokenValue;
            button.dataset.tokenType = 'keyword';
            button.textContent = tokenValue;
            keywordList.appendChild(button);
        });

        // Hide the show-all button
        const showAllBtn = document.getElementById('show-all-keywords');
        if (showAllBtn) {
            showAllBtn.style.display = 'none';
        }
    }

    filterKeywords(searchTerm) {
        if (!this.allKeywords || this.allKeywords.length === 0) {
            return;
        }

        const keywordList = document.getElementById('keyword-list');
        if (!keywordList) return;

        const term = searchTerm.toLowerCase().trim();

        // Filter keywords
        const filtered = term === ''
            ? this.allKeywords.slice(0, 10)  // Show first 10 if no search
            : this.allKeywords.filter(token => {
                const value = (token.token_value || token.value || '').toLowerCase();
                return value.includes(term);
            });

        // Update display
        keywordList.innerHTML = '';
        if (filtered.length === 0) {
            keywordList.innerHTML = '<p class="text-muted">No matching commands found</p>';
            return;
        }

        filtered.forEach(token => {
            const tokenValue = token.token_value || token.value || 'unknown';
            const button = document.createElement('button');
            button.className = 'btn btn-primary token-option mb-2 me-2 keyword-btn';
            button.dataset.value = tokenValue;
            button.dataset.tokenType = 'keyword';
            button.textContent = tokenValue;
            keywordList.appendChild(button);
        });

        // Show count
        const showAllBtn = document.getElementById('show-all-keywords');
        if (showAllBtn) {
            if (term === '' && this.allKeywords.length > 10) {
                showAllBtn.style.display = 'block';
                showAllBtn.textContent = `Show all ${this.allKeywords.length} commands`;
            } else {
                showAllBtn.style.display = 'none';
            }
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    showError(message) {
        // TODO: Implement toast notifications
        console.error(message);
    }

    showSuccess(message) {
        // TODO: Implement toast notifications
        console.log(message);
    }

    async performSemanticSearch(query) {
        const resultsContainer = document.getElementById('semantic-search-results');
        const clearButton = document.getElementById('clear-search');

        if (!resultsContainer) return;

        // Show loading state
        resultsContainer.style.display = 'block';
        resultsContainer.innerHTML = `
            <div class="text-center p-3">
                <div class="spinner-border spinner-border-sm text-primary" role="status">
                    <span class="visually-hidden">Searching...</span>
                </div>
                <small class="ms-2 text-muted">Searching...</small>
            </div>
        `;

        if (clearButton) {
            clearButton.style.display = 'block';
        }

        try {
            const response = await fetch(`/api/cli/semantic-search?q=${encodeURIComponent(query)}&limit=25`, {
                credentials: 'same-origin',
                headers: {
                    'Accept': 'application/json'
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            this.renderSemanticSearchResults(data.results, query);
        } catch (error) {
            console.error('Semantic search error:', error);
            resultsContainer.innerHTML = `
                <div class="alert alert-warning mb-0">
                    <i class="bi bi-exclamation-triangle"></i>
                    <strong>Search Error</strong>
                    <p class="mb-0">${error.message}</p>
                </div>
            `;
        }
    }

    renderSemanticSearchResults(results, query) {
        const resultsContainer = document.getElementById('semantic-search-results');
        if (!resultsContainer) return;

        if (results.length === 0) {
            resultsContainer.innerHTML = `
                <div class="alert alert-info mb-0">
                    <i class="bi bi-info-circle"></i>
                    No commands found for "<strong>${this.escapeHtml(query)}</strong>".
                    Try different keywords or browse by technology below.
                </div>
            `;
            return;
        }

        let html = `
            <div class="card">
                <div class="card-header bg-light d-flex justify-content-between align-items-center">
                    <strong>
                        <i class="bi bi-search"></i>
                        Search Results for "${this.escapeHtml(query)}"
                    </strong>
                    <span class="badge bg-primary">${results.length} found</span>
                </div>
                <div class="list-group list-group-flush" style="max-height: 500px; overflow-y: auto;">
        `;

        results.forEach((result, index) => {
            const hasParams = result.command_text.includes('<') || result.command_text.includes('[');
            const isSimple = !hasParams;
            const relevanceBadge = result.relevance_score >= 90 ? 'bg-success' :
                                   result.relevance_score >= 75 ? 'bg-info' : 'bg-secondary';

            html += `
                <div class="list-group-item list-group-item-action command-template ${isSimple ? 'border-start border-success border-3' : ''}"
                     data-command-text="${this.escapeHtml(result.command_base || result.command_text)}"
                     data-mode-name="${result.mode_name}"
                     style="cursor: pointer;">
                    <div class="d-flex justify-content-between align-items-start">
                        <div class="flex-grow-1">
                            <div class="command-syntax mb-1">
                                ${this.highlightSyntax(result.command_text)}
                            </div>
                            <div class="small">
                                <span class="badge bg-secondary">${this.escapeHtml(result.mode_name)}</span>
                                <span class="badge bg-light text-dark">${this.escapeHtml(result.mode_category)}</span>
                                <span class="badge ${relevanceBadge}">
                                    ${result.relevance_score}% match
                                </span>
                                ${isSimple ? '<span class="badge bg-success"><i class="bi bi-lightning-fill"></i> Ready</span>' : ''}
                            </div>
                            ${result.matched_keywords && result.matched_keywords.length > 0 ? `
                                <div class="small text-muted mt-1">
                                    <i class="bi bi-tags"></i> Matched: ${result.matched_keywords.map(k => this.escapeHtml(k)).join(', ')}
                                </div>
                            ` : ''}
                        </div>
                        <div class="ms-2">
                            ${hasParams ?
                                '<button class="btn btn-sm btn-primary"><i class="bi bi-wrench"></i> Build</button>' :
                                '<button class="btn btn-sm btn-success"><i class="bi bi-plus-circle"></i> Use</button>'
                            }
                        </div>
                    </div>
                </div>
            `;
        });

        html += `
                </div>
                <div class="card-footer bg-light text-muted small">
                    <i class="bi bi-info-circle"></i>
                    Click any command to use the progressive builder or insert it directly.
                </div>
            </div>
        `;

        resultsContainer.innerHTML = html;
    }

    clearSemanticSearch() {
        const resultsContainer = document.getElementById('semantic-search-results');
        const clearButton = document.getElementById('clear-search');

        if (resultsContainer) {
            resultsContainer.style.display = 'none';
            resultsContainer.innerHTML = '';
        }

        if (clearButton) {
            clearButton.style.display = 'none';
        }
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.hybridNavigator = new HybridNavigator();
});
