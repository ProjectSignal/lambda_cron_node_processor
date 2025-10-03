# bs/parseHtmlForDescription.py - Lambda-adapted version
from datetime import datetime
import json
import copy
import os
import re
import requests
import time
from fuzzywuzzy import fuzz
import asyncio
import hmac
import hashlib

# == Imports from Lambda codebase ==
from bs.scrape import scrape_profile_data
from bs.generate_description import generate_descriptions_litellm
from bs.db import upstash_index, get_or_create_webpage_document
# Note: Upstash vector operations will now be handled via createVectors.py
from bs.createVectors import (
    createDataCollectionUsingCanHelpSkills,
    normalize_text
)
# For vector upsert via Upstash
from upstash_vector import Vector
from other.cloudflareFunctions import CloudflareImageHandler, delete_cloudflare_image

# Import Lambda config
from config import config
from clients import get_clients
from logging_config import setup_logger

_clients = get_clients()
api_client = _clients.api

logger = setup_logger("bs.parseHtmlForDescription")
logger.debug("Logger initialized")


def _fetch_node(node_id: str):
    """Retrieve node data via the REST API."""
    # API Route: nodes.getById, Input: {"nodeId": node_id}, Output: {"data": {...}}
    response = api_client.get(f"nodes/{node_id}")
    if isinstance(response, dict) and response.get("success") is False:
        logger.error("Node fetch failed for %s: %s", node_id, response.get("message"))
        return {}
    if isinstance(response, dict) and "data" in response:
        return response["data"]
    return response


def _update_node(node_id: str, payload: dict):
    """Persist node updates via the REST API."""
    # API Route: nodes.update, Input: payload, Output: {"success": bool}
    response = api_client.request("PATCH", f"nodes/{node_id}", payload)
    if isinstance(response, dict) and response.get("success") is False:
        logger.error("Node update failed for %s: %s", node_id, response.get("message"))
    return response


def _delete_node(node_id: str):
    """Delete a node via the REST API."""
    # API Route: nodes.delete, Input: {"nodeId": node_id}, Output: {"success": bool}
    response = api_client.request("DELETE", f"nodes/{node_id}")
    if isinstance(response, dict) and response.get("success") is False:
        logger.error("Node delete failed for %s: %s", node_id, response.get("message"))
    return response


def _mark_node_error(node_id: str, error_message: str):
    """Flag a node as errored."""
    payload = {
        "nodeId": node_id,
        "errorMessage": error_message,
    }
    # API Route: nodes.markError, Input: payload, Output: {"success": bool}
    response = api_client.request("POST", "nodes/mark-error", payload)
    if isinstance(response, dict) and response.get("success") is False:
        logger.error("Failed to mark node %s as errored: %s", node_id, response.get("message"))
    return response


def _search_nodes_for_user(user_id: str, exclude_node_id: str):
    """Search for nodes belonging to the same user for duplicate detection."""
    payload = {
        "userId": user_id,
        "excludeNodeId": exclude_node_id,
    }
    # API Route: nodes.searchByUser, Input: payload, Output: {"nodes": [...]}
    response = api_client.request("POST", "nodes/search-by-user", payload)
    if isinstance(response, dict) and response.get("success") is False:
        logger.error("Node search failed for user %s: %s", user_id, response.get("message"))
        return []
    return response.get("nodes", [])

# == ENV variables for Cloudflare - Use Lambda config ==
CLOUDFLARE_ACCOUNT_ID = config.CLOUDFLARE_ACCOUNT_ID
CLOUDFLARE_API_TOKEN = config.CLOUDFLARE_API_TOKEN  # User API Token for Images
logger.info(f"CLOUDFLARE_ACCOUNT_ID: {CLOUDFLARE_ACCOUNT_ID}")
logger.info(f"CLOUDFLARE_API_TOKEN: {CLOUDFLARE_API_TOKEN}")

