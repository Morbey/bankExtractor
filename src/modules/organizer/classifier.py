"""Document classifier for automatic categorization."""

import re
from dataclasses import dataclass
from typing import Optional

from src.core import get_logger

from .models import DocumentType
from .parser import ParsedDocument

logger = get_logger("organizer.classifier")


@dataclass
class ClassificationResult:
    """Result of document classification."""

    document_type: DocumentType
    provider_name: Optional[str]
    provider_category: Optional[str]
    confidence: float  # 0.0 to 1.0
    tags: list[str]


# Known providers and their patterns
PROVIDER_PATTERNS = {
    # Utilities - Electricity
    "EDP": {
        "patterns": [r"edp\s*comercial", r"edp\s*serviço\s*universal", r"energias\s*de\s*portugal"],
        "category": "utilities",
        "tags": ["eletricidade", "energia"],
    },
    "Endesa": {
        "patterns": [r"endesa", r"endesa\s*energia"],
        "category": "utilities",
        "tags": ["eletricidade", "energia"],
    },
    "Galp": {
        "patterns": [r"galp\s*energia", r"galp\s*power"],
        "category": "utilities",
        "tags": ["eletricidade", "gás", "energia"],
    },
    "E-Redes": {
        "patterns": [r"e-redes", r"eredes", r"edp\s*distribuição"],
        "category": "utilities",
        "tags": ["eletricidade", "rede"],
    },
    # Utilities - Water
    "EPAL": {
        "patterns": [r"epal", r"empresa\s*portuguesa.*águas\s*livres"],
        "category": "utilities",
        "tags": ["água"],
    },
    "Águas de Portugal": {
        "patterns": [r"águas\s*de\s*portugal", r"adp"],
        "category": "utilities",
        "tags": ["água"],
    },
    # Utilities - Gas
    "Lisboagás": {
        "patterns": [r"lisboagás", r"lisboacas"],
        "category": "utilities",
        "tags": ["gás"],
    },
    # Telecommunications
    "NOS": {
        "patterns": [r"\bnos\b", r"nos\s*comunicações"],
        "category": "telecomunicacoes",
        "tags": ["internet", "tv", "telefone"],
    },
    "MEO": {
        "patterns": [r"\bmeo\b", r"meo\s*-\s*serviços"],
        "category": "telecomunicacoes",
        "tags": ["internet", "tv", "telefone"],
    },
    "Vodafone": {
        "patterns": [r"vodafone\s*portugal", r"\bvodafone\b"],
        "category": "telecomunicacoes",
        "tags": ["internet", "telemóvel"],
    },
    "NOWO": {
        "patterns": [r"\bnowo\b"],
        "category": "telecomunicacoes",
        "tags": ["internet", "tv"],
    },
    # Banks
    "CGD": {
        "patterns": [r"caixa\s*geral\s*de\s*depósitos", r"\bcgd\b"],
        "category": "banco",
        "tags": ["banco", "extrato"],
    },
    "Millennium BCP": {
        "patterns": [r"millennium\s*bcp", r"banco\s*comercial\s*português"],
        "category": "banco",
        "tags": ["banco", "extrato"],
    },
    "Santander": {
        "patterns": [r"santander\s*totta", r"banco\s*santander"],
        "category": "banco",
        "tags": ["banco", "extrato"],
    },
    "Novo Banco": {
        "patterns": [r"novo\s*banco"],
        "category": "banco",
        "tags": ["banco", "extrato"],
    },
    "Banco CTT": {
        "patterns": [r"banco\s*ctt", r"ctt\s*banco"],
        "category": "banco",
        "tags": ["banco", "extrato"],
    },
    # Insurance
    "Fidelidade": {
        "patterns": [r"fidelidade", r"fidelidade\s*seguros"],
        "category": "seguros",
        "tags": ["seguro"],
    },
    "Allianz": {
        "patterns": [r"allianz\s*portugal", r"\ballianz\b"],
        "category": "seguros",
        "tags": ["seguro"],
    },
    "Tranquilidade": {
        "patterns": [r"tranquilidade", r"generali\s*tranquilidade"],
        "category": "seguros",
        "tags": ["seguro"],
    },
    # Transport
    "Via Verde": {
        "patterns": [r"via\s*verde"],
        "category": "transportes",
        "tags": ["portagens", "transporte"],
    },
    "CP": {
        "patterns": [r"comboios\s*de\s*portugal", r"\bcp\b.*comboios"],
        "category": "transportes",
        "tags": ["comboio", "transporte"],
    },
    # Government
    "Finanças": {
        "patterns": [
            r"autoridade\s*tributária",
            r"portal\s*das\s*finanças",
            r"at\s*-\s*autoridade",
        ],
        "category": "governo",
        "tags": ["impostos", "finanças"],
    },
}


