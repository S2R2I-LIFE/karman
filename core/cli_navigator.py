#!/usr/bin/env python3
"""
CLI Navigator - Progressive disclosure algorithm for command building
Core UX feature that shows only valid next tokens based on current command state
"""

import sqlite3
import json
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict


@dataclass
class NextToken:
    """Represents a possible next token in command construction"""
    token_type: str  # keyword, variable, optional, choice, group
    token_value: str
    is_optional: bool
    choices: List[str]  # For choice tokens
    description: str  # Helpful hint
    
    def to_dict(self):
        return asdict(self)


class CLINavigator:
    """Progressive disclosure navigator for CLI commands"""
    
    def __init__(self, db_path='custom-cvp.db'):
        self.db_path = db_path
        self.cache = {}  # Simple in-memory cache
    
    def get_next_tokens(self, mode_name: str, current_tokens: List[str]) -> List[NextToken]:
        """Get valid next tokens based on current command state
        
        This is the core progressive disclosure algorithm:
        1. Find all commands in mode matching current prefix
        2. Extract token at next position from each matching command
        3. Deduplicate and categorize tokens
        4. Return with metadata
        """
        
        # Create cache key
        cache_key = f"{mode_name}::{':'.join(current_tokens)}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get mode_id
        cursor.execute('SELECT mode_id FROM cli_modes WHERE mode_name = ?', (mode_name,))
        mode_row = cursor.fetchone()
        if not mode_row:
            conn.close()
            return []
        
        mode_id = mode_row[0]
        
        # If no tokens yet, return all first tokens for this mode
        if not current_tokens:
            next_tokens = self._get_first_tokens(cursor, mode_id)
            conn.close()
            self.cache[cache_key] = next_tokens
            return next_tokens
        
        # OPTIMIZED APPROACH: Instead of checking all commands,
        # directly query for tokens at the next position
        next_position = len(current_tokens)
        
        # Build a query to find commands that could match
        # We'll use a simpler, more permissive matching strategy
        cursor.execute('''
            SELECT DISTINCT t.token_type, t.token_value, t.is_optional
            FROM cli_command_tokens t
            JOIN cli_commands c ON t.command_id = c.command_id
            WHERE c.mode_id = ? AND t.position = ?
        ''', (mode_id, next_position))
        
        tokens_dict = {}
        for row in cursor.fetchall():
            token_type, token_value, is_optional = row
            token_key = f"{token_type}:{token_value}"
            
            if token_key not in tokens_dict:
                tokens_dict[token_key] = NextToken(
                    token_type=token_type,
                    token_value=token_value,
                    is_optional=is_optional,
                    choices=self._parse_choices(token_value) if token_type == 'choice' else [],
                    description=self._generate_description(token_type, token_value)
                )
        
        next_tokens = list(tokens_dict.values())
        conn.close()
        
        # Cache result
        self.cache[cache_key] = next_tokens
        return next_tokens
    
    def _get_first_tokens(self, cursor, mode_id: int) -> List[NextToken]:
        """Get all possible first tokens for a mode"""
        
        cursor.execute('''
            SELECT DISTINCT t.token_type, t.token_value, t.is_optional
            FROM cli_command_tokens t
            JOIN cli_commands c ON t.command_id = c.command_id
            WHERE c.mode_id = ? AND t.position = 0
            ORDER BY t.token_value
        ''', (mode_id,))
        
        tokens = []
        seen = set()
        
        for row in cursor.fetchall():
            token_type, token_value, is_optional = row
            
            # Deduplicate
            key = f"{token_type}:{token_value}"
            if key in seen:
                continue
            seen.add(key)
            
            tokens.append(NextToken(
                token_type=token_type,
                token_value=token_value,
                is_optional=is_optional,
                choices=self._parse_choices(token_value) if token_type == 'choice' else [],
                description=self._generate_description(token_type, token_value)
            ))
        
        return tokens
    
    def _find_matching_commands(self, cursor, mode_id: int, current_tokens: List[str]) -> List[int]:
        """Find commands that match current token sequence"""
        
        # Get all commands for this mode
        cursor.execute('''
            SELECT command_id FROM cli_commands 
            WHERE mode_id = ?
        ''', (mode_id,))
        
        command_ids = [row[0] for row in cursor.fetchall()]
        matching = []
        
        for command_id in command_ids:
            if self._command_matches_tokens(cursor, command_id, current_tokens):
                matching.append(command_id)
        
        return matching
    
    def _command_matches_tokens(self, cursor, command_id: int, tokens: List[str]) -> bool:
        """Check if command's tokens match the current token sequence"""
        
        cursor.execute('''
            SELECT token_type, token_value, is_optional
            FROM cli_command_tokens
            WHERE command_id = ?
            ORDER BY position
        ''', (command_id,))
        
        command_tokens = cursor.fetchall()
        
        # Simple matching: compare tokens position by position
        # TODO: Handle optional tokens better
        for i, user_token in enumerate(tokens):
            if i >= len(command_tokens):
                return False
            
            token_type, token_value, is_optional = command_tokens[i]
            
            # For keywords, must match exactly (case-insensitive)
            if token_type == 'keyword':
                if user_token.lower() != token_value.lower():
                    return False
            # For variables, any value matches
            elif token_type == 'variable':
                continue
            # For choices, must be one of the choices
            elif token_type == 'choice':
                choices = self._parse_choices(token_value)
                if user_token not in choices:
                    return False
            # For optional/group, more complex matching needed
            # For now, accept any value
            
        return True
    
    def _extract_next_tokens(self, cursor, command_ids: List[int], position: int) -> List[NextToken]:
        """Extract tokens at given position from matching commands"""
        
        tokens_dict = {}  # token_key -> NextToken
        
        for command_id in command_ids:
            cursor.execute('''
                SELECT token_type, token_value, is_optional
                FROM cli_command_tokens
                WHERE command_id = ? AND position = ?
            ''', (command_id, position))
            
            row = cursor.fetchone()
            if not row:
                continue
            
            token_type, token_value, is_optional = row
            
            # Create unique key
            token_key = f"{token_type}:{token_value}"
            
            if token_key not in tokens_dict:
                tokens_dict[token_key] = NextToken(
                    token_type=token_type,
                    token_value=token_value,
                    is_optional=is_optional,
                    choices=self._parse_choices(token_value) if token_type == 'choice' else [],
                    description=self._generate_description(token_type, token_value)
                )
        
        return list(tokens_dict.values())
    
    def _parse_choices(self, token_value: str) -> List[str]:
        """Parse choice token value to extract individual choices"""
        # Simple split by |
        return [c.strip() for c in token_value.split('|')]
    
    def _generate_description(self, token_type: str, token_value: str) -> str:
        """Generate helpful description for token"""
        if token_type == 'keyword':
            return f"Keyword: {token_value}"
        elif token_type == 'variable':
            return f"Parameter: {token_value}"
        elif token_type == 'choice':
            choices = self._parse_choices(token_value)
            return f"Choose one: {', '.join(choices)}"
        elif token_type == 'optional':
            return f"Optional: {token_value}"
        elif token_type == 'group':
            return f"Group: {token_value}"
        else:
            return token_value
    
    def validate_command(self, mode_name: str, tokens: List[str]) -> Tuple[bool, Optional[str]]:
        """Validate if token sequence forms a valid command
        
        Returns: (is_valid, error_message)
        """
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get mode_id
        cursor.execute('SELECT mode_id FROM cli_modes WHERE mode_name = ?', (mode_name,))
        mode_row = cursor.fetchone()
        if not mode_row:
            conn.close()
            return False, f"Mode '{mode_name}' not found"
        
        mode_id = mode_row[0]
        
        # Find matching commands
        matching = self._find_matching_commands(cursor, mode_id, tokens)
        conn.close()
        
        if not matching:
            return False, "No matching command found"
        
        # Check if any matching command has the exact token count
        # (i.e., command is complete)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for command_id in matching:
            cursor.execute('''
                SELECT COUNT(*) FROM cli_command_tokens
                WHERE command_id = ?
            ''', (command_id,))
            
            token_count = cursor.fetchone()[0]
            if token_count == len(tokens):
                conn.close()
                return True, None
        
        conn.close()
        return False, "Command incomplete"
    
    def get_command_matches(self, mode_name: str, tokens: List[str]) -> List[Dict]:
        """Get all commands matching current token sequence"""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get mode_id
        cursor.execute('SELECT mode_id FROM cli_modes WHERE mode_name = ?', (mode_name,))
        mode_row = cursor.fetchone()
        if not mode_row:
            conn.close()
            return []
        
        mode_id = mode_row[0]
        
        # Find matching commands
        matching_ids = self._find_matching_commands(cursor, mode_id, tokens)
        
        # Get command details
        results = []
        for command_id in matching_ids:
            cursor.execute('''
                SELECT command_id, command_text, command_base
                FROM cli_commands
                WHERE command_id = ?
            ''', (command_id,))
            
            row = cursor.fetchone()
            if row:
                results.append({
                    'command_id': row[0],
                    'command_text': row[1],
                    'command_base': row[2]
                })
        
        conn.close()
        return results
    
    def get_completions(self, mode_name: str, partial_command: str) -> List[str]:
        """Get autocomplete suggestions for partial command"""
        
        # Split partial command into tokens
        tokens = partial_command.strip().split()
        
        if not tokens:
            return []
        
        # Get next possible tokens
        next_tokens = self.get_next_tokens(mode_name, tokens[:-1])
        
        # Filter by last partial token
        partial = tokens[-1].lower()
        completions = []
        
        for token in next_tokens:
            if token.token_type == 'keyword':
                if token.token_value.lower().startswith(partial):
                    completions.append(token.token_value)
            elif token.token_type == 'choice':
                for choice in token.choices:
                    if choice.lower().startswith(partial):
                        completions.append(choice)
        
        return sorted(completions)


