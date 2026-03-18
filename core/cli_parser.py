#!/usr/bin/env python3
"""
CLI Parser - Parse Arista showcli.txt into structured database
Handles complex command syntax with nested brackets, choices, and variables
"""

import re
import sqlite3
import hashlib
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ParsedCommand:
    """Represents a parsed CLI command"""
    mode: str
    command_text: str
    command_base: str
    has_no_prefix: bool
    has_default_prefix: bool
    line_number: int
    syntax_hash: str
    tokens: List['Token']


@dataclass
class Token:
    """Represents a token in a command"""
    position: int
    token_type: str  # keyword, variable, optional, choice, group
    token_value: str
    is_optional: bool
    choices: List[str]
    parent_id: Optional[int] = None


class TokenParser:
    """Recursive descent parser for CLI command syntax"""
    
    def __init__(self, command_text: str):
        self.text = command_text
        self.pos = 0
        self.tokens = []
        self.current_position = 0
    
    def parse(self) -> List[Token]:
        """Parse command into tokens"""
        self.tokens = []
        self.pos = 0
        self.current_position = 0
        
        while self.pos < len(self.text):
            self._parse_token()
        
        return self.tokens
    
    def _current_char(self) -> str:
        """Get current character"""
        if self.pos < len(self.text):
            return self.text[self.pos]
        return ''
    
    def _peek_char(self, offset=1) -> str:
        """Peek ahead at character"""
        if self.pos + offset < len(self.text):
            return self.text[self.pos + offset]
        return ''
    
    def _skip_whitespace(self):
        """Skip whitespace"""
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1
    
    def _parse_token(self):
        """Parse next token"""
        self._skip_whitespace()
        
        if self.pos >= len(self.text):
            return
        
        char = self._current_char()
        
        if char == '[':
            self._parse_optional()
        elif char == '(':
            self._parse_choice()
        elif char == '{':
            self._parse_group()
        else:
            self._parse_word()
    
    def _parse_optional(self):
        """Parse optional section: [...]"""
        self.pos += 1  # Skip '['
        start_pos = self.pos
        depth = 1
        
        # Find matching bracket
        while self.pos < len(self.text) and depth > 0:
            if self.text[self.pos] == '[':
                depth += 1
            elif self.text[self.pos] == ']':
                depth -= 1
            self.pos += 1
        
        content = self.text[start_pos:self.pos-1].strip()
        
        # Check for [no|default] prefix pattern
        if content.startswith('no|default'):
            # This is a prefix, not a regular optional
            token = Token(
                position=self.current_position,
                token_type='prefix',
                token_value='[no|default]',
                is_optional=True,
                choices=['no', 'default']
            )
            self.tokens.append(token)
            self.current_position += 1
        else:
            # Regular optional - parse content
            token = Token(
                position=self.current_position,
                token_type='optional',
                token_value=content,
                is_optional=True,
                choices=[]
            )
            self.tokens.append(token)
            self.current_position += 1
    
    def _parse_choice(self):
        """Parse choice section: (A|B|C)"""
        self.pos += 1  # Skip '('
        start_pos = self.pos
        depth = 1
        
        # Find matching paren
        while self.pos < len(self.text) and depth > 0:
            if self.text[self.pos] == '(':
                depth += 1
            elif self.text[self.pos] == ')':
                depth -= 1
            self.pos += 1
        
        content = self.text[start_pos:self.pos-1].strip()
        
        # Split by | to get choices
        choices = [c.strip() for c in content.split('|')]
        
        token = Token(
            position=self.current_position,
            token_type='choice',
            token_value=content,
            is_optional=False,
            choices=choices
        )
        self.tokens.append(token)
        self.current_position += 1
    
    def _parse_group(self):
        """Parse group section: {...}"""
        self.pos += 1  # Skip '{'
        start_pos = self.pos
        depth = 1
        
        # Find matching brace
        while self.pos < len(self.text) and depth > 0:
            if self.text[self.pos] == '{':
                depth += 1
            elif self.text[self.pos] == '}':
                depth -= 1
            self.pos += 1
        
        content = self.text[start_pos:self.pos-1].strip()
        
        token = Token(
            position=self.current_position,
            token_type='group',
            token_value=content,
            is_optional=False,
            choices=[]
        )
        self.tokens.append(token)
        self.current_position += 1
    
    def _parse_word(self):
        """Parse a word (keyword or variable)"""
        start_pos = self.pos
        
        # Read until whitespace or special char
        while (self.pos < len(self.text) and 
               not self.text[self.pos].isspace() and
               self.text[self.pos] not in '[](){}'):
            self.pos += 1
        
        word = self.text[start_pos:self.pos]
        
        if not word:
            return
        
        # Classify: UPPERCASE = variable, lowercase = keyword
        if word.isupper() or '_' in word:
            token_type = 'variable'
        else:
            token_type = 'keyword'
        
        token = Token(
            position=self.current_position,
            token_type=token_type,
            token_value=word,
            is_optional=False,
            choices=[]
        )
        self.tokens.append(token)
        self.current_position += 1


