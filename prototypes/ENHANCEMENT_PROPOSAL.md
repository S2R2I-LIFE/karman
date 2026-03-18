# CLI Browser Enhancement Proposal
## Making it Educational and Practically Useful for Network Engineers

---

## Current State Analysis

### What We Have Now:
- ✅ 712 modes parsed from Arista EOS CLI
- ✅ 12,013 commands with tokenized syntax
- ✅ Token types (keyword, variable, optional, choice)
- ✅ Mode categorization (8 categories)
- ✅ Progressive disclosure UI

### What's Missing (Critical Gaps):
- ❌ **No command descriptions** - "What does this command do?"
- ❌ **No parameter explanations** - "What is PREFIX vs PREFIX6?"
- ❌ **No use cases** - "When would I use this?"
- ❌ **No examples** - "Show me a real-world scenario"
- ❌ **No output examples** - "What will this command show me?"
- ❌ **No relationship mapping** - "What commands work together?"
- ❌ **No troubleshooting workflows** - "How do I debug BGP?"
- ❌ **No warnings/gotchas** - "What could go wrong?"

---

## Problem Statement

**Current approach provides a phone book of commands without context.**

A network engineer facing a BGP neighbor issue needs:
1. Which mode to enter
2. Which commands diagnose the problem
3. What parameters those commands accept
4. What output to expect
5. How to interpret the results
6. How to fix the issue

**We currently only provide #1 and partial #2.**

---

## Proposed Enhancements

### Phase 1: Data Enrichment (Foundation)

#### 1.1 Enhanced Database Schema

```sql
-- Command Documentation Table
CREATE TABLE cli_command_docs (
    doc_id INTEGER PRIMARY KEY AUTOINCREMENT,
    command_id INTEGER,
    short_description TEXT,         -- One-liner: "Configures BGP address family"
    long_description TEXT,           -- Detailed explanation
    use_cases TEXT,                  -- JSON: ["MPLS L3VPN", "Data center EVPN"]
    privilege_level INTEGER,         -- 0-15
    config_persistence TEXT,         -- "Running only" or "NVRAM"
    created_at TIMESTAMP,
    FOREIGN KEY (command_id) REFERENCES cli_commands(command_id)
);

-- Parameter Documentation Table
CREATE TABLE cli_parameter_docs (
    param_id INTEGER PRIMARY KEY AUTOINCREMENT,
    parameter_name TEXT,             -- "PREFIX", "ADDR_FAMILY", etc.
    description TEXT,                -- "IPv4 prefix in CIDR notation"
    data_type TEXT,                  -- "ipv4-prefix", "integer", "string"
    valid_values TEXT,               -- JSON: ["ipv4 unicast", "ipv6 unicast"]
    default_value TEXT,
    examples TEXT                    -- JSON: ["10.0.0.0/8", "192.168.1.0/24"]
);

-- Command Examples Table
CREATE TABLE cli_command_examples (
    example_id INTEGER PRIMARY KEY AUTOINCREMENT,
    command_id INTEGER,
    scenario TEXT,                   -- "Configure eBGP neighbor"
    full_example TEXT,               -- Complete command sequence
    expected_output TEXT,            -- What you should see
    explanation TEXT,                -- Step-by-step breakdown
    difficulty TEXT,                 -- "beginner", "intermediate", "advanced"
    FOREIGN KEY (command_id) REFERENCES cli_commands(command_id)
);

-- Troubleshooting Workflows Table
CREATE TABLE cli_workflows (
    workflow_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,                      -- "BGP Neighbor Not Establishing"
    problem_description TEXT,
    category TEXT,                   -- "BGP", "Interface", "OSPF"
    severity TEXT,                   -- "critical", "warning", "info"
    steps TEXT                       -- JSON array of workflow steps
);

-- Workflow Steps (linking commands)
CREATE TABLE cli_workflow_steps (
    step_id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER,
    step_number INTEGER,
    mode_name TEXT,
    command_id INTEGER,
    explanation TEXT,                -- Why this step?
    expected_result TEXT,            -- What indicates success/failure?
    FOREIGN KEY (workflow_id) REFERENCES cli_workflows(workflow_id),
    FOREIGN KEY (command_id) REFERENCES cli_commands(command_id)
);

-- Command Relationships
CREATE TABLE cli_command_relationships (
    rel_id INTEGER PRIMARY KEY AUTOINCREMENT,
    command_id INTEGER,
    related_command_id INTEGER,
    relationship_type TEXT,          -- "requires", "conflicts", "related", "alternative"
    description TEXT,
    FOREIGN KEY (command_id) REFERENCES cli_commands(command_id),
    FOREIGN KEY (related_command_id) REFERENCES cli_commands(command_id)
);

-- Common Gotchas / Warnings
CREATE TABLE cli_command_warnings (
    warning_id INTEGER PRIMARY KEY AUTOINCREMENT,
    command_id INTEGER,
    warning_type TEXT,               -- "data_loss", "outage", "memory_intensive"
    severity TEXT,                   -- "critical", "warning", "info"
    message TEXT,
    mitigation TEXT,                 -- How to avoid the issue
    FOREIGN KEY (command_id) REFERENCES cli_commands(command_id)
);
```

