
import os
import ast
import sys

def check_syntax(start_path):
    print(f"Checking syntax for files in {start_path}...")
    error_count = 0
    
    for root, _, files in os.walk(start_path):
        if 'venv' in root or '.git' in root or '__pycache__' in root:
            continue
            
        for file in files:
            if file.endswith(".py"):
                full_path = os.path.join(root, file)
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        source = f.read()
                    ast.parse(source)
                except SyntaxError as e:
                    print(f"[ERROR] SyntaxError in {full_path}: {e}")
                    print(f"Line {e.lineno}: {e.text.strip() if e.text else 'Unknown'}")
                    error_count += 1
                except Exception as e:
                    print(f"[ERROR] Cannot read/parse {full_path}: {e}")
                    error_count += 1
    
    if error_count == 0:
        print("\nAll files passed syntax check.")
    else:
        print(f"\nFound {error_count} syntax errors.")
        sys.exit(1)

if __name__ == "__main__":
    check_syntax(".")
