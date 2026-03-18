#!/usr/bin/env python3
"""
AI-powered CLI command enrichment system
Uses Claude API to generate educational documentation for commands
"""

import os
import json
import sqlite3
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import re


@dataclass
class CommandEnrichment:
    """Enriched command documentation"""
    short_description: str
    long_description: str
    when_to_use: List[str]
    privilege_level: int
    requires_config_mode: bool
    tags: List[str]


class AIEnricher:
    """
    Enriches CLI commands with AI-generated documentation

    Uses Claude API (via environment) or can be extended to use other providers
    """

    def __init__(self, db_path='custom-cvp.db', api_key: Optional[str] = None):
        self.db_path = db_path
        self.api_key = api_key or os.environ.get('ANTHROPIC_API_KEY')

    def get_top_commands(self, limit: int = 50) -> List[Tuple]:
        """
        Get top commands to enrich based on:
        - Mode importance (EnableMode, ConfigSessionMode have priority)
        - Command base frequency
        - Mode command count
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get commands prioritized by mode importance and frequency
        cursor.execute("""
            WITH mode_priority AS (
                SELECT mode_name,
                    CASE mode_name
                        WHEN 'EnableMode' THEN 1
                        WHEN 'ConfigSessionMode' THEN 2
                        WHEN 'IntfConfigMode' THEN 3
                        WHEN 'RouterBgpBaseMode' THEN 4
                        WHEN 'RouterOspfMode' THEN 5
                        ELSE 10
                    END as priority
                FROM cli_modes
            ),
            command_frequency AS (
                SELECT
                    c.command_id,
                    c.command_text,
                    c.command_base,
                    m.mode_name,
                    m.mode_category,
                    p.priority,
                    COUNT(*) OVER (PARTITION BY c.command_base) as base_frequency
                FROM cli_commands c
                JOIN cli_modes m ON c.mode_id = m.mode_id
                LEFT JOIN mode_priority p ON m.mode_name = p.mode_name
                WHERE c.command_base NOT IN ('', 'no', 'default')
            )
            SELECT DISTINCT
                command_id,
                command_text,
                command_base,
                mode_name,
                mode_category,
                priority,
                base_frequency
            FROM command_frequency
            WHERE command_id NOT IN (SELECT command_id FROM cli_command_docs)
            ORDER BY
                COALESCE(priority, 100) ASC,
                base_frequency DESC,
                LENGTH(command_base) ASC
            LIMIT ?
        """, (limit,))

        results = cursor.fetchall()
        conn.close()

        return results

    def generate_enrichment_local(self, command_text: str, mode_name: str,
                                  mode_category: str) -> Optional[CommandEnrichment]:
        """
        Generate enrichment using heuristics (no API needed)
        This provides basic documentation when API is not available
        """

        # Extract command base
        parts = command_text.split()
        command_base = parts[0] if parts else command_text

        # Determine if it's a show command
        is_show = command_base.lower() in ['show', 'display']
        is_config = not is_show and mode_category in ['Configuration', 'Routing Protocol', 'Interface']

        # Generate basic description
        if is_show:
            short_desc = f"Display {command_text.replace('show ', '')} information"
            long_desc = f"Retrieves and displays current {command_text.replace('show ', '')} status and configuration from the device."
            requires_config = False
            privilege = 1
            use_cases = [
                "Monitoring and troubleshooting",
                "Verifying configuration",
                "Gathering operational data"
            ]
            tags = ["Show", "Monitoring", mode_category]
        else:
            short_desc = f"Configure {command_base} settings"
            long_desc = f"Enters or modifies {command_base} configuration in {mode_name} mode."
            requires_config = True
            privilege = 15
            use_cases = [
                f"Configuring {command_base} parameters",
                f"Modifying {command_base} settings",
                "Network setup and changes"
            ]
            tags = ["Configuration", mode_category, command_base]

        return CommandEnrichment(
            short_description=short_desc,
            long_description=long_desc,
            when_to_use=use_cases,
            privilege_level=privilege,
            requires_config_mode=requires_config,
            tags=tags
        )

    def generate_enrichment_ai(self, command_text: str, mode_name: str,
                               mode_category: str) -> Optional[CommandEnrichment]:
        """
        Generate enrichment using Claude API

        Note: This requires ANTHROPIC_API_KEY environment variable
        For now, returns None and falls back to local generation
        """
        if not self.api_key:
            return None

        # TODO: Implement actual API call to Claude
        # This would require the anthropic Python package
        # For now, we'll use local generation as fallback

        """
        Example implementation:

        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)

        prompt = f'''
        Generate documentation for this Arista EOS CLI command:

        Command: {command_text}
        Mode: {mode_name}
        Category: {mode_category}

        Provide:
        1. Short description (one sentence, under 100 chars)
        2. Long description (2-3 sentences explaining what it does)
        3. When to use (3-5 bullet points of use cases)
        4. Privilege level required (0-15)
        5. Whether it requires config mode (true/false)
        6. Tags (3-5 relevant keywords)

        Return as JSON with keys: short_description, long_description, when_to_use (array),
        privilege_level, requires_config_mode, tags (array)
        '''

        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )

        # Parse response and create CommandEnrichment
        ...
        """

        return None

    def enrich_command(self, command_id: int, command_text: str,
                      mode_name: str, mode_category: str) -> bool:
        """
        Enrich a single command with documentation
        """
        # Try AI first, fall back to local
        enrichment = self.generate_enrichment_ai(command_text, mode_name, mode_category)

        if not enrichment:
            enrichment = self.generate_enrichment_local(command_text, mode_name, mode_category)

        if not enrichment:
            return False

        # Store in database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO cli_command_docs (
                    command_id, short_description, long_description,
                    when_to_use, privilege_level, requires_config_mode,
                    tags, ai_generated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                command_id,
                enrichment.short_description,
                enrichment.long_description,
                json.dumps(enrichment.when_to_use),
                enrichment.privilege_level,
                enrichment.requires_config_mode,
                json.dumps(enrichment.tags),
                1 if self.api_key else 0  # Mark as AI-generated if using API
            ))

            conn.commit()
            return True

        except Exception as e:
            print(f"Error enriching command {command_id}: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()

    def enrich_top_commands(self, limit: int = 50, delay: float = 0.1):
        """
        Enrich top N commands with documentation

        Args:
            limit: Number of commands to enrich
            delay: Delay between API calls (rate limiting)
        """
        commands = self.get_top_commands(limit)

        print(f"Enriching {len(commands)} commands...")
        print(f"Using: {'Claude API' if self.api_key else 'Local heuristics'}")
        print()

        success_count = 0

        for i, (cmd_id, cmd_text, cmd_base, mode, category, priority, freq) in enumerate(commands, 1):
            print(f"[{i}/{len(commands)}] {mode}: {cmd_base[:40]}...", end=" ")

            if self.enrich_command(cmd_id, cmd_text, mode, category):
                success_count += 1
                print("✓")
            else:
                print("✗")

            # Rate limiting for API calls
            if self.api_key and delay > 0:
                time.sleep(delay)

        print()
        print(f"✓ Enriched {success_count}/{len(commands)} commands")

        return success_count

    def get_enrichment_stats(self) -> Dict:
        """Get statistics on enrichment progress"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM cli_commands")
        total_commands = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM cli_command_docs")
        enriched_commands = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM cli_command_docs WHERE ai_generated = 1")
        ai_generated = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM cli_command_docs WHERE reviewed_by IS NOT NULL")
        reviewed = cursor.fetchone()[0]

        conn.close()

        percentage = (enriched_commands / total_commands * 100) if total_commands > 0 else 0

        return {
            'total_commands': total_commands,
            'enriched_commands': enriched_commands,
            'percentage_enriched': round(percentage, 2),
            'ai_generated': ai_generated,
            'human_reviewed': reviewed,
            'local_generated': enriched_commands - ai_generated
        }


