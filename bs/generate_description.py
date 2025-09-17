# generate_description.py - Lambda-adapted version
import sys
import os
import time
import re
import ast
import json
from typing import Any, Dict, List
import xml.etree.ElementTree as ET
from io import StringIO
from bs4 import BeautifulSoup
import asyncio  # <-- Import asyncio for concurrent tasks

# ---------------------
# 1) Redis Integration
# ---------------------
from bs.db import redis_client as r, async_redis_client as ar

# ---------------------
# LLM Provider Configuration
# ---------------------
DEFAULT_LLM_PROVIDER = os.getenv("GENERATE_DESCRIPTION_PROVIDER", "gemini")

from config import LLMManager, CustomCallback
from logging_config import setup_logger
from clients import get_clients

# 2) Prompts
from prompts.location import LOCATION_USER_PROMPT, stop_sequences as location_stop_sequences
from prompts.wed import WED_USER_PROMPT, stop_sequences as wed_stop_sequences
from prompts.canhelp import (
    CANHELP_USER_PROMPT,
    stop_sequences as canhelp_stop_sequences
)
from prompts.orgstring import (
    ORGSTRING_SYSTEM_PROMPT,
    ORGSTRING_USER_PROMPT,
    stop_sequences as orgstring_stop_sequences
)
from prompts.descriptionForKeyword import USER_MESSAGE, stop_sequences as description_stop_sequences

# 3) Other helpers
from other.jsonToXml import json_to_xml

logger = setup_logger("bs.generate_description")
logger.debug("Logger initialized")

_clients = get_clients()
api_client = _clients.api

# ---------------------------------------
# COMMON HELPER for Normalization
# ---------------------------------------
def normalize_text(text: str) -> str:
    """
    Convert text to a normalized form to ensure consistent Redis keys.
    - Converts to lowercase
    - Removes special characters (except spaces)
    - Replaces multiple spaces with single space
    - Removes leading/trailing whitespace
    """
    if not text:
        return ""
    text = text.strip().lower()
    # Replace special characters (including :) with spaces
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    # Replace multiple spaces with single space
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ---------------------------------------
# Company Info
# ---------------------------------------
def company_name_similarity(name1: str, name2: str) -> float:
    """
    Calculate similarity between two company names.
    Returns a score between 0 and 1, where 1 means exact match.
    """
    def clean_name(name):
        name = name.lower().strip()
        suffixes = [' inc', ' corp', ' llc', ' ltd', ' limited', ' corporation']
        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
        return name.strip()
    
    name1 = clean_name(name1)
    name2 = clean_name(name2)
    
    if name1 == name2:
        return 1.0
        
    words1 = set(name1.split())
    words2 = set(name2.split())
    overlap = len(words1.intersection(words2))
    total = len(words1.union(words2))
    
    return overlap / total if total > 0 else 0.0


async def get_company_info(company_url: str = None, company_name: str = None) -> dict:
    """
    Fetch company information from webpage collection based on LinkedIn URL or company name.
    """
    try:
        webpage_data = None
        
        if company_url:
            clean_url = company_url.split('?')[0]
            # API Route: webpages.getByUrl, Input: {"url": clean_url}, Output: {"data": {...}}
            response = api_client.get("webpages/by-url", params={"url": clean_url})
            if isinstance(response, dict) and response.get("success") is False:
                logger.error("Company lookup failed for url %s: %s", clean_url, response.get("message"))
            else:
                if isinstance(response, dict) and "data" in response:
                    webpage_data = response["data"]
                else:
                    webpage_data = response

        if not webpage_data and company_name:
            payload = {"name": company_name}
            # API Route: webpages.searchByName, Input: payload, Output: {"webpages": [...]}
            response = api_client.request("POST", "webpages/search", payload)
            if isinstance(response, dict) and response.get("success") is False:
                logger.error("Company search failed for %s: %s", company_name, response.get("message"))
                candidates = []
            else:
                candidates = response.get("webpages", [])
            best_match = None
            highest_similarity = 0

            for company in candidates:
                if "name" not in company:
                    continue
                similarity = company_name_similarity(company_name, company.get("name", ""))
                if similarity > highest_similarity and similarity >= 0.9:  # 90% threshold
                    highest_similarity = similarity
                    best_match = company

            webpage_data = best_match
        
        if webpage_data:
            return {
                "name": webpage_data.get("name", ""),
                "headline": webpage_data.get("headline", ""),
                "about": webpage_data.get("about", ""),
                "website": webpage_data.get("website", ""),
                "location": webpage_data.get("location", ""),
                "followers": webpage_data.get("followers", ""),
                "industry": webpage_data.get("industry", ""),
                "company_size": webpage_data.get("company_size", ""),
                "headquarters": webpage_data.get("headquarters", ""),
                "type": webpage_data.get("type", ""),
                "founded": webpage_data.get("founded", ""),
                "specialties": webpage_data.get("specialties", "")
            }
        return None
    except Exception as e:
        logger.error(f"Error fetching company info: {str(e)}")
        return None


