# How to Access the CLI Browser

## Quick Guide

The CLI Browser is now fully integrated into the Kármán web interface!

### 🎯 Two Ways to Access:

#### Option 1: Navigation Bar (Recommended)
1. Log in to Kármán web interface at `http://localhost:5000`
2. Look at the top navigation bar
3. Click **"CLI Browser"** (with terminal icon 🖥️)
   - Located after "Tasks" in the navigation menu
   - Icon: `bi-terminal`

#### Option 2: Dashboard Quick Link
1. Go to the Dashboard (home page)
2. Scroll down to **"Quick Actions"** section
3. Look for the **NEW FEATURE** section
4. Click the large **"CLI Browser"** button
   - Shows: "Interactive command reference with 500+ documented commands"

---

## Navigation Bar Layout

```
Kármán
├── Dashboard
├── Devices
├── Configlets
├── Builder
├── Tasks
└── CLI Browser  ← NEW! Click here
```

---

## What You'll See

When you click on CLI Browser, you'll be taken to:
- **Route**: `/cli-browser`
- **Page**: Interactive CLI command reference

### Main Features:
1. **Mode Selector** - 712 Arista EOS CLI modes
2. **Getting Started** - 4 most common modes:
   - EnableMode (4,516 commands)
   - ConfigSessionMode (1,940 commands)
   - RouterBgpBaseMode (396 commands)
   - IntfConfigMode (1,408 commands)
3. **Progressive Disclosure** - Build commands step-by-step
4. **Search** - Find commands quickly
5. **Command Documentation** - 500+ commands with descriptions (NEW!)

---

## Statistics

Current CLI Browser contains:
- **712 modes** across 8 categories
- **24,026 commands** total
- **500 enriched commands** with documentation
- **3 troubleshooting workflows**
- **14 workflow steps**

---

## Next Steps After Accessing CLI Browser

### For First-Time Users:
1. Click one of the "Getting Started" modes
2. Try building a command using progressive disclosure
3. Explore different mode categories

### For Advanced Users:
1. Use the search function to find specific commands
2. View enriched command documentation
3. Explore troubleshooting workflows (coming soon to UI)

---

## Technical Details

### Route Information:
- **Main Route**: `/cli-browser`
- **Template**: `web/templates/cli_browser.html`
- **Backend**: `web/app.py` (lines 566-579)

### API Endpoints Available:
- `/api/cli/modes` - Get all modes
- `/api/cli/modes/categories` - Modes by category
- `/api/cli/commands/<mode>` - Commands for a mode
- `/api/cli/next-tokens` - Progressive disclosure
- `/api/cli/search?q=<query>` - Search commands
- `/api/cli/stats` - Statistics

---

## Troubleshooting

### Can't See "CLI Browser" Link?
1. Make sure you're logged in
2. Refresh the page (Ctrl+F5 or Cmd+Shift+R)
3. Check that `web/templates/base.html` has been updated
4. Restart the Flask development server

### CLI Browser Not Loading?
1. Check browser console for errors (F12)
2. Verify database exists at `custom-cvp.db`
3. Check Flask logs for error messages

### Navigation Bar Too Crowded?
The navigation automatically collapses on mobile devices. Click the hamburger menu (≡) to see all options.

---

## Recent Updates (2026-01-21)

✅ **Added CLI Browser to navigation bar**
- Location: After "Tasks" menu item
- Icon: Terminal icon (bi-terminal)
- Always visible when logged in

✅ **Added Quick Action on Dashboard**
- Highlighted as "NEW FEATURE"
- Large button with description
- Easy discovery for new users

✅ **Fixed Mode Name Issues**
- RouterBgpMode → RouterBgpBaseMode
- InterfaceEthernetMode → IntfConfigMode

✅ **Enhanced Documentation**
- 500 commands now have descriptions
- 3 troubleshooting workflows added
- Foundation for 24,000+ command enrichment

---

## For Developers

### To Update Navigation:
Edit `web/templates/base.html` lines 59-64

### To Update Dashboard Quick Action:
Edit `web/templates/dashboard.html` lines 200-220

### To Add More CLI Features:
See `IMPLEMENTATION_COMPLETE.md` for architecture details

---

**Status: Navigation Complete ✅**

Users can now easily access the CLI Browser from any page in the application!
