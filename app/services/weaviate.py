import weaviate
from app.config import settings

CLASS_NAME = "VulnerabilityPattern"


def get_client() -> weaviate.WeaviateClient:
    return weaviate.connect_to_weaviate_cloud(
        cluster_url=settings.weaviate_url,
        auth_credentials=weaviate.auth.AuthApiKey(settings.weaviate_api_key),
    )


def retrieve_similar_patterns(diff: str, k: int = 5) -> list[dict]:
    client = get_client()
    try:
        collection = client.collections.get(CLASS_NAME)
        results = collection.query.near_text(
            query=diff,
            limit=k,
        )
        return [obj.properties for obj in results.objects]
    finally:
        client.close()
