"""Classification Rules Engine - Automatic document classification based on configurable rules.

This module provides:
- Flexible rule definitions for matching documents
- Multiple match types: exact, contains, regex
- Multiple match sources: sender, subject, body, PDF content, NIF
- Rule persistence and management
- Priority-based rule evaluation
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import uuid4

from rich.console import Console
from rich.table import Table

from src.core.config import settings
from src.core.logger import get_logger

console = Console()
logger = get_logger(__name__)


class MatchType(str, Enum):
    """How to match the pattern against the value."""

    EXACT = "exact"  # Exact match (case-insensitive)
    CONTAINS = "contains"  # Value contains pattern
    REGEX = "regex"  # Regular expression match
    STARTS_WITH = "starts_with"  # Value starts with pattern
    ENDS_WITH = "ends_with"  # Value ends with pattern


class MatchSource(str, Enum):
    """What field to match against."""

    SENDER_EMAIL = "sender_email"  # Email sender address
    SENDER_NAME = "sender_name"  # Email sender display name
    SUBJECT = "subject"  # Email subject
    BODY = "body"  # Email body content
    PDF_CONTENT = "pdf_content"  # Full PDF text
    PDF_NIF = "pdf_nif"  # NIF found in PDF
    PDF_VENDOR = "pdf_vendor"  # Vendor name from PDF
    FILENAME = "filename"  # Attachment filename


class RuleAction(str, Enum):
    """What action to take when rule matches."""

    ASSIGN_ENTITY = "assign_entity"  # Assign to entity by ID
    ASSIGN_CATEGORY = "assign_category"  # Assign invoice category
    ASSIGN_DOCUMENT_TYPE = "assign_document_type"  # Set document type
    MARK_IGNORE = "mark_ignore"  # Ignore/skip this document


@dataclass
class RuleCondition:
    """A single condition within a rule."""

    source: MatchSource
    match_type: MatchType
    pattern: str
    case_sensitive: bool = False

    def matches(self, data: dict) -> bool:
        """Check if this condition matches the provided data.

        Args:
            data: Dictionary with keys matching MatchSource values.

        Returns:
            True if condition matches.
        """
        value = data.get(self.source.value, "")
        if value is None:
            value = ""

        if not self.case_sensitive:
            value = value.lower()
            pattern = self.pattern.lower()
        else:
            pattern = self.pattern

        try:
            if self.match_type == MatchType.EXACT:
                return value == pattern
            elif self.match_type == MatchType.CONTAINS:
                return pattern in value
            elif self.match_type == MatchType.STARTS_WITH:
                return value.startswith(pattern)
            elif self.match_type == MatchType.ENDS_WITH:
                return value.endswith(pattern)
            elif self.match_type == MatchType.REGEX:
                flags = 0 if self.case_sensitive else re.IGNORECASE
                return bool(re.search(self.pattern, value, flags))
        except Exception as e:
            logger.error(f"Error matching condition: {e}")
            return False

        return False

    def to_dict(self) -> dict:
        return {
            "source": self.source.value,
            "match_type": self.match_type.value,
            "pattern": self.pattern,
            "case_sensitive": self.case_sensitive,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RuleCondition":
        return cls(
            source=MatchSource(data["source"]),
            match_type=MatchType(data["match_type"]),
            pattern=data["pattern"],
            case_sensitive=data.get("case_sensitive", False),
        )


@dataclass
class ClassificationRule:
    """A classification rule with conditions and actions."""

    id: str
    name: str
    description: str
    conditions: list[RuleCondition]
    action: RuleAction
    action_value: str  # Entity ID, category name, or document type
    priority: int = 100  # Lower = higher priority
    enabled: bool = True
    match_all: bool = True  # True = AND all conditions, False = OR
    created_at: str = ""
    hit_count: int = 0  # Track how many times rule matched

    def matches(self, data: dict) -> bool:
        """Check if this rule matches the provided data.

        Args:
            data: Dictionary with document data.

        Returns:
            True if rule matches.
        """
        if not self.enabled or not self.conditions:
            return False

        if self.match_all:
            # AND - all conditions must match
            return all(cond.matches(data) for cond in self.conditions)
        else:
            # OR - at least one condition must match
            return any(cond.matches(data) for cond in self.conditions)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "conditions": [c.to_dict() for c in self.conditions],
            "action": self.action.value,
            "action_value": self.action_value,
            "priority": self.priority,
            "enabled": self.enabled,
            "match_all": self.match_all,
            "created_at": self.created_at,
            "hit_count": self.hit_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ClassificationRule":
        return cls(
            id=data.get("id", str(uuid4())),
            name=data["name"],
            description=data.get("description", ""),
            conditions=[RuleCondition.from_dict(c) for c in data.get("conditions", [])],
            action=RuleAction(data["action"]),
            action_value=data["action_value"],
            priority=data.get("priority", 100),
            enabled=data.get("enabled", True),
            match_all=data.get("match_all", True),
            created_at=data.get("created_at", ""),
            hit_count=data.get("hit_count", 0),
        )


@dataclass
class RuleMatch:
    """Result of a rule match."""

    rule: ClassificationRule
    action: RuleAction
    action_value: str
    matched_conditions: list[str]  # Human-readable list of what matched


class ClassificationRulesEngine:
    """Engine for managing and applying classification rules."""

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize the rules engine.

        Args:
            config_path: Path to rules configuration file.
        """
        self.config_path = config_path or settings.data_dir / "classification_rules.json"
        self._rules: dict[str, ClassificationRule] = {}
        self._load_rules()

    def _load_rules(self) -> None:
        """Load rules from file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for rule_data in data.get("rules", []):
                        rule = ClassificationRule.from_dict(rule_data)
                        self._rules[rule.id] = rule
                logger.debug(f"Loaded {len(self._rules)} classification rules")
            except Exception as e:
                logger.error(f"Error loading classification rules: {e}")

    def _save_rules(self) -> None:
        """Save rules to file."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "rules": [r.to_dict() for r in self._rules.values()],
                "updated_at": datetime.now().isoformat(),
            }
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved {len(self._rules)} classification rules")
        except Exception as e:
            logger.error(f"Error saving classification rules: {e}")

    def add_rule(self, rule: ClassificationRule) -> ClassificationRule:
        """Add a new rule.

        Args:
            rule: Rule to add.

        Returns:
            Added rule.
        """
        if not rule.id:
            rule.id = str(uuid4())
        if not rule.created_at:
            rule.created_at = datetime.now().isoformat()

        self._rules[rule.id] = rule
        self._save_rules()
        logger.info(f"Added classification rule: {rule.name}")
        return rule

    def create_rule(
        self,
        name: str,
        conditions: list[RuleCondition],
        action: RuleAction,
        action_value: str,
        description: str = "",
        priority: int = 100,
        match_all: bool = True,
    ) -> ClassificationRule:
        """Create and add a new rule.

        Args:
            name: Rule name.
            conditions: List of conditions.
            action: Action to take when matched.
            action_value: Value for the action.
            description: Rule description.
            priority: Rule priority (lower = higher).
            match_all: True for AND, False for OR.

        Returns:
            Created rule.
        """
        rule = ClassificationRule(
            id=str(uuid4()),
            name=name,
            description=description,
            conditions=conditions,
            action=action,
            action_value=action_value,
            priority=priority,
            match_all=match_all,
            created_at=datetime.now().isoformat(),
        )
        return self.add_rule(rule)

    def get_rule(self, rule_id: str) -> Optional[ClassificationRule]:
        """Get a rule by ID."""
        return self._rules.get(rule_id)

    def get_all_rules(self) -> list[ClassificationRule]:
        """Get all rules sorted by priority."""
        return sorted(self._rules.values(), key=lambda r: r.priority)

    def update_rule(self, rule: ClassificationRule) -> None:
        """Update an existing rule."""
        if rule.id in self._rules:
            self._rules[rule.id] = rule
            self._save_rules()

    def delete_rule(self, rule_id: str) -> bool:
        """Delete a rule.

        Args:
            rule_id: Rule ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        if rule_id in self._rules:
            del self._rules[rule_id]
            self._save_rules()
            return True
        return False

    def enable_rule(self, rule_id: str, enabled: bool = True) -> bool:
        """Enable or disable a rule."""
        rule = self.get_rule(rule_id)
        if rule:
            rule.enabled = enabled
            self._save_rules()
            return True
        return False

    def find_matching_rules(self, data: dict) -> list[RuleMatch]:
        """Find all rules that match the provided data.

        Args:
            data: Dictionary with document data. Keys should match MatchSource values.

        Returns:
            List of matching rules sorted by priority.
        """
        matches = []

        for rule in self.get_all_rules():
            if rule.matches(data):
                # Build list of what matched
                matched_conditions = []
                for cond in rule.conditions:
                    if cond.matches(data):
                        source_name = cond.source.value.replace("_", " ").title()
                        matched_conditions.append(f"{source_name}: '{cond.pattern}'")

                matches.append(
                    RuleMatch(
                        rule=rule,
                        action=rule.action,
                        action_value=rule.action_value,
                        matched_conditions=matched_conditions,
                    )
                )

                # Increment hit count
                rule.hit_count += 1

        # Save updated hit counts
        if matches:
            self._save_rules()

        return matches

    def get_best_match(self, data: dict) -> Optional[RuleMatch]:
        """Get the best (highest priority) matching rule.

        Args:
            data: Dictionary with document data.

        Returns:
            Best matching rule or None.
        """
        matches = self.find_matching_rules(data)
        return matches[0] if matches else None

    def create_rule_from_invoice(
        self,
        entity_id: str,
        sender_email: Optional[str] = None,
        subject_pattern: Optional[str] = None,
        body_pattern: Optional[str] = None,
        nif: Optional[str] = None,
        pdf_pattern: Optional[str] = None,
        rule_name: Optional[str] = None,
    ) -> ClassificationRule:
        """Create a rule from invoice data interactively or automatically.

        Args:
            entity_id: Entity ID to assign.
            sender_email: Sender email to match.
            subject_pattern: Subject pattern to match.
            body_pattern: Body pattern to match.
            nif: NIF to match in PDF.
            pdf_pattern: Pattern to match in PDF content.
            rule_name: Name for the rule.

        Returns:
            Created rule.
        """
        conditions = []

        if sender_email:
            conditions.append(
                RuleCondition(
                    source=MatchSource.SENDER_EMAIL,
                    match_type=MatchType.EXACT,
                    pattern=sender_email,
                )
            )

        if subject_pattern:
            conditions.append(
                RuleCondition(
                    source=MatchSource.SUBJECT,
                    match_type=MatchType.CONTAINS,
                    pattern=subject_pattern,
                )
            )

        if body_pattern:
            conditions.append(
                RuleCondition(
                    source=MatchSource.BODY,
                    match_type=MatchType.CONTAINS,
                    pattern=body_pattern,
                )
            )

        if nif:
            conditions.append(
                RuleCondition(
                    source=MatchSource.PDF_NIF,
                    match_type=MatchType.EXACT,
                    pattern=nif,
                )
            )

        if pdf_pattern:
            conditions.append(
                RuleCondition(
                    source=MatchSource.PDF_CONTENT,
                    match_type=MatchType.CONTAINS,
                    pattern=pdf_pattern,
                )
            )

        if not conditions:
            raise ValueError("At least one condition is required")

        name = rule_name or f"Rule for entity {entity_id[:8]}"

        return self.create_rule(
            name=name,
            conditions=conditions,
            action=RuleAction.ASSIGN_ENTITY,
            action_value=entity_id,
            description="Auto-created rule",
            match_all=len(conditions) == 1,  # Use OR if multiple conditions
        )

    def show_rules_summary(self) -> None:
        """Display a summary of all rules."""
        rules = self.get_all_rules()

        if not rules:
            console.print("[yellow]Nenhuma regra de classificação definida.[/yellow]")
            return

        table = Table(title=f"Regras de Classificação ({len(rules)})")
        table.add_column("Pri", style="dim", width=4)
        table.add_column("Nome", style="cyan", max_width=25)
        table.add_column("Condições", style="white", max_width=35)
        table.add_column("Acção", style="green")
        table.add_column("Hits", style="yellow", justify="right")
        table.add_column("On", style="dim", width=3)

        for rule in rules:
            # Build conditions summary
            cond_summary = []
            for c in rule.conditions[:2]:  # Show first 2
                source = c.source.value.split("_")[0]
                cond_summary.append(f"{source}:{c.pattern[:15]}")
            if len(rule.conditions) > 2:
                cond_summary.append(f"+{len(rule.conditions)-2}")

            connector = " AND " if rule.match_all else " OR "

            table.add_row(
                str(rule.priority),
                rule.name[:25],
                connector.join(cond_summary),
                f"{rule.action.value}",
                str(rule.hit_count),
                "✓" if rule.enabled else "✗",
            )

        console.print(table)


# Global instance
_rules_engine: Optional[ClassificationRulesEngine] = None


def get_rules_engine() -> ClassificationRulesEngine:
    """Get the global rules engine instance."""
    global _rules_engine
    if _rules_engine is None:
        _rules_engine = ClassificationRulesEngine()
    return _rules_engine