#### 1.2 Data Sources for Enrichment

**Option A: Manual Curation (Highest Quality)**
- Create web interface for engineers to add documentation
- Crowdsource from team's tribal knowledge
- Start with top 100 most-used commands

**Option B: AI-Powered Generation (Fast Bootstrap)**
- Use Claude/GPT-4 to generate descriptions from command syntax
- Leverage Arista EOS documentation (if available)
- Human review and refinement

**Option C: Hybrid Approach (Recommended)**
1. AI generates initial documentation for all 12K commands
2. Flag high-priority commands (top 500 by usage)
3. Human experts review and enhance priority commands
4. Community contributions for long-tail commands

---

### Phase 2: UI/UX Transformation

#### 2.1 Workflow-First Navigation

```
Primary Navigation:
├── Troubleshooting Scenarios (Featured)
│   ├── BGP Issues
│   │   ├── Neighbor not establishing
│   │   ├── Routes not received
│   │   ├── Flapping session
│   ├── Interface Issues
│   │   ├── Interface down
│   │   ├── Speed/duplex mismatch
│   │   ├── High errors/drops
│   ├── OSPF Issues
│   ├── Performance Issues
│   └── Security Issues
│
├── Browse by Task
│   ├── Initial Configuration
│   ├── Monitoring & Show Commands
│   ├── Troubleshooting & Debug
│   ├── Optimization & Tuning
│   └── Maintenance Operations
│
├── Browse by Technology
│   ├── Routing Protocols (BGP, OSPF, EIGRP)
│   ├── Switching (VLANs, STP, MLAG)
│   ├── Interfaces (Physical, Logical, Tunnels)
│   ├── Security (ACLs, AAA, Encryption)
│   └── Management (SNMP, Logging, NTP)
│
└── All Commands (Traditional)
    └── By Mode (712 modes)
```

#### 2.2 Enhanced Command View

For each command, display:

```
┌─────────────────────────────────────────────────┐
│ Command: address-family ipv4 unicast            │
├─────────────────────────────────────────────────┤
│ CONTEXT                                         │
│ • Mode: RouterBgpBaseMode                       │
│ • Category: Routing > BGP                       │
│ • Privilege: 15 (Config mode required)          │
│ • Tags: [BGP] [IPv4] [Configuration]            │
├─────────────────────────────────────────────────┤
│ DESCRIPTION                                     │
│ Enters BGP address family configuration mode    │
│ to configure IPv4 unicast routing parameters.   │
│                                                  │
│ When to use:                                    │
│ • Configuring basic BGP IPv4 routing            │
│ • Activating neighbors in IPv4 address family   │
│ • Applying route policies per address family    │
├─────────────────────────────────────────────────┤
│ SYNTAX                                          │
│ [no] address-family <ADDR_FAMILY>               │
│                                                  │
│ Parameters:                                     │
│ • ADDR_FAMILY: ipv4 unicast, ipv6 unicast, etc. │
│ • no: Remove address family configuration       │
├─────────────────────────────────────────────────┤
│ EXAMPLE WORKFLOW                                │
│                                                  │
│ Router# configure terminal                      │
│ Router(config)# router bgp 65000                │
│ Router(config-router)# address-family ipv4 uni  │
│ Router(config-router-af)# network 10.0.0.0/8    │
│ Router(config-router-af)# neighbor 10.1.1.1 act │
│                                                  │
│ Expected result:                                │
│ • Enters address family mode (prompt changes)   │
│ • Configuration can now be applied to IPv4 AF   │
├─────────────────────────────────────────────────┤
│ VERIFICATION                                    │
│ show bgp ipv4 unicast summary                   │
│ show running-config | section bgp              │
├─────────────────────────────────────────────────┤
│ RELATED COMMANDS                                │
│ • router bgp (enter BGP config mode)            │
│ • neighbor activate (activate neighbor in AF)   │
│ • show bgp summary (view BGP status)            │
├─────────────────────────────────────────────────┤
│ ⚠️ WARNINGS                                     │
│ • Changes require 'neighbor activate'           │
│ • May need to clear BGP session (disruption)    │
└─────────────────────────────────────────────────┘

[Insert to Configlet] [Add to Favorites] [Share]
```

#### 2.3 Interactive Troubleshooting Wizard

```
Scenario: BGP Neighbor Not Establishing
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Problem: BGP neighbor stuck in "Active" state
Goal: Diagnose and resolve connectivity issue

Step 1: Check BGP summary
┌─────────────────────────────────────┐
│ Command to run:                     │
│ > show bgp summary                  │
│                                     │
│ What to look for:                   │
│ • Neighbor state (Idle/Active/Est)  │
│ • Message counters                  │
│ • AS number mismatch                │
└─────────────────────────────────────┘
[Run Command] [View Example Output] [Next Step]

Step 2: Check neighbor details
┌─────────────────────────────────────┐
│ Command to run:                     │
│ > show bgp neighbors <IP>           │
│                                     │
│ What to look for:                   │
│ • BGP state and reason              │
│ • Last reset reason                 │
│ • TCP connection status             │
│ • Hold time configuration           │
└─────────────────────────────────────┘

Step 3: Verify IP connectivity
[Continue workflow...]

Step 4: Check BGP configuration
[Continue workflow...]
```

