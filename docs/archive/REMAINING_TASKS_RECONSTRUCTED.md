# CLI Command Browser - Remaining Tasks (RECONSTRUCTED)

## Immediate Fixes Needed (HIGH PRIORITY)

### 1. Fix Getting Started Section - Mode Name Errors

**Problem**: The "Getting Started" section references modes that don't exist in the database

**Current State** (BROKEN):
```html
<!-- web/templates/cli_browser.html lines 86-109 -->
1. ConfigSessionMode         ✓ EXISTS (1,940 commands)
2. EnableMode                ✓ EXISTS (4,516 commands)
3. RouterBgpMode             ✗ DOES NOT EXIST (should be RouterBgpBaseMode)
4. InterfaceEthernetMode     ✗ DOES NOT EXIST (should be IntfConfigMode)
```

**Recommended Fix**:
Update `web/templates/cli_browser.html` lines 86-109 with correct mode names:

```html
<!-- 1. ConfigSessionMode - KEEP AS IS ✓ -->
<a href="#" class="list-group-item list-group-item-action mode-item mode-item-featured"
    data-mode-name="ConfigSessionMode" data-category="Configuration">
    <strong>ConfigSessionMode</strong>
    <br><small class="text-muted">Main config mode (1,940 commands)</small>
</a>

<!-- 2. EnableMode - KEEP AS IS ✓ -->
<a href="#" class="list-group-item list-group-item-action mode-item mode-item-featured"
    data-mode-name="EnableMode" data-category="Enable">
    <strong>EnableMode</strong>
    <br><small class="text-muted">Show commands & troubleshooting (4,516 commands)</small>
</a>

<!-- 3. CHANGE RouterBgpMode → RouterBgpBaseMode -->
<a href="#" class="list-group-item list-group-item-action mode-item mode-item-featured"
    data-mode-name="RouterBgpBaseMode" data-category="Routing Protocol">
    <strong>RouterBgpBaseMode</strong>
    <br><small class="text-muted">BGP routing config (396 commands)</small>
</a>

<!-- 4. CHANGE InterfaceEthernetMode → IntfConfigMode -->
<a href="#" class="list-group-item list-group-item-action mode-item mode-item-featured"
    data-mode-name="IntfConfigMode" data-category="Configuration">
    <strong>IntfConfigMode</strong>
    <br><small class="text-muted">Interface configuration (1,408 commands)</small>
</a>
```

**Impact**: Without this fix, clicking on the last two "Getting Started" modes will result in errors or empty results.

---

## Mode Selection Rationale

### Database Statistics (712 total modes)
Top modes by command count:
1. **EnableMode** - 4,516 commands (Enable category)
2. **ConfigSessionMode** - 1,940 commands (Configuration category)
3. **IntfConfigMode** - 1,408 commands (Configuration category)
4. **RouterBgpBaseMode** - 396 commands (Routing Protocol category)
5. RouterBgpVrfMode - 358 commands (Routing Protocol category)
6. RouteMapMode - 168 commands (Other category)
7. RouterOspfMode - 112 commands (Routing Protocol category)

### Why These 4 Modes for "Getting Started"?

1. **EnableMode** (4,516 commands)
   - Most comprehensive mode
   - Users start here for show commands and troubleshooting
   - Essential for any network engineer

2. **ConfigSessionMode** (1,940 commands)
   - Primary entry point for configuration
   - Gateway to other config modes (interfaces, routing, etc.)
   - Second most used mode

3. **IntfConfigMode** (1,408 commands)
   - Interface configuration is one of the most common tasks
   - Third most used mode
   - Directly accessed from ConfigSessionMode

4. **RouterBgpBaseMode** (396 commands)
   - Most commonly used routing protocol mode
   - Representative example of routing configuration
   - Good introduction to hierarchical mode navigation

**Alternative Consideration**:
- Could replace RouterBgpBaseMode with **RouterOspfMode** (112 commands) if OSPF is more commonly used in your environment
- Could add **RouteMapMode** (168 commands) for policy configuration

---

## Mode Categories in Database

```
Categories:
- BGP               (46 modes)
- Configuration     (numerous modes)
- Enable            (1-2 modes)
- Interface         (8 modes)
- OSPF              (numerous modes)
- Other             (miscellaneous)
- Routing Protocol  (numerous modes)
- VLAN              (numerous modes)
```