def upload_images_to_cloudflare(profile_data):
    """
    Given profile_data with raw image URLs, generate Cloudflare URLs in place.
    - avatarURL
    - each companyLogo in workExperience
    - each schoolLogo in education
    """
    handler = CloudflareImageHandler(debug=True)

    # 1. Avatar
    if profile_data.get("avatarURL"):
        # Check if it's already a Cloudflare URL
        avatar_url = profile_data["avatarURL"]
        if not isinstance(avatar_url, str) or not avatar_url.startswith("https://imagedelivery.net"):
            try:
                new_avatar = handler.upload_image(profile_data["avatarURL"])
                if isinstance(new_avatar, dict) and new_avatar.get("success"):
                    profile_data["avatarURL"] = new_avatar.get("result", {}).get("variants", [])[0]
                else:
                    logger.warning(f"Avatar upload unsuccessful, keeping original URL: {profile_data['avatarURL']}")
            except Exception as e:
                logger.error(f"Error uploading avatar image: {str(e)}")
                # Keep original URL on failure
        else:
            logger.info(f"Keeping existing Cloudflare avatar URL: {avatar_url}")

    # 2. Work experience
    if profile_data.get("workExperience"):
        for exp in profile_data["workExperience"]:
            if exp.get("companyLogo"):
                # Check if it's already a Cloudflare URL
                company_logo = exp["companyLogo"]
                if not isinstance(company_logo, str) or not company_logo.startswith("https://imagedelivery.net"):
                    try:
                        new_logo = handler.upload_image(exp["companyLogo"])
                        if isinstance(new_logo, dict) and new_logo.get("success"):
                            exp["companyLogo"] = new_logo.get("result", {}).get("variants", [])[0]
                        else:
                            logger.warning(f"Company logo upload unsuccessful, keeping original URL: {exp['companyLogo']}")
                    except Exception as e:
                        logger.error(f"Error uploading company logo: {str(e)}")
                        # Keep original URL on failure
                else:
                    logger.info(f"Keeping existing Cloudflare company logo URL: {company_logo}")

    # 3. Education
    if profile_data.get("education"):
        for edu in profile_data["education"]:
            if edu.get("schoolLogo"):
                # Check if it's already a Cloudflare URL
                school_logo = edu["schoolLogo"]
                if not isinstance(school_logo, str) or not school_logo.startswith("https://imagedelivery.net"):
                    try:
                        new_logo = handler.upload_image(edu["schoolLogo"])
                        if isinstance(new_logo, dict) and new_logo.get("success"):
                            edu["schoolLogo"] = new_logo.get("result", {}).get("variants", [])[0]
                        else:
                            logger.warning(f"School logo upload unsuccessful, keeping original URL: {edu['schoolLogo']}")
                    except Exception as e:
                        logger.error(f"Error uploading school logo: {str(e)}")
                        # Keep original URL on failure
                else:
                    logger.info(f"Keeping existing Cloudflare school logo URL: {school_logo}")

    return profile_data

def extract_cloudflare_urls(profile_data):
    """
    Extract all Cloudflare URLs from a profile data object.
    Returns a list of URLs that are from Cloudflare (starting with https://imagedelivery.net).
    """
    cloudflare_urls = []
    
    # Check avatar URL
    avatar_url = profile_data.get("avatarURL")
    if isinstance(avatar_url, str) and avatar_url.startswith("https://imagedelivery.net"):
        cloudflare_urls.append(avatar_url)
    
    # Check work experience logos
    if profile_data.get("workExperience"):
        for exp in profile_data["workExperience"]:
            logo_url = exp.get("companyLogo")
            if isinstance(logo_url, str) and logo_url.startswith("https://imagedelivery.net"):
                cloudflare_urls.append(logo_url)
    
    # Check education logos
    if profile_data.get("education"):
        for edu in profile_data["education"]:
            logo_url = edu.get("schoolLogo")
            if isinstance(logo_url, str) and logo_url.startswith("https://imagedelivery.net"):
                cloudflare_urls.append(logo_url)
                
    return cloudflare_urls


