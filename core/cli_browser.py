#!/usr/bin/env python3
"""
CLI Browser Manager - Database operations for CLI command browser
Follows existing manager pattern (InventoryManager, ConfigletManager)
"""

import sqlite3
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass
class CLIMode:
    """Represents a CLI mode"""
    mode_id: int
    mode_name: str
    mode_category: str
    parent_mode_id: Optional[int]
    description: str
    
    def to_dict(self):
        return asdict(self)


@dataclass
class CLICommand:
    """Represents a CLI command"""
    command_id: int
    mode_id: int
    mode_name: str
    command_text: str
    command_base: str
    has_no_prefix: bool
    has_default_prefix: bool
    line_number: int
    
    def to_dict(self):
        return asdict(self)


@dataclass
class CLIToken:
    """Represents a command token"""
    token_id: int
    command_id: int
    position: int
    token_type: str
    token_value: str
    is_optional: bool
    parent_token_id: Optional[int]
    
    def to_dict(self):
        return asdict(self)


class CLIBrowserManager:
    """Manager for CLI browser database operations"""
    
    def __init__(self, db_path='custom-cvp.db'):
        self.db_path = db_path
    
    def get_modes(self, category: Optional[str] = None) -> List[CLIMode]:
        """Get all modes, optionally filtered by category"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if category:
            cursor.execute('''
                SELECT * FROM cli_modes 
                WHERE mode_category = ?
                ORDER BY mode_name
            ''', (category,))
        else:
            cursor.execute('SELECT * FROM cli_modes ORDER BY mode_name')
        
        modes = [CLIMode(**dict(row)) for row in cursor.fetchall()]
        conn.close()
        return modes
    
    def get_mode_categories(self) -> Dict[str, List[CLIMode]]:
        """Get modes grouped by category"""
        modes = self.get_modes()
        categories = {}
        
        for mode in modes:
            category = mode.mode_category
            if category not in categories:
                categories[category] = []
            categories[category].append(mode)
        
        return categories
    
    def get_mode_by_name(self, mode_name: str) -> Optional[CLIMode]:
        """Get a specific mode by name"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM cli_modes WHERE mode_name = ?', (mode_name,))
        row = cursor.fetchone()
        conn.close()
        
        return CLIMode(**dict(row)) if row else None
    
    def get_commands_by_mode(self, mode_name: str, limit: int = 100) -> List[CLICommand]:
        """Get commands for a specific mode"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT c.*, m.mode_name
            FROM cli_commands c
            JOIN cli_modes m ON c.mode_id = m.mode_id
            WHERE m.mode_name = ?
            ORDER BY c.command_base, c.command_text
            LIMIT ?
        ''', (mode_name, limit))
        
        commands = [CLICommand(**dict(row)) for row in cursor.fetchall()]
        conn.close()
        return commands
    
    def get_command_by_id(self, command_id: int) -> Optional[CLICommand]:
        """Get a specific command by ID"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT c.*, m.mode_name
            FROM cli_commands c
            JOIN cli_modes m ON c.mode_id = m.mode_id
            WHERE c.command_id = ?
        ''', (command_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        return CLICommand(**dict(row)) if row else None
    
    def get_command_tokens(self, command_id: int) -> List[CLIToken]:
        """Get all tokens for a command"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM cli_command_tokens
            WHERE command_id = ?
            ORDER BY position
        ''', (command_id,))
        
        tokens = [CLIToken(**dict(row)) for row in cursor.fetchall()]
        conn.close()
        return tokens
    
    def search_commands(self, query: str, limit: int = 50) -> List[CLICommand]:
        """Search commands by text (case-insensitive)"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Search in command text and command base
        search_pattern = f'%{query}%'
        cursor.execute('''
            SELECT c.*, m.mode_name
            FROM cli_commands c
            JOIN cli_modes m ON c.mode_id = m.mode_id
            WHERE c.command_text LIKE ? OR c.command_base LIKE ?
            ORDER BY
                CASE
                    WHEN c.command_base LIKE ? THEN 1
                    ELSE 2
                END,
                c.command_base, c.command_text
            LIMIT ?
        ''', (search_pattern, search_pattern, f'{query}%', limit))

        commands = [CLICommand(**dict(row)) for row in cursor.fetchall()]
        conn.close()
        return commands

    def semantic_search(self, query: str, limit: int = 50) -> List[Dict]:
        """
        Semantic search across all commands (not restricted by technology/category)
        Searches command text, base, and uses keyword matching for better results
        Returns enriched results with relevance scoring
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Parse query into keywords
        query_lower = query.lower()
        keywords = query_lower.split()

        # Build search conditions for each keyword
        # Use multiple search patterns for better matching
        search_patterns = []
        params = []

        # Exact phrase match (highest priority)
        search_patterns.append('(c.command_text LIKE ? OR c.command_base LIKE ?)')
        params.extend([f'%{query_lower}%', f'%{query_lower}%'])

        # Individual keyword matches
        for keyword in keywords:
            if len(keyword) > 2:  # Skip very short keywords
                search_patterns.append('(c.command_text LIKE ? OR c.command_base LIKE ?)')
                params.extend([f'%{keyword}%', f'%{keyword}%'])

        where_clause = ' OR '.join(search_patterns)

        # Query with deduplication and relevance scoring
        cursor.execute(f'''
            SELECT DISTINCT
                c.command_text,
                c.command_base,
                m.mode_name,
                m.mode_category,
                c.command_id,
                c.has_no_prefix,
                c.has_default_prefix,
                CASE
                    -- Exact match in base command (highest score)
                    WHEN LOWER(c.command_base) = ? THEN 100
                    -- Starts with query
                    WHEN LOWER(c.command_base) LIKE ? THEN 90
                    WHEN LOWER(c.command_text) LIKE ? THEN 85
                    -- Contains exact phrase
                    WHEN LOWER(c.command_text) LIKE ? THEN 75
                    -- Contains all keywords
                    WHEN {' AND '.join([f'LOWER(c.command_text) LIKE ?' for _ in keywords if len(_) > 2])} THEN 60
                    -- Contains some keywords
                    ELSE 40
                END as relevance_score
            FROM cli_commands c
            JOIN cli_modes m ON c.mode_id = m.mode_id
            WHERE {where_clause}
            GROUP BY c.command_text
            ORDER BY relevance_score DESC, c.command_base, c.command_text
            LIMIT ?
        ''', (
            query_lower,
            f'{query_lower}%',
            f'{query_lower}%',
            f'%{query_lower}%',
            *[f'%{k}%' for k in keywords if len(k) > 2],
            *params,
            limit
        ))

        results = []
        seen_commands = set()

        for row in cursor.fetchall():
            # Create unique key to prevent duplicates
            unique_key = f"{row['command_text']}|{row['mode_name']}"
            if unique_key in seen_commands:
                continue
            seen_commands.add(unique_key)

            # Build result dictionary
            result = {
                'command_text': row['command_text'],
                'command_base': row['command_base'],
                'mode_name': row['mode_name'],
                'mode_category': row['mode_category'],
                'command_id': row['command_id'],
                'has_no_prefix': bool(row['has_no_prefix']),
                'has_default_prefix': bool(row['has_default_prefix']),
                'relevance_score': row['relevance_score'],
                'matched_keywords': [k for k in keywords if k in row['command_text'].lower()]
            }

            results.append(result)

        conn.close()
        return results
    
    def get_statistics(self) -> Dict[str, int]:
        """Get browser statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM cli_modes')
        mode_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM cli_commands')
        command_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM cli_command_tokens')
        token_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(DISTINCT mode_category) FROM cli_modes')
        category_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM cli_command_cache')
        cache_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM cli_explanations')
        explanation_count = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'modes': mode_count,
            'commands': command_count,
            'tokens': token_count,
            'categories': category_count,
            'cache_entries': cache_count,
            'explanations': explanation_count
        }
    
    def get_commands_by_base(self, command_base: str, mode_name: Optional[str] = None, limit: int = 50) -> List[CLICommand]:
        """Get commands by base command, optionally filtered by mode"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        if mode_name:
            cursor.execute('''
                SELECT c.*, m.mode_name
                FROM cli_commands c
                JOIN cli_modes m ON c.mode_id = m.mode_id
                WHERE c.command_base = ? AND m.mode_name = ?
                ORDER BY c.command_text
                LIMIT ?
            ''', (command_base, mode_name, limit))
        else:
            cursor.execute('''
                SELECT c.*, m.mode_name
                FROM cli_commands c
                JOIN cli_modes m ON c.mode_id = m.mode_id
                WHERE c.command_base = ?
                ORDER BY m.mode_name, c.command_text
                LIMIT ?
            ''', (command_base, limit))
        
        commands = [CLICommand(**dict(row)) for row in cursor.fetchall()]
        conn.close()
        return commands


if __name__ == '__main__':
    # Test the manager
    manager = CLIBrowserManager()
    
    stats = manager.get_statistics()
    print("CLI Browser Statistics:")
    print(f"  Modes: {stats['modes']}")
    print(f"  Commands: {stats['commands']}")
    print(f"  Tokens: {stats['tokens']}")
    print(f"  Categories: {stats['categories']}")
    print(f"  Cache entries: {stats['cache_entries']}")
    print(f"  Explanations: {stats['explanations']}")
    
    # Test category grouping
    categories = manager.get_mode_categories()
    print(f"\nMode categories: {list(categories.keys())}")
    
    # Test search
    results = manager.search_commands('interface', limit=5)
    print(f"\nSearch 'interface' found {len(results)} results")
    for cmd in results[:3]:
        print(f"  {cmd.mode_name}: {cmd.command_text[:60]}...")