class CLIParser:
    """Main CLI parser - parses showcli.txt and populates database"""
    
    def __init__(self, db_path='custom-cvp.db'):
        self.db_path = db_path
        self.modes = {}  # mode_name -> mode_id
        self.mode_categories = {}  # Auto-detect categories
        
    def parse_file(self, showcli_path: str) -> Dict:
        """Parse entire showcli.txt file"""
        
        print(f"[PARSER] Reading {showcli_path}...")
        
        with open(showcli_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        print(f"[PARSER] Found {len(lines)} lines")
        
        # Phase 1: Extract all modes
        print("[PARSER] Phase 1: Extracting modes...")
        for line_num, line in enumerate(lines, 1):
            mode = self._extract_mode(line)
            if mode and mode not in self.modes:
                category = self._categorize_mode(mode)
                self.modes[mode] = {
                    'id': None,
                    'category': category,
                    'parent': None
                }
        
        print(f"[PARSER] Found {len(self.modes)} unique modes")
        
        # Phase 2: Parse all commands
        print("[PARSER] Phase 2: Parsing commands...")
        commands = []
        
        for line_num, line in enumerate(lines, 1):
            parsed = self.parse_line(line, line_num)
            if parsed:
                commands.append(parsed)
        
        print(f"[PARSER] Parsed {len(commands)} commands")
        
        return {
            'modes': self.modes,
            'commands': commands,
            'total_lines': len(lines)
        }
    
    def parse_line(self, line: str, line_number: int) -> Optional[ParsedCommand]:
        """Parse a single line from showcli.txt
        
        Format: <MODE>: <COMMAND_SYNTAX>
        Example: ConfigSessionMode: interface Ethernet INTERFACE_ID
        """
        
        line = line.strip()
        if not line or not ':' in line:
            return None
        
        # Split on first colon
        parts = line.split(':', 1)
        if len(parts) != 2:
            return None
        
        mode = parts[0].strip()
        command = parts[1].strip()
        
        if not mode or not command:
            return None
        
        # Check for [no|default] prefix
        has_no_prefix = command.startswith('[no|default]')
        has_default_prefix = has_no_prefix
        
        # Extract command base (first few keywords)
        command_base = self._extract_command_base(command)
        
        # Calculate syntax hash for deduplication
        syntax_hash = self._calculate_syntax_hash(command)
        
        # Parse tokens
        token_parser = TokenParser(command)
        tokens = token_parser.parse()
        
        return ParsedCommand(
            mode=mode,
            command_text=command,
            command_base=command_base,
            has_no_prefix=has_no_prefix,
            has_default_prefix=has_default_prefix,
            line_number=line_number,
            syntax_hash=syntax_hash,
            tokens=tokens
        )
    
    def _extract_mode(self, line: str) -> Optional[str]:
        """Extract mode name from line"""
        if ':' not in line:
            return None
        
        mode = line.split(':', 1)[0].strip()
        
        # Accept any non-empty mode name
        # (Some modes like 'MssDevice' don't follow typical naming conventions)
        if mode and len(mode) > 0:
            return mode
        
        return None
    
    def _categorize_mode(self, mode_name: str) -> str:
        """Auto-categorize mode based on name"""
        
        if 'Config' in mode_name and not any(x in mode_name for x in ['Bgp', 'Ospf', 'Router']):
            return 'Configuration'
        elif 'Router' in mode_name or 'Bgp' in mode_name:
            return 'Routing Protocol (BGP)'
        elif 'Ospf' in mode_name:
            return 'Routing Protocol (OSPF)'
        elif 'Interface' in mode_name or 'Ethernet' in mode_name:
            return 'Interface Configuration'
        elif 'Vlan' in mode_name:
            return 'VLAN Configuration'
        elif 'Enable' in mode_name:
            return 'Privileged EXEC'
        elif 'Mlag' in mode_name:
            return 'MLAG Configuration'
        elif 'Qos' in mode_name:
            return 'QoS Configuration'
        elif 'Aaa' in mode_name or 'Radius' in mode_name or 'Tacacs' in mode_name:
            return 'AAA & Authentication'
        elif 'Monitor' in mode_name or 'Event' in mode_name:
            return 'Monitoring & Events'
        elif 'Management' in mode_name:
            return 'Management'
        else:
            return 'Advanced/Specialized'
    
    def _extract_command_base(self, command: str) -> str:
        """Extract base command (first 1-2 keywords) for grouping
        
        Example: 'interface Ethernet INTF_ID' -> 'interface'
        Example: 'ip route PREFIX NEXTHOP' -> 'ip route'
        """
        
        # Remove [no|default] prefix if present
        cmd = command
        if cmd.startswith('[no|default]'):
            cmd = cmd.replace('[no|default]', '').strip()
        
        # Extract first few words (up to first variable or special char)
        words = []
        for part in cmd.split():
            # Stop at variables (UPPERCASE), brackets, parens
            if (part.isupper() or 
                part.startswith('[') or 
                part.startswith('(') or 
                part.startswith('{')):
                break
            words.append(part)
            
            # Limit to 3 words max
            if len(words) >= 3:
                break
        
        return ' '.join(words) if words else command.split()[0]
    
    def _calculate_syntax_hash(self, command: str) -> str:
        """Calculate hash for command syntax (for deduplication)"""
        # Normalize: remove [no|default], extra whitespace
        normalized = command.replace('[no|default]', '').strip()
        normalized = ' '.join(normalized.split())
        
        return hashlib.md5(normalized.encode()).hexdigest()
    
    def populate_database(self, parsed_data: Dict) -> bool:
        """Populate database with parsed data"""
        
        print("[PARSER] Connecting to database...")
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Insert modes
            print(f"[PARSER] Inserting {len(parsed_data['modes'])} modes...")
            for mode_name, mode_data in parsed_data['modes'].items():
                cursor.execute('''
                    INSERT OR IGNORE INTO cli_modes (mode_name, mode_category, description)
                    VALUES (?, ?, ?)
                ''', (mode_name, mode_data['category'], f"Auto-detected {mode_data['category']} mode"))
                
                # Get mode_id
                cursor.execute('SELECT mode_id FROM cli_modes WHERE mode_name = ?', (mode_name,))
                mode_id = cursor.fetchone()[0]
                mode_data['id'] = mode_id
            
            # Insert commands
            print(f"[PARSER] Inserting {len(parsed_data['commands'])} commands...")
            for cmd in parsed_data['commands']:
                # Get mode_id - create mode if it doesn't exist (edge case)
                if cmd.mode not in parsed_data['modes']:
                    print(f"[PARSER] Warning: Mode '{cmd.mode}' not in modes dict, creating on-the-fly...")
                    category = self._categorize_mode(cmd.mode)
                    cursor.execute('''
                        INSERT OR IGNORE INTO cli_modes (mode_name, mode_category, description)
                        VALUES (?, ?, ?)
                    ''', (cmd.mode, category, f"Auto-detected {category} mode"))
                    cursor.execute('SELECT mode_id FROM cli_modes WHERE mode_name = ?', (cmd.mode,))
                    mode_id = cursor.fetchone()[0]
                    parsed_data['modes'][cmd.mode] = {'id': mode_id, 'category': category, 'parent': None}
                else:
                    mode_id = parsed_data['modes'][cmd.mode]['id']
                
                cursor.execute('''
                    INSERT INTO cli_commands 
                    (mode_id, command_text, command_base, has_no_prefix, 
                     has_default_prefix, line_number, syntax_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (mode_id, cmd.command_text, cmd.command_base, 
                      cmd.has_no_prefix, cmd.has_default_prefix,
                      cmd.line_number, cmd.syntax_hash))
                
                command_id = cursor.lastrowid
                
                # Insert tokens
                for token in cmd.tokens:
                    cursor.execute('''
                        INSERT INTO cli_command_tokens
                        (command_id, position, token_type, token_value, 
                         is_optional, parent_token_id)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (command_id, token.position, token.token_type,
                          token.token_value, token.is_optional, token.parent_id))
            
            conn.commit()
            print("[PARSER] ✓ Database populated successfully")
            return True
            
        except Exception as e:
            print(f"[PARSER] ✗ Error populating database: {e}")
            conn.rollback()
            return False
        finally:
            conn.close()


if __name__ == '__main__':
    import sys
    
    # Get paths
    if len(sys.argv) > 1:
        showcli_path = sys.argv[1]
    else:
        showcli_path = 'showcli.txt'
    
    if len(sys.argv) > 2:
        db_path = sys.argv[2]
    else:
        db_path = 'custom-cvp.db'
    
    # Parse file
    parser = CLIParser(db_path)
    parsed_data = parser.parse_file(showcli_path)
    
    # Populate database
    success = parser.populate_database(parsed_data)
    
    if success:
        print(f"\n✓ Successfully parsed {parsed_data['total_lines']} lines")
        print(f"✓ Extracted {len(parsed_data['modes'])} modes")
        print(f"✓ Parsed {len(parsed_data['commands'])} commands")
    else:
        print("\n✗ Failed to populate database")
        sys.exit(1)
