from __future__ import annotations

# SQL fragments for pgvector-backed memory store.


def upsert_memory_sql(distance_ops: str = "vector_cosine_ops") -> str:
    return f"""
    INSERT INTO memory_item (
        id, user_id, type, text, tags, confidence, ttl_days, retention_policy,
        embedding_model, embedding_dim, embedding, payload
    ) VALUES (
        %(id)s, %(user_id)s, %(type)s, %(text)s, %(tags)s, %(confidence)s, %(ttl_days)s, %(retention_policy)s,
        %(embedding_model)s, %(embedding_dim)s, %(embedding)s, %(payload)s
    )
    ON CONFLICT (id) DO UPDATE SET
        text = EXCLUDED.text,
        tags = EXCLUDED.tags,
        confidence = EXCLUDED.confidence,
        ttl_days = EXCLUDED.ttl_days,
        retention_policy = EXCLUDED.retention_policy,
        embedding_model = EXCLUDED.embedding_model,
        embedding_dim = EXCLUDED.embedding_dim,
        embedding = EXCLUDED.embedding,
        payload = EXCLUDED.payload,
        ts_seen = now()
    ;
    """


def search_memory_sql(metric: str = "cosine") -> str:
    return """
    SELECT id, user_id, type, text, tags, ts_created, ts_seen, confidence,
           ttl_days, retention_policy, embedding_model, embedding_dim, payload,
           (embedding <-> %(query_vec)s::vector) AS distance
    FROM memory_item
    WHERE user_id = %(user_id)s
      AND (%(types)s IS NULL OR type = ANY (%(types)s))
      AND (%(tags)s IS NULL OR tags && %(tags)s)
    ORDER BY embedding <-> %(query_vec)s::vector
    LIMIT %(limit)s
    ;
    """
