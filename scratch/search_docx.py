import os
import zipfile
import xml.etree.ElementTree as ET

def get_docx_text(path):
    try:
        with zipfile.ZipFile(path) as z:
            xml_content = z.read('word/document.xml')
            root = ET.fromstring(xml_content)
            
            # Namespace map
            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
            
            texts = []
            for p in root.findall('.//w:p', ns):
                p_texts = []
                for r in p.findall('.//w:r', ns):
                    t = r.find('w:t', ns)
                    if t is not None and t.text:
                        p_texts.append(t.text)
                if p_texts:
                    texts.append(''.join(p_texts))
            return '\n'.join(texts)
    except Exception as e:
        return f"Error reading {path}: {str(e)}"

def main():
    desktop = os.path.join(os.environ['USERPROFILE'], 'Desktop')
    print(f"Scanning desktop: {desktop}")
    
    for f in os.listdir(desktop):
        if f.endswith('.docx') and not f.startswith('~$'):
            path = os.path.join(desktop, f)
            text = get_docx_text(path)
            
            # Print first 200 chars to identify
            print(f"\n--- FILE: {f} ---")
            print(text[:500])
            print("-" * 40)

if __name__ == '__main__':
    main()
