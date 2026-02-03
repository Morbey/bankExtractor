"""Invoice file organizer - categorizes and organizes invoice files."""

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.categories import InvoiceCategory, InvoiceCategorizer
from src.core.config import settings
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
    ):
        """Initialize organizer.

        Args:
            base_dir: Base directory for organized invoices (default: data/faturas)
            categorizer: Custom categorizer (uses default if not provided)
            pdf_parser: PDF parser instance (creates new if not provided)
        """
        self.base_dir = base_dir or settings.data_dir / "faturas"
        self.categorizer = categorizer or InvoiceCategorizer()
        self.pdf_parser = pdf_parser or PDFInvoiceParser()
        self.logger = get_logger(__name__)

        # Ensure base directory exists
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_category_folder(self, category: InvoiceCategory) -> Path:
        """Get the folder path for a category.

        Args:
            category: Invoice category.

        Returns:
            Path to category folder.
        """
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

            # Get destination folder
            dest_folder = self.get_category_folder(category)

            # Build destination filename
            if add_date_prefix and metadata.invoice_date:
                date_prefix = metadata.invoice_date.strftime("%Y%m%d")
            else:
                date_prefix = datetime.now().strftime("%Y%m%d")

            # Clean filename
            original_name = file_path.name
            if not original_name.startswith(date_prefix):
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
            folder = self.base_dir / self.categorizer.get_folder_name(category)
            if folder.exists():
                count = len(list(folder.glob("*.pdf")))
                if count > 0:
                    stats[category] = count

        return stats

    def list_category_files(self, category: InvoiceCategory) -> list[Path]:
        """List all files in a category folder.

        Args:
            category: The category to list.

        Returns:
            List of file paths.
        """
        folder = self.get_category_folder(category)
        return sorted(folder.glob("*.pdf"))

    def recategorize_file(
        self,
        file_path: Path,
        new_category: InvoiceCategory,
        move: bool = True,
    ) -> OrganizedInvoice:
        """Manually recategorize a file to a different category.

        Args:
            file_path: Path to the file to recategorize.
            new_category: New category for the file.
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

            dest_folder = self.get_category_folder(new_category)
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