# ---------------------------------------------------------------------------------
# Utility: Checking if a scraped profile is "empty"
# ---------------------------------------------------------------------------------
def check_empty_profile(profile_info):
    """
    Check if more than 3 important profile keys are empty.
    If >= 3 keys are empty, raise ValueError to abort further processing.
    """
    keys_to_check = ["about", "workExperience", "education", "skills", "contacts", "currentLocation"]
    empty_keys = [key for key in keys_to_check if not profile_info.get(key)]
    if len(empty_keys) >= 3:
        raise ValueError(f"Three or more profile keys are empty: {', '.join(empty_keys)}")


# ---------------------------------------------------------------------------------
# Utility: Duplicate Checking
# ---------------------------------------------------------------------------------
def calculate_work_experience_similarity(exp1, exp2):
    """Simple similarity check for work experiences by matching company names."""
    if not exp1 or not exp2:
        return 0
    
    companies1 = {exp.get('companyName', '').lower().strip() for exp in exp1 if exp.get('companyName')}
    companies2 = {exp.get('companyName', '').lower().strip() for exp in exp2 if exp.get('companyName')}
    if not companies1 or not companies2:
        return 0
            
    intersection = len(companies1.intersection(companies2))
    union = len(companies1.union(companies2))
    return (intersection / union) * 100 if union > 0 else 0


def calculate_overall_similarity(new_profile, existing_profile):
    """
    Overall similarity between two profiles using weighted metrics.
    Similar to your existing approach, uses fuzzy matching on name, about, headline, etc.
    """
    total_weight = 0
    total_similarity = 0

    # Name similarity (0.4)
    name1 = new_profile.get('name', '')
    name2 = existing_profile.get('name', '')
    if name1 and name2:
        name_similarity = fuzz.ratio(name1.lower().strip(), name2.lower().strip())
        total_similarity += name_similarity * 0.4
        total_weight += 0.4

    # About similarity (0.2)
    about1 = new_profile.get('about', '')
    about2 = existing_profile.get('about', '')
    if about1 and about2:
        about_similarity = fuzz.ratio(about1.lower().strip(), about2.lower().strip())
        total_similarity += about_similarity * 0.2
        total_weight += 0.2

    # Headline similarity (0.2)
    headline1 = new_profile.get('bio', '')
    headline2 = existing_profile.get('bio', '')
    if headline1 and headline2:
        headline_similarity = fuzz.ratio(headline1.lower().strip(), headline2.lower().strip())
        total_similarity += headline_similarity * 0.2
        total_weight += 0.2

    # Work experience similarity (0.2)
    work_exp1 = new_profile.get('workExperience', [])
    work_exp2 = existing_profile.get('workExperience', [])
    if work_exp1 and work_exp2:
        work_exp_similarity = calculate_work_experience_similarity(work_exp1, work_exp2)
        total_similarity += work_exp_similarity * 0.2
        total_weight += 0.2

    if total_weight <= 0.4:  # Only name was compared
        return total_similarity * 0.5

    final_similarity = (total_similarity / total_weight) * total_weight
    return final_similarity


def find_potential_duplicate(new_profile_info):
    """
    Find potential duplicate profiles for a given user based on similarity metrics.
    Return tuple: (best_match_node, similarity) or (None, 0) if no match
    """
    user_id = new_profile_info.get("userId")
    if not user_id:
        return None, 0

    logger.info(f"Checking for potential duplicates for profile: {new_profile_info.get('name')}")

    try:
        existing_nodes = _search_nodes_for_user(
            user_id=user_id,
            exclude_node_id=new_profile_info.get('_id'),
        )

        logger.info(f"Found {len(existing_nodes)} possible nodes to compare with for userId {user_id}")
        matches = []
        for existing_node in existing_nodes:
            # Quick check on name similarity as a filter
            name_similarity = fuzz.ratio(
                new_profile_info.get('name', '').lower().strip(),
                existing_node.get('name', '').lower().strip()
            )
            if name_similarity >= 50:
                overall_similarity = calculate_overall_similarity(new_profile_info, existing_node)
                if overall_similarity >= 50:
                    matches.append((existing_node, overall_similarity))

        if matches:
            # Return the best match
            best_match = max(matches, key=lambda x: x[1])
            logger.info(f"Best duplicate match: {best_match[0]['_id']} with similarity {best_match[1]:.2f}%")
            return best_match[0], best_match[1]
        return None, 0
    except Exception as e:
        logger.error(f"Error in find_potential_duplicate: {str(e)}")
        return None, 0

