# Hybrid Navigation: Technology + Progressive Disclosure

## The Best of Both Worlds

Combine **technology-based organization** (intuitive browsing) with **progressive disclosure** (tab-complete experience).

---

## Problem with Current Approach

**Mode-based navigation alone:**
- ❌ Requires knowledge of Arista CLI structure
- ❌ Commands scattered across 712 modes
- ❌ "RouterBgpBaseMode" is cryptic
- ❌ Hard to discover related commands

**Progressive disclosure alone:**
- ✅ Great for building commands
- ❌ But you still need to pick a mode first
- ❌ Doesn't help with discovery

---

## Proposed Hybrid Solution

### Visual Flow

```
┌─────────────────────────────────────────────────────────┐
│  Technology Tabs                                         │
│  [BGP] [OSPF] [Interfaces] [VLANs] [ACLs] [QoS]         │
└─────────────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────────────┐
│  Command Templates (in selected technology)              │
│                                                          │
│  □ show bgp summary                                     │
│  □ show bgp neighbors  ← Click to build                │
│  □ neighbor ... remote-as                               │
│  □ router bgp                                           │
└─────────────────────────────────────────────────────────┘
                    ↓ User clicks command
┌─────────────────────────────────────────────────────────┐
│  Progressive Command Builder                             │
│                                                          │
│  Built: neighbor 10.1.1.1 remote-as                     │
│                                                          │
│  Next token: Enter AS Number                            │
│  [65000] [65001] [65535] or [Custom: ______]           │
│                                                          │
│  Like tab-complete, but visual!                         │
└─────────────────────────────────────────────────────────┘
```

---

## User Experience Flow

### Example 1: Simple Command

**User wants to check BGP neighbors**

1. Click **"BGP"** technology tab
2. See list of BGP commands
3. Click **"show bgp summary"**
4. ✅ Command complete! (no parameters needed)
5. Click "Insert" or "Copy"

**Result:** Found and used command in 3 clicks

---

### Example 2: Complex Command with Parameters

**User wants to configure BGP neighbor**

1. Click **"BGP"** technology tab
2. See list of BGP commands
3. Click **"neighbor ... remote-as"** template
4. **Progressive builder opens:**

```
Step 1: Select keyword
→ [neighbor] ← Auto-filled

Step 2: Enter neighbor IP
→ Input field shows: <IP_ADDRESS>
→ User types: 10.1.1.1
→ Validation: ✓ Valid IPv4

Step 3: Select keyword
→ [remote-as] ← Auto-filled

Step 4: Enter AS number
→ Input field shows: <ASN>
→ Suggestions: [65000] [65001] [4200000000]
→ User selects: 65001
→ Validation: ✓ Valid ASN

✅ Command built: neighbor 10.1.1.1 remote-as 65001

[Insert to Configlet] [Copy] [Reset]
```

5. System shows:
   - Required mode: RouterBgpBaseMode
   - Related commands (neighbor activate, neighbor description)
   - Link to "Configure BGP Neighbor" workflow

**Result:** Built complex command with validation and guidance

---

### Example 3: Command with Options

**User wants to configure address family**

1. Click **"BGP"** technology tab
2. Click **"address-family"** template
3. **Progressive builder:**

```
Step 1: Optional prefix (no/default)
→ [no] [default] [Skip (optional)]
→ User selects: Skip

Step 2: Keyword
→ [address-family] ← Auto-filled

Step 3: Choose address family type
→ [ipv4 unicast] [ipv6 unicast] [evpn] [vpnv4] [vpnv6]
→ User clicks: ipv4 unicast

✅ Command built: address-family ipv4 unicast

Next steps suggested:
  1. neighbor <IP> activate
  2. network <PREFIX>
  3. See "BGP IPv4 Configuration" workflow
```

---

## Key Features of Hybrid Approach

### 1. Technology-First Discovery
```
User thinking: "I need to work with BGP"
↓
Click BGP tab
↓
See ALL BGP commands (3,036) grouped together
↓
Not scattered across 46 modes!
```

### 2. Progressive Token Selection (Like Tab-Complete)
```
Token Types Visual Coding:

[keyword]              ← Blue chip (fixed value)
<VARIABLE>             ← Orange input field with validation
[choice1|choice2]      ← Blue chips (pick one)
[optional]?            ← Gray chip (can skip)
```

### 3. Real-Time Validation
```
✓ Valid IP address: 10.1.1.1
✗ Invalid IP: 999.999.999.999
  → Shows error immediately

✓ Valid ASN range: 1-4294967295
✗ Out of range: 5000000000
  → Explains valid range
```

