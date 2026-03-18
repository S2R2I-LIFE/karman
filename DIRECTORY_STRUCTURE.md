# Custom CVP - Production Directory Structure

## Root Directory
```
custom-cvp/
├── README.md                          # Main documentation
├── README-DOCKER.md                   # Docker deployment guide
├── QUICK_START.md                     # Quick start guide
├── DEPLOYMENT_NOTES.md                # Deployment notes
├── DOCKER_DEPLOYMENT.md               # Docker deployment details
├── WEB_INTERFACE.md                   # Web interface documentation
├── EXAMPLES.md                        # Usage examples
├── BUILDER_QUICK_START.md             # Config builder guide
├── CVP_CONFIGLETS.md                  # CVP integration guide
├── docker-compose.yml                 # Docker Compose configuration
├── Dockerfile                         # Docker image definition
├── docker-entrypoint.sh               # Container startup script
├── requirements.txt                   # Python dependencies
├── .dockerignore                      # Docker build ignore patterns
├── .gitignore                         # Git ignore patterns
│
├── builder.py                         # Configuration builder
├── validator.py                       # Configuration validator
├── import_cvp_configlets.py          # CVP configlet importer
├── init_default_user.py              # Default user initialization
│
├── cli/                               # CLI tools
│   └── orchestrator_cli.py
│
├── config/                            # Configuration files
│   └── cvp_connection.yaml.example
│
├── configlets/                        # Configlet storage
│
├── connectors/                        # Device connectors
│   ├── __init__.py
│   ├── eapi_connector.py             # Arista eAPI connector
│   ├── netmiko_connector.py          # SSH connector
│   ├── cvp_connector.py              # CVP connector
│   └── gnmi_connector.py             # gNMI connector
│
├── core/                              # Core application modules
│   ├── __init__.py
│   ├── inventory.py                  # Device inventory management
│   ├── configlet.py                  # Configlet management
│   ├── task.py                       # Task management
│   ├── cli_browser.py                # CLI command browser
│   ├── cli_navigator.py              # CLI navigation
│   ├── cli_parser.py                 # CLI parsing
│   ├── user.py                       # User management
│   ├── notification.py               # Notifications
│   └── ai_enrichment.py              # AI features
│
├── data/                              # Persistent data (mounted volume)
│   └── custom-cvp.db                 # SQLite database
│
├── database/                          # Database utilities
│
├── docs/                              # Documentation
│   └── archive/                      # Archived development docs
│
├── logs/                              # Application logs (mounted volume)
│
├── migrations/                        # Database migrations
│   ├── add_cli_browser.py
│   └── add_user_auth.py
│
├── output/                            # Generated output (mounted volume)
│   └── generated-configs/
│
├── prototypes/                        # Prototype implementations
│
├── scheduler/                         # Task scheduler
│
├── schemas/                           # Data schemas
│
├── screenshots/                       # Application screenshots
│
├── scripts/                           # Utility scripts
│   ├── deployment/                   # Deployment scripts
│   │   ├── deploy.sh
│   │   ├── start_web.sh
│   │   ├── start_web_production.sh
│   │   └── verify_setup.sh
│   └── development/                  # Development/testing scripts
│       ├── test_*.py
│       ├── debug_*.py
│       └── ...
│
├── templates/                         # Jinja2 configuration templates
│   ├── base/
│   ├── layer2/
│   ├── layer3/
│   └── overlays/
│
├── tests/                             # Unit tests
│
├── variables/                         # Device variables
│   ├── device-vars/
│   └── global-vars/
│
└── web/                               # Web application
    ├── app.py                        # Flask application
    ├── auth_decorators.py            # Authentication decorators
    ├── email_sender.py               # Email functionality
    │
    ├── static/                       # Static assets
    │   ├── css/
    │   │   ├── style.css            # Main stylesheet (with dark mode)
    │   │   └── cli-browser.css
    │   ├── js/
    │   │   ├── cli-browser.js
    │   │   └── hybrid_navigation.js
    │   └── docs/
    │       └── index.html
    │
    └── templates/                    # HTML templates
        ├── base.html                 # Base template (with theme support)
        ├── login.html
        ├── register.html
        ├── dashboard.html
        ├── settings.html             # NEW: Settings page
        ├── devices.html
        ├── device_detail.html
        ├── device_add.html
        ├── device_assign_configlet.html  # NEW
        ├── device_connect.html       # NEW
        ├── configlets.html
        ├── configlet_detail.html
        ├── configlet_create.html
        ├── configlet_edit.html
        ├── builder.html
        ├── builder_result.html
        ├── tasks.html
        ├── task_detail.html
        ├── task_create.html
        ├── cli_browser.html
        ├── cli_browser_hybrid.html
        └── admin/
            └── access_requests.html
```

## Key Changes from Development

### Removed
- ❌ Old database backups (*.db.backup_*)
- ❌ Corrupted root database file
- ❌ Python cache (__pycache__)
- ❌ Development documentation (moved to docs/archive/)
- ❌ Test scripts (moved to scripts/development/)
- ❌ Generated config samples
- ❌ Large text dumps (showcli.txt)

### Organized
- ✅ Development scripts → scripts/development/
- ✅ Deployment scripts → scripts/deployment/
- ✅ Development docs → docs/archive/
- ✅ Added .dockerignore and .gitignore

### Production Ready
- ✅ Clean root directory
- ✅ Only essential documentation
- ✅ Proper .dockerignore for efficient builds
- ✅ All application code intact
- ✅ All new features implemented
- ✅ Database in correct location (/app/data/)

## Mounted Volumes in Docker

These directories are mounted from the host:
- `./data` → `/app/data` (database persistence)
- `./output` → `/app/output` (generated configs)
- `./logs` → `/app/logs` (application logs)
- `./templates` → `/app/templates:ro` (read-only template access)
- `./variables` → `/app/variables:ro` (read-only variable access)