---

## Phase 4: AI Integration (~Implementation)

- [ ] Implement `core/ai_explainer.py` with provider chain
  - Ollama (qwen3:30b) as primary
  - Gemini (gemini-2.0-flash-exp) as fallback
  - OpenAI (gpt-4o-mini) as second fallback
  - Anthropic (claude-3-5-sonnet-20241022) as final fallback
- [ ] Create `config/ai_config.yaml` configuration file
- [ ] Update `.env.example` with AI API key placeholders
- [ ] Wire up `/api/cli/explain` route to use AIExplainer
- [ ] Implement 30-day TTL caching in `cli_explanations` table
- [ ] Test with real AI models

---

## Phase 5: Configlet Builder Integration

- [ ] Add "CLI Browser" tab to existing `web/templates/builder.html`
- [ ] Create `web/static/js/configlet-integration.js`
  - Command insertion into textarea
  - Context detection (which mode user is in)
  - Proper indentation formatting
- [ ] Integrate with ConfigValidator
- [ ] Add "Insert to Configlet" button in CLI browser

---

## Phase 6: Testing & Optimization

### Testing
- [ ] Write unit tests:
  - `tests/test_cli_parser.py` - Parser edge cases
  - `tests/test_cli_navigator.py` - Progressive disclosure
  - `tests/test_ai_explainer.py` - AI provider fallback chain
- [ ] Write integration tests:
  - Full command construction workflow
  - End-to-end API tests

### Performance
- [ ] Database query optimization
- [ ] Cache hit rate analysis
- [ ] Progressive disclosure speed test with 12K commands

### UI/UX
- [ ] Mobile responsiveness testing
- [ ] Tooltip refinement
- [ ] Keyboard shortcuts (optional)

### Documentation
- [ ] User guide (how to use CLI browser)
- [ ] API documentation
- [ ] Developer setup guide

---

## Known Issues to Address

### 1. Mode Names Validation ✓ ADDRESSED ABOVE
**Status**: Fixed by updating mode names in Getting Started section

### 2. Optional Tokens Handling
**Problem**: Progressive disclosure doesn't handle optional tokens perfectly
**Current**: Basic support, may show too many options
**Future**: Smarter filtering based on command context
**Files**: `core/cli_navigator.py`, `_command_matches_tokens` method

### 3. Database Locks During Testing
**Problem**: Can't test while web server is running
**Solution**: Use connection pooling or read-only connections for tests
**Files**: All core/*.py files that access database

---

## Enhancements (Nice to Have)

- [ ] Command history tracking (most used commands)
- [ ] Favorites/bookmarks for commands
- [ ] Export commands to file
- [ ] Bulk command generation (templates)
- [ ] Dark mode toggle for CLI browser
- [ ] Command comparison (diff two similar commands)
- [ ] Integration with network diagram (show which devices support command)
- [ ] Add more "Getting Started" modes based on user environment:
  - RouterOspfMode for OSPF-heavy networks
  - VlanConfigMode for VLAN management
  - RouteMapMode for policy-based routing

---

## Current Status Summary

✅ **Completed** (Phases 1-3):
- Database with 712 modes, 12,013 commands
- Progressive disclosure algorithm (optimized)
- Full web UI with responsive design
- Mode selector with Getting Started section
- Syntax highlighting and validation

⚠️ **Needs Immediate Fix**:
- **RouterBgpMode → RouterBgpBaseMode** in Getting Started section (line 99)
- **InterfaceEthernetMode → IntfConfigMode** in Getting Started section (line 105)

📋 **Remaining**:
- AI integration (Phase 4)
- Configlet integration (Phase 5)
- Testing & docs (Phase 6)

---

## Implementation Priority

### IMMEDIATE (Do First)
1. Fix mode names in Getting Started section (5 minutes)
   - File: `web/templates/cli_browser.html`
   - Lines: 99, 105

### SHORT TERM (Next Steps)
2. Validate all mode references across the codebase
3. Test Getting Started section with fixed mode names
4. Consider adding mode existence validation on page load

### LONG TERM (Future Phases)
5. AI Integration (Phase 4)
6. Configlet Integration (Phase 5)
7. Testing & Documentation (Phase 6)
