import ast
import os
import sys
from pathlib import Path

class DocstringRemover(ast.NodeTransformer):
    def visit_Module(self, node):
        self.generic_visit(node)
        node.body = self._filter_body(node.body)
        return node

    def visit_ClassDef(self, node):
        self.generic_visit(node)
        node.body = self._filter_body(node.body)
        if not node.body:
            node.body = [ast.Pass()]
        return node

    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        node.body = self._filter_body(node.body)
        if not node.body:
            node.body = [ast.Pass()]
        return node

    def visit_AsyncFunctionDef(self, node):
        self.generic_visit(node)
        node.body = self._filter_body(node.body)
        if not node.body:
            node.body = [ast.Pass()]
        return node

    def _filter_body(self, body):
        """Removes standalone string literals from a body of statements."""
        new_body = []
        for i, stmt in enumerate(body):
            # Check if stmt is a standalone string literal (Potential docstring or leftover)
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                # We skip it if it's the first statement (docstring) or if it's just a floating string
                continue
            new_body.append(stmt)
        return new_body

def strip_file(file_path: Path):
    """Removes all comments and docstrings using AST unparse."""
    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()

    try:
        tree = ast.parse(source)
    except Exception as e:
        print(f"  Error parsing {file_path}: {e}")
        return

    # Transform the tree to remove docstrings
    remover = DocstringRemover()
    new_tree = remover.visit(tree)

    # Use ast.unparse to generate code without comments or docstrings
    # Note: ast.unparse requires Python 3.9+
    try:
        new_source = ast.unparse(new_tree)
    except Exception as e:
        print(f"  Error unparsing {file_path}: {e}")
        return

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(new_source)

def main():
    if len(sys.argv) > 1:
        target_dirs = [Path(p) for p in sys.argv[1:]]
    else:
        target_dirs = [
            Path("/Users/hoangnam/qtrader/qtrader"),
            Path("/Users/hoangnam/qtrader/tests")
        ]
    
    for t_dir in target_dirs:
        if not t_dir.exists():
            print(f"Path {t_dir} not found. Skipping.")
            continue
            
        if t_dir.is_file():
             print(f"Stripping {t_dir}...")
             strip_file(t_dir)
             continue

        print(f"Stripping files in {t_dir}...")
        for root, _, files in os.walk(t_dir):
            for file in files:
                if file.endswith(".py"):
                    f_path = Path(root) / file
                    # print(f"  Stripping {f_path}")
                    strip_file(f_path)

if __name__ == "__main__":
    main()
