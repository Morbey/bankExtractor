"""Invoice categorization system with configurable rules."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import re


class InvoiceCategory(str, Enum):
    """Standard invoice categories."""

    COMUNICACOES = "comunicacoes"
    VIA_VERDE = "via_verde"
    ENERGIA = "energia"
    AGUA = "agua"
    COMBUSTIVEL = "combustivel"
    SEGUROS = "seguros"
    SAUDE = "saude"
    ALIMENTACAO = "alimentacao"
    TRANSPORTES = "transportes"
    ALOJAMENTO = "alojamento"
    SERVICOS = "servicos"
    MATERIAL_ESCRITORIO = "material_escritorio"
    SOFTWARE = "software"
    OUTROS = "outros"


@dataclass
class CategoryRule:
    """Rule for matching invoices to categories."""

    category: InvoiceCategory
    patterns: list[str] = field(default_factory=list)  # Regex patterns for sender/subject
    sender_domains: list[str] = field(default_factory=list)  # Email domains
    keywords: list[str] = field(default_factory=list)  # Keywords in PDF content
    nif_list: list[str] = field(default_factory=list)  # Known NIFs

    def matches_sender(self, sender: str) -> bool:
        """Check if sender matches this rule."""
        sender_lower = sender.lower()

        # Check domain
        for domain in self.sender_domains:
            if domain.lower() in sender_lower:
                return True

        # Check patterns
        for pattern in self.patterns:
            if re.search(pattern, sender_lower, re.IGNORECASE):
                return True

        return False

    def matches_subject(self, subject: str) -> bool:
        """Check if email subject matches this rule."""
        subject_lower = subject.lower()

        for pattern in self.patterns:
            if re.search(pattern, subject_lower, re.IGNORECASE):
                return True

        for keyword in self.keywords:
            if keyword.lower() in subject_lower:
                return True

        return False

    def matches_content(self, content: str) -> bool:
        """Check if PDF content matches this rule."""
        content_lower = content.lower()

        for keyword in self.keywords:
            if keyword.lower() in content_lower:
                return True

        for nif in self.nif_list:
            if nif in content:
                return True

        return False


# Default category rules - Portuguese providers
DEFAULT_RULES: list[CategoryRule] = [
    # Comunicacoes
    CategoryRule(
        category=InvoiceCategory.COMUNICACOES,
        patterns=[r"vodafone", r"nos\.pt", r"meo", r"nowo", r"lycamobile"],
        sender_domains=["vodafone.pt", "nos.pt", "meo.pt", "nowo.pt"],
        keywords=["vodafone", "nos comunicações", "meo", "telecomunicações", "telemóvel", "internet fixa"],
        nif_list=["502618930", "504448064", "500780472"],  # Vodafone, NOS, MEO
    ),

    # Via Verde
    CategoryRule(
        category=InvoiceCategory.VIA_VERDE,
        patterns=[r"via.?verde", r"brisa"],
        sender_domains=["viaverde.pt", "brisa.pt"],
        keywords=["via verde", "portagem", "brisa", "a]auto-estrada"],
        nif_list=["500075066"],  # Via Verde
    ),

    # Energia
    CategoryRule(
        category=InvoiceCategory.ENERGIA,
        patterns=[r"edp", r"galp.?energia", r"endesa", r"iberdrola", r"goldenergy"],
        sender_domains=["edp.pt", "galp.com", "endesa.pt", "iberdrola.pt", "goldenergy.pt"],
        keywords=["energia", "eletricidade", "electricidade", "gás natural", "edp comercial"],
        nif_list=["503504564", "504499777", "503161314"],  # EDP, Galp, Endesa
    ),

    # Agua
    CategoryRule(
        category=InvoiceCategory.AGUA,
        patterns=[r"epal", r"águas", r"aguas", r"smas", r"indaqua"],
        sender_domains=["epal.pt", "aguasdoporto.pt"],
        keywords=["água", "abastecimento", "saneamento", "epal"],
        nif_list=["500904568"],  # EPAL
    ),

    # Combustivel
    CategoryRule(
        category=InvoiceCategory.COMBUSTIVEL,
        patterns=[r"galp", r"bp", r"repsol", r"cepsa", r"prio"],
        sender_domains=["galp.com", "bp.com", "repsol.com"],
        keywords=["combustível", "gasolina", "gasóleo", "posto de abastecimento"],
        nif_list=["500008505", "500243493"],  # Galp, BP
    ),

    # Seguros
    CategoryRule(
        category=InvoiceCategory.SEGUROS,
        patterns=[r"fidelidade", r"allianz", r"generali", r"tranquilidade", r"ageas", r"ok.?teleseguros"],
        sender_domains=["fidelidade.pt", "allianz.pt", "generali.pt", "tranquilidade.pt"],
        keywords=["seguro", "apólice", "prémio", "sinistro", "cobertura"],
        nif_list=["500918880", "500037540"],  # Fidelidade, Allianz
    ),

    # Saude
    CategoryRule(
        category=InvoiceCategory.SAUDE,
        patterns=[r"farmácia", r"farmacia", r"hospital", r"clínica", r"clinica", r"médic"],
        sender_domains=["farmaciasportuguesas.pt"],
        keywords=["farmácia", "medicamento", "consulta médica", "saúde", "clínica"],
    ),

    # Software/Tecnologia
    CategoryRule(
        category=InvoiceCategory.SOFTWARE,
        patterns=[r"microsoft", r"google", r"adobe", r"github", r"amazon.?web", r"aws"],
        sender_domains=["microsoft.com", "google.com", "adobe.com", "github.com", "amazon.com"],
        keywords=["software", "licença", "subscrição", "cloud", "saas"],
    ),

    # Material de Escritorio
    CategoryRule(
        category=InvoiceCategory.MATERIAL_ESCRITORIO,
        patterns=[r"staples", r"note", r"office"],
        sender_domains=["staples.pt", "note.pt"],
        keywords=["material de escritório", "papelaria", "toner", "impressora"],
    ),

    # Alimentacao
    CategoryRule(
        category=InvoiceCategory.ALIMENTACAO,
        patterns=[r"continente", r"pingo.?doce", r"lidl", r"auchan", r"mercadona"],
        sender_domains=["continente.pt", "pingodoce.pt"],
        keywords=["supermercado", "alimentação", "mercearia"],
    ),

    # Transportes
    CategoryRule(
        category=InvoiceCategory.TRANSPORTES,
        patterns=[r"uber", r"bolt", r"cp\.pt", r"metro", r"carris", r"taxi"],
        sender_domains=["uber.com", "bolt.eu", "cp.pt"],
        keywords=["transporte", "viagem", "bilhete", "táxi", "comboio"],
    ),

    # Alojamento
    CategoryRule(
        category=InvoiceCategory.ALOJAMENTO,
        patterns=[r"booking", r"airbnb", r"hotel", r"trivago"],
        sender_domains=["booking.com", "airbnb.com"],
        keywords=["hotel", "alojamento", "reserva", "estadia"],
    ),
]


class InvoiceCategorizer:
    """Categorizes invoices based on configurable rules."""

    def __init__(self, rules: Optional[list[CategoryRule]] = None):
        """Initialize categorizer with rules.

        Args:
            rules: List of category rules. Uses DEFAULT_RULES if not provided.
        """
        self.rules = rules or DEFAULT_RULES.copy()

    def add_rule(self, rule: CategoryRule) -> None:
        """Add a new categorization rule."""
        self.rules.append(rule)

    def categorize_by_sender(self, sender: str) -> InvoiceCategory:
        """Categorize based on email sender.

        Args:
            sender: Email sender address or name.

        Returns:
            Matched category or OUTROS if no match.
        """
        for rule in self.rules:
            if rule.matches_sender(sender):
                return rule.category
        return InvoiceCategory.OUTROS

    def categorize_by_subject(self, subject: str) -> InvoiceCategory:
        """Categorize based on email subject.

        Args:
            subject: Email subject line.

        Returns:
            Matched category or OUTROS if no match.
        """
        for rule in self.rules:
            if rule.matches_subject(subject):
                return rule.category
        return InvoiceCategory.OUTROS

    def categorize_by_content(self, content: str) -> InvoiceCategory:
        """Categorize based on PDF content.

        Args:
            content: Extracted text from PDF.

        Returns:
            Matched category or OUTROS if no match.
        """
        for rule in self.rules:
            if rule.matches_content(content):
                return rule.category
        return InvoiceCategory.OUTROS

    def categorize(
        self,
        sender: Optional[str] = None,
        subject: Optional[str] = None,
        content: Optional[str] = None,
    ) -> InvoiceCategory:
        """Categorize using all available information.

        Tries sender first, then subject, then content.

        Args:
            sender: Email sender address or name.
            subject: Email subject line.
            content: Extracted text from PDF.

        Returns:
            Best matched category or OUTROS if no match.
        """
        # Try sender first (most reliable)
        if sender:
            category = self.categorize_by_sender(sender)
            if category != InvoiceCategory.OUTROS:
                return category

        # Try subject
        if subject:
            category = self.categorize_by_subject(subject)
            if category != InvoiceCategory.OUTROS:
                return category

        # Try PDF content
        if content:
            category = self.categorize_by_content(content)
            if category != InvoiceCategory.OUTROS:
                return category

        return InvoiceCategory.OUTROS

    def get_folder_name(self, category: InvoiceCategory) -> str:
        """Get the folder name for a category.

        Args:
            category: The invoice category.

        Returns:
            Folder name string.
        """
        return category.value
