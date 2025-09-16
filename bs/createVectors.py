# bs/createVectors.py
import json
import os
import datetime
import requests
from dotenv import load_dotenv

from logging_config import setup_logger
logger = setup_logger("bs.createVectors")
logger.debug("Logger initialized")

# Use the existing Redis client and Upstash index from db.py
from bs.db import redis_client, upstash_index

import re

def normalize_text(text: str) -> str:
    """
    Normalize text to generate consistent Redis keys and vector IDs.
    """
    if not text:
        return ""
    text = text.strip().lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

load_dotenv()   

# Jina API configuration for embeddings
JINA_API_KEY = os.getenv("JINA_EMBEDDING_API_KEY")
JINA_API_URL = 'https://api.jina.ai/v1/embeddings'
JINA_HEADERS = {
    'Content-Type': 'application/json',
    'Authorization': f'Bearer {JINA_API_KEY}'
}

def get_jina_embeddings(texts):
    """
    Get embeddings for multiple texts using the Jina API.
    Returns a list of 1024-d float vectors.
    """
    start_time = datetime.datetime.now()
    try:
        logger.info(f"Starting Jina API embedding generation for {len(texts)} texts")
        data = {
            "model": "jina-embeddings-v3",
            "task": "text-matching",
            "late_chunking": False,
            "dimensions": 1024,
            "embedding_type": "float",
            "input": texts
        }
        response = requests.post(JINA_API_URL, headers=JINA_HEADERS, json=data)
        response.raise_for_status()
        result = response.json()
        embeddings = [item["embedding"] for item in result["data"]]
        end_time = datetime.datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"Successfully generated {len(embeddings)} embeddings in {duration:.2f} seconds (avg {duration/len(embeddings):.2f}s per text)")
        for i, emb in enumerate(embeddings):
            if not isinstance(emb, list) or len(emb) != 1024:
                raise ValueError(f"Invalid embedding at position {i}: expected 1024-dim vector, got {len(emb) if isinstance(emb, list) else type(emb)}")
        return embeddings
    except Exception as e:
        logger.error(f"Error getting Jina embeddings: {e}")
        raise

def createDataCollectionUsingCanHelpSkills(data):
    """
    Process canHelpSkills from the profile data.
    For each skill, check Redis cache for an embedding.
    If missing, generate using Jina and cache it.
    Returns a list of dicts containing the skill metadata and embedding.
    """
    start_time = datetime.datetime.now()
    logger.info(f"Starting skill processing for profile {data.get('_id')} with name {data.get('name')}")
    dataCollection = []
    
    skills_dict = data.get("canHelpSkills", {})
    total_skills = len(skills_dict)
    logger.info(f"Found {total_skills} skills to process")
    
    norm_skill_keys = [f"skill:{normalize_text(skill)}" for skill in skills_dict.keys()]
    cached_values = redis_client.mget(*norm_skill_keys)
    
    # Log cache statistics
    cached_count = len([v for v in cached_values if v is not None])
    uncached_count = len([v for v in cached_values if v is None])
    logger.info(f"Cache status for skills: {cached_count}/{total_skills} found in cache ({(cached_count/total_skills)*100:.1f}%), {uncached_count} need generation")
    
    uncached_descriptions = []
    uncached_indices = []
    uncached_keys = []
    
    for i, (skill_name, skill_description, redis_key, cached_value) in enumerate(
        zip(skills_dict.keys(), skills_dict.values(), norm_skill_keys, cached_values)
    ):
        if not cached_value:
            uncached_descriptions.append(skill_description)
            uncached_indices.append(i)
            uncached_keys.append(redis_key)
    
    if uncached_descriptions:
        logger.info(f"Generating embeddings for {len(uncached_descriptions)} uncached skills")
        new_embeddings = get_jina_embeddings(uncached_descriptions)
        logger.info(f"Successfully generated embeddings for {len(new_embeddings)} skills")
    
    for i, (skill_name, skill_description, redis_key, cached_value) in enumerate(
        zip(skills_dict.keys(), skills_dict.values(), norm_skill_keys, cached_values)
    ):
        dataNew = {
            "personId": data.get("_id"),
            "name": data.get("name", ""),
            "userId": data.get("userId"),
            "skillName": skill_name,
            "skillDescription": skill_description
        }
        
        if cached_value:
            try:
                cached_data = json.loads(cached_value)
                if "embeddings" in cached_data:
                    dataNew["embeddings"] = cached_data["embeddings"]
                else:
                    raise KeyError("No embedding data found in cache")
            except Exception as e:
                logger.error(f"Error parsing cached skill data: {str(e)}")
                raise
        else:
            if i in uncached_indices:
                uncached_idx = uncached_indices.index(i)
                embeddings = new_embeddings[uncached_idx]
                dataNew["embeddings"] = embeddings
                skill_object = {
                    "description": skill_description,
                    "embeddings": embeddings
                }
                redis_client.set(redis_key, json.dumps(skill_object, ensure_ascii=False))
            else:
                logger.error(f"Unexpected: missing embedding for skill at index {i}")
        dataCollection.append(dataNew)
    
    end_time = datetime.datetime.now()
    duration = (end_time - start_time).total_seconds()
    logger.info(f"Completed skill processing in {duration:.2f} seconds. Processed {len(dataCollection)} skills total.")
    return dataCollection
