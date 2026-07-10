# 快速开始

## 安装

```bash
pip install pydoctrans
```

要求：

- Python 3.11+
- LibreOffice（自动检测，无需手动配置）

## 第一个转换

```python
from pydoctrans import convert

# Word → PDF
with open("report.docx", "rb") as f:
    pdf_bytes = convert(f.read(), format="pdf", file_name="report.docx")

with open("report.pdf", "wb") as f:
    f.write(pdf_bytes)
```

## 命令行

```bash
python -m pydoctrans convert report.docx report.pdf
```

## 作为 HTTP 服务

```bash
python -m pydoctrans serve --port 8000
```

```bash
curl -F "file=@report.docx" -F "format=pdf" http://localhost:8000/convert -o report.pdf
```

## Docker

```bash
docker build -t pydoctrans .
docker run -p 8000:8000 pydoctrans
```
