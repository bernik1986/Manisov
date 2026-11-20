"""One lock for every PDFium call, including native object destruction."""

from threading import RLock


PDFIUM_LOCK = RLock()