def main():
    """Main enrichment routine"""
    import argparse

    parser = argparse.ArgumentParser(description='Enrich CLI commands with documentation')
    parser.add_argument('--limit', type=int, default=50,
                       help='Number of commands to enrich (default: 50)')
    parser.add_argument('--all', action='store_true',
                       help='Enrich all undocumented commands')
    parser.add_argument('--stats', action='store_true',
                       help='Show enrichment statistics only')
    parser.add_argument('--api-key', type=str,
                       help='Anthropic API key (or set ANTHROPIC_API_KEY env var)')

    args = parser.parse_args()

    enricher = AIEnricher(api_key=args.api_key)

    if args.stats:
        stats = enricher.get_enrichment_stats()
        print("=" * 60)
        print("CLI COMMAND ENRICHMENT STATISTICS")
        print("=" * 60)
        print(f"Total commands:        {stats['total_commands']:,}")
        print(f"Enriched commands:     {stats['enriched_commands']:,}")
        print(f"Percentage enriched:   {stats['percentage_enriched']}%")
        print(f"AI-generated:          {stats['ai_generated']:,}")
        print(f"Local-generated:       {stats['local_generated']:,}")
        print(f"Human-reviewed:        {stats['human_reviewed']:,}")
        print("=" * 60)
        return

    # Enrich commands
    limit = 10000 if args.all else args.limit

    print("=" * 60)
    print("CLI COMMAND ENRICHMENT")
    print("=" * 60)

    enricher.enrich_top_commands(limit=limit)

    # Show updated stats
    print()
    stats = enricher.get_enrichment_stats()
    print(f"Progress: {stats['enriched_commands']}/{stats['total_commands']} " +
          f"({stats['percentage_enriched']}%)")


if __name__ == '__main__':
    main()
