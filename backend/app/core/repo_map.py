"""Repo Map Scanner — Lightweight AST codebase analyzer that maps classes, functions, and imports."""

import os
import ast
from typing import Dict, Any, List

class CodebaseMapScanner:
    """Recursively scans a workspace directory and uses AST to map classes, methods, and functions."""

    def __init__(self, ignored_names: List[str] = None):
        self.ignored_names = ignored_names or [
            ".git", ".venv", "venv", "__pycache__", "node_modules", "agenthub_export", "dist", "build"
        ]

    def scan_directory(self, directory_path: str) -> str:
        """Scan directory_path recursively and return a structured markdown map of symbols."""
        if not os.path.exists(directory_path):
            return "（沙盒目录目前不存在）"

        tree_lines = []
        for root, dirs, files in os.walk(directory_path):
            # Prune ignored directories in-place
            dirs[:] = [d for d in dirs if d not in self.ignored_names and not d.startswith(".")]
            
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext not in (".py", ".js", ".jsx", ".ts", ".tsx"):
                    continue
                    
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, directory_path)
                
                try:
                    if ext == ".py":
                        symbols = self._parse_file_symbols(abs_path)
                    else:
                        symbols = self._parse_js_symbols(abs_path)
                    if symbols:
                        tree_lines.append(self._format_file_symbols(rel_path, symbols))
                except Exception as e:
                    # Ignore parsing errors for broken scripts during live dev sessions
                    pass

        if not tree_lines:
            return "（沙盒内目前没有可解析的 Python/JS/TS 符号定义）"

        return "\n".join(tree_lines)

    def _parse_file_symbols(self, file_path: str) -> Dict[str, Any]:
        """Parse file using AST to extract class names, methods, functions, and imports."""
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return {}

        imports = []
        classes = {}
        functions = []

        for node in tree.body:
            if isinstance(node, ast.Import):
                for name in node.names:
                    imports.append(name.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for name in node.names:
                    imports.append(f"{module}.{name.name}")
            elif isinstance(node, ast.FunctionDef):
                args_str = self._format_args(node.args)
                functions.append(f"{node.name}({args_str})")
            elif isinstance(node, ast.ClassDef):
                methods = []
                for subnode in node.body:
                    if isinstance(subnode, ast.FunctionDef):
                        args_str = self._format_args(subnode.args)
                        methods.append(f"{subnode.name}({args_str})")
                classes[node.name] = methods

        return {
            "imports": imports,
            "classes": classes,
            "functions": functions
        }

    def _parse_js_symbols(self, file_path: str) -> Dict[str, Any]:
        """Parse JS/TS file using regex to extract class names, methods, functions, and imports."""
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()

        imports = []
        classes = {}
        functions = []

        import re
        # Remove single line and multi-line comments for easier regex matching
        code_clean = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        code_clean = re.sub(r'//.*$', '', code_clean, flags=re.MULTILINE)

        # 1. Match imports
        import_patterns = [
            r'import\s+.*?from\s+[\'"]([^\'"]+)[\'"]',
            r'import\s+[\'"]([^\'"]+)[\'"]',
            r'(?:const|let|var)\s+.*?\s*=\s*require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)'
        ]
        for pattern in import_patterns:
            for match in re.finditer(pattern, code_clean):
                imports.append(match.group(1))

        # Deduplicate and extract bare module name if it starts with relative paths
        clean_imports = []
        for imp in imports:
            # We want react, axios, path, etc. or clean relative names
            clean_imports.append(imp.split('/')[-1])
        imports = list(dict.fromkeys(clean_imports))

        # 2. Extract classes and functions
        keywords = {'if', 'for', 'catch', 'while', 'switch', 'function', 'constructor', 'super', 'import', 'export', 'return'}
        lines = code_clean.splitlines()
        current_class = None

        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Class match
            cls_match = re.match(r'(?:export\s+)?(?:default\s+)?class\s+(\w+)', line_str)
            if cls_match:
                current_class = cls_match.group(1)
                classes[current_class] = []
                continue

            # Reset active class if we hit other declarations
            if current_class and (line.startswith('class ') or line.startswith('export class ') or line.startswith('function ') or line.startswith('export function ') or line.startswith('export default ')):
                current_class = None

            # Match standard function
            func_match = re.search(r'(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)\s*\((.*?)\)', line_str)
            if func_match:
                name = func_match.group(1)
                args = func_match.group(2).strip()
                functions.append(f"{name}({args})")
                continue

            # Match arrow function
            arrow_match = re.search(r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\((.*?)\)\s*=>', line_str)
            if arrow_match:
                name = arrow_match.group(1)
                args = arrow_match.group(2).strip()
                functions.append(f"{name}({args})")
                continue

            # Match method inside class
            if current_class:
                method_match = re.search(r'^(?:async\s+)?(\w+)\s*\((.*?)\)\s*\{', line_str)
                if method_match:
                    meth_name = method_match.group(1)
                    meth_args = method_match.group(2).strip()
                    if meth_name not in keywords:
                        classes[current_class].append(f"{meth_name}({meth_args})")

        return {
            "imports": imports,
            "classes": classes,
            "functions": functions
        }

    def _format_args(self, args: ast.arguments) -> str:
        """Format ast.arguments into a simple arg string."""
        arg_names = []
        for arg in args.args:
            arg_names.append(arg.arg)
        # Handle kwonlyargs or vararg/kwarg if needed, keeping it compact
        if args.vararg:
            arg_names.append(f"*{args.vararg.arg}")
        if args.kwarg:
            arg_names.append(f"**{args.kwarg.arg}")
        return ", ".join(arg_names)

    def _format_file_symbols(self, rel_path: str, symbols: Dict[str, Any]) -> str:
        """Formats the symbols dict into a compact markdown representation."""
        lines = [f"- 📄 `{rel_path}`"]
        
        # Format imports compactly on one line
        if symbols["imports"]:
            lines.append(f"    - 🔌 imports: {', '.join(f'`{imp}`' for imp in symbols['imports'][:10])}")
            
        # Format standalone functions
        for func in symbols["functions"]:
            lines.append(f"    - ⚙️ function: `{func}`")
            
        # Format classes and methods
        for cls_name, methods in symbols["classes"].items():
            lines.append(f"    - 📦 class: `{cls_name}`")
            for meth in methods:
                lines.append(f"        - 🛠️ method: `{meth}`")
                
        return "\n".join(lines)


# Singleton instance
codebase_map_scanner = CodebaseMapScanner()