# -------------------------------
# UPDATED VECTOR UPSERT FUNCTION
# -------------------------------
async def update_vector_stores(profile_info, person_id):
    """
    Generate new embeddings for 'canHelpSkills' and upsert them
    into Upstash using Vector objects.
    """
    logger.info(f"Updating vector stores for person ID: {person_id}")
    BATCH_SIZE = 100  # Match the batch size from example
    
    try:
        # Process skills (canHelpSkills)
        canHelpOutput = createDataCollectionUsingCanHelpSkills(profile_info)
        if canHelpOutput:
            skill_vectors = []
            total_processed = 0
            logger.info(f"Processing {len(canHelpOutput)} skills for person {person_id}")
            
            for item in canHelpOutput:
                skill_name = item["skillName"]
                vector_id = f"{str(person_id)}_{normalize_text(skill_name)}"
                logger.info(f"Creating skill vector - ID: {vector_id}, Skill: {skill_name}")
                vector_obj = Vector(
                    id=vector_id,
                    vector=item["embeddings"],
                    metadata={
                        "skillName": item["skillName"],
                        "skillDescription": item["skillDescription"],
                        "personId": str(item["personId"]),
                        "userId": str(item["userId"])
                    },
                    data=item["skillDescription"]
                )
                skill_vectors.append(vector_obj)
                
                # Process batch if we've reached batch size
                if len(skill_vectors) >= BATCH_SIZE:
                    try:
                        logger.info(f"Upserting batch of {len(skill_vectors)} skill vectors to Upstash")
                        upstash_index.upsert(vectors=skill_vectors, namespace="skills")
                        total_processed += len(skill_vectors)
                        logger.info(f"Successfully upserted batch. Total processed: {total_processed}")
                        skill_vectors = []  # Clear the batch
                    except Exception as e:
                        logger.error(f"Failed to upsert skill batch: {str(e)}")
                        raise
            
            # Process any remaining skill vectors
            if skill_vectors:
                try:
                    logger.info(f"Upserting final batch of {len(skill_vectors)} skill vectors to Upstash")
                    upstash_index.upsert(vectors=skill_vectors, namespace="skills")
                    total_processed += len(skill_vectors)
                    logger.info(f"Successfully upserted all {total_processed} skills to Upstash vector store")
                except Exception as e:
                    logger.error(f"Failed to upsert final skill batch: {str(e)}")
                    raise

        return True

    except Exception as e:
        logger.error(f"Error updating vector stores: {str(e)}")
        # Re-raise the exception to be handled by the caller
        raise