---

### Phase 3: Smart Features

#### 3.1 Context-Aware Suggestions

```
User enters: "show bgp"

Browser suggests:
┌────────────────────────────────────────────────┐
│ 🎯 Most Common Next Steps:                    │
│                                                │
│ 1. show bgp summary                            │
│    └─ View all BGP neighbors status            │
│                                                │
│ 2. show bgp neighbors                          │
│    └─ Detailed neighbor information            │
│                                                │
│ 3. show bgp ipv4 unicast                       │
│    └─ View IPv4 routing table                  │
│                                                │
│ 💡 Based on: 1,247 similar queries            │
└────────────────────────────────────────────────┘
```

#### 3.2 Command Builder with Validation

```
Build: neighbor configuration in RouterBgpBaseMode

┌────────────────────────────────────────┐
│ neighbor <IP> remote-as <ASN>          │
│                                        │
│ IP Address: [10.1.1.1    ] ✓ Valid    │
│ Remote AS:  [65001       ] ✓ Valid    │
│                                        │
│ Optional parameters:                   │
│ ☐ update-source <interface>            │
│ ☐ ebgp-multihop <ttl>                  │
│ ☐ password <string>                    │
│                                        │
│ Generated command:                     │
│ neighbor 10.1.1.1 remote-as 65001      │
│                                        │
│ [Copy] [Insert to Configlet] [Explain]│
└────────────────────────────────────────┘
```

#### 3.3 Learning Paths

```
Learning Path: BGP Configuration Mastery

Progress: 3/10 modules complete

┌──────────────────────────────────────┐
│ ✅ Module 1: Basic BGP Setup         │
│ ✅ Module 2: Neighbor Configuration   │
│ ✅ Module 3: Address Families         │
│ ⏸️  Module 4: Route Maps (IN PROG)   │
│ 🔒 Module 5: Communities & Policies   │
│ 🔒 Module 6: Route Reflectors         │
│ 🔒 Module 7: Troubleshooting          │
└──────────────────────────────────────┘

Each module includes:
• Command reference
• Lab scenarios
• Practice exercises
• Verification steps
```

---

## Implementation Roadmap

### Quick Wins (1-2 weeks)
1. ✅ Create enhanced UI prototype (DONE)
2. Add top 50 command descriptions (manual)
3. Implement workflow-based navigation
4. Add command search with descriptions

### Phase 1 (2-4 weeks)
1. Extend database schema with documentation tables
2. AI-generate initial documentation for all commands
3. Create web interface for documentation management
4. Implement enhanced command detail view

### Phase 2 (4-6 weeks)
1. Build troubleshooting workflow system
2. Create 20-30 common troubleshooting scenarios
3. Add parameter documentation
4. Implement command relationship mapping

### Phase 3 (6-8 weeks)
1. Interactive command builder
2. Context-aware suggestions
3. Learning path system
4. Integration with configlet builder

---

## Data Collection Strategy

### Immediate: Top 100 Commands
Focus on most commonly used commands across:
- Show commands (EnableMode)
- Interface configuration
- BGP configuration
- OSPF configuration

### Community Contribution
- Web form for adding command docs
- Gamification (points, badges)
- Expert review workflow
- Version control for documentation

### AI Bootstrap
```python
def enrich_command_with_ai(command_text, mode_name):
    """
    Use Claude/GPT-4 to generate documentation
    """
    prompt = f"""
    Generate documentation for this Arista EOS CLI command:

    Mode: {mode_name}
    Command: {command_text}

    Provide:
    1. Short description (one sentence)
    2. Long description (2-3 sentences)
    3. Use cases (3-5 bullet points)
    4. Parameter explanations
    5. Example configuration
    6. Common gotchas
    7. Related commands
    """

    response = claude_api.complete(prompt)
    return parse_ai_response(response)
```

---

## Success Metrics

### Usage Metrics
- Time to find relevant command (reduce by 70%)
- Commands successfully executed (increase by 50%)
- User satisfaction score (target 4.5/5)

### Educational Metrics
- Users completing learning paths
- Reduction in "what does this do?" questions
- Community contributions per month

### Business Metrics
- Reduced time to resolve network issues
- Fewer configuration errors
- Faster onboarding for new engineers

---

## Conclusion

The current CLI browser is a good **reference tool** but needs to become a **learning and troubleshooting companion**.

Key transformations needed:
1. **Add context** - Explain what, why, when, how
2. **Show workflows** - Guide users through real scenarios
3. **Provide examples** - Real-world configurations
4. **Enable discovery** - Help users find what they need
5. **Teach progressively** - Build expertise over time

**This transforms the tool from "here are 12K commands" to "here's how to solve your network problem."**
