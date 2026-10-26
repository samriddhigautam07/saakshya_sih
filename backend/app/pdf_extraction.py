"""Bounded, page-referenced digital PDF text extraction and optional Tesseract OCR."""

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
import math
from pathlib import Path
import time
from typing import Callable

from PIL import Image
import pymupdf
import pytesseract
from pytesseract import TesseractNotFoundError


@dataclass(frozen=True)
class ExtractionResult:
    status: str
    text: str
    extracted_at: datetime


class OCRUnavailableError(Exception):
    """Raised when the Tesseract executable is not installed or cannot be started."""


class OCRPageTooLargeError(Exception):
    """Raised when rendering a page would exceed the configured pixel limit."""


class OCRPageTimeoutError(Exception):
    """Raised when OCR for a single page reaches its time limit."""


class OCRPageError(Exception):
    """Raised when an individual page cannot be rendered or recognized."""


def perform_ocr(page: pymupdf.Page, dpi: int, max_pixels: int, timeout_seconds: float) -> str:
    """Render one bounded page and OCR the raster without modifying the source PDF."""
    scale = dpi / 72.0
    expected_width = max(1, math.ceil(page.rect.width * scale))
    expected_height = max(1, math.ceil(page.rect.height * scale))
    if expected_width * expected_height > max_pixels:
        raise OCRPageTooLargeError
    try:
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        image = Image.open(BytesIO(pixmap.tobytes("png")))
        return pytesseract.image_to_string(image, config="--psm 6", timeout=timeout_seconds).strip()
    except TesseractNotFoundError as error:
        raise OCRUnavailableError from error
    except RuntimeError as error:
        if "timeout" in str(error).lower():
            raise OCRPageTimeoutError from error
        raise OCRPageError from error
    except Exception as error:
        raise OCRPageError from error


def extract_pdf_text(
    path: Path,
    max_characters: int,
    *,
    max_pages: int = 200,
    ocr_enabled: bool = True,
    ocr_max_pages: int = 20,
    ocr_dpi: int = 150,
    ocr_min_digital_chars: int = 16,
    ocr_max_page_pixels: int = 12_000_000,
    ocr_page_timeout_seconds: int = 10,
    processing_timeout_seconds: int = 60,
    ocr_page: Callable[[pymupdf.Page, int, int, float], str] | None = None,
) -> ExtractionResult:
    ocr_page = ocr_page or perform_ocr
    extracted_at = datetime.now(timezone.utc)
    try:
        document = pymupdf.open(path)
    except (pymupdf.FileDataError, pymupdf.EmptyFileError, ValueError, RuntimeError):
        return ExtractionResult("corrupt", "", extracted_at)

    started_at = time.monotonic()
    try:
        with document:
            if document.needs_pass:
                return ExtractionResult("encrypted", "", extracted_at)
            if document.page_count == 0:
                return ExtractionResult("empty", "", extracted_at)
            if document.page_count > max_pages:
                return ExtractionResult("page_limit_exceeded", "", extracted_at)

            parts: list[str] = []
            ocr_attempted = 0
            saw_ocr_text = False
            saw_scanned_page = False
            status: str | None = None
            tesseract_missing = False

            for page_number, page in enumerate(document, start=1):
                if time.monotonic() - started_at >= processing_timeout_seconds:
                    status = "processing_timeout"
                    break
                try:
                    digital_text = page.get_text("text").strip()
                    images = page.get_images(full=True)
                except Exception:
                    status = status or "failed"
                    continue

                needs_ocr = len(digital_text) < ocr_min_digital_chars and bool(images)
                if digital_text and (not needs_ocr or not ocr_enabled):
                    parts.append(f"[Page {page_number} | Digital]\n{digital_text}")
                if not images or not needs_ocr:
                    continue

                saw_scanned_page = True
                if not ocr_enabled:
                    status = status or "scanned_ocr_unavailable"
                    continue
                if tesseract_missing:
                    status = "ocr_unavailable"
                    continue
                if ocr_attempted >= ocr_max_pages:
                    status = status or "ocr_page_limit_exceeded"
                    continue
                remaining = processing_timeout_seconds - (time.monotonic() - started_at)
                if remaining <= 0:
                    status = "processing_timeout"
                    break
                ocr_attempted += 1
                try:
                    recognized = ocr_page(
                        page,
                        ocr_dpi,
                        ocr_max_page_pixels,
                        min(float(ocr_page_timeout_seconds), remaining),
                    )
                    if recognized:
                        parts.append(f"[Page {page_number} | OCR]\n{recognized}")
                        saw_ocr_text = True
                    else:
                        status = status or "ocr_partial_failure"
                except OCRUnavailableError:
                    tesseract_missing = True
                    status = "ocr_unavailable"
                except OCRPageTooLargeError:
                    status = status or "ocr_page_too_large"
                except OCRPageTimeoutError:
                    status = "processing_timeout"
                    break
                except OCRPageError:
                    status = status or "ocr_partial_failure"

            text = "\n\n".join(parts)
            if len(text) > max_characters:
                return ExtractionResult("text_truncated", text[:max_characters], extracted_at)
            if status:
                return ExtractionResult(status, text, extracted_at)
            if saw_ocr_text:
                return ExtractionResult("text_extracted_with_ocr", text, extracted_at)
            if saw_scanned_page:
                return ExtractionResult("scanned_ocr_unavailable" if not ocr_enabled else "ocr_partial_failure", text, extracted_at)
            if text:
                return ExtractionResult("text_extracted", text, extracted_at)
            return ExtractionResult("empty", "", extracted_at)
    except Exception:
        return ExtractionResult("failed", "", extracted_at)