# ---------------------------------------------------------------------------------
# Utility: Final Node Update + Image Upload
# ---------------------------------------------------------------------------------
def update_node_in_db(node_id, updated_data):
    """
    Final DB update on the older node or on a new node.
    We set 'descriptionGenerated' = True, plus a timestamp.
    """
    try:
        # First, get the current node data to check for existing Cloudflare images
        current_node = _fetch_node(node_id)
        
        # Log that we're preserving existing Cloudflare images
        if current_node:
            existing_cloudflare_urls = extract_cloudflare_urls(current_node)
            if existing_cloudflare_urls:
                logger.info(f"Preserving {len(existing_cloudflare_urls)} existing Cloudflare images instead of deleting and recreating")
        
        # Create a copy of updated_data to avoid modifying the original
        data_to_set = copy.deepcopy(updated_data)
        data_to_set.pop("_id", None)
        data_to_set.pop("userId", None)
        # Ensure conflicting keys are removed before spreading into $set
        data_to_set.pop("error", None)
        data_to_set.pop("errorMessage", None)
        data_to_set.pop("errorAt", None)
        data_to_set.pop("apiScrapedError", None)
        # data_to_set.pop("highLevelProfileInsightsCompleted", None)
        
        payload = {
            "set": {
                **data_to_set,
                "descriptionGenerated": True,
                "scrapped": True,
                "descriptionGeneratedAt": datetime.utcnow().isoformat(),
            },
            "unset": ["error", "errorAt", "errorMessage", "apiScrapedError"],
        }

        # API Route: nodes.updateProfile, Input: payload, Output: {"success": bool}
        response = _update_node(node_id, payload)
        if response.get("success"):
            logger.info(f"Successfully updated node {node_id} with new data.")
        else:
            logger.info(f"Node update API did not confirm success for {node_id}")
        return True
    except Exception as e:
        logger.error(f"Error updating node {node_id}: {str(e)}")
        return False


# ---------------------------------------------------------------------------------
# Utility: Webpage Document Creation
# ---------------------------------------------------------------------------------
def create_webpage_documents(profile_info):
    """
    Create or get webpage documents for both profile and work experiences.
    Args:
        profile_info: Dictionary containing profile information including work experience
    Returns:
        Updated profile_info with webpage IDs added
    """
    # Create/get webpage documents for work experiences
    if "workExperience" in profile_info:
        for exp in profile_info["workExperience"]:
            if exp.get("companyUrl"):  # Only create if we have a URL
                company_webpage_id = get_or_create_webpage_document(
                    url=exp["companyUrl"],
                    name=exp.get("companyName", "")
                )
                exp["webpageId"] = company_webpage_id
                logger.info(f"Created/Retrieved webpage document for company: {exp.get('companyName')} with ID: {company_webpage_id}")

    return profile_info


def _collect_webpage_ids(profile_info):
    """Return a de-duplicated list of webpageIds extracted from work experience."""
    if not profile_info:
        return []

    webpage_ids = []
    seen: set = set()
    for experience in profile_info.get("workExperience", []) or []:
        if not isinstance(experience, dict):
            continue
        webpage_id = experience.get("webpageId")
        if not webpage_id:
            continue
        web_id_str = str(webpage_id)
        if web_id_str in seen:
            continue
        seen.add(web_id_str)
        webpage_ids.append(web_id_str)
    return webpage_ids


