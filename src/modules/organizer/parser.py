"""PDF parser for extracting text and metadata from documents."""

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import pdfplumber

from src.core import get_logger

logger = get_logger("organizer.parser")


@dataclass
class ParsedDocument:
    """Result of parsing a PDF document."""

    file_path: Path
    file_name: str
    file_size: int
    file_hash: str
    text_content: str
    page_count: int

    # Extracted data (may be None if not found)
    document_date: Optional[date] = None
    due_date: Optional[date] = None
    amount: Optional[float] = None
    reference: Optional[str] = None
    nif: Optional[str] = None


class PDFParser:
    """Parser for extracting information from PDF documents."""

    # Common date formats in Portuguese documents
    DATE_PATTERNS = [
        # DD/MM/YYYY or DD-MM-YYYY
        r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})",
        # DD de Mês de YYYY
        r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})",
        # YYYY-MM-DD (ISO format)
        r"(\d{4})-(\d{2})-(\d{2})",
    ]

    # Month names in Portuguese
    MONTH_NAMES = {
        "janeiro": 1,
        "fevereiro": 2,
        "março": 3,
        "marco": 3,
        "abril": 4,
        "maio": 5,
        "junho": 6,
        "julho": 7,
        "agosto": 8,
        "setembro": 9,
        "outubro": 10,
        "novembro": 11,
        "dezembro": 12,
    }

    # Patterns for extracting amounts (Portuguese format: 1.234,56 €)
    AMOUNT_PATTERNS = [
        # Total a pagar: 123,45 €
        r"total\s*(?:a\s*pagar)?[:\s]*(\d{1,3}(?:\.\d{3})*,\d{2})\s*€?",
        # Valor: 123,45€
        r"valor[:\s]*(\d{1,3}(?:\.\d{3})*,\d{2})\s*€?",
        # Montante: 123,45
        r"montante[:\s]*(\d{1,3}(?:\.\d{3})*,\d{2})",
        # 123,45 EUR
        r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*(?:EUR|€)",
        # Total: € 123,45
        r"total[:\s]*€?\s*(\d{1,3}(?:\.\d{3})*,\d{2})",
    ]

    # Pattern for Portuguese NIF (tax ID)
    NIF_PATTERN = r"\b(\d{9})\b"

    # Reference/invoice number patterns
    REFERENCE_PATTERNS = [
        r"fatura\s*(?:n[º°.]?|número)?[:\s]*([A-Z0-9\-/]+)",
        r"documento\s*(?:n[º°.]?)?[:\s]*([A-Z0-9\-/]+)",
        r"referência[:\s]*([A-Z0-9\-/]+)",
        r"n[º°.]\s*([A-Z0-9\-/]+)",
    ]

    def __init__(self):
        self.logger = logger

    def parse(self, file_path: Path) -> Optional[ParsedDocument]:
        """Parse a PDF file and extract information.

        Args:
            file_path: Path to the PDF file

        Returns:
            ParsedDocument with extracted information, or None if parsing fails
        """
        if not file_path.exists():
            self.logger.error(f"Ficheiro não encontrado: {file_path}")
            return None

        if not file_path.suffix.lower() == ".pdf":
            self.logger.warning(f"Ficheiro não é PDF: {file_path}")
            return None

        try:
            # Get file info
            file_size = file_path.stat().st_size
            file_hash = self._calculate_hash(file_path)

            # Extract text from PDF
            text_content, page_count = self._extract_text(file_path)

            if not text_content:
                self.logger.warning(f"Não foi possível extrair texto: {file_path}")
                text_content = ""

            # Create base result
            result = ParsedDocument(
                file_path=file_path,
                file_name=file_path.name,
                file_size=file_size,
                file_hash=file_hash,
                text_content=text_content,
                page_count=page_count,
            )

            # Extract structured data
            if text_content:
                result.document_date = self._extract_date(text_content)
                result.due_date = self._extract_due_date(text_content)
                result.amount = self._extract_amount(text_content)
                result.reference = self._extract_reference(text_content)
                result.nif = self._extract_nif(text_content)

            self.logger.info(f"Parsed: {file_path.name}")
            return result

        except Exception as e:
            self.logger.error(f"Erro ao processar {file_path}: {e}")
            return None

    def _calculate_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _extract_text(self, file_path: Path) -> tuple[str, int]:
        """Extract text content from PDF.

        Returns:
            Tuple of (text_content, page_count)
        """
        text_parts = []
        page_count = 0

        with pdfplumber.open(file_path) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)

        return "\n".join(text_parts), page_count

    def _extract_date(self, text: str) -> Optional[date]:
        """Extract document date from text."""
        text_lower = text.lower()

        # Look for "data" or "emissão" followed by date
        date_context_patterns = [
            r"data[:\s]+",
            r"emissão[:\s]+",
            r"emitido\s+(?:em|a)[:\s]+",
        ]

        for context in date_context_patterns:
            match = re.search(context + self.DATE_PATTERNS[0], text_lower)
            if match:
                try:
                    day, month, year = match.groups()[-3:]
                    return date(int(year), int(month), int(day))
                except (ValueError, IndexError):
                    continue

        # Try general date patterns
        for pattern in self.DATE_PATTERNS:
            matches = re.findall(pattern, text_lower)
            for match in matches:
                try:
                    if len(match) == 3:
                        if pattern == self.DATE_PATTERNS[2]:  # ISO format
                            year, month, day = match
                        elif pattern == self.DATE_PATTERNS[1]:  # Month name
                            day, month_name, year = match
                            month = self.MONTH_NAMES.get(month_name.lower())
                            if not month:
                                continue
                        else:  # DD/MM/YYYY
                            day, month, year = match
                        return date(int(year), int(month), int(day))
                except (ValueError, TypeError):
                    continue

        return None

    def _extract_due_date(self, text: str) -> Optional[date]:
        """Extract due date (data limite) from text."""
        text_lower = text.lower()

        due_patterns = [
            r"data\s*limite[:\s]+",
            r"vencimento[:\s]+",
            r"pagar\s*até[:\s]+",
            r"válido\s*até[:\s]+",
        ]

        for pattern in due_patterns:
            match = re.search(pattern + self.DATE_PATTERNS[0], text_lower)
            if match:
                try:
                    groups = match.groups()
                    day, month, year = groups[-3:]
                    return date(int(year), int(month), int(day))
                except (ValueError, IndexError):
                    continue

        return None

    def _extract_amount(self, text: str) -> Optional[float]:
        """Extract monetary amount from text."""
        text_lower = text.lower()

        for pattern in self.AMOUNT_PATTERNS:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                try:
                    amount_str = match.group(1)
                    # Convert Portuguese format (1.234,56) to float
                    amount_str = amount_str.replace(".", "").replace(",", ".")
                    return float(amount_str)
                except (ValueError, IndexError):
                    continue

        return None

    def _extract_reference(self, text: str) -> Optional[str]:
        """Extract document reference/invoice number."""
        for pattern in self.REFERENCE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                ref = match.group(1).strip()
                if len(ref) >= 3:  # Minimum reasonable reference length
                    return ref

        return None

    def _extract_nif(self, text: str) -> Optional[str]:
        """Extract Portuguese NIF (tax identification number)."""
        # Look for NIF in context
        nif_context = re.search(
            r"(?:NIF|contribuinte|NIPC)[:\s]*(\d{9})",
            text,
            re.IGNORECASE,
        )
        if nif_context:
            return nif_context.group(1)

        # Look for standalone 9-digit numbers that could be NIFs
        # Portuguese NIFs start with specific digits
        nif_matches = re.findall(self.NIF_PATTERN, text)
        for nif in nif_matches:
            # Validate NIF format (starts with 1-9)
            if nif[0] in "123456789":
                return nif

        return None


def parse_pdf(file_path: Path) -> Optional[ParsedDocument]:
    """Convenience function to parse a PDF file.

    Args:
        file_path: Path to the PDF file

    Returns:
        ParsedDocument with extracted information
    """
    parser = PDFParser()
    return parser.parse(file_path)
