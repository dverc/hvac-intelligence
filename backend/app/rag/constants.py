"""RAG namespaces aligned with §4.2 rag_knowledge_query tool schema."""

RAG_NAMESPACES: frozenset[str] = frozenset(
    {
        "faq_general",
        "equipment_manuals",
        "warranty_terms",
        "troubleshooting",
        "pricing",
    }
)

DEFAULT_TOP_K = 5