# ---------------------------------------------------------------------------------
# Main Flow: Called by run_scrapper_openai / run_scrapper_claude
# ---------------------------------------------------------------------------------
async def run_scraper_base(profileHTML, name, username, personId, userId, created_at, existing_node):
    """
    The central function that implements the flow:
      1) Scrape (no Cloudflare)
      2) Check empties
      3) Duplicate check
         - If duplicate => use older node ID for vector store
             -> generate description from new data
             -> update vectors using older node's ID
             -> remove new node from DB
             -> final step: merge with existing Cloudflare images & update older node
         - If not duplicate => check if data changed or if this is first time
             -> if not changed => exit
             -> if changed => generate description, update vectors, preserve existing images, update node
    """
    error_count = 0
    max_errors = 3

    logger.info(f"Starting scraper process for {name} ({username}) - Node: {personId}")
    new_profile_info = {}

    try:
        # Step 1: Check if API scraped data exists and use it, otherwise scrape
        if existing_node and existing_node.get("apiScraped") is True:
            logger.info(f"Using existing API scraped data for node {personId}")
            # Use deepcopy to avoid modifying the original existing_node accidentally
            new_profile_info = copy.deepcopy(existing_node)
            # Ensure essential keys that might not be in the apiScraped version are present or updated
            # Note: We overwrite potentially existing values from existing_node with current run's values
            new_profile_info["name"] = name
            new_profile_info["createdAt"] = created_at # Use current timestamp
            new_profile_info["userId"] = userId
            new_profile_info["_id"] = personId
            # apiScraped field remains in new_profile_info, downstream logic might need to handle/remove it if necessary
        else:
            logger.info(f"Scraping profile data for node {personId}")
            # Scrape the data (NO Cloudflare calls in scraping)
            new_profile_info = scrape_profile_data(profileHTML)
            new_profile_info["name"] = name
            new_profile_info["createdAt"] = created_at
            new_profile_info["userId"] = userId
            new_profile_info["_id"] = personId

        # Store new_profile_info as JSON locally for potential future reference
        # Step 2: Check empties
        check_empty_profile(new_profile_info)

        # Step 3: Duplicate check (no description needed for the check)
        duplicate_node, similarity = find_potential_duplicate(new_profile_info)
        if duplicate_node:
            # *** DUPLICATE CASE ***
            older_node_id = str(duplicate_node["_id"])
            logger.info(f"Detected duplicate with older node {older_node_id}. Similarity={similarity:.2f}%")

            # (1) Generate description with the newly scraped data
            updated_profile_info = await generate_descriptions_litellm(new_profile_info)

            # (2) Update vectors using the older node's ID
            await update_vector_stores(updated_profile_info, older_node_id)

            # (3) Delete the new node from DB (the "newer" node)
            _delete_node(personId)
            logger.info(f"Deleted the new node {personId} via API")
            
            # (4) Create webpage documents
            updated_profile_info = create_webpage_documents(updated_profile_info)
            
            # (5) Upload only new images to Cloudflare, preserving existing ones
            final_profile_info = upload_images_to_cloudflare(updated_profile_info)
            
            # (6) Update older node in DB
            update_node_in_db(older_node_id, final_profile_info)
            logger.info(f"Duplicate handling complete for older node {older_node_id}")
            return {
                "success": True,
                "deduplicated": True,
                "effective_node_id": older_node_id,
                "merged_from_node_id": str(personId),
                "webpage_ids": _collect_webpage_ids(final_profile_info),
                "profile": final_profile_info,
                "skipped": False,
            }

        else:
            # *** NON-DUPLICATE CASE ***
            # Check if fields have changed or if it's first time scraping
            # 1) If existing_node is None => first time => proceed with normal flow
            # 2) If existing_node is present => compare workExperience, education, etc.
            logger.info(f"no duplicate node found")
            has_changes = False
            changed_fields = []
            if existing_node:
                # Compare relevant fields using the new comparison logic
                has_changes, changed_fields = has_significant_changes(new_profile_info, existing_node)
                logger.info(f"Change detection results - has_changes: {has_changes}, changed_fields: {changed_fields}")
                
                # If no changes => exit
                if not has_changes and not existing_node.get("error"):
                    logger.info("No significant changes found; skipping update.")
                    profile_source = existing_node or new_profile_info
                    return {
                        "success": True,
                        "deduplicated": False,
                        "effective_node_id": str(personId),
                        "webpage_ids": _collect_webpage_ids(profile_source),
                        "profile": profile_source,
                        "skipped": True,
                        "changed_fields": [],
                    }
                
                if changed_fields:
                    logger.info(f"Changes detected in fields: {', '.join(changed_fields)}")
            else:
                logger.info("No existing node found, proceeding with first-time processing")

            # Only proceed if:
            # 1. No existing_node (first time processing) OR
            # 2. Has changes OR
            # 3. Has error flag
            if not existing_node or has_changes or existing_node.get("error"):
                logger.info("Proceeding with update due to: " + 
                          ("first time processing" if not existing_node else 
                           "changes detected" if has_changes else 
                           "error flag present"))
                
                # Generate description, update vectors, images, update node
                updated_profile_info = await generate_descriptions_litellm(new_profile_info)

                await update_vector_stores(updated_profile_info, personId)

                # Create webpage documents for profile and work experiences
                updated_profile_info = create_webpage_documents(updated_profile_info)

                # Upload images to Cloudflare, preserving existing ones
                final_profile_info = upload_images_to_cloudflare(updated_profile_info)
                
                # Update node in DB
                update_node_in_db(personId, final_profile_info)
                logger.info(f"Non-duplicate node updated successfully.")
                return {
                    "success": True,
                    "deduplicated": False,
                    "effective_node_id": str(personId),
                    "webpage_ids": _collect_webpage_ids(final_profile_info),
                    "profile": final_profile_info,
                    "skipped": False,
                    "changed_fields": changed_fields if existing_node else ["initial_generation"],
                }
            else:
                logger.info("Skipping update as no changes or errors were found")
                profile_source = existing_node or new_profile_info
                return {
                    "success": True,
                    "deduplicated": False,
                    "effective_node_id": str(personId),
                    "webpage_ids": _collect_webpage_ids(profile_source),
                    "profile": profile_source,
                    "skipped": True,
                    "changed_fields": [],
                }

    except Exception as e:
        logger.error(f"Error in scraper process for node {personId}: {str(e)}")
        error_count += 1
        error_message = str(e)
        # Handle empty profile case using existing_node data
        if "Three or more profile keys are empty" in str(e):
            # Check if error already exists in the existing node data
            existing_error = existing_node.get("errorMessage", "") if existing_node else ""

            if "Three or more profile keys are empty" in existing_error:
                # Second occurrence - delete the node
                try:
                    _delete_node(personId)
                    logger.info(f"Deleted node {personId} due to repeated empty profile errors")
                    return  # Exit early after deletion
                except Exception as delete_error:
                    logger.error(f"Error during node deletion: {str(delete_error)}")

        # Original error handling with modification to store specific message
        try:
            if "Three or more profile keys are empty" in error_message:
                error_message = f"Empty profile detected: {error_message}"

            _mark_node_error(personId, error_message)
        except Exception as e2:
            logger.error(f"Error while marking node {personId} as error: {str(e2)}")

        if error_count >= max_errors:
            logger.error(f"Max retries ({max_errors}) reached for {personId}")
            return {
                "success": False,
                "error": error_message,
                "deduplicated": False,
                "effective_node_id": str(personId),
                "webpage_ids": [],
                "profile": existing_node,
                "skipped": False,
            }

        return {
            "success": False,
            "error": error_message,
            "deduplicated": False,
            "effective_node_id": str(personId),
            "webpage_ids": [],
            "profile": existing_node,
            "skipped": False,
        }