### 4. Context-Aware Help
```
For each token, show:
├─ Description: "BGP Autonomous System Number"
├─ Valid values: 1-4294967295
├─ Examples: 65000, 65001, 4200000000
├─ Common values: [65000] [65001] [Your org default]
└─ Documentation link
```

### 5. Workflow Integration
```
After building: neighbor 10.1.1.1 remote-as 65001

System suggests:
  📖 Related Commands:
    • neighbor activate (required next step)
    • neighbor description (recommended)
    • neighbor update-source

  🔧 Related Workflows:
    • Configure eBGP Neighbor (6 steps)
    • Configure iBGP Neighbor (5 steps)

  🐛 Troubleshooting:
    • BGP Neighbor Not Establishing
```

---

## Implementation Architecture

### Database Schema Updates

```sql
-- Tag commands with technology
ALTER TABLE cli_commands ADD COLUMN technology_tags TEXT;  -- JSON array

-- Tag commands with intent/action
ALTER TABLE cli_commands ADD COLUMN action_tags TEXT;      -- JSON array

-- Example data:
technology_tags: ["BGP", "Routing"]
action_tags: ["show", "monitor"]
```

### API Endpoints Needed

```python
# Get commands by technology
GET /api/cli/technology/bgp
→ Returns: All BGP-related commands with metadata

# Get commands by technology + action
GET /api/cli/technology/bgp?action=show
→ Returns: BGP show commands only

# Progressive disclosure (existing, no change needed)
POST /api/cli/next-tokens
{
  "mode": "RouterBgpBaseMode",
  "tokens": ["neighbor", "10.1.1.1"]
}
→ Returns: Next valid tokens

# Validate command
POST /api/cli/validate
{
  "mode": "RouterBgpBaseMode",
  "tokens": ["neighbor", "10.1.1.1", "remote-as", "65001"]
}
→ Returns: { valid: true, mode: "...", next_steps: [...] }
```

### Frontend Components

```javascript
// Technology Navigation Component
<TechnologyTabs>
  <Tab name="BGP" count="3036" icon="globe" />
  <Tab name="Interfaces" count="2606" icon="ethernet" />
  ...
</TechnologyTabs>

// Command Template List
<CommandList technology="bgp" action="show">
  <CommandTemplate
    name="show bgp summary"
    description="View BGP neighbor summary"
    onClick={startBuilding}
  />
  ...
</CommandList>

// Progressive Builder (right panel)
<ProgressiveBuilder
  command="neighbor"
  onTokenSelect={handleToken}
  onComplete={handleComplete}
/>
```

---

## User Interface Layout

```
┌────────────────────────────────────────────────────┐
│  CLI Browser - Hybrid Navigation                   │
├────────────────────────────────────────────────────┤
│                                                     │
│  [BGP] [OSPF] [Interfaces] [VLANs] [ACLs] [QoS]    │ ← Technology Tabs
│                                                     │
│  Filter: [All] [Show] [Configure] [Clear]          │ ← Action Filter
│                                                     │
├─────────────────────┬───────────────────────────────┤
│  Command Templates  │  Progressive Builder          │
│  (Left Panel)       │  (Right Panel)                │
├─────────────────────┼───────────────────────────────┤
│                     │                               │
│  □ show bgp summary │  Click a command to           │
│    View summary     │  start building →             │
│                     │                               │
│  □ show bgp neighbors│                              │
│    Detailed info    │                               │
│                     │                               │
│  □ neighbor remote-as│                              │
│    Configure peer   │                               │
│    [CLICK]          │                               │
│         ↓           │                               │
│    [EXPANDED]       │  ┌─────────────────────────┐  │
│                     │  │ Building: neighbor      │  │
│                     │  │                         │  │
│                     │  │ Next: Enter IP          │  │
│                     │  │ [Input: _______]        │  │
│                     │  │                         │  │
│                     │  │ Examples:               │  │
│                     │  │  • 10.1.1.1             │  │
│                     │  │  • 192.168.1.1          │  │
│                     │  └─────────────────────────┘  │
│                     │                               │
└─────────────────────┴───────────────────────────────┘
```

---

## Advantages Over Mode-Based Alone

| Feature | Mode-Based | Hybrid (Tech + Progressive) |
|---------|------------|-----------------------------|
| **Discovery** | Hard - need to know modes | Easy - browse by technology |
| **Organization** | 712 separate modes | ~20 technology groups |
| **Learning Curve** | Steep - need CLI knowledge | Gentle - intuitive categories |
| **Command Building** | Progressive disclosure ✓ | Progressive disclosure ✓ |
| **Validation** | Yes | Yes + contextual help |
| **Related Commands** | Not obvious | Grouped together |
| **Workflows** | Separate | Integrated |

---

## Migration Strategy

