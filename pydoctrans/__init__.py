"""pydoctrans — Python Document Transformer.

A document conversion tool that leverages LibreOffice for server-side
format conversion with sandbox isolation and concurrency control.
"""

from pydoctrans.convert import ConversionError, convert

__all__ = ["convert", "ConversionError"]
__version__ = "0.2.0"
