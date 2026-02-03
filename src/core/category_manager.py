"""Category management system for invoice and document organization.

This module provides:
- JSON-based category storage
- Category CRUD operations
- Category validation and normalization
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Category:
    """Represents an invoice/document category."""

    id: str
    nome: str
    descricao: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "nome": self.nome,
            "descricao": self.descricao,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Category":
        """Create Category from dictionary."""
        return cls(
            id=data["id"],
            nome=data["nome"],
            descricao=data.get("descricao", ""),
        )


# Default categories with Portuguese names and descriptions
DEFAULT_CATEGORIES: list[dict] = [
    {"id": "agua", "nome": "Agua", "descricao": "EPAL, SMAS, SIMAS"},
    {"id": "bancario", "nome": "Bancario", "descricao": "CGD, Banco CTT, Millennium"},
    {"id": "combustivel", "nome": "Combustivel", "descricao": "Galp, BP, Repsol"},
    {"id": "comunicacoes", "nome": "Comunicacoes", "descricao": "Vodafone, NOS, MEO"},
    {"id": "educacao", "nome": "Educacao", "descricao": "Escolas, Colegios, Creches"},
    {"id": "energia", "nome": "Energia", "descricao": "EDP, Galp, Endesa"},
    {"id": "saude", "nome": "Saude", "descricao": "Farmacias, Hospitais, Clinicas"},
    {"id": "seguros", "nome": "Seguros", "descricao": "Fidelidade, Allianz, Tranquilidade"},
    {"id": "software", "nome": "Software", "descricao": "Microsoft, Google, Adobe"},
    {"id": "transportes", "nome": "Transportes", "descricao": "Uber, Bolt, CP"},
    {"id": "via_verde", "nome": "Via Verde", "descricao": "Portagens, Via Verde"},
    {"id": "outros", "nome": "Outros", "descricao": "Outros documentos"},
]


class CategoryManager:
    """Manages document categories stored in JSON file."""

    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize category manager.

        Args:
            config_dir: Directory for configuration files.
                       Defaults to settings.data_dir.
        """
        self.config_dir = config_dir or settings.data_dir
        self.categories_path = self.config_dir / "categorias.json"
        self._categories: dict[str, Category] = {}
        self._load_categories()

    def _load_categories(self) -> None:
        """Load categories from JSON file, creating with defaults if not exists."""
        if self.categories_path.exists():
            try:
                with open(self.categories_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for cat_data in data.get("categorias", []):
                        category = Category.from_dict(cat_data)
                        self._categories[category.id] = category
                logger.debug(f"Loaded {len(self._categories)} categories")
            except Exception as e:
                logger.error(f"Error loading categories: {e}")
                self._initialize_defaults()
        else:
            self._initialize_defaults()

    def _initialize_defaults(self) -> None:
        """Initialize with default categories."""
        logger.info("Initializing default categories")
        for cat_data in DEFAULT_CATEGORIES:
            category = Category.from_dict(cat_data)
            self._categories[category.id] = category
        self._save_categories()

    def _save_categories(self) -> None:
        """Save categories to JSON file."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            data = {"categorias": [cat.to_dict() for cat in self._categories.values()]}
            with open(self.categories_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved {len(self._categories)} categories")
        except Exception as e:
            logger.error(f"Error saving categories: {e}")

    def get_all_categories(self) -> list[Category]:
        """Get all categories sorted alphabetically by name.

        Returns:
            List of Category objects sorted by name.
        """
        return sorted(self._categories.values(), key=lambda c: c.nome.lower())

    def get_category(self, category_id: str) -> Optional[Category]:
        """Get category by ID.

        Args:
            category_id: The category ID to look up.

        Returns:
            Category if found, None otherwise.
        """
        return self._categories.get(category_id)

    def category_exists(self, category_id: str) -> bool:
        """Check if a category exists.

        Args:
            category_id: The category ID to check.

        Returns:
            True if category exists, False otherwise.
        """
        return category_id in self._categories

    def add_category(
        self,
        category_id: str,
        nome: str,
        descricao: str = "",
    ) -> Category:
        """Add a new category.

        Args:
            category_id: Unique identifier for the category.
            nome: Display name for the category.
            descricao: Optional description.

        Returns:
            The created Category object.

        Raises:
            ValueError: If category with same ID already exists.
        """
        # Normalize ID
        normalized_id = self._normalize_id(category_id)

        if normalized_id in self._categories:
            raise ValueError(f"Categoria com ID '{normalized_id}' ja existe")

        category = Category(
            id=normalized_id,
            nome=nome,
            descricao=descricao,
        )
        self._categories[normalized_id] = category
        self._save_categories()
        logger.info(f"Added category: {nome} ({normalized_id})")
        return category

    def update_category(
        self,
        category_id: str,
        nome: Optional[str] = None,
        descricao: Optional[str] = None,
    ) -> Optional[Category]:
        """Update an existing category.

        Args:
            category_id: ID of category to update.
            nome: New name (optional).
            descricao: New description (optional).

        Returns:
            Updated Category or None if not found.
        """
        category = self._categories.get(category_id)
        if not category:
            return None

        if nome is not None:
            category.nome = nome
        if descricao is not None:
            category.descricao = descricao

        self._save_categories()
        logger.info(f"Updated category: {category.nome}")
        return category

    def delete_category(self, category_id: str) -> bool:
        """Delete a category.

        Args:
            category_id: ID of category to delete.

        Returns:
            True if deleted, False if not found.
        """
        if category_id in self._categories:
            category_name = self._categories[category_id].nome
            del self._categories[category_id]
            self._save_categories()
            logger.info(f"Deleted category: {category_name}")
            return True
        return False

    def _normalize_id(self, category_id: str) -> str:
        """Normalize category ID for consistent storage.

        Args:
            category_id: Raw category ID.

        Returns:
            Normalized ID (lowercase, underscores instead of spaces).
        """
        return category_id.lower().replace(" ", "_").replace("-", "_")

    def get_category_by_name(self, nome: str) -> Optional[Category]:
        """Find category by name (case-insensitive).

        Args:
            nome: Category name to search for.

        Returns:
            Category if found, None otherwise.
        """
        nome_lower = nome.lower()
        for category in self._categories.values():
            if category.nome.lower() == nome_lower:
                return category
        return None


# Global instance
_manager: Optional[CategoryManager] = None


def get_category_manager() -> CategoryManager:
    """Get the global category manager instance."""
    global _manager
    if _manager is None:
        _manager = CategoryManager()
    return _manager
