---
name: code-interpreter-usage
description: Guide for using Open WebUI Code Interpreter with Pyodide. Use when user wants to execute Python code, analyze data, or process uploaded files (CSV, Excel, PDF, DOCX, PPTX) in the chat.
---

# Open WebUI Code Interpreter Usage Guide

## Overview
Open WebUI's Code Interpreter uses Pyodide to execute Python code directly in the browser. Data analysis and file processing are possible without a server.

## File Access
- Uploaded files are placed in the `/mnt/uploads/` directory
- **User can view and access files from the "Files" sidebar on the right side of the screen**

## Workflow for Processing Uploaded Files
When a user attaches files to the chat, follow these steps:

1. **Call `prepare_files_for_code_interpreter` tool** to get file paths in `/mnt/uploads/`
2. **Use Code Interpreter** to access and process the files

Example workflow:
```
User: "Analyze this Excel file" [attaches data.xlsx]
→ Call prepare_files_for_code_interpreter tool
→ Tool returns: /mnt/uploads/data.xlsx
→ Execute Python code to analyze the file
```

## Processing Document Files

### PDF Files (PyMuPDF - Built-in)
```python
import pymupdf

# Open PDF
doc = pymupdf.open('/mnt/uploads/document.pdf')

# Extract text from all pages
for page in doc:
    text = page.get_text()
    print(text)

# Get page count
print(f"Total pages: {doc.page_count}")
```

### Excel Files (XLSX - zipfile + lxml workaround)
**Note**: python-calamine is not available, so extract as ZIP and parse XML.
```python
import zipfile
from lxml import etree
import pandas as pd

def extract_xlsx_to_dataframe(filepath, sheet_name=None):
    """Extract XLSX file to pandas DataFrame using zipfile + lxml"""
    with zipfile.ZipFile(filepath, 'r') as z:
        # Get shared strings (for cell values that reference shared strings)
        shared_strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            xml_content = z.read('xl/sharedStrings.xml')
            tree = etree.fromstring(xml_content)
            ns = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            for si in tree.xpath('//main:si', namespaces=ns):
                t = si.xpath('./main:t', namespaces=ns)
                shared_strings.append(t[0].text if t and t[0].text else '')

        # Get worksheet files
        sheet_files = [f for f in z.namelist() if f.startswith('xl/worksheets/sheet') and f.endswith('.xml')]
        sheet_files = sorted(sheet_files, key=lambda x: int(x.split('sheet')[1].split('.')[0]))

        # Parse sheet
        target_sheet = sheet_files[0]  # Default to first sheet
        if sheet_name:
            # You could implement workbook.xml parsing to find sheet by name
            pass

        xml_content = z.read(target_sheet)
        tree = etree.fromstring(xml_content)
        ns = {'main': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

        # Extract rows
        rows = []
        for row in tree.xpath('//main:row', namespaces=ns):
            row_data = {}
            for cell in row.xpath('./main:c', namespaces=ns):
                cell_ref = cell.get('r', '')
                cell_type = cell.get('t', '')

                # Extract column letter and row number
                col_match = ''.join(c for c in cell_ref if c.isalpha())
                row_match = ''.join(c for c in cell_ref if c.isdigit())

                v = cell.xpath('./main:v', namespaces=ns)
                if v and v[0].text:
                    value = v[0].text
                    # If cell type is 's', it's a shared string
                    if cell_type == 's' and shared_strings:
                        idx = int(value)
                        value = shared_strings[idx] if idx < len(shared_strings) else value
                    row_data[col_match] = value

            if row_data:
                rows.append((int(row_match) if row_match else len(rows), row_data))

        # Sort by row number and create DataFrame
        if rows:
            rows.sort(key=lambda x: x[0])
            data = [r[1] for r in rows]

            # Get columns from first row (header)
            if data:
                columns = sorted(data[0].keys(), key=lambda x: (len(x), x))
                df_data = []
                for i, row in enumerate(data):
                    if i == 0:
                        # First row as header
                        continue
                    df_data.append([row.get(col, '') for col in columns])
                return pd.DataFrame(df_data, columns=columns)

        return pd.DataFrame()

# Example usage
df = extract_xlsx_to_dataframe('/mnt/uploads/data.xlsx')
print(df.head())
```

### Word Documents (DOCX - zipfile + lxml workaround)
**Note**: python-docx is not built-in, so extract as ZIP and parse XML.
```python
import zipfile
from lxml import etree

def extract_docx_text(filepath):
    """Extract text from DOCX file"""
    with zipfile.ZipFile(filepath, 'r') as z:
        xml_content = z.read('word/document.xml')
    tree = etree.fromstring(xml_content)
    # Define namespace
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    # Get all text elements
    texts = tree.xpath('//w:t', namespaces=ns)
    return ' '.join(t.text for t in texts if t.text)

text = extract_docx_text('/mnt/uploads/document.docx')
print(text)
```

### PowerPoint Files (PPTX - zipfile + lxml workaround)
**Note**: python-pptx is not built-in, so extract as ZIP and parse XML.
```python
import zipfile
from lxml import etree
import re

def extract_pptx_text(filepath):
    """Extract text from PPTX file"""
    texts = []
    ns = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}

    with zipfile.ZipFile(filepath, 'r') as z:
        # Get all slide files
        slide_files = sorted([f for f in z.namelist() if f.startswith('ppt/slides/slide') and f.endswith('.xml')])

        for slide_file in slide_files:
            xml_content = z.read(slide_file)
            tree = etree.fromstring(xml_content)
            # Get text elements
            slide_texts = tree.xpath('//a:t', namespaces=ns)
            slide_text = ' '.join(t.text for t in slide_texts if t.text)
            if slide_text:
                slide_num = re.search(r'slide(\d+)', slide_file)
                texts.append(f"Slide {slide_num.group(1) if slide_num else '?'}: {slide_text}")

    return '\n'.join(texts)

text = extract_pptx_text('/mnt/uploads/slides.pptx')
print(text)
```

## Available Packages (Built-in)
- **Data Analysis**: numpy, pandas, scipy, scikit-learn, statsmodels
- **Visualization**: matplotlib, bokeh, altair
- **Image Processing**: Pillow, opencv-python
- **PDF**: PyMuPDF (pymupdf)
- **XML Processing**: lxml
- **Others**: networkx, sympy, nltk, httpx, requests, beautifulsoup4

## Package Limitations
**Important**: The following are all disabled in Open WebUI's Code Interpreter:
- `pip install` ❌
- `subprocess` ❌
- `micropip.install()` ❌

**Only built-in packages are available.** Additional package installation is not possible.

### What You Cannot Do with Built-in Packages
- Direct DOCX/PPTX reading (no python-docx/python-pptx) → Use zipfile + lxml workaround
- Heavy C extension packages (PyTorch, TensorFlow)
- GPU/CUDA processing

## Other Limitations
- Single-threaded execution (no parallel processing)
- Network access may be partially restricted
- Large files may take longer to process

## Best Practices
- Consider pre-sampling large data files
- Use matplotlib or altair for visualization
- Execute complex processes step-by-step for debugging
- DOCX/PPTX text extraction is possible with zipfile + lxml
