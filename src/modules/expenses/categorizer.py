"""Expense categorizer for automatic classification."""

from typing import Optional

from src.core import get_logger

from .models import ExpenseCategory, PROVIDER_CATEGORIES

logger = get_logger("expenses.categorizer")


# Keywords for category detection
CATEGORY_KEYWORDS = {
    ExpenseCategory.UTILITIES: [
        "eletricidade",
        "electricidade",
        "luz",
        "energia",
        "água",
        "agua",
        "gás",
        "gas",
        "saneamento",
        "resíduos",
        "lixo",
    ],
    ExpenseCategory.TELECOM: [
        "internet",
        "telefone",
        "telemóvel",
        "telemovel",
        "móvel",
        "movel",
        "fibra",
        "tv",
        "televisão",
        "televisao",
        "cabo",
        "dados",
    ],
    ExpenseCategory.TRANSPORT: [
        "combustível",
        "combustivel",
        "gasolina",
        "gasóleo",
        "gasoleo",
        "portagem",
        "portagens",
        "estacionamento",
        "parque",
        "uber",
        "bolt",
        "táxi",
        "taxi",
        "metro",
        "autocarro",
        "comboio",
        "passe",
    ],
    ExpenseCategory.INSURANCE: [
        "seguro",
        "seguros",
        "apólice",
        "apolice",
        "prémio",
        "premio",
        "cobertura",
        "sinistro",
    ],
    ExpenseCategory.HEALTH: [
        "farmácia",
        "farmacia",
        "medicamento",
        "médico",
        "medico",
        "hospital",
        "clínica",
        "clinica",
        "consulta",
        "exame",
        "análise",
        "dentista",
        "oftalmologista",
        "saúde",
        "saude",
    ],
    ExpenseCategory.EDUCATION: [
        "escola",
        "universidade",
        "faculdade",
        "curso",
        "formação",
        "formacao",
        "livro",
        "propina",
        "matrícula",
        "matricula",
        "educação",
        "educacao",
        "ensino",
    ],
    ExpenseCategory.FOOD: [
        "supermercado",
        "mercearia",
        "restaurante",
        "café",
        "cafe",
        "padaria",
        "talho",
        "peixaria",
        "alimentação",
        "alimentacao",
        "continente",
        "pingo doce",
        "lidl",
        "aldi",
        "minipreço",
    ],
    ExpenseCategory.HOUSING: [
        "renda",
        "aluguer",
        "hipoteca",
        "condomínio",
        "condominio",
        "manutenção",
        "manutencao",
        "reparação",
        "reparacao",
        "mobília",
        "mobilia",
        "decoração",
        "decoracao",
    ],
    ExpenseCategory.ENTERTAINMENT: [
        "cinema",
        "teatro",
        "concerto",
        "spotify",
        "netflix",
        "hbo",
        "disney",
        "playstation",
        "xbox",
        "steam",
        "jogo",
        "bilhete",
        "lazer",
        "entretenimento",
        "diversão",
    ],
    ExpenseCategory.CLOTHING: [
        "roupa",
        "vestuário",
        "vestuario",
        "calçado",
        "calcado",
        "zara",
        "h&m",
        "primark",
        "mango",
        "bershka",
        "pull&bear",
    ],
    ExpenseCategory.TAXES: [
        "imposto",
        "irs",
        "irc",
        "imi",
        "iuc",
        "iva",
        "taxa",
        "finanças",
        "financas",
        "contribuição",
        "contribuicao",
        "segurança social",
        "seguranca social",
    ],
    ExpenseCategory.BANK_FEES: [
        "comissão",
        "comissao",
        "anuidade",
        "manutenção conta",
        "transferência",
        "transferencia",
        "juros",
        "descoberto",
    ],
    ExpenseCategory.SUBSCRIPTIONS: [
        "subscrição",
        "subscricao",
        "assinatura",
        "mensalidade",
        "plano",
        "premium",
        "membership",
    ],
}


