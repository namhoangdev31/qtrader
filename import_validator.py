import os
import re
import ast
from collections import defaultdict

class ImportValidator:
    def __init__(self, root_dir='qtrader'):
        self.root_dir = root_dir
        self.graph = defaultdict(set)
        self.file_to_module = {}
        self.module_to_file = {}

    def _get_module_name(self, filepath):
        rel_path = os.path.relpath(filepath, os.path.dirname(self.root_dir))
        return rel_path.replace(os.path.sep, '.').replace('.py', '')

    def build_graph(self):
        for root, dirs, files in os.walk(self.root_dir):
            for file in files:
                if file.endswith('.py'):
                    filepath = os.path.join(root, file)
                    module_name = self._get_module_name(filepath)
                    # Handle __init__.py
                    if module_name.endswith('.__init__'):
                        module_name = module_name[:-len('.__init__')]
                    
                    self.file_to_module[filepath] = module_name
                    self.module_to_file[module_name] = filepath

                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        try:
                            tree = ast.parse(f.read())
                        except SyntaxError:
                            continue

                        for node in ast.walk(tree):
                            if isinstance(node, ast.Import):
                                for alias in node.names:
                                    if alias.name.startswith('qtrader'):
                                        self.graph[module_name].add(alias.name)
                            elif isinstance(node, ast.ImportFrom):
                                if node.module and node.level == 0:
                                    if node.module.startswith('qtrader'):
                                        self.graph[module_name].add(node.module)
                                # Relative imports (level > 0)
                                elif node.level > 0:
                                    # Resolve relative import
                                    parts = module_name.split('.')
                                    # For a.b.c, level 1 -> a.b, level 2 -> a
                                    prefix = '.'.join(parts[:-node.level])
                                    if node.module:
                                        full_module = f"{prefix}.{node.module}"
                                    else:
                                        full_module = prefix
                                    if full_module.startswith('qtrader'):
                                        self.graph[module_name].add(full_module)

    def find_cycles(self):
        visited = set()
        stack = []
        cycles = []

        def visit(u, path):
            if u in stack:
                cycle_start_idx = path.index(u)
                cycles.append(path[cycle_start_idx:] + [u])
                return
            if u in visited:
                return

            visited.add(u)
            stack.append(u)
            
            # Simple module name match (some imports might be submodules not in our file list)
            # E.g. qtrader.core.types.Event -> we check for qtrader.core.types
            for v_full in self.graph.get(u, []):
                # Try to find the actual file module in our map
                v = v_full
                while v and v not in self.module_to_file:
                    if '.' not in v:
                        break
                    v = '.'.join(v.split('.')[:-1])
                
                if v in self.module_to_file:
                    visit(v, path + [u])

            stack.pop()

        for module in list(self.module_to_file.keys()):
            visit(module, [])
        
        return cycles

if __name__ == "__main__":
    validator = ImportValidator()
    print("Building import graph...")
    validator.build_graph()
    print("Scanning for circular dependencies...")
    cycles = validator.find_cycles()
    if cycles:
        print(f"Found {len(cycles)} cycles:")
        for cycle in cycles:
            print(" -> ".join(cycle))
    else:
        print("No circular dependencies found. DAG validated.")
