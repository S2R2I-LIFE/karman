-- Custom configlet groups

CREATE TABLE IF NOT EXISTS configlet_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    color TEXT DEFAULT 'primary',
    icon TEXT DEFAULT 'bi-folder',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS configlet_group_assignments (
    configlet_name TEXT NOT NULL,
    group_id INTEGER NOT NULL,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (configlet_name, group_id),
    FOREIGN KEY (configlet_name) REFERENCES configlets(name) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES configlet_groups(id) ON DELETE CASCADE
);
