-- Migration: Add technology and action tags to commands
-- Purpose: Support hybrid navigation with technology-based browsing

-- Add technology_tags column (JSON array of technologies)
ALTER TABLE cli_commands ADD COLUMN technology_tags TEXT;

-- Add action_tags column (JSON array of actions)
ALTER TABLE cli_commands ADD COLUMN action_tags TEXT;

-- Create index for faster technology-based queries
CREATE INDEX IF NOT EXISTS idx_cli_commands_technology_tags ON cli_commands(technology_tags);
CREATE INDEX IF NOT EXISTS idx_cli_commands_action_tags ON cli_commands(action_tags);

-- Add comments
PRAGMA table_info(cli_commands);
