"""Classification Rules Manager - Persistent rule storage and learning.

This module manages classification rules for automatic invoice categorization:
- Load/save rules from JSON file
- Learn from manual classifications
- Match rules by sender, body patterns, or PDF content
"""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.core.categories import CategoryRule, InvoiceCategory, InvoiceCategorizer
from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class LearnedRule:
    """A rule learned from manual classification."""

    id: str
    category: str
    rule_type: str  # "sender", "body_pattern", "pdf_pattern", "nif"
    pattern: str  # The pattern to match
    confidence: float = 1.0  # Confidence score (can increase with usage)
    match_count: int = 0  # Number of times this rule matched
    created_at: str = ""
    last_used: str = ""
    source: str = ""  # Where this rule came from (e.g., "manual", "entity_link")


@dataclass
class ClassificationResult:
    """Result of classifying an invoice."""

    category: InvoiceCategory
    confidence: float
    matched_rule: Optional[LearnedRule] = None
    matched_by: str = ""  # "sender", "body", "pdf", "default"


class ClassificationRulesManager:
    """Manages classification rules with persistence and learning."""

    RULES_FILE = "classification_rules.json"

    def __init__(self, data_dir: Optional[Path] = None):
        """Initialize the rules manager.

        Args:
            data_dir: Directory for storing rules. Defaults to settings.data_dir.
        """
        self.data_dir = data_dir or settings.data_dir
        self.rules_file = self.data_dir / self.RULES_FILE
        self.rules: list[LearnedRule] = []
        self._categorizer = InvoiceCategorizer()
        self._load_rules()

    def _load_rules(self) -> None:
        """Load rules from JSON file."""
        if not self.rules_file.exists():
            self.rules = []
            return

        try:
            with open(self.rules_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.rules = [LearnedRule(**rule) for rule in data.get("rules", [])]
            logger.info(f"Loaded {len(self.rules)} classification rules.")
        except Exception as e:
            logger.error(f"Error loading rules: {e}")
            self.rules = []

    def _save_rules(self) -> None:
        """Save rules to JSON file."""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            data = {
                "version": "1.0",
                "updated_at": datetime.now().isoformat(),
                "rules": [asdict(rule) for rule in self.rules],
            }
            with open(self.rules_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved {len(self.rules)} classification rules.")
        except Exception as e:
            logger.error(f"Error saving rules: {e}")

    def _generate_rule_id(self) -> str:
        """Generate a unique rule ID."""
        import uuid
        return f"rule_{uuid.uuid4().hex[:8]}"

    def add_sender_rule(
        self,
        sender_email: str,
        category: InvoiceCategory,
        source: str = "manual",
    ) -> LearnedRule:
        """Add a rule based on sender email.

        Args:
            sender_email: The sender email address or pattern.
            category: The category to assign.
            source: Where the rule came from.

        Returns:
            The created rule.
        """
        # Extract domain for more general matching
        pattern = sender_email.lower()

        # Check if similar rule exists
        existing = self._find_rule_by_pattern(pattern, "sender")
        if existing:
            existing.category = category.value
            existing.match_count += 1
            existing.last_used = datetime.now().isoformat()
            self._save_rules()
            return existing

        rule = LearnedRule(
            id=self._generate_rule_id(),
            category=category.value,
            rule_type="sender",
            pattern=pattern,
            created_at=datetime.now().isoformat(),
            source=source,
        )
        self.rules.append(rule)
        self._save_rules()
        logger.info(f"Added sender rule: {pattern} -> {category.value}")
        return rule

    def add_body_pattern_rule(
        self,
        pattern: str,
        category: InvoiceCategory,
        source: str = "manual",
    ) -> LearnedRule:
        """Add a rule based on email body pattern.

        Args:
            pattern: Regex pattern to match in email body.
            category: The category to assign.
            source: Where the rule came from.

        Returns:
            The created rule.
        """
        existing = self._find_rule_by_pattern(pattern, "body_pattern")
        if existing:
            existing.category = category.value
            existing.match_count += 1
            existing.last_used = datetime.now().isoformat()
            self._save_rules()
            return existing

        rule = LearnedRule(
            id=self._generate_rule_id(),
            category=category.value,
            rule_type="body_pattern",
            pattern=pattern,
            created_at=datetime.now().isoformat(),
            source=source,
        )
        self.rules.append(rule)
        self._save_rules()
        logger.info(f"Added body pattern rule: {pattern} -> {category.value}")
        return rule

    def add_pdf_pattern_rule(
        self,
        pattern: str,
        category: InvoiceCategory,
        source: str = "manual",
    ) -> LearnedRule:
        """Add a rule based on PDF content pattern.

        Args:
            pattern: Regex pattern to match in PDF content.
            category: The category to assign.
            source: Where the rule came from.

        Returns:
            The created rule.
        """
        existing = self._find_rule_by_pattern(pattern, "pdf_pattern")
        if existing:
            existing.category = category.value
            existing.match_count += 1
            existing.last_used = datetime.now().isoformat()
            self._save_rules()
            return existing

        rule = LearnedRule(
            id=self._generate_rule_id(),
            category=category.value,
            rule_type="pdf_pattern",
            pattern=pattern,
            created_at=datetime.now().isoformat(),
            source=source,
        )
        self.rules.append(rule)
        self._save_rules()
        logger.info(f"Added PDF pattern rule: {pattern} -> {category.value}")
        return rule

    def add_nif_rule(
        self,
        nif: str,
        category: InvoiceCategory,
        source: str = "manual",
    ) -> LearnedRule:
        """Add a rule based on NIF (Portuguese tax number).

        Args:
            nif: The NIF to match.
            category: The category to assign.
            source: Where the rule came from.

        Returns:
            The created rule.
        """
        existing = self._find_rule_by_pattern(nif, "nif")
        if existing:
            existing.category = category.value
            existing.match_count += 1
            existing.last_used = datetime.now().isoformat()
            self._save_rules()
            return existing

        rule = LearnedRule(
            id=self._generate_rule_id(),
            category=category.value,
            rule_type="nif",
            pattern=nif,
            created_at=datetime.now().isoformat(),
            source=source,
        )
        self.rules.append(rule)
        self._save_rules()
        logger.info(f"Added NIF rule: {nif} -> {category.value}")
        return rule

    def _find_rule_by_pattern(
        self,
        pattern: str,
        rule_type: str,
    ) -> Optional[LearnedRule]:
        """Find an existing rule by pattern and type."""
        pattern_lower = pattern.lower()
        for rule in self.rules:
            if rule.rule_type == rule_type and rule.pattern.lower() == pattern_lower:
                return rule
        return None

    def classify(
        self,
        sender: Optional[str] = None,
        email_body: Optional[str] = None,
        pdf_content: Optional[str] = None,
        nifs: Optional[list[str]] = None,
    ) -> ClassificationResult:
        """Classify an invoice using learned rules and default rules.

        Args:
            sender: Email sender address.
            email_body: Email body text.
            pdf_content: Extracted PDF text.
            nifs: List of NIFs found in the invoice.

        Returns:
            ClassificationResult with category and match info.
        """
        # Try learned rules first (higher priority)
        result = self._try_learned_rules(sender, email_body, pdf_content, nifs)
        if result:
            return result

        # Fall back to default categorizer
        category = self._categorizer.categorize(
            sender=sender,
            subject="",  # We don't have subject separately in this context
            content=pdf_content,
        )

        matched_by = "default"
        if sender and self._categorizer.categorize_by_sender(sender) != InvoiceCategory.OUTROS:
            matched_by = "default_sender"
        elif pdf_content and self._categorizer.categorize_by_content(pdf_content) != InvoiceCategory.OUTROS:
            matched_by = "default_content"

        return ClassificationResult(
            category=category,
            confidence=0.7 if category != InvoiceCategory.OUTROS else 0.0,
            matched_by=matched_by,
        )

    def _try_learned_rules(
        self,
        sender: Optional[str],
        email_body: Optional[str],
        pdf_content: Optional[str],
        nifs: Optional[list[str]],
    ) -> Optional[ClassificationResult]:
        """Try to classify using learned rules.

        Returns:
            ClassificationResult if a rule matches, None otherwise.
        """
        # Sort rules by match_count (most reliable first)
        sorted_rules = sorted(self.rules, key=lambda r: r.match_count, reverse=True)

        for rule in sorted_rules:
            try:
                if rule.rule_type == "sender" and sender:
                    if rule.pattern.lower() in sender.lower():
                        self._update_rule_usage(rule)
                        return ClassificationResult(
                            category=InvoiceCategory(rule.category),
                            confidence=min(0.9 + (rule.match_count * 0.01), 1.0),
                            matched_rule=rule,
                            matched_by="sender",
                        )

                elif rule.rule_type == "body_pattern" and email_body:
                    if re.search(rule.pattern, email_body, re.IGNORECASE):
                        self._update_rule_usage(rule)
                        return ClassificationResult(
                            category=InvoiceCategory(rule.category),
                            confidence=min(0.85 + (rule.match_count * 0.01), 1.0),
                            matched_rule=rule,
                            matched_by="body",
                        )

                elif rule.rule_type == "pdf_pattern" and pdf_content:
                    if re.search(rule.pattern, pdf_content, re.IGNORECASE):
                        self._update_rule_usage(rule)
                        return ClassificationResult(
                            category=InvoiceCategory(rule.category),
                            confidence=min(0.8 + (rule.match_count * 0.01), 1.0),
                            matched_rule=rule,
                            matched_by="pdf",
                        )

                elif rule.rule_type == "nif" and nifs:
                    if rule.pattern in nifs:
                        self._update_rule_usage(rule)
                        return ClassificationResult(
                            category=InvoiceCategory(rule.category),
                            confidence=min(0.95 + (rule.match_count * 0.005), 1.0),
                            matched_rule=rule,
                            matched_by="nif",
                        )

            except Exception as e:
                logger.debug(f"Error applying rule {rule.id}: {e}")
                continue

        return None

    def _update_rule_usage(self, rule: LearnedRule) -> None:
        """Update rule usage statistics."""
        rule.match_count += 1
        rule.last_used = datetime.now().isoformat()
        self._save_rules()

    def learn_from_classification(
        self,
        sender: Optional[str],
        email_body: Optional[str],
        pdf_content: Optional[str],
        nifs: Optional[list[str]],
        category: InvoiceCategory,
    ) -> list[LearnedRule]:
        """Learn rules from a manual classification.

        Creates rules based on available information to improve future classifications.

        Args:
            sender: Email sender address.
            email_body: Email body text.
            pdf_content: Extracted PDF text.
            nifs: List of NIFs found.
            category: The category assigned by user.

        Returns:
            List of created rules.
        """
        created_rules = []

        # Always create sender rule if available (most reliable)
        if sender:
            rule = self.add_sender_rule(sender, category, source="learned")
            created_rules.append(rule)

        # Create NIF rules (very reliable)
        if nifs:
            for nif in nifs[:2]:  # Limit to first 2 NIFs
                rule = self.add_nif_rule(nif, category, source="learned")
                created_rules.append(rule)

        return created_rules

    def get_all_rules(self) -> list[LearnedRule]:
        """Get all learned rules."""
        return self.rules.copy()

    def get_rules_by_category(self, category: InvoiceCategory) -> list[LearnedRule]:
        """Get rules for a specific category."""
        return [r for r in self.rules if r.category == category.value]

    def get_rules_by_type(self, rule_type: str) -> list[LearnedRule]:
        """Get rules of a specific type."""
        return [r for r in self.rules if r.rule_type == rule_type]

    def delete_rule(self, rule_id: str) -> bool:
        """Delete a rule by ID.

        Args:
            rule_id: The rule ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        for i, rule in enumerate(self.rules):
            if rule.id == rule_id:
                del self.rules[i]
                self._save_rules()
                logger.info(f"Deleted rule: {rule_id}")
                return True
        return False

    def clear_all_rules(self) -> int:
        """Clear all learned rules.

        Returns:
            Number of rules deleted.
        """
        count = len(self.rules)
        self.rules = []
        self._save_rules()
        logger.info(f"Cleared {count} rules.")
        return count

    def export_rules(self, output_file: Path) -> bool:
        """Export rules to a JSON file.

        Args:
            output_file: Path to export file.

        Returns:
            True if successful.
        """
        try:
            data = {
                "version": "1.0",
                "exported_at": datetime.now().isoformat(),
                "rules": [asdict(rule) for rule in self.rules],
            }
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Error exporting rules: {e}")
            return False

    def import_rules(self, input_file: Path, merge: bool = True) -> int:
        """Import rules from a JSON file.

        Args:
            input_file: Path to import file.
            merge: If True, merge with existing rules. If False, replace all.

        Returns:
            Number of rules imported.
        """
        try:
            with open(input_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            imported = [LearnedRule(**rule) for rule in data.get("rules", [])]

            if not merge:
                self.rules = imported
            else:
                # Merge, avoiding duplicates
                existing_patterns = {(r.rule_type, r.pattern.lower()) for r in self.rules}
                for rule in imported:
                    key = (rule.rule_type, rule.pattern.lower())
                    if key not in existing_patterns:
                        self.rules.append(rule)
                        existing_patterns.add(key)

            self._save_rules()
            return len(imported)
        except Exception as e:
            logger.error(f"Error importing rules: {e}")
            return 0


# Singleton instance
_rules_manager: Optional[ClassificationRulesManager] = None


def get_rules_manager() -> ClassificationRulesManager:
    """Get the global rules manager instance."""
    global _rules_manager
    if _rules_manager is None:
        _rules_manager = ClassificationRulesManager()
    return _rules_manager
