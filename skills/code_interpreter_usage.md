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

### Excel Files (python-calamine - Built-in)
```python
import pandas as pd

# Read Excel with calamine engine
df = pd.read_excel('/mnt/uploads/data.xlsx', engine='calamine')
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
