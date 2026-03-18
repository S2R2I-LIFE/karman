/**
 * CLI Browser - Interactive Command Builder
 * Implements progressive disclosure for EOS CLI commands
 */

class CLIBrowser {
    constructor(options) {
        this.apiBase = options.apiBase || '/api/cli';
        this.currentMode = null;
        this.currentTokens = [];
        this.history = [];  // For undo

        // DOM elements
        this.currentModeEl = document.querySelector(options.currentModeElement);
        this.currentCommandEl = document.querySelector(options.currentCommandElement);
        this.tokenButtonsEl = document.querySelector(options.tokenButtonsElement);
        this.explanationPanelEl = document.querySelector(options.explanationPanelElement);
        this.explanationContentEl = document.querySelector(options.explanationContentElement);
        this.explanationSourceEl = document.querySelector(options.explanationSourceElement);
    }

    /**
     * Select a CLI mode and load first tokens
     */
    async selectMode(modeName) {
        this.currentMode = modeName;
        this.currentTokens = [];
        this.history = [];

        // Update UI
        this.currentModeEl.textContent = modeName;
        this.currentModeEl.style.display = '';
        this.updateCommandDisplay();
        this.updateButtons();

        // Load first tokens
        await this.loadNextTokens();
    }

    /**
     * Load next valid tokens from API
     */
    async loadNextTokens() {
        if (!this.currentMode) return;

        try {
            const response = await fetch(`${this.apiBase}/next-tokens`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    mode: this.currentMode,
                    tokens: this.currentTokens
                })
            });

            const data = await response.json();

            if (data.error) {
                this.showToast('Error', data.error, 'danger');
                return;
            }

            this.renderTokenButtons(data.next_tokens);
        } catch (error) {
            this.showToast('Error', `Failed to load tokens: ${error.message}`, 'danger');
        }
    }

    /**
     * Render token option buttons
     */
    renderTokenButtons(tokens) {
        if (!tokens || tokens.length === 0) {
            this.tokenButtonsEl.innerHTML = `
                <div class="alert alert-success">
                    <i class="bi bi-check-circle"></i> Command complete! 
                    Click <strong>Validate</strong> to verify or <strong>Explain</strong> for details.
                </div>
            `;
            return;
        }

        // Group tokens by type
        const grouped = {
            keyword: [],
            variable: [],
            choice: [],
            optional: [],
            group: []
        };

        tokens.forEach(token => {
            if (grouped[token.token_type]) {
                grouped[token.token_type].push(token);
            }
        });

        let html = '';

        // Render keywords first
        if (grouped.keyword.length > 0) {
            html += '<div class="mb-2"><small class="text-muted fw-bold">KEYWORDS</small></div>';
            html += '<div class="row g-2 mb-3">';
            grouped.keyword.forEach(token => {
                html += `
                    <div class="col-md-6 col-lg-4">
                        <button class="btn btn-outline-primary token-btn token-btn-keyword w-100" 
                                data-token="${this.escapeHtml(token.token_value)}"
                                data-type="${token.token_type}">
                            <strong>${this.escapeHtml(token.token_value)}</strong>
                            <br><small class="text-muted">${this.escapeHtml(token.description)}</small>
                        </button>
                    </div>
                `;
            });
            html += '</div>';
        }

        // Render choices
        if (grouped.choice.length > 0) {
            html += '<div class="mb-2"><small class="text-muted fw-bold">CHOICES</small></div>';
            html += '<div class="row g-2 mb-3">';
            grouped.choice.forEach(token => {
                // Show each choice as a separate button
                token.choices.forEach(choice => {
                    html += `
                        <div class="col-md-6 col-lg-4">
                            <button class="btn btn-outline-purple token-btn token-btn-choice w-100"
                                    data-token="${this.escapeHtml(choice)}"
                                    data-type="choice">
                                <strong>${this.escapeHtml(choice)}</strong>
                            </button>
                        </div>
                    `;
                });
            });
            html += '</div>';
        }

        // Render variables
        if (grouped.variable.length > 0) {
            html += '<div class="mb-2"><small class="text-muted fw-bold">PARAMETERS</small></div>';
            html += '<div class="row g-2 mb-3">';
            grouped.variable.forEach(token => {
                html += `
                    <div class="col-12">
                        <div class="input-group">
                            <span class="input-group-text token-btn-variable">${this.escapeHtml(token.token_value)}</span>
                            <input type="text" 
                                   class="form-control token-input" 
                                   data-token-name="${this.escapeHtml(token.token_value)}"
                                   placeholder="Enter ${this.escapeHtml(token.token_value)}">
                            <button class="btn btn-success token-add-btn" 
                                    data-input="${this.escapeHtml(token.token_value)}">
                                Add
                            </button>
                        </div>
                        <small class="text-muted">${this.escapeHtml(token.description)}</small>
                    </div>
                `;
            });
            html += '</div>';
        }

        // Render optional
        if (grouped.optional.length > 0) {
            html += '<div class="mb-2"><small class="text-muted fw-bold">OPTIONAL</small></div>';
            html += '<div class="row g-2 mb-3">';
            grouped.optional.forEach(token => {
                html += `
                    <div class="col-md-6 col-lg-4">
                        <button class="btn btn-outline-secondary token-btn token-btn-optional w-100"
                                data-token="${this.escapeHtml(token.token_value)}"
                                data-type="optional">
                            [${this.escapeHtml(token.token_value)}]
                            <br><small>${this.escapeHtml(token.description)}</small>
                        </button>
                    </div>
                `;
            });
            html += '</div>';
        }

        this.tokenButtonsEl.innerHTML = html;

        // Add click handlers
        this.tokenButtonsEl.querySelectorAll('.token-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const token = e.currentTarget.dataset.token;
                this.addToken(token);
            });
        });

        // Add handlers for variable inputs
        this.tokenButtonsEl.querySelectorAll('.token-add-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const inputName = e.currentTarget.dataset.input;
                const inputEl = this.tokenButtonsEl.querySelector(`[data-token-name="${inputName}"]`);
                if (inputEl && inputEl.value.trim()) {
                    this.addToken(inputEl.value.trim());
                    inputEl.value = '';
                }
            });
        });

        // Enter key on inputs
        this.tokenButtonsEl.querySelectorAll('.token-input').forEach(input => {
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && e.target.value.trim()) {
                    this.addToken(e.target.value.trim());
                    e.target.value = '';
                }
            });
        });
    }

    /**
     * Add a token to current command
     */
    addToken(token) {
        // Save state for undo
        this.history.push([...this.currentTokens]);

        // Add token
        this.currentTokens.push(token);

        // Update UI
        this.updateCommandDisplay();
        this.updateButtons();

        // Load next tokens
        this.loadNextTokens();
    }

    /**
     * Update command display
     */
    updateCommandDisplay() {
        if (this.currentTokens.length === 0) {
            this.currentCommandEl.innerHTML = '<span class="text-muted">Building command...</span>';
            return;
        }

        // Render with syntax highlighting
        const commandHtml = this.currentTokens.map((token, index) => {
            // Classify token type
            if (token.toUpperCase() === token && token.includes('_')) {
                return `<span class="cli-variable">${this.escapeHtml(token)}</span>`;
            } else if (token.startsWith('[')) {
                return `<span class="cli-optional">${this.escapeHtml(token)}</span>`;
            } else {
                return `<span class="cli-keyword">${this.escapeHtml(token)}</span>`;
            }
        }).join(' ');

        this.currentCommandEl.innerHTML = commandHtml;
    }

    /**
     * Update button states
     */
    updateButtons() {
        const hasTokens = this.currentTokens.length > 0;
        const hasHistory = this.history.length > 0;

        document.getElementById('btn-undo').disabled = !hasHistory;
        document.getElementById('btn-reset').disabled = !hasTokens;
        document.getElementById('btn-validate').disabled = !hasTokens;
        document.getElementById('btn-explain').disabled = !hasTokens;
        document.getElementById('btn-copy').disabled = !hasTokens;
    }

    /**
     * Undo last token
     */
    undo() {
        if (this.history.length === 0) return;

        this.currentTokens = this.history.pop();
        this.updateCommandDisplay();
        this.updateButtons();
        this.loadNextTokens();
    }

    /**
     * Reset command
     */
    reset() {
        if (!confirm('Reset command and start over?')) return;

        this.currentTokens = [];
        this.history = [];
        this.updateCommandDisplay();
        this.updateButtons();
        this.loadNextTokens();
    }

    /**
     * Validate command
     */
    async validate() {
        if (!this.currentMode || this.currentTokens.length === 0) return;

        try {
            const response = await fetch(`${this.apiBase}/validate`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    mode: this.currentMode,
                    tokens: this.currentTokens
                })
            });

            const data = await response.json();

            if (data.valid) {
                this.showToast('Valid Command', 'Command syntax is valid!', 'success');
            } else {
                this.showToast('Invalid Command', data.error || 'Command syntax is invalid', 'warning');
            }
        } catch (error) {
            this.showToast('Error', `Validation failed: ${error.message}`, 'danger');
        }
    }

    /**
     * Get AI explanation
     */
    async explain() {
        if (!this.currentMode || this.currentTokens.length === 0) return;

        const command = this.currentTokens.join(' ');

        // Show loading
        this.explanationPanelEl.style.display = 'block';
        this.explanationContentEl.innerHTML = `
            <div class="spinner-border spinner-border-sm" role="status">
                <span class="visually-hidden">Loading...</span>
            </div>
            <span class="ms-2">Generating explanation...</span>
        `;

        try {
            const response = await fetch(`${this.apiBase}/explain`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    command: command,
                    mode: this.currentMode
                })
            });

            const data = await response.json();

            if (data.error) {
                this.explanationContentEl.innerHTML = `
                    <div class="alert alert-danger">${this.escapeHtml(data.error)}</div>
                `;
                return;
            }

            this.explanationContentEl.innerHTML = this.renderMarkdown(data.explanation);
            this.explanationSourceEl.textContent = data.source;

            if (data.cached) {
                this.explanationSourceEl.innerHTML += ' <span class="badge bg-success">Cached</span>';
            }
        } catch (error) {
            this.explanationContentEl.innerHTML = `
                <div class="alert alert-danger">Failed to load explanation: ${this.escapeHtml(error.message)}</div>
            `;
        }
    }

    /**
     * Copy command to clipboard
     */
    async copyCommand() {
        if (this.currentTokens.length === 0) return;

        const command = this.currentTokens.join(' ');

        try {
            await navigator.clipboard.writeText(command);
            this.showToast('Copied', 'Command copied to clipboard!', 'success');
        } catch (error) {
            this.showToast('Error', 'Failed to copy to clipboard', 'danger');
        }
    }

    /**
     * Show toast notification
     */
    showToast(title, message, type = 'info') {
        const toastContainer = document.getElementById('toast-container');
        const toastId = `toast-${Date.now()}`;

        const bgClass = {
            'success': 'bg-success',
            'danger': 'bg-danger',
            'warning': 'bg-warning',
            'info': 'bg-info'
        }[type] || 'bg-info';

        const toast = document.createElement('div');
        toast.id = toastId;
        toast.className = `toast align-items-center text-white ${bgClass} border-0`;
        toast.setAttribute('role', 'alert');
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    <strong>${this.escapeHtml(title)}</strong><br>
                    ${this.escapeHtml(message)}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;

        toastContainer.appendChild(toast);
        const bsToast = new bootstrap.Toast(toast, { delay: 3000 });
        bsToast.show();

        toast.addEventListener('hidden.bs.toast', () => {
            toast.remove();
        });
    }

    /**
     * Simple HTML escape
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Simple markdown renderer (basic support)
     */
    renderMarkdown(text) {
        // Basic markdown: bold, italic, code, lists
        let html = this.escapeHtml(text);

        // Code blocks
        html = html.replace(/```(.*?)```/gs, '<pre><code>$1</code></pre>');

        // Inline code
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

        // Bold
        html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

        // Italic
        html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

        // Line breaks
        html = html.replace(/\n/g, '<br>');

        return html;
    }
}