def normalize_work_experience(work_exp):
    """Normalize work experience data for comparison by removing volatile fields and standardizing format."""
    if not work_exp:
        return []
    
    normalized = []
    for exp in work_exp:
        # Create a copy to avoid modifying the original
        exp_copy = exp.copy()
        # Remove fields that might change frequently or are not significant for comparison
        exp_copy.pop('companyLogo', None)  # Logos might change
        exp_copy.pop('duration', None)     # Duration format might vary
        exp_copy.pop('webpageId', None)    # Webpage IDs might change
        # Normalize the description by removing whitespace and newlines
        if 'description' in exp_copy:
            exp_copy['description'] = ' '.join(exp_copy['description'].split())
        normalized.append(exp_copy)
    
    # Sort by company name to ensure consistent ordering
    return sorted(normalized, key=lambda x: x.get('companyName', ''))


def normalize_education(education):
    """Normalize education data for comparison by removing volatile fields and standardizing format."""
    if not education:
        return []
    
    normalized = []
    for edu in education:
        # Create a copy to avoid modifying the original
        edu_copy = edu.copy()
        # Remove fields that might change frequently
        edu_copy.pop('schoolLogo', None)  # Logos might change
        normalized.append(edu_copy)
    
    # Sort by school name to ensure consistent ordering
    return sorted(normalized, key=lambda x: x.get('school', ''))


