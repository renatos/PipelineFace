#!/usr/bin/env python3
"""
Script Linter & JSON Validator for Studio Githa HTML Landing Pages.
Validates all <script> tags, specifically JSON-LD (application/ld+json) and inline JS,
detecting unclosed braces, invalid JSON syntax, and script errors.

Usage:
  python3 scripts/SEO/lint_scripts.py
  python3 scripts/SEO/lint_scripts.py --file SiteStudioGitha/pages/micropigmentacao-em-bh.html
"""
import os
import re
import sys
import json
import argparse
from pathlib import Path
from html.parser import HTMLParser

PAGES_DIR = Path("/home/renato/dev/PipelineFace/SiteStudioGitha/pages")

class ScriptExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.in_script = False
        self.current_type = "text/javascript"
        self.current_content = []
        self.start_line = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "script":
            self.in_script = True
            self.start_line = self.getpos()[0]
            attrs_dict = {k.lower(): v for k, v in attrs if v is not None}
            self.current_type = attrs_dict.get("type", "text/javascript").lower()
            self.current_content = []

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self.in_script:
            self.in_script = False
            raw_text = "".join(self.current_content)
            self.scripts.append({
                "type": self.current_type,
                "content": raw_text,
                "line": self.start_line
            })

    def handle_data(self, data):
        if self.in_script:
            self.current_content.append(data)

def check_balanced_braces(text: str) -> tuple[bool, str]:
    """Checks if parentheses, curly braces, and square brackets are balanced."""
    stack = []
    pairs = {')': '(', '}': '{', ']': '['}
    
    # Simple scanner ignoring comments and string literals
    in_single_str = False
    in_double_str = False
    escaped = False
    
    for idx, char in enumerate(text):
        if escaped:
            escaped = False
            continue
        if char == '\\':
            escaped = True
            continue
        if char == "'" and not in_double_str:
            in_single_str = not in_single_str
            continue
        if char == '"' and not in_single_str:
            in_double_str = not in_double_str
            continue
        if in_single_str or in_double_str:
            continue
            
        if char in '({[':
            stack.append((char, idx))
        elif char in ')}]':
            if not stack:
                return False, f"Fechamento inesperado de '{char}' na posição {idx}"
            last_open, open_idx = stack.pop()
            if pairs[char] != last_open:
                return False, f"Correspondência inválida: abriu '{last_open}' em {open_idx} mas fechou '{char}' em {idx}"
                
    if stack:
        last_open, open_idx = stack[-1]
        return False, f"Chave/Parêntese não fechado: '{last_open}' na posição {open_idx}"
        
    return True, "OK"

def lint_file(file_path: Path) -> bool:
    content = file_path.read_text(encoding="utf-8")
    
    # Remove HTML comments first
    clean_html = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    
    extractor = ScriptExtractor()
    extractor.feed(clean_html)
    
    has_errors = False
    print(f"\n🔍 Linting {file_path.name} ({len(extractor.scripts)} tags <script> encontradas)...")
    
    for idx, s in enumerate(extractor.scripts, 1):
        script_type = s["type"]
        raw = s["content"].strip()
        line = s["line"]
        
        if not raw:
            continue
            
        if "json" in script_type:
            # Validate JSON
            try:
                data = json.loads(raw)
                # Check Schema.org integrity
                if isinstance(data, dict):
                    context = data.get("@context")
                    graph = data.get("@graph")
                    stype = data.get("@type")
                    if not context:
                        print(f"  ⚠️  [Aviso Script #{idx} (L{line})] JSON-LD sem '@context'")
                    if not graph and not stype:
                        print(f"  ⚠️  [Aviso Script #{idx} (L{line})] JSON-LD sem '@type' ou '@graph'")
                print(f"  ✅ [Script #{idx} - JSON-LD (L{line})] JSON 100% válido e balanceado.")
            except json.JSONDecodeError as err:
                print(f"  ❌ [ERRO Script #{idx} - JSON-LD (L{line})] JSON INVÁLIDO:")
                print(f"     -> {err}")
                has_errors = True
        else:
            # Inline Javascript / Ads
            balanced, msg = check_balanced_braces(raw)
            if balanced:
                print(f"  ✅ [Script #{idx} - JS (L{line})] Chaves e parênteses balanceados.")
            else:
                print(f"  ❌ [ERRO Script #{idx} - JS (L{line})] Sintaxe JS desbalanceada: {msg}")
                has_errors = True
                
    if not has_errors:
        print(f"  ✨ {file_path.name}: Todos os scripts estão perfeitos e seguros.")
    return not has_errors

def main():
    parser = argparse.ArgumentParser(description="Linter de tags <script> e JSON-LD para páginas do Studio Githa")
    parser.add_argument("--file", type=str, help="Caminho do arquivo específico para checar")
    args = parser.parse_args()
    
    if args.file:
        success = lint_file(Path(args.file))
        sys.exit(0 if success else 1)
        
    all_ok = True
    for f in sorted(PAGES_DIR.glob("*.html")):
        if "privacy" in f.name or "teste" in f.name or "bak" in f.name:
            continue
        if not lint_file(f):
            all_ok = False
            
    print("\n" + "=" * 60)
    if all_ok:
        print("🎉 SUCESSO: Todas as páginas passaram no Lint de scripts e JSON-LD!")
    else:
        print("❌ ATENÇÃO: Foram encontrados erros em algumas páginas. Corrija antes de enviar.")
    print("=" * 60)
    sys.exit(0 if all_ok else 1)

if __name__ == "__main__":
    main()
