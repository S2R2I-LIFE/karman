# CLI Command Browser - Remaining Tasks

## Immediate Fixes Needed

### 1. Fix Getting Started Section (HIGH PRIORITY) ✓ FIXED
**Issue**: RouterBgpMode and InterfaceEthernetMode didn't exist in the database
**Fix**: Updated `web/templates/cli_browser.html` lines 99-109
- Changed `RouterBgpMode` to `RouterBgpBaseMode`
- Changed `InterfaceEthernetMode` to `IntfConfigMode`
- These are the actual mode names in the database

**Status**: ✓ COMPLETED - All mode references have been updated

## Phase 4: AI Integration (~2-3 hours)

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

## Phase 5: Configlet Builder Integration (~1-2 hours)

- [ ] Add "CLI Browser" tab to existing `web/templates/builder.html`
- [ ] Create `web/static/js/configlet-integration.js`
  - Command insertion into textarea
  - Context detection (which mode user is in)
  - Proper indentation formatting
- [ ] Integrate with ConfigValidator
- [ ] Add "Insert to Configlet" button in CLI browser

## Phase 6: Testing & Optimization (~1-2 hours)

- [ ] Write unit tests:
  - `tests/test_cli_parser.py` - Parser edge cases
  - `tests/test_cli_navigator.py` - Progressive disclosure
  - `tests/test_ai_explainer.py` - AI provider fallback chain
- [ ] Write integration tests:
  - Full command construction workflow
  - End-to-end API tests
- [ ] Performance optimization:
  - Database query optimization
  - Cache hit rate analysis
  - Progressive disclosure speed test with 12K commands
- [ ] UI/UX refinement:
  - Mobile responsiveness testing
  - Tooltip refinement
  - Keyboard shortcuts (optional)
- [ ] Documentation:
  - User guide (how to use CLI browser)
  - API documentation
  - Developer setup guide

## Known Issues to Address

### 1. Mode Names Validation
**Problem**: Featured modes in "Getting Started" may reference non-existent modes
**Solution**: Cross-reference all featured mode names against actual database modes
**Files**: `web/templates/cli_browser.html`, lines 82-120

### 2. Optional Tokens Handling
**Problem**: Progressive disclosure doesn't handle optional tokens perfectly
**Current**: Basic support, may show too many options
**Future**: Smarter filtering based on command context
**Files**: `core/cli_navigator.py`, `_command_matches_tokens` method

### 3. Database Locks During Testing
**Problem**: Can't test while web server is running
**Solution**: Use connection pooling or read-only connections for tests
**Files**: All core/*.py files that access database

## Enhancements (Nice to Have)

- [ ] Command history tracking (most used commands)
- [ ] Favorites/bookmarks for commands
- [ ] Export commands to file
- [ ] Bulk command generation (templates)
- [ ] Dark mode toggle for CLI browser
- [ ] Command comparison (diff two similar commands)
- [ ] Integration with network diagram (show which devices support command)

## Current Status Summary

✅ **Completed** (Phases 1-3):
- Database with 707 modes, 12,013 commands
- Progressive disclosure algorithm (optimized)
- Full web UI with responsive design
- Mode selector with Getting Started section
- Syntax highlighting and validation

✅ **Fixed**:
- RouterBgpMode → RouterBgpBaseMode in Getting Started section
- InterfaceEthernetMode → IntfConfigMode in Getting Started section

🔄 **In Progress**:
- UX improvements (tooltips, better categorization)

📋 **Remaining**: 
- AI integration (Phase 4)
- Configlet integration (Phase 5)  
- Testing & docs (Phase 6)

## Estimated Time to Completion

- Immediate fix: 5 minutes
- Phase 4 (AI): 2-3 hours
- Phase 5 (Configlet): 1-2 hours
- Phase 6 (Testing): 1-2 hours

**Total remaining**: ~4-7 hours of development work