### Phase 1: Tag Existing Commands (1-2 days)
```python
# Run script to analyze and tag all commands
python3 tag_commands_by_technology.py

# Results:
# - 3,036 commands tagged "BGP"
# - 2,606 commands tagged "Interfaces"
# - etc.
```

### Phase 2: Update API (2-3 days)
```python
# Add technology-based endpoints
# Modify existing progressive disclosure to work with tech groups
# Add validation with richer error messages
```

### Phase 3: Build UI Components (3-5 days)
```javascript
// Create TechnologyTabs component
// Create CommandTemplateList component
// Enhance ProgressiveBuilder with better UX
// Add inline validation and hints
```

### Phase 4: Integration & Testing (2-3 days)
```
// Wire up components
// Test all command building flows
// Add keyboard shortcuts
// Polish UX
```

**Total: ~2 weeks**

---

## Future Enhancements

### Smart Suggestions
```
User selects: neighbor
System suggests common patterns:
  • Last 5 neighbors you configured
  • Your organization's AS number
  • Common loopback IPs in your network
```

### Command History
```
Recently built commands:
  1. neighbor 10.1.1.1 remote-as 65001
  2. neighbor 10.1.1.2 remote-as 65001
  3. neighbor 10.2.1.1 remote-as 65002

[Reuse] [Modify] [Favorite]
```

### Bulk Operations
```
Configure multiple neighbors:
  Pattern: neighbor <IP> remote-as 65001

  IPs: [10.1.1.1] [10.1.1.2] [10.1.1.3]

  Generates:
    neighbor 10.1.1.1 remote-as 65001
    neighbor 10.1.1.2 remote-as 65001
    neighbor 10.1.1.3 remote-as 65001
```

### AI-Assisted Building
```
User types: "configure bgp neighbor to 10.1.1.1 as 65001"

AI suggests:
  neighbor 10.1.1.1 remote-as 65001
  [Accept] [Modify] [Explain]
```

---

## Example Use Cases

### Use Case 1: New Network Engineer
```
Scenario: Junior engineer needs to check OSPF neighbors

Old way (mode-based):
  1. Know that OSPF commands are in EnableMode
  2. Navigate to EnableMode
  3. Know the command is "show ip ospf neighbor"
  4. Type or build it

New way (hybrid):
  1. Click "OSPF" tab
  2. See "show ospf neighbors" template
  3. Click it
  4. Done! (command has no parameters)

Time saved: 70%
Knowledge required: Minimal
```

### Use Case 2: Senior Engineer, New Feature
```
Scenario: Experienced engineer learning EVPN (new feature)

Old way:
  1. Google: "Arista EVPN commands"
  2. Find mode names (multiple modes involved)
  3. Search through modes
  4. Trial and error

New way:
  1. Search or browse for "EVPN"
  2. See all EVPN commands grouped
  3. Click command template
  4. Progressive builder guides through parameters
  5. See related workflows

Time saved: 60%
Learning curve: Reduced
```

### Use Case 3: Troubleshooting Under Pressure
```
Scenario: Network is down, need to check BGP fast

Old way:
  1. Remember "show bgp summary" command
  2. Type it out
  3. Remember other diagnostic commands
  4. Type each one

New way:
  1. Click "BGP" tab
  2. Click "Troubleshoot" filter
  3. See all diagnostic commands
  4. Click each to run
  5. See "BGP Troubleshooting" workflow
  6. Follow step-by-step

Time saved: 50%
Errors avoided: Many
```

---

## Success Metrics

### Quantitative
- **Command discovery time:** Target 70% reduction
- **Command building errors:** Target 80% reduction
- **Time to completion:** Target 50% reduction
- **User satisfaction:** Target 4.5/5 stars

### Qualitative
- Users can find commands without knowing modes
- Beginners feel confident building commands
- Experts appreciate grouped related commands
- Fewer "how do I..." support questions

---

## Conclusion

**The hybrid approach gives users:**

1. ✅ **Intuitive discovery** via technology tabs
2. ✅ **Guided building** via progressive disclosure
3. ✅ **Real-time validation** preventing errors
4. ✅ **Contextual help** for learning
5. ✅ **Workflow integration** for complex tasks

**Result: A CLI browser that's actually useful for network engineers at all skill levels.**

---

## Files & Prototypes

- **Visual Prototype:** `prototypes/hybrid_tech_progressive.html`
- **Technology Analysis:** `analyze_command_patterns.py`
- **Alternative Approaches:** `ALTERNATIVE_NAVIGATION_PROPOSALS.md`
- **This Document:** `HYBRID_NAVIGATION_DESIGN.md`

**Next step:** Implement technology tagging and build the hybrid UI!