# ---------------------------------------
# Shared Parsers
# ---------------------------------------
def parse_python_list(output_str: str) -> List[str]:
    """
    Safely parse a Python list from a string. Returns empty list on error.
    """
    try:
        return ast.literal_eval(output_str)
    except (SyntaxError, ValueError):
        logger.error(f"Unable to parse output as Python list: {output_str}")
        return []


def extract_unique_location_entities(location: Any) -> List[str]:
    """
    Extract unique location entities from the location string or dictionary.
    Returns a list of unique location names.
    """
    unique_entities = []
    if isinstance(location, dict):
        for key in ['city', 'state', 'country']:
            if location.get(key):
                unique_entities.append(location[key].strip())
    elif isinstance(location, str):
        parts = [part.strip() for part in location.split(',')]
        unique_entities.extend(part for part in parts if part)
    
    seen = set()
    return [x for x in unique_entities if not (x in seen or seen.add(x))]


# ---------------------------------------
# CANHELP Generation & Parsing
# ---------------------------------------
def parse_canhelp_xml(xml_content: str) -> List[str]:
    """
    Parse the canHelp XML output and extract keywords from both core_expertise and unique_titles
    using BeautifulSoup. Returns a combined list of keyword strings.
    """
    try:
        output_match = re.search(r'<output>(.*?)</output>', xml_content, re.DOTALL)
        if not output_match:
            logger.error("No <output> tag found in XML content")
            return []
            
        xml_portion = f"<output>{output_match.group(1)}</output>"
        soup = BeautifulSoup(xml_portion, "xml")
        
        keyword_tags = soup.find_all("keyword")
        title_tags = soup.find_all("title")
        
        if not keyword_tags and not title_tags:
            logger.error("No <keyword> or <title> tags found in the XML content")
            return []

        keywords = []
        for tag in keyword_tags:
            kw = tag.get_text(strip=True)
            if kw:
                keywords.append(kw)
                
        for tag in title_tags:
            title = tag.get_text(strip=True)
            if title:
                keywords.append(title)
        return keywords
    except Exception as e:
        logger.error(f"Error parsing canHelp XML: {str(e)}")
        return []


async def get_chat_completion_canhelp(profile_data: Dict[str, Any]) -> str:
    """
    Generate a list of canHelp skills using LiteLLM (step 1).
    """
    llm = LLMManager()
    xml_data = json_to_xml(profile_data)
    if not xml_data:
        logger.error("Failed to convert profile data to XML")
        return ""

    user_prompt = CANHELP_USER_PROMPT.replace("{{input}}", xml_data)
    messages = [
        {"role": "user", "content": user_prompt}
    ]

    response = await llm.get_completion(
        provider=DEFAULT_LLM_PROVIDER,
        messages=messages,
        fallback=True,
        stop=canhelp_stop_sequences
    )
    response_content = response.choices[0].message.content + canhelp_stop_sequences[0]
    return response_content


def parse_description_xml(xml_content: str) -> Dict[str, str]:
    """
    Parse the description XML output and extract keyword descriptions.
    Returns a dictionary with keyword names as keys and descriptions as values.
    """
    try:
        output_match = re.search(r'<output>(.*?)</output>', xml_content, re.DOTALL)
        if not output_match:
            logger.error("No <output> tag found in XML content")
            return {}
            
        xml_portion = f"<output>{output_match.group(1)}</output>"
        soup = BeautifulSoup(xml_portion, "xml")
        keyword_tags = soup.find_all("keyword")
        if not keyword_tags:
            logger.error("No <keyword> tags found in the XML content")
            return {}

        descriptions = {}
        for tag in keyword_tags:
            name_tag = tag.find("name")
            desc_tag = tag.find("description")
            if name_tag and desc_tag:
                name = name_tag.get_text(strip=True)
                desc = desc_tag.get_text(strip=True)
                if name and desc:
                    desc = desc.replace('\n', ' ').replace('\r', ' ')
                    desc = ' '.join(desc.split())
                    descriptions[name] = desc
        return descriptions
    except Exception as e:
        logger.error(f"Error parsing description XML: {str(e)}")
        return {}