# Document type indicators
DOCUMENT_TYPE_PATTERNS = {
    DocumentType.INVOICE: [
        r"fatura",
        r"factura",
        r"invoice",
        r"nota\s*de\s*débito",
        r"documento\s*de\s*faturação",
    ],
    DocumentType.STATEMENT: [
        r"extrato",
        r"extrato\s*de\s*conta",
        r"movimentos",
        r"statement",
        r"resumo\s*de\s*conta",
    ],
    DocumentType.RECEIPT: [
        r"recibo",
        r"comprovativo\s*de\s*pagamento",
        r"receipt",
        r"prova\s*de\s*pagamento",
    ],
    DocumentType.CONTRACT: [
        r"contrato",
        r"contract",
        r"acordo",
        r"termos\s*e\s*condições",
    ],
    DocumentType.TAX: [
        r"declaração\s*de\s*irs",
        r"imi\b",
        r"iuc\b",
        r"imposto",
        r"nota\s*de\s*liquidação",
    ],
}


class DocumentClassifier:
    """Classifier for automatic document categorization."""

    def __init__(self):
        self.logger = logger

    def classify(self, parsed_doc: ParsedDocument) -> ClassificationResult:
        """Classify a parsed document.

        Args:
            parsed_doc: ParsedDocument from PDF parser

        Returns:
            ClassificationResult with type, provider, and tags
        """
        text = parsed_doc.text_content.lower() if parsed_doc.text_content else ""
        file_name = parsed_doc.file_name.lower()

        # Detect document type
        doc_type, type_confidence = self._detect_document_type(text, file_name)

        # Detect provider
        provider_name, provider_category, provider_tags = self._detect_provider(text)

        # Combine confidence
        confidence = type_confidence
        if provider_name:
            confidence = min(confidence + 0.2, 1.0)

        # Build tags list
        tags = list(provider_tags) if provider_tags else []

        # Add document type tag
        tags.append(doc_type.value)

        # Add month/year tags if date available
        if parsed_doc.document_date:
            tags.append(f"ano:{parsed_doc.document_date.year}")
            tags.append(f"mes:{parsed_doc.document_date.month:02d}")

        # Deduplicate tags
        tags = list(dict.fromkeys(tags))

        self.logger.debug(
            f"Classified {parsed_doc.file_name}: type={doc_type.value}, "
            f"provider={provider_name}, confidence={confidence:.2f}"
        )

        return ClassificationResult(
            document_type=doc_type,
            provider_name=provider_name,
            provider_category=provider_category,
            confidence=confidence,
            tags=tags,
        )

    def _detect_document_type(self, text: str, file_name: str) -> tuple[DocumentType, float]:
        """Detect the type of document.

        Returns:
            Tuple of (DocumentType, confidence)
        """
        scores = {doc_type: 0 for doc_type in DocumentType}

        # Check text content
        for doc_type, patterns in DOCUMENT_TYPE_PATTERNS.items():
            for pattern in patterns:
                matches = len(re.findall(pattern, text, re.IGNORECASE))
                scores[doc_type] += matches

        # Check filename
        for doc_type, patterns in DOCUMENT_TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, file_name, re.IGNORECASE):
                    scores[doc_type] += 2  # Weight filename matches higher

        # Find best match
        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]

        if best_score == 0:
            return DocumentType.OTHER, 0.3

        # Calculate confidence based on score
        confidence = min(0.5 + (best_score * 0.1), 0.95)
        return best_type, confidence

    def _detect_provider(self, text: str) -> tuple[Optional[str], Optional[str], list[str]]:
        """Detect the document provider/vendor.

        Returns:
            Tuple of (provider_name, provider_category, tags)
        """
        for provider_name, config in PROVIDER_PATTERNS.items():
            for pattern in config["patterns"]:
                if re.search(pattern, text, re.IGNORECASE):
                    return (
                        provider_name,
                        config["category"],
                        config["tags"],
                    )

        return None, None, []


def classify_document(parsed_doc: ParsedDocument) -> ClassificationResult:
    """Convenience function to classify a parsed document.

    Args:
        parsed_doc: ParsedDocument from PDF parser

    Returns:
        ClassificationResult with type, provider, and tags
    """
    classifier = DocumentClassifier()
    return classifier.classify(parsed_doc)