if __name__ == '__main__':
    # Test the navigator
    navigator = CLINavigator()
    
    # Test 1: Get first tokens for ConfigSessionMode
    print("Test 1: First tokens for ConfigSessionMode")
    mode = "ConfigSessionMode"
    first_tokens = navigator.get_next_tokens(mode, [])
    print(f"  Found {len(first_tokens)} first tokens")
    for token in first_tokens[:5]:
        print(f"    {token.token_type}: {token.token_value}")
    
    # Test 2: Progressive disclosure - "interface"
    print("\nTest 2: Next tokens after 'interface'")
    next_tokens = navigator.get_next_tokens(mode, ["interface"])
    print(f"  Found {len(next_tokens)} next tokens")
    for token in next_tokens[:5]:
        print(f"    {token.token_type}: {token.token_value}")
    
    # Test 3: Validate command
    print("\nTest 3: Validate 'interface Ethernet1'")
    valid, msg = navigator.validate_command(mode, ["interface", "Ethernet1"])
    print(f"  Valid: {valid}, Message: {msg}")
    
    # Test 4: Get matching commands
    print("\nTest 4: Get matches for 'interface'")
    matches = navigator.get_command_matches(mode, ["interface"])
    print(f"  Found {len(matches)} matching commands")
    for match in matches[:3]:
        print(f"    {match['command_text'][:60]}...")
