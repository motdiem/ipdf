"""ipdf - turn Markdown or Word documents into iPhone-readable PDFs."""

from .converter import convert, ConversionError
from .styles import PAGE_PRESETS, FONT_STACKS, THEMES

__version__ = "0.1.0"

__all__ = [
    "convert",
    "ConversionError",
    "PAGE_PRESETS",
    "FONT_STACKS",
    "THEMES",
    "__version__",
]
