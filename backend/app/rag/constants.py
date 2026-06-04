"""RAG base namespaces aligned with §4.2 rag_knowledge_query tool schema."""

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


def get_namespace(org_slug: str, namespace: str) -> str:
    """Build org-prefixed Pinecone/mock namespace (e.g. hvac-demo::faq_general)."""
    base = get_base_namespace(namespace)
    if base not in RAG_NAMESPACES:
        raise ValueError(f"Invalid namespace: {namespace}")
    return f"{org_slug}::{base}"


def get_base_namespace(namespace: str) -> str:
    """Strip org slug prefix if present; return the base namespace key."""
    if "::" in namespace:
        return namespace.split("::", 1)[1]
    return namespace


def is_valid_base_namespace(namespace: str) -> bool:
    return get_base_namespace(namespace) in RAG_NAMESPACES