class ExpenseCategorizer:
    """Automatic expense categorizer based on provider and content."""

    def __init__(self):
        self.logger = logger

    def categorize(
        self,
        provider_name: Optional[str] = None,
        description: Optional[str] = None,
        amount: Optional[float] = None,
    ) -> tuple[ExpenseCategory, float]:
        """Categorize an expense based on available information.

        Args:
            provider_name: Name of the provider/vendor
            description: Description or text from the document
            amount: Amount of the expense (for heuristics)

        Returns:
            Tuple of (category, confidence) where confidence is 0.0 to 1.0
        """
        # Try provider-based categorization first (highest confidence)
        if provider_name:
            category = self._categorize_by_provider(provider_name)
            if category:
                return category, 0.95

        # Try keyword-based categorization from description
        if description:
            category, confidence = self._categorize_by_keywords(description)
            if category:
                return category, confidence

        # Default to OTHER with low confidence
        return ExpenseCategory.OTHER, 0.3

    def _categorize_by_provider(self, provider_name: str) -> Optional[ExpenseCategory]:
        """Categorize by exact or fuzzy provider name match."""
        # Exact match
        if provider_name in PROVIDER_CATEGORIES:
            return PROVIDER_CATEGORIES[provider_name]

        # Case-insensitive match
        provider_lower = provider_name.lower()
        for known_provider, category in PROVIDER_CATEGORIES.items():
            if known_provider.lower() in provider_lower or provider_lower in known_provider.lower():
                return category

        return None

    def _categorize_by_keywords(self, text: str) -> tuple[Optional[ExpenseCategory], float]:
        """Categorize by keyword matching in text."""
        text_lower = text.lower()

        # Count matches per category
        category_scores = {}
        for category, keywords in CATEGORY_KEYWORDS.items():
            score = 0
            for keyword in keywords:
                if keyword in text_lower:
                    score += 1
            if score > 0:
                category_scores[category] = score

        if not category_scores:
            return None, 0.0

        # Get category with highest score
        best_category = max(category_scores, key=category_scores.get)
        best_score = category_scores[best_category]

        # Calculate confidence based on number of matches
        confidence = min(0.5 + (best_score * 0.15), 0.85)

        return best_category, confidence

    def suggest_category(
        self,
        provider_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> list[tuple[ExpenseCategory, float]]:
        """Suggest multiple possible categories with confidence scores.

        Args:
            provider_name: Name of the provider
            description: Description text

        Returns:
            List of (category, confidence) tuples, sorted by confidence
        """
        suggestions = []

        # Provider-based suggestion
        if provider_name:
            category = self._categorize_by_provider(provider_name)
            if category:
                suggestions.append((category, 0.95))

        # Keyword-based suggestions
        if description:
            text_lower = description.lower()
            for category, keywords in CATEGORY_KEYWORDS.items():
                score = sum(1 for kw in keywords if kw in text_lower)
                if score > 0:
                    confidence = min(0.3 + (score * 0.1), 0.8)
                    # Don't duplicate if already from provider
                    if not any(cat == category for cat, _ in suggestions):
                        suggestions.append((category, confidence))

        # Sort by confidence
        suggestions.sort(key=lambda x: x[1], reverse=True)

        # Always include OTHER as fallback
        if not suggestions or suggestions[-1][0] != ExpenseCategory.OTHER:
            suggestions.append((ExpenseCategory.OTHER, 0.1))

        return suggestions[:5]  # Return top 5

    def is_essential(
        self,
        category: ExpenseCategory,
        provider_name: Optional[str] = None,
    ) -> bool:
        """Determine if an expense is essential (vs discretionary).

        Args:
            category: Expense category
            provider_name: Provider name for additional context

        Returns:
            True if the expense is considered essential
        """
        essential_categories = {
            ExpenseCategory.UTILITIES,
            ExpenseCategory.HOUSING,
            ExpenseCategory.HEALTH,
            ExpenseCategory.TAXES,
            ExpenseCategory.INSURANCE,
            ExpenseCategory.FOOD,
            ExpenseCategory.TRANSPORT,  # Basic transport
        }

        return category in essential_categories

    def is_recurring(
        self,
        category: ExpenseCategory,
        provider_name: Optional[str] = None,
    ) -> bool:
        """Determine if an expense is likely recurring.

        Args:
            category: Expense category
            provider_name: Provider name

        Returns:
            True if the expense is likely recurring
        """
        recurring_categories = {
            ExpenseCategory.UTILITIES,
            ExpenseCategory.TELECOM,
            ExpenseCategory.INSURANCE,
            ExpenseCategory.SUBSCRIPTIONS,
            ExpenseCategory.HOUSING,
        }

        return category in recurring_categories

    def is_tax_deductible(
        self,
        category: ExpenseCategory,
        description: Optional[str] = None,
    ) -> bool:
        """Determine if an expense might be tax deductible.

        Args:
            category: Expense category
            description: Additional description

        Returns:
            True if potentially tax deductible
        """
        deductible_categories = {
            ExpenseCategory.HEALTH,
            ExpenseCategory.EDUCATION,
            ExpenseCategory.HOUSING,  # Rent for certain situations
        }

        return category in deductible_categories


def categorize_expense(
    provider_name: Optional[str] = None,
    description: Optional[str] = None,
    amount: Optional[float] = None,
) -> tuple[ExpenseCategory, float]:
    """Convenience function to categorize an expense.

    Args:
        provider_name: Provider/vendor name
        description: Description or document text
        amount: Expense amount

    Returns:
        Tuple of (category, confidence)
    """
    categorizer = ExpenseCategorizer()
    return categorizer.categorize(provider_name, description, amount)
