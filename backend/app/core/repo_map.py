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
                if not file.endswith(".py"):
                    continue
                    
                abs_path = os.path.join(root, file)
                rel_path = os.path.relpath(abs_path, directory_path)
                
                try:
                    symbols = self._parse_file_symbols(abs_path)
                    if symbols:
                        tree_lines.append(self._format_file_symbols(rel_path, symbols))
                except Exception as e:
                    # Ignore parsing errors for broken scripts during live dev sessions
                    pass

        if not tree_lines:
            return "（沙盒内目前没有可解析的 Python 符号定义）"

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