def normalize_simple_field(value):
    """Normalize simple comparable values (strings, ints, dicts) for stable change detection."""
    if value is None:
        return ""
    if isinstance(value, str):
        # Collapse whitespace and lowercase so cosmetic edits do not trigger reruns
        return re.sub(r"\s+", " ", value).strip().lower()
    try:
        # Produce deterministic serialization for nested structures
        return json.dumps(value, sort_keys=True, default=str)
    except TypeError:
        return str(value)


def compare_fields(field1, field2, field_name):
    """Compare two fields with special handling for different field types."""
    if field_name == 'workExperience':
        return normalize_work_experience(field1) == normalize_work_experience(field2)
    elif field_name == 'education':
        return normalize_education(field1) == normalize_education(field2)
    elif field_name == 'contacts':
        # For simple dicts, do a string comparison of sorted JSON
        return json.dumps(field1, sort_keys=True) == json.dumps(field2, sort_keys=True)
    else:
        # For simple fields like about, bio, and currentLocation
        return normalize_simple_field(field1) == normalize_simple_field(field2)


def has_significant_changes(new_profile_info, existing_node):
    """
    Check if there are significant changes between new and existing profile data.
    Returns (bool, list): Tuple of (has_changes, changed_fields)
    
    If descriptionGenerated is False in existing_node, returns (True, ["initial_generation"])
    to indicate that this is the first time generating description.
    """
    # If descriptionGenerated is False or doesn't exist, we should process it

    if not existing_node.get("descriptionGenerated", False):
        logger.info("Profile has not had description generated yet, proceeding with generation")
        return True, ["initial_generation"]
    
    fields_to_compare = [
        "about",
        "bio",
        "linkedinHeadline",
        "workExperience",
        "education",
        "currentLocation",
    ]
    changed_fields = []
    
    for field in fields_to_compare:
        new_value = new_profile_info.get(field)
        existing_value = existing_node.get(field)
        
        if not compare_fields(new_value, existing_value, field):
            logger.info(f"\n{'='*50}\nChanges detected in field: '{field}'\n{'='*50}")
            
            if field == "workExperience":
                # Normalize both for comparison
                new_normalized = normalize_work_experience(new_value)
                existing_normalized = normalize_work_experience(existing_value)
                
                # Compare each experience
                new_companies = {exp.get('companyName'): exp for exp in new_normalized}
                existing_companies = {exp.get('companyName'): exp for exp in existing_normalized}
                
                # Check for changes in existing companies
                for company in set(new_companies.keys()) & set(existing_companies.keys()):
                    new_exp = new_companies[company]
                    existing_exp = existing_companies[company]
                    if new_exp != existing_exp:
                        logger.info(f"\nChanges in company: {company}")
                        for key in set(new_exp.keys()) | set(existing_exp.keys()):
                            if new_exp.get(key) != existing_exp.get(key):
                                logger.info(f"Field '{key}' changed:")
                                logger.info(f"  Old: {existing_exp.get(key)}")
                                logger.info(f"  New: {new_exp.get(key)}")
                
                # Check for added companies
                added = set(new_companies.keys()) - set(existing_companies.keys())
                if added:
                    logger.info(f"\nNewly added companies: {added}")
                
                # Check for removed companies
                removed = set(existing_companies.keys()) - set(new_companies.keys())
                if removed:
                    logger.info(f"\nRemoved companies: {removed}")
                
            elif field in ['education', 'contacts']:
                logger.info("Old value:")
                logger.info(json.dumps(existing_value, indent=2))
                logger.info("\nNew value:")
                logger.info(json.dumps(new_value, indent=2))
            else:
                logger.info(f"Old value: {existing_value}")
                logger.info(f"New value: {new_value}")
            
            changed_fields.append(field)
    
    return bool(changed_fields), changed_fields
