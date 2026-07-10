"""pydoctrans — Python Document Transformer.

A document conversion tool that leverages LibreOffice for server-side
format conversion with sandbox isolation and concurrency control.
"""

from pydoctrans.convert import ConversionError, convert
from pydoctrans.hooks import AfterHook, BeforeHook, ConversionContext

__all__ = [
    "convert",
    "ConversionError",
    "ConversionContext",
    "BeforeHook",
    "AfterHook",
]
__version__ = "0.4.0"
