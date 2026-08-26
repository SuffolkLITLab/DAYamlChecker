import os
import sys
from docx import Document

def validate_docx(file_path):
    try:
        doc = Document(file_path)
        # Check if it has some content or at least is readable
        _ = [p.text for p in doc.paragraphs]
        return True, "Valid"
    except Exception as e:
        return False, str(e)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python validate_docx.py <file1.docx> [file2.docx ...]")
        sys.exit(1)
    
    all_valid = True
    for path in sys.argv[1:]:
        is_valid, msg = validate_docx(path)
        if is_valid:
            print(f"OK: {path}")
        else:
            print(f"FAIL: {path} - {msg}")
            all_valid = False
            
    if not all_valid:
        sys.exit(1)
