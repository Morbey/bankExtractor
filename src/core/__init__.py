"""Core utilities and shared functionality."""

from .category_manager import Category, CategoryManager, get_category_manager
from .classification_rules import (
    ClassificationRule,
    ClassificationRulesEngine,
    MatchSource,
    MatchType,
    RuleAction,
    RuleCondition,
    RuleMatch,
    get_rules_engine,
)
from .config import settings
from .credentials import CredentialManager
from .document_registry import (
    AccountingScope,
    DocumentRecord,
    DocumentRegistry,
    DocumentStatus,
    DocumentType,
    Entity,
    EntityType,
    get_document_registry,
)
from .iban_manager import IBANManager, get_iban_manager
from .logger import get_logger
from .transfer_manager import TransferInfo, TransferManager, get_transfer_manager

__all__ = [
    "settings",
    "CredentialManager",
    "get_logger",
    "IBANManager",
    "get_iban_manager",
    "TransferManager",
    "TransferInfo",
    "get_transfer_manager",
    "DocumentRegistry",
    "DocumentRecord",
    "DocumentType",
    "DocumentStatus",
    "Entity",
    "EntityType",
    "AccountingScope",
    "get_document_registry",
    "ClassificationRulesEngine",
    "ClassificationRule",
    "RuleCondition",
    "RuleMatch",
    "RuleAction",
    "MatchSource",
    "MatchType",
    "get_rules_engine",
    "CategoryManager",
    "Category",
    "get_category_manager",
]
