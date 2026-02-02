"""PDF parsing and metadata extraction for invoices."""

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

import pdfplumber

from src.core.logger import get_logger


@dataclass
class InvoiceMetadata:
    """Extracted metadata from an invoice PDF."""

    file_path: Path
    raw_text: str

    # Extracted fields (may be None if not found)
    nif_emitente: Optional[str] = None
    nif_cliente: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    total_amount: Optional[Decimal] = None
    currency: str = "EUR"
    vendor_name: Optional[str] = None

    @property
    def has_valid_nif(self) -> bool:
        """Check if we have at least one valid NIF."""
        return self.nif_emitente is not None or self.nif_cliente is not None


class PDFInvoiceParser:
    """Parses PDF invoices and extracts metadata."""

    # Portuguese NIF regex (9 digits)
    NIF_PATTERN = re.compile(r"\b(\d{9})\b")

    # Common date formats in Portuguese invoices
    DATE_PATTERNS = [
        (r"(\d{2})[/\-.](\d{2})[/\-.](\d{4})", "%d/%m/%Y"),  # DD/MM/YYYY
        (r"(\d{4})[/\-.](\d{2})[/\-.](\d{2})", "%Y/%m/%d"),  # YYYY/MM/DD
        (r"(\d{2}) de (\w+) de (\d{4})", "pt_month"),  # DD de Mês de YYYY
    ]

    # Portuguese month names
    PT_MONTHS = {
        "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
        "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
        "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
    }

    # Amount patterns
    AMOUNT_PATTERNS = [
        r"total[:\s]*€?\s*([\d\s]+[,.][\d]{2})",
        r"valor total[:\s]*€?\s*([\d\s]+[,.][\d]{2})",
        r"montante[:\s]*€?\s*([\d\s]+[,.][\d]{2})",
        r"a pagar[:\s]*€?\s*([\d\s]+[,.][\d]{2})",
        r"€\s*([\d\s]+[,.][\d]{2})",
    ]

    # Invoice number patterns
    INVOICE_NUMBER_PATTERNS = [
        r"fatura\s*n[º°.]?\s*[:.]?\s*([A-Z0-9/\-]+)",
        r"factura\s*n[º°.]?\s*[:.]?\s*([A-Z0-9/\-]+)",
        r"invoice\s*n[º°.]?\s*[:.]?\s*([A-Z0-9/\-]+)",
        r"n[º°.]\s*fatura\s*[:.]?\s*([A-Z0-9/\-]+)",
        r"documento\s*n[º°.]?\s*[:.]?\s*([A-Z0-9/\-]+)",
        r"ft\s+([A-Z0-9/\-]+)",  # FT followed by number
    ]

    def __init__(self):
        """Initialize PDF parser."""
        self.logger = get_logger(__name__)

    def extract_text(self, pdf_path: Path) -> str:
        """Extract text content from PDF.

        Args:
            pdf_path: Path to PDF file.

        Returns:
            Extracted text content.
        """
        try:
            with pdfplumber.open(pdf_path) as pdf:
                text_parts = []
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                return "\n".join(text_parts)
        except Exception as e:
            self.logger.error(f"Erro ao extrair texto de {pdf_path}: {e}")
            return ""

    def _extract_nifs(self, text: str) -> list[str]:
        """Extract all potential NIFs from text."""
        matches = self.NIF_PATTERN.findall(text)
        # Validate NIFs (basic validation - check digit)
        valid_nifs = []
        for nif in matches:
            if self._validate_nif(nif):
                valid_nifs.append(nif)
        return valid_nifs

    def _validate_nif(self, nif: str) -> bool:
        """Validate Portuguese NIF using check digit."""
        if len(nif) != 9:
            return False

        # First digit must be 1, 2, 5, 6, 7, 8, or 9
        if nif[0] not in "125678790":
            return False

        try:
            # Calculate check digit
            check_sum = 0
            for i, digit in enumerate(nif[:-1]):
                check_sum += int(digit) * (9 - i)

            remainder = check_sum % 11
            check_digit = 0 if remainder < 2 else 11 - remainder

            return int(nif[-1]) == check_digit
        except ValueError:
            return False

    def _parse_portuguese_date(self, day: str, month_name: str, year: str) -> Optional[date]:
        """Parse Portuguese format date (e.g., '15 de janeiro de 2024')."""
        month = self.PT_MONTHS.get(month_name.lower())
        if month:
            try:
                return date(int(year), month, int(day))
            except ValueError:
                pass
        return None

    def _extract_dates(self, text: str) -> list[date]:
        """Extract all dates from text."""
        dates = []

        # DD/MM/YYYY or similar
        pattern1 = re.compile(r"(\d{2})[/\-.](\d{2})[/\-.](\d{4})")
        for match in pattern1.finditer(text):
            try:
                d = date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
                dates.append(d)
            except ValueError:
                pass

        # Portuguese month format
        pattern2 = re.compile(r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})", re.IGNORECASE)
        for match in pattern2.finditer(text):
            d = self._parse_portuguese_date(match.group(1), match.group(2), match.group(3))
            if d:
                dates.append(d)

        return dates

    def _extract_amount(self, text: str) -> Optional[Decimal]:
        """Extract total amount from text."""
        text_lower = text.lower()

        for pattern in self.AMOUNT_PATTERNS:
            match = re.search(pattern, text_lower, re.IGNORECASE)
            if match:
                amount_str = match.group(1)
                # Clean up: remove spaces, convert comma to dot
                amount_str = amount_str.replace(" ", "").replace(",", ".")
                try:
                    return Decimal(amount_str)
                except Exception:
                    pass

        return None

    def _extract_invoice_number(self, text: str) -> Optional[str]:
        """Extract invoice number from text."""
        for pattern in self.INVOICE_NUMBER_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    def _extract_vendor_name(self, text: str, nifs: list[str]) -> Optional[str]:
        """Try to extract vendor name from text."""
        # Common patterns for vendor identification
        patterns = [
            r"^([A-Z][A-Za-z\s,\.]+(?:Lda|SA|S\.A\.|Unipessoal))",
            r"emitido por[:\s]*([A-Za-z\s]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.MULTILINE)
            if match:
                return match.group(1).strip()

        # If we have known NIFs, we could look them up (future enhancement)
        return None

    def parse(self, pdf_path: Path) -> InvoiceMetadata:
        """Parse PDF and extract invoice metadata.

        Args:
            pdf_path: Path to PDF file.

        Returns:
            InvoiceMetadata with extracted information.
        """
        self.logger.info(f"Parsing: {pdf_path.name}")

        text = self.extract_text(pdf_path)

        if not text:
            return InvoiceMetadata(file_path=pdf_path, raw_text="")

        # Extract NIFs
        nifs = self._extract_nifs(text)
        nif_emitente = nifs[0] if len(nifs) > 0 else None
        nif_cliente = nifs[1] if len(nifs) > 1 else None

        # Extract dates
        dates = self._extract_dates(text)
        invoice_date = min(dates) if dates else None

        # Extract amount
        total_amount = self._extract_amount(text)

        # Extract invoice number
        invoice_number = self._extract_invoice_number(text)

        # Extract vendor name
        vendor_name = self._extract_vendor_name(text, nifs)

        return InvoiceMetadata(
            file_path=pdf_path,
            raw_text=text,
            nif_emitente=nif_emitente,
            nif_cliente=nif_cliente,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            total_amount=total_amount,
            vendor_name=vendor_name,
        )

    def parse_multiple(self, pdf_paths: list[Path]) -> list[InvoiceMetadata]:
        """Parse multiple PDFs.

        Args:
            pdf_paths: List of PDF file paths.

        Returns:
            List of InvoiceMetadata objects.
        """
        results = []
        for path in pdf_paths:
            if path.suffix.lower() == ".pdf":
                metadata = self.parse(path)
                results.append(metadata)
        return results
