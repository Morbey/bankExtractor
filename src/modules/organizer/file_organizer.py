"""Invoice file organizer - categorizes and organizes invoice files."""

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.categories import InvoiceCategory, InvoiceCategorizer
from src.core.config import settings
from src.core.iban_manager import get_iban_manager
from src.core.logger import get_logger
from src.modules.invoices.pdf_parser import InvoiceMetadata, PDFInvoiceParser


@dataclass
class OrganizedInvoice:
    """Result of organizing an invoice."""

    original_path: Path
    destination_path: Path
    category: InvoiceCategory
    metadata: Optional[InvoiceMetadata] = None
    success: bool = True
    error: Optional[str] = None


class InvoiceOrganizer:
    """Organizes invoice files into category folders."""

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        categorizer: Optional[InvoiceCategorizer] = None,
        pdf_parser: Optional[PDFInvoiceParser] = None,
        organize_by_year: bool = True,
    ):
        """Initialize organizer.

        Args:
            base_dir: Base directory for organized invoices (default: data/faturas)
            categorizer: Custom categorizer (uses default if not provided)
            pdf_parser: PDF parser instance (creates new if not provided)
            organize_by_year: If True, creates year subfolders within categories
        """
        self.base_dir = base_dir or settings.data_dir / "faturas"
        self.categorizer = categorizer or InvoiceCategorizer()
        self.pdf_parser = pdf_parser or PDFInvoiceParser()
        self.organize_by_year = organize_by_year
        self.logger = get_logger(__name__)

        # Ensure base directory exists
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_category_folder(
        self,
        category: InvoiceCategory,
        year: Optional[int] = None,
    ) -> Path:
        """Get the folder path for a category.

        Structure: base_dir/ano/categoria/ (e.g., data/faturas/2026/agua/)

        Args:
            category: Invoice category.
            year: Year for folder (if organize_by_year is True).

        Returns:
            Path to category folder.
        """
        # Structure: ano/categoria (e.g., 2026/agua)
        if self.organize_by_year and year:
            folder = self.base_dir / str(year) / self.categorizer.get_folder_name(category)
        else:
            folder = self.base_dir / self.categorizer.get_folder_name(category)

        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def categorize_file(
        self,
        file_path: Path,
        sender: Optional[str] = None,
        subject: Optional[str] = None,
    ) -> tuple[InvoiceCategory, InvoiceMetadata]:
        """Categorize a file based on content and optional email info.

        Args:
            file_path: Path to PDF file.
            sender: Email sender (if from email).
            subject: Email subject (if from email).

        Returns:
            Tuple of (category, metadata).
        """
        # Parse PDF for content analysis
        metadata = self.pdf_parser.parse(file_path)

        # Try to categorize using all available info
        category = self.categorizer.categorize(
            sender=sender,
            subject=subject,
            content=metadata.raw_text,
        )

        return category, metadata

    def organize_file(
        self,
        file_path: Path,
        sender: Optional[str] = None,
        subject: Optional[str] = None,
        move: bool = False,
        add_date_prefix: bool = True,
    ) -> OrganizedInvoice:
        """Organize a single invoice file into the appropriate category folder.

        Args:
            file_path: Path to the invoice file.
            sender: Email sender (for categorization).
            subject: Email subject (for categorization).
            move: If True, moves file. If False, copies file.
            add_date_prefix: Add date prefix to filename.

        Returns:
            OrganizedInvoice with result information.
        """
        try:
            if not file_path.exists():
                return OrganizedInvoice(
                    original_path=file_path,
                    destination_path=file_path,
                    category=InvoiceCategory.OUTROS,
                    success=False,
                    error="Ficheiro não encontrado",
                )

            # Categorize the file
            category, metadata = self.categorize_file(file_path, sender, subject)

            # Determine the year for organization
            if metadata.invoice_date:
                invoice_year = metadata.invoice_date.year
                date_prefix = metadata.invoice_date.strftime("%Y%m%d")
            else:
                invoice_year = datetime.now().year
                date_prefix = datetime.now().strftime("%Y%m%d")

            # Get destination folder (with year subfolder if enabled)
            dest_folder = self.get_category_folder(category, year=invoice_year)

            # Special handling for bank documents - organize by IBAN
            if category == InvoiceCategory.BANCARIO and metadata.raw_text:
                iban_manager = get_iban_manager()
                iban = iban_manager.extract_iban_from_text(metadata.raw_text)
                if iban:
                    account_folder = iban_manager.get_or_prompt_folder(iban)
                    dest_folder = dest_folder / account_folder
                    dest_folder.mkdir(parents=True, exist_ok=True)

            # Build destination filename
            if not add_date_prefix:
                date_prefix = ""

            # Clean filename
            original_name = file_path.name
            if date_prefix and not original_name.startswith(date_prefix):
                dest_filename = f"{date_prefix}_{original_name}"
            else:
                dest_filename = original_name

            dest_path = dest_folder / dest_filename

            # Handle duplicates
            counter = 1
            while dest_path.exists():
                stem = dest_path.stem
                suffix = dest_path.suffix
                # Remove previous counter if exists
                if f"_{counter-1}" in stem:
                    stem = stem.rsplit(f"_{counter-1}", 1)[0]
                dest_path = dest_folder / f"{stem}_{counter}{suffix}"
                counter += 1

            # Move or copy file
            if move:
                shutil.move(str(file_path), str(dest_path))
                self.logger.info(f"Movido: {file_path.name} -> {category.value}/")
            else:
                shutil.copy2(str(file_path), str(dest_path))
                self.logger.info(f"Copiado: {file_path.name} -> {category.value}/")

            return OrganizedInvoice(
                original_path=file_path,
                destination_path=dest_path,
                category=category,
                metadata=metadata,
                success=True,
            )

        except Exception as e:
            self.logger.error(f"Erro ao organizar {file_path}: {e}")
            return OrganizedInvoice(
                original_path=file_path,
                destination_path=file_path,
                category=InvoiceCategory.OUTROS,
                success=False,
                error=str(e),
            )

    def organize_directory(
        self,
        source_dir: Path,
        move: bool = False,
        recursive: bool = False,
    ) -> list[OrganizedInvoice]:
        """Organize all PDF files in a directory.

        Args:
            source_dir: Directory containing invoice files.
            move: If True, moves files. If False, copies files.
            recursive: If True, processes subdirectories.

        Returns:
            List of OrganizedInvoice results.
        """
        results = []

        if recursive:
            pdf_files = list(source_dir.rglob("*.pdf"))
        else:
            pdf_files = list(source_dir.glob("*.pdf"))

        self.logger.info(f"Encontrados {len(pdf_files)} ficheiros PDF em {source_dir}")

        for pdf_file in pdf_files:
            # Skip if already in a category folder
            if pdf_file.parent != source_dir and pdf_file.parent.parent == self.base_dir:
                self.logger.debug(f"Ignorando {pdf_file} (já categorizado)")
                continue

            result = self.organize_file(pdf_file, move=move)
            results.append(result)

        return results

    def get_category_stats(self) -> dict[InvoiceCategory, int]:
        """Get count of files in each category folder.

        Returns:
            Dictionary mapping category to file count.
        """
        stats = {}

        for category in InvoiceCategory:
            count = 0
            cat_name = self.categorizer.get_folder_name(category)

            # Search in all year folders: base_dir/*/categoria/
            for year_folder in self.base_dir.iterdir():
                if year_folder.is_dir() and year_folder.name.isdigit():
                    cat_folder = year_folder / cat_name
                    if cat_folder.exists():
                        count += len(list(cat_folder.glob("*.pdf")))

            # Also check base_dir/categoria/ (no year)
            direct_folder = self.base_dir / cat_name
            if direct_folder.exists():
                count += len(list(direct_folder.glob("*.pdf")))

            if count > 0:
                stats[category] = count

        return stats

    def list_category_files(
        self,
        category: InvoiceCategory,
        year: Optional[int] = None,
    ) -> list[Path]:
        """List all files in a category folder.

        Args:
            category: The category to list.
            year: Optional year to filter by.

        Returns:
            List of file paths.
        """
        cat_name = self.categorizer.get_folder_name(category)
        files = []

        if year:
            # Specific year: base_dir/ano/categoria/
            folder = self.base_dir / str(year) / cat_name
            if folder.exists():
                files = list(folder.glob("*.pdf"))
        else:
            # All years: search in base_dir/*/categoria/
            for year_folder in self.base_dir.iterdir():
                if year_folder.is_dir() and year_folder.name.isdigit():
                    cat_folder = year_folder / cat_name
                    if cat_folder.exists():
                        files.extend(cat_folder.glob("*.pdf"))

            # Also check base_dir/categoria/ (no year)
            direct_folder = self.base_dir / cat_name
            if direct_folder.exists():
                files.extend(direct_folder.glob("*.pdf"))

        return sorted(files)

    def recategorize_file(
        self,
        file_path: Path,
        new_category: InvoiceCategory,
        year: Optional[int] = None,
        move: bool = True,
    ) -> OrganizedInvoice:
        """Manually recategorize a file to a different category.

        Args:
            file_path: Path to the file to recategorize.
            new_category: New category for the file.
            year: Year for organization (if organize_by_year is enabled).
            move: If True, moves file. If False, copies.

        Returns:
            OrganizedInvoice with result.
        """
        try:
            if not file_path.exists():
                return OrganizedInvoice(
                    original_path=file_path,
                    destination_path=file_path,
                    category=new_category,
                    success=False,
                    error="Ficheiro não encontrado",
                )

            # Try to extract year from filename if not provided
            if not year and self.organize_by_year:
                # Try to get year from filename (YYYYMMDD_ prefix)
                name = file_path.stem
                if len(name) >= 8 and name[:8].isdigit():
                    year = int(name[:4])
                else:
                    year = datetime.now().year

            dest_folder = self.get_category_folder(new_category, year=year)
            dest_path = dest_folder / file_path.name

            # Handle duplicates
            counter = 1
            while dest_path.exists():
                stem = file_path.stem
                suffix = file_path.suffix
                dest_path = dest_folder / f"{stem}_{counter}{suffix}"
                counter += 1

            if move:
                shutil.move(str(file_path), str(dest_path))
                self.logger.info(f"Recategorizado: {file_path.name} -> {new_category.value}/")
            else:
                shutil.copy2(str(file_path), str(dest_path))

            return OrganizedInvoice(
                original_path=file_path,
                destination_path=dest_path,
                category=new_category,
                success=True,
            )

        except Exception as e:
            return OrganizedInvoice(
                original_path=file_path,
                destination_path=file_path,
                category=new_category,
                success=False,
                error=str(e),
            )
