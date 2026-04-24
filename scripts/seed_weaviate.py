#!/usr/bin/env python3
"""One-time script to load vulnerability patterns into Weaviate Cloud."""
import os
import sys
import yaml
import weaviate
import weaviate.classes as wvc

# Load env before importing app
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app.config import settings

CLASS_NAME = "VulnerabilityPattern"
PATTERNS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "vulnerability_patterns.yaml")


def seed():
    client = weaviate.connect_to_weaviate_cloud(
        cluster_url=settings.weaviate_url,
        auth_credentials=weaviate.auth.AuthApiKey(settings.weaviate_api_key),
    )
    try:
        # Create collection if it doesn't exist
        existing = [c.name for c in client.collections.list_all().values()]
        if CLASS_NAME not in existing:
            client.collections.create(
                CLASS_NAME,
                vectorizer_config=wvc.config.Configure.Vectorizer.text2vec_weaviate(),
                properties=[
                    wvc.config.Property(name="name", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="category", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="severity", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="description", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="example_code", data_type=wvc.config.DataType.TEXT),
                    wvc.config.Property(name="remediation", data_type=wvc.config.DataType.TEXT),
                ],
            )
            print(f"Created collection: {CLASS_NAME}")
        else:
            print(f"Collection {CLASS_NAME} already exists, skipping creation")

        collection = client.collections.get(CLASS_NAME)

        with open(PATTERNS_FILE) as f:
            data = yaml.safe_load(f)

        patterns = data["patterns"]
        existing_names = {
            obj.properties.get("name")
            for obj in collection.iterator()
        }

        inserted = 0
        for pattern in patterns:
            if pattern["name"] not in existing_names:
                collection.data.insert(pattern)
                inserted += 1

        print(f"Inserted {inserted} new patterns ({len(patterns) - inserted} already existed)")
    finally:
        client.close()


if __name__ == "__main__":
    seed()