async def get_chat_completion_description(keywords: List[str]) -> Dict[str, str]:
    """
    Generate detailed descriptions for a batch of keywords using LiteLLM (step 2 for canHelp).
    Returns { keyword -> description }
    """
    llm = LLMManager()
    
    keywords_xml = "\n".join([f"<keyword>{keyword}</keyword>" for keyword in keywords])
    user_prompt = USER_MESSAGE.replace("{{INSERT_KEYWORDS}}", keywords_xml)

    messages = [
        {"role": "user", "content": user_prompt}
    ]

    response = await llm.get_completion(
        provider=DEFAULT_LLM_PROVIDER,
        messages=messages,
        fallback=True,
        stop=description_stop_sequences
    )
    
    response_content = response.choices[0].message.content + description_stop_sequences[0]
    return parse_description_xml(response_content)


async def process_canhelp_skills_with_descriptions(skills: List[str]) -> Dict[str, str]:
    """
    Processes canHelp skills and generates descriptions,
    reusing any previously-cached descriptions from Redis to ensure consistency.
    
    Returns { skill -> description }.

    IMPORTANT: We are now removing the part that *stores* new skill descriptions
               in Redis. We'll still check if there's a cached version, but
               we won't write any new data if there's a cache miss.
    """
    logger.info(f"Processing {len(skills)} skills for descriptions")
    all_descriptions = {}
    uncached_skills = []

    # 1) Prepare Redis keys for bulk checking
    norm_skills = [normalize_text(skill) for skill in skills]
    redis_keys = [f"skill:{norm}" for norm in norm_skills]
    # 2) Bulk check Redis cache (READ ONLY)
    cached_values = r.mget(*redis_keys)
    # 3) Process results and identify uncached skills
    for skill, cached_value in zip(skills, cached_values):
        if cached_value:
            logger.info(f"Cache HIT for skill: {skill}")
            # We expect a JSON object with at least a 'description' field
            try:
                # Remove decode() since Redis is configured with decode_responses=True
                cached_data = json.loads(cached_value)
                if isinstance(cached_data, dict) and "description" in cached_data:
                    # Only take the description from cache, embeddings will be regenerated
                    all_descriptions[skill] = cached_data["description"]
                else:
                    logger.warning(f"Inconsistent cache data for skill: {skill}, ignoring.")
                    uncached_skills.append(skill)
            except Exception as e:
                logger.error(f"Failed to parse cached skill for {skill}: {e}")
                uncached_skills.append(skill)
        else:
            logger.info(f"Cache MISS for skill: {skill}")
            uncached_skills.append(skill)

    # 4) Generate descriptions for uncached skills in small batches
    batch_size = 2
    if uncached_skills:
        logger.info(f"Generating descriptions for {len(uncached_skills)} uncached skills in batches of {batch_size}")
    
    for i in range(0, len(uncached_skills), batch_size):
        batch = uncached_skills[i:i + batch_size]
        logger.info(f"Processing batch {i//batch_size + 1} with skills: {', '.join(batch)}")
        try:
            batch_descriptions = await get_chat_completion_description(batch)
            # In the older code, we would store each skill in Redis. Now, we skip that part.
            # We'll just add them to the local dictionary:
            for original_skill in batch:
                if original_skill in batch_descriptions:
                    all_descriptions[original_skill] = batch_descriptions[original_skill]
                else:
                    # fallback: if the LLM's returned name is normalized or changed
                    norm_batch_skill = normalize_text(original_skill)
                    for llm_skill_key, llm_skill_desc in batch_descriptions.items():
                        if normalize_text(llm_skill_key) == norm_batch_skill:
                            all_descriptions[original_skill] = llm_skill_desc
                            break
            
            # Sleep a bit if not at the end, to avoid rate limiting
            if i + batch_size < len(uncached_skills):
                await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Error processing batch {i//batch_size}: {str(e)}")
            continue

    return all_descriptions


# ---------------------------------------
# WED Summaries
# ---------------------------------------
async def get_chat_completion_wed(combined_for_WED: Dict[str, Any]) -> str:
    """
    Generate a ~240-word single-paragraph summary of the person's work & education.
    Appends lists of unique educational and work organizations afterwards.
    """
    llm = LLMManager()
    try:
        if not isinstance(combined_for_WED, dict):
            logger.error("Input must be a dictionary")
            return ""

        required_fields = ["name", "workExperience", "education"]
        # Check only for presence, not emptiness, as empty lists are valid
        missing_fields = [field for field in required_fields if field not in combined_for_WED]
        if missing_fields:
            logger.error(f"Missing required fields: {missing_fields}")
            # Allow proceeding even if some are missing, summary might be less useful
            # return "" # Previous behavior

        xml_data = json_to_xml(combined_for_WED)
        if not xml_data:
            logger.error("Failed to convert JSON to XML")
            return ""

        user_prompt = WED_USER_PROMPT.replace("{{profile}}", xml_data)
        messages = [
            {"role": "user", "content": user_prompt},
        ]

        response = await llm.get_completion(
            provider=DEFAULT_LLM_PROVIDER,
            messages=messages,
            fallback=True,
            stop=wed_stop_sequences
        )
        
        response_content = response.choices[0].message.content + wed_stop_sequences[0]
        output_match = re.search(r'<output>(.*?)</output>', response_content, re.DOTALL)
        if output_match:
            summary = output_match.group(1).strip()

            # Extract unique education org names
            education_orgs = set()
            for edu in combined_for_WED.get("education", []):
                if edu.get("school"):
                    education_orgs.add(edu["school"].strip())

            # Extract unique work org names
            work_orgs = set()
            for work in combined_for_WED.get("workExperience", []):
                 if work.get("companyName"):
                    work_orgs.add(work["companyName"].strip())

            # Format the lists into markdown strings
            education_str = ""
            if education_orgs:
                # Sort for consistent output
                sorted_edu_orgs = sorted(list(education_orgs))
                education_str = "\n\n**Education Institutions:**\n" + "\n".join([f"- {org}" for org in sorted_edu_orgs])

            work_str = ""
            if work_orgs:
                 # Sort for consistent output
                sorted_work_orgs = sorted(list(work_orgs))
                work_str = "\n\n**Work Organizations:**\n" + "\n".join([f"- {org}" for org in sorted_work_orgs])

            # Combine summary and formatted lists
            final_output = summary + education_str + work_str
            return final_output
        else:
            logger.warning("No <output> tag found in WED response. Cannot append organization lists.")
            return "" # Return empty if no summary was generated initially

    except Exception as e:
        logger.error(f"Error in get_chat_completion_wed: {str(e)}")
        # Adding traceback for better debugging
        import traceback
        logger.error(traceback.format_exc())
        return ""


# ---------------------------------------
# Organizations
# ---------------------------------------
def parse_orgstring_xml(xml_content: str) -> List[Dict[str, Any]]:
    """
    Parse the orgstring XML output and extract organization names and synonyms.
    Returns a list of dictionaries with organization names and synonyms.
    """
    output_match = re.search(r'<output>(.*?)</output>', xml_content, re.DOTALL)
    if not output_match:
        logger.error("No <output> tag found in XML content")
        return []
        
    xml_portion = f"<output>{output_match.group(1)}</output>"
    soup = BeautifulSoup(xml_portion, "xml")
    
    organization_tags = soup.find_all("organization")
    if not organization_tags:
        logger.error("No <organization> tags found in the XML content")
        return []

    organizations = []
    for org_tag in organization_tags:
        org_name_tag = org_tag.find("orgName")
        org_name = org_name_tag.get_text(strip=True) if org_name_tag else ""
        synonyms = []
        synonym_tags = org_tag.find_all("synonym")
        for syn in synonym_tags:
            syn_text = syn.get_text(strip=True)
            if syn_text:
                synonyms.append(syn_text)
        if org_name:
            organizations.append({
                "orgName": org_name,
                "orgSynonyms": synonyms
            })
    return organizations


async def get_chat_completion_orgString(entities: List[str]) -> str:
    """
    Generate organization names and synonyms using XML-style input.
    """
    llm = LLMManager()
    entities_xml = "\n".join([f"<entity>{entity}</entity>" for entity in entities])
    user_prompt = ORGSTRING_USER_PROMPT.format(entities=entities_xml)

    messages = [
        {"role": "system", "content": ORGSTRING_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt}
    ]

    response = await llm.get_completion(
        provider=DEFAULT_LLM_PROVIDER,
        messages=messages,
        fallback=True,
        stop=orgstring_stop_sequences
    )
    response_content = response.choices[0].message.content + orgstring_stop_sequences[0]
    return response_content


def extract_entities(profile_info: Dict[str, Any]) -> List[str]:
    """
    Gather organization or school names from the profile.
    """
    entities = []
    education = profile_info.get("education", [])
    for edu in education:
        school = edu.get("school")
        if school:
            entities.append(school)

    work_experience = profile_info.get("workExperience", [])
    for work in work_experience:
        company = work.get("companyName")
        if company:
            entities.append(company)
    return entities


# ---------------------------------------
# MAIN Entry
# ---------------------------------------
async def generate_descriptions_litellm(profile_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main entry function that generates the following in parallel:
      - locationDescription
      - canHelp (two-step: first retrieve keywords, then get descriptions)
      - workAndEducationDescription
      - organizations (orgString)
    
    Returns updated profile_info with these fields:
      "locationDescription",
      "canHelpSkills",
      "workAndEducationDescription",
      "organizations"
    """
    profile_copy = profile_info.copy()
    tasks = []

    # ---- Location Description Task ----
    # unique_locations = extract_unique_location_entities(profile_copy.get('currentLocation'))
    # if unique_locations:
    #     location_task = asyncio.create_task(process_location_descriptions(unique_locations))
    #     tasks.append(location_task)
    # else:
    #     location_task = None

    # ---- CanHelp Skills Task ----
    canhelp_task = asyncio.create_task(get_chat_completion_canhelp(profile_copy))
    tasks.append(canhelp_task)

    # ---- Work & Education Description Task ----
    # COMMENTED OUT: We are no longer using workAndEducationDescription
    # combined_for_WED = {
    #     'name': profile_copy.get('name', ''),
    #     'headline': profile_copy.get('bio', ''),
    #     'about': profile_copy.get('about', ''),
    #     'workExperience': profile_copy.get('workExperience', []), 
    #     'education': profile_copy.get('education', [])
    # }
    # wed_task = asyncio.create_task(get_chat_completion_wed(combined_for_WED))
    # tasks.append(wed_task)
    wed_task = None
    
    # ---- Organization Strings Task ----
    org_entities = extract_entities(profile_copy)
    if org_entities:
        org_task = asyncio.create_task(get_chat_completion_orgString(org_entities))
        tasks.append(org_task)
    else:
        org_task = None

    # Execute all tasks concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results safely
    task_index = 0

    # Location Results
    # if location_task:
    #     location_result = results[task_index]
    #     if isinstance(location_result, Exception):
    #         logger.error(f"Location description task failed: {location_result}")
    #         profile_copy['locationDescription'] = []
    #     else:
    #         profile_copy['locationDescription'] = location_result
    #     task_index += 1
    # else:
    #     profile_copy['locationDescription'] = []

    # CanHelp Results
    canhelp_result = results[task_index]
    if isinstance(canhelp_result, Exception):
        logger.error(f"CanHelp task failed: {canhelp_result}")
        profile_copy['canHelpSkills'] = {}
    else:
        keywords = parse_canhelp_xml(canhelp_result)
        skill_descriptions = await process_canhelp_skills_with_descriptions(keywords)
        profile_copy['canHelpSkills'] = skill_descriptions
    task_index += 1

    # WED Results
    # COMMENTED OUT: We are no longer using workAndEducationDescription
    # if wed_task:
    #     wed_result = results[task_index]
    #     if isinstance(wed_result, Exception):
    #         logger.error(f"Work/Education description task failed: {wed_result}")
    #         profile_copy['workAndEducationDescription'] = ""
    #     else:
    #         profile_copy['workAndEducationDescription'] = wed_result
    #     task_index += 1

    # Organization Results
    if org_task:
        org_result = results[task_index]
        if isinstance(org_result, Exception):
            logger.error(f"Organization string task failed: {org_result}")
            profile_copy['organizations'] = []
        else:
            profile_copy['organizations'] = parse_orgstring_xml(org_result)
    else:
        profile_copy['organizations'] = []

    return profile_copy


# Optional: For direct testing
if __name__ == "__main__":
    async def main():
        with open('pranit.json', 'r') as file:
            sample_profile = json.load(file)
        
        start_time = time.time()
        result = await generate_descriptions_litellm(sample_profile)
        end_time = time.time()
        total_time = end_time - start_time
        
        with open('generated_profile_redis_cache.json', 'w') as file:
            json.dump(result, file, indent=2)
        
        print(f"Result saved to generated_profile_result.json")
        print(f"Total execution time: {total_time:.2f} seconds")

    asyncio.run(main())
