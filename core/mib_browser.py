"""
Arista MIB Browser
Parses raw ASN.1 .txt MIB files into structured, searchable objects.
No external dependencies — pure stdlib regex parsing.
"""
import os
import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional

MIB_DIR = os.environ.get(
    'MIB_DIR',
    os.path.join(os.path.dirname(os.path.dirname(__file__)), 'screenshots', 'arista-mibs')
)

# Definition keywords we care about (order matters for the type badge)
_DEF_KEYWORDS = (
    'OBJECT-TYPE',
    'NOTIFICATION-TYPE',
    'TEXTUAL-CONVENTION',
    'MODULE-IDENTITY',
    'OBJECT-IDENTIFIER',
    'OBJECT-GROUP',
    'NOTIFICATION-GROUP',
    'MODULE-COMPLIANCE',
)
_DEF_RE = re.compile(
    r'^([\w][\w-]*)\s+(' + '|'.join(_DEF_KEYWORDS) + r')\b',
    re.MULTILINE
)


@dataclass
class MibObject:
    name: str
    obj_type: str
    syntax: str
    access: str
    status: str
    description: str
    parent_ref: str   # e.g. "aristaIfObjects 1"


@dataclass
class MibModule:
    name: str
    description: str
    filename: str
    objects: List[MibObject] = field(default_factory=list)


class MIBBrowserManager:
    def __init__(self):
        self.modules: Dict[str, MibModule] = {}
        self._load_all()

    # ── Parsing ───────────────────────────────────────────────────────────────

    def _load_all(self):
        if not os.path.isdir(MIB_DIR):
            print(f"[MIBBrowser] WARNING: MIB directory not found: {MIB_DIR}")
            return
        for fname in sorted(os.listdir(MIB_DIR)):
            if fname.endswith('.txt'):
                path = os.path.join(MIB_DIR, fname)
                try:
                    mod = self._parse_file(path, fname)
                    if mod:
                        self.modules[mod.name] = mod
                except Exception as e:
                    print(f"[MIBBrowser] Error parsing {fname}: {e}")
        total = sum(len(m.objects) for m in self.modules.values())
        print(f"[MIBBrowser] Loaded {len(self.modules)} modules, {total} objects")

    def _parse_file(self, path: str, fname: str) -> Optional[MibModule]:
        with open(path, 'r', errors='replace') as f:
            content = f.read()

        # Module name
        m = re.search(r'^(\S+)\s+DEFINITIONS\s*::=\s*BEGIN', content, re.MULTILINE)
        if not m:
            return None
        module_name = m.group(1)

        # Module-level description from MODULE-IDENTITY block
        mod_desc = ''
        mi = re.search(r'\bMODULE-IDENTITY\b.*?DESCRIPTION\s+"(.*?)"', content, re.DOTALL)
        if mi:
            mod_desc = re.sub(r'\s+', ' ', mi.group(1)).strip()[:500]

        mod = MibModule(name=module_name, description=mod_desc, filename=fname)

        # Tokenise: find every named definition block
        matches = list(_DEF_RE.finditer(content))
        for i, match in enumerate(matches):
            obj_name = match.group(1)
            obj_type = match.group(2)

            # Skip the module-name line itself
            if obj_name == module_name:
                continue

            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
            block = content[start:end]

            mod.objects.append(MibObject(
                name=obj_name,
                obj_type=obj_type,
                syntax=self._extract_simple(block, 'SYNTAX'),
                access=(self._extract_simple(block, 'MAX-ACCESS') or
                        self._extract_simple(block, 'ACCESS')),
                status=self._extract_simple(block, 'STATUS'),
                description=self._extract_description(block),
                parent_ref=self._extract_parent_ref(block),
            ))

        return mod

    # ── Field extractors ──────────────────────────────────────────────────────

    @staticmethod
    def _extract_simple(block: str, keyword: str) -> str:
        m = re.search(rf'\b{keyword}\s+(\S+)', block)
        return m.group(1) if m else ''

    @staticmethod
    def _extract_description(block: str) -> str:
        m = re.search(r'\bDESCRIPTION\s+"(.*?)"', block, re.DOTALL)
        return re.sub(r'\s+', ' ', m.group(1)).strip() if m else ''

    @staticmethod
    def _extract_parent_ref(block: str) -> str:
        m = re.search(r'::=\s*\{\s*([\w][\w\s-]*\d+)\s*\}', block)
        return m.group(1).strip() if m else ''

    # ── Public API ────────────────────────────────────────────────────────────

    def get_modules_summary(self) -> List[dict]:
        return [
            {
                'name': m.name,
                'description': m.description,
                'object_count': len(m.objects),
                'filename': m.filename,
            }
            for m in sorted(self.modules.values(), key=lambda x: x.name)
        ]

    def get_module(self, module_name: str) -> Optional[dict]:
        mod = self.modules.get(module_name)
        if not mod:
            return None
        return {
            'name': mod.name,
            'description': mod.description,
            'filename': mod.filename,
            'objects': [
                {
                    'name': o.name,
                    'type': o.obj_type,
                    'syntax': o.syntax,
                    'access': o.access,
                    'status': o.status,
                    'description': o.description,
                    'parent_ref': o.parent_ref,
                }
                for o in mod.objects
            ],
        }

    def search(self, query: str, limit: int = 150) -> List[dict]:
        q = query.lower().strip()
        if not q:
            return []
        results = []
        for mod in self.modules.values():
            for o in mod.objects:
                name_l = o.name.lower()
                desc_l = o.description.lower()
                if name_l.startswith(q):
                    score = 30
                elif q in name_l:
                    score = 20
                elif q in desc_l:
                    score = 5
                else:
                    continue
                results.append({
                    'name': o.name,
                    'module': mod.name,
                    'type': o.obj_type,
                    'syntax': o.syntax,
                    'access': o.access,
                    'status': o.status,
                    'description': o.description[:300],
                    'score': score,
                })
        results.sort(key=lambda x: -x['score'])
        return results[:limit]

    def get_stats(self) -> dict:
        total = sum(len(m.objects) for m in self.modules.values())
        type_counts: Dict[str, int] = {}
        for mod in self.modules.values():
            for o in mod.objects:
                type_counts[o.obj_type] = type_counts.get(o.obj_type, 0) + 1
        return {
            'modules': len(self.modules),
            'objects': total,
            'type_counts': type_counts,
        }
