import re
import json
from bs4 import BeautifulSoup
import unicodedata
import subprocess
import os
from dotenv import load_dotenv


#TODO: Uncomment this to run local file
# import logging  # Add this import
# Replace the logger_config import and setup with this:
# def get_logger(name):
#     logger = logging.getLogger(name)
#     logger.setLevel(logging.DEBUG)
    
#     # Create console handler with formatting
#     handler = logging.StreamHandler()
#     formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#     handler.setFormatter(formatter)
    
#     # Add handler to logger
#     logger.addHandler(handler)
#     return logger
# logger = get_logger("bs.scrape")

# Get the logger - Lambda version
from logging_config import setup_logger
logger = setup_logger("bs.scrape")
logger.debug("Logger initialized")

load_dotenv()

 
def clean_string(s):
    """Clean and normalize string."""
    if not s:
        return ""
        
    # Remove newlines and normalize spaces
    s = re.sub(r"\n\s*\n", "\n", s)
    s = re.sub(r" +", " ", s)
    
    # Remove various "see more/less" patterns
    s = re.sub(r"more\\n See less$", "", s)
    s = re.sub(r"\…more\n See less$", "", s)
    s = re.sub(r"See more\n See less$", "", s)
    s = re.sub(r"…\s*$", "", s)  # Remove ellipsis at the end
    s = re.sub(r"\.\.\.\s*$", "", s)  # Remove three dots at the end
    
    # Replace newlines with spaces
    s = s.replace("\n", " ")
    
    # Normalize unicode characters
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    
    # Remove extra spaces and trim
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def clean_html(raw_html):
    """Remove HTML tags from string."""
    cleanr = re.compile("<.*?>")
    return re.sub(cleanr, "", raw_html).strip()


def extract_contact_info(contacts_text):
    """Extract contact information from text."""
    patterns = {
        "email": r"Email\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
        "linkedin": r"LinkedIn\s+(https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9-]+)",
        "twitter": r"Twitter\s+(https?://(?:www\.)?twitter\.com/[a-zA-Z0-9_]+)",
        "website": r"Website\s+(https?://(?:www\.)?[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})",
    }
    contact_info = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, contacts_text)
        contact_info[key] = match.group(1) if match else None
    return contact_info


def extract_skills(skills_section):
    """Extract skills from section."""
    skills = []
    if skills_section:
        skills_list = re.findall(
            r'<ol class="skills-list.*?">(.*?)</ol>', skills_section.group(1), re.DOTALL
        )
        if skills_list:
            skills_items = re.findall(
                r'<li class="skill-item.*?">(.*?)</li>', skills_list[0], re.DOTALL
            )
            for skill_item in skills_items:
                skills.append(clean_html(skill_item))
    return skills


def fetch_current_location(html):
    """Fetch the current location from the profile section."""
    soup = BeautifulSoup(html, "html.parser")
    basic_profile_section = soup.find("section", class_="basic-profile-section")
    div_tags = basic_profile_section.find_all("div", recursive=False) if basic_profile_section else []
    
    if len(div_tags) >= 3:
        target_div = div_tags[2]
        inner_divs = target_div.find_all("div", recursive=False)
        
        if len(inner_divs) >= 4:
            location_div = inner_divs[3]
        else:
            location_div = inner_divs[-1]
            
        # Find the text before the dot-separator
        dot_separator = location_div.find("span", class_="dot-separator")
        if dot_separator:
            # Get all text nodes before the dot-separator
            location_text = ""
            for content in location_div.contents:
                if content == dot_separator:
                    break
                if isinstance(content, str):
                    location_text += content
                elif content.name != "span":  # Skip span elements (like the followers count)
                    location_text += content.get_text()
        else:
            location_text = clean_string(location_div.get_text())
            
        return clean_string(location_text)
    return None

def fetch_bio_section(html):
    """Fetch the bio from the profile section."""
    soup = BeautifulSoup(html, "html.parser")
    basic_profile_section = soup.find("section", class_="basic-profile-section")
    div_tags = basic_profile_section.find_all("div", recursive=False) if basic_profile_section else []
    about_text = ""
    if len(div_tags) >= 3:
        target_div = div_tags[2]
        inner_divs = target_div.find_all("div", recursive=False)
        
        if len(inner_divs) >= 4:
                # Extract text from the HTML element
            raw_text = inner_divs[1].get_text()
    
            # Clean the extracted text
            about_text = clean_string(raw_text)
        else:
            about_text = ""
    return about_text


def find_about_section(soup):
    """Find the about section based on class containing 'about-section'."""
    about_section = soup.find('section', class_=lambda x: x and 'about-section' in x.lower())
    if about_section:
        return about_section
    return None

def clean_about_text(text):
    """Remove 'about' from the start of the text if present."""
    return re.sub(r'^about\s*', '', text, flags=re.IGNORECASE).strip()

def extract_education(education_section):
    """Extract education information from sections."""
    educations = []
    education_ol = education_section.find('ol') if education_section else None
    education_items = education_ol.find_all('li', recursive=False) if education_ol else []

    for li in education_items:
        # Try multiple ways to find the content container
        content_container = None
        
        # First try the editable class approach (previous case)
        content_container = li.find('a', class_=lambda x: x and 'editable' in x) if li else None
        if not content_container:
            content_container = li.find('div', class_=lambda x: x and 'editable' in x) if li else None
            
        # If not found, try with any anchor tag with flex grow class (new case)
        if not content_container:
            content_container = li.find('a', class_=lambda x: x and 'flex' in x and 'grow' in x) if li else None
            
        # Last resort, just get the first anchor or div
        if not content_container:
            content_container = li.find('a') if li else None
        if not content_container:
            content_container = li.find('div', recursive=False) if li else None
            
        if not content_container:
            continue
            
        # Get school URL if it's an anchor tag
        school_url = content_container.get('href', '') if content_container.name == 'a' else ''
        
        # Extract school logo
        school_logo = None
        img_tag = content_container.find('img')
        if img_tag and img_tag.get('src'):
            school_logo = img_tag['src']
        
        # Find the main content div - try multiple approaches
        content_div = content_container.find('div', class_=lambda x: x and 'self-center' in x)
        if not content_div:
            # Fallback to any div that might contain the education details
            content_div = content_container.find('div', recursive=False)
            
        if not content_div:
            continue
        
        # Extract school name, degree, and field of study
        school = ""
        degree = ""
        field_of_study = ""
        dates = ""
        description = ""
        
        # Process each div in the content section
        divs = content_div.find_all('div', recursive=False)
        for i, div in enumerate(divs):
            if i == 0:  # First div is usually school name
                school = clean_string(div.get_text())
            elif i == 1 and 'body-small' in (div.get('class') or []):  # Second div contains degree and field of study
                spans = div.find_all('span')
                if spans:
                    degree = clean_string(spans[0].get_text()) if spans else ""
                    # Look for field of study after dot-separator
                    for j, span in enumerate(spans):
                        if j > 0 and span.get('class') and 'dot-separator' in span.get('class'):
                            if j+1 < len(spans):
                                field_of_study = clean_string(spans[j+1].get_text())
                            break
            elif i == 2:  # Third div usually contains dates
                spans = div.find_all('span')
                dates = clean_string(' '.join([span.get_text() for span in spans]))
        
        # Look for description div (it's usually has a description class)
        description_div = content_div.find('div', class_=lambda x: x and 'description' in x)
        if description_div:
            description = clean_string(description_div.get_text())
   
        educations.append({
            "school": school,
            "schoolUrl": school_url,
            "schoolLogo": school_logo,
            "degree": degree,
            "field_of_study": field_of_study,
            "dates": dates,
            "description": description
        })
    return educations


def clean_company_url(url):
    """Remove everything after ? from the company URL."""
    return url.split('?')[0]

def extract_experience(experience_sections):
    """Extract experience information from sections."""
    experience_details_list = []
    for exp_section in experience_sections:
        soup = BeautifulSoup(exp_section, "html.parser")
        experience_items = soup.find_all("ol")
        for ol in experience_items:
            parent_lis = ol.find_all("li", recursive=False)
            for li in parent_lis:
                experience_details_list.extend(extract_experience_from_li(li))
    return experience_details_list

def extract_experience_from_li(li):
    experience_items = []
    ul_tags = li.find_all("ul", recursive=True)
    
    for ul_tag in ul_tags:
        li_tags = ul_tag.find_all("li", recursive=False)
        if len(li_tags) == 1:
            experience_item = extract_experience_from_ul_tag(ul_tag)
            if experience_item:
                experience_items.append(experience_item)
        else:
            a_tag = li.find('a', recursive=False)
            company_url = clean_company_url(a_tag.get('href', '')) if a_tag else ''
            
            # Extract company logo
            company_logo = None
            if a_tag:
                img_tag = a_tag.find('img')
                if img_tag and img_tag.get('src'):
                    company_logo = img_tag['src']
            
            # Extract company name
            company_name = ""
            if a_tag:
                current_tag = a_tag
                while current_tag:
                    current_tag = current_tag.find('span')
                    if current_tag and current_tag.get_text(strip=True):
                        company_name = clean_string(current_tag.get_text())
                        break
            else:
                # If a_tag is not present, find the first div and extract text from span
                first_div = li.find('div', recursive=False)
                if first_div:
                    span_tag = first_div.find('span')
                    if span_tag:
                        company_name = clean_string(span_tag.get_text())
            
            for li_tag in li_tags:
                experience_item = extract_experience_from_multiple_li_tags(li_tag, company_url, company_name, company_logo)
                if experience_item:
                    experience_items.append(experience_item)
        
    return experience_items

def extract_experience_from_multiple_li_tags(li_tag, company_url, company_name, company_logo):
    div_inside_ul = li_tag.find_all('div', recursive=False)[1] if len(li_tag.find_all('div', recursive=False)) > 1 else li_tag.find_all(recursive=False)[-1] if len(li_tag.find_all(recursive=False)) > 0 else None
    if not div_inside_ul:
        return None

    all_divs = div_inside_ul.find_all('div', recursive=False)
    
    # Extract title
    title_elem = div_inside_ul.find('div', class_='body-medium-bold') or div_inside_ul.find('div', class_='list-item-heading') or all_divs[0] if all_divs else None
    title = clean_string(title_elem.get_text()) if title_elem else ""

    # Extract duration
    duration_elem = all_divs[1] if len(all_divs) >= 2 else None
    duration = clean_string(' '.join([span.get_text() for span in duration_elem.find_all('span')[:-1]])) if duration_elem else ""

    # Initialize location and description
    location = ""
    description = ""

    # Handle the last two elements (potential location and description)
    remaining_divs = all_divs[2:]
    if len(remaining_divs) == 1:
        div = remaining_divs[0]
        content = clean_string(div.get_text())
        if div.find(class_=lambda x: x and 'description' in x.lower()):
            description = content
        else:
            location = content
    elif len(remaining_divs) >= 2:
        potential_location = clean_string(remaining_divs[0].get_text())
        potential_description = clean_string(remaining_divs[1].get_text())
        
        if len(potential_location.split()) <= 6:  # Changed from 5 to 6
            location = potential_location
            description = potential_description
        else:
            description = potential_location
            # Check if the last div might be a location
            if len(potential_description.split()) <= 6:  # Changed from 5 to 6
                location = potential_description

    return {
        "companyUrl": company_url,
        "companyLogo": company_logo,
        "title": title,
        "companyName": company_name,
        "duration": duration,
        "location": location,
        "description": description
    }

def extract_experience_from_ul_tag(ul_tag):
    li_tag = ul_tag.find('li', recursive=False)
    if not li_tag:
        return None
        
    # First try to find an a tag directly under li
    a_tag = li_tag.find('a', recursive=False)
    
    # If no a tag found, look for first div under li
    if a_tag:
        company_url = clean_company_url(a_tag.get('href', ''))
        div_inside_ul = ul_tag.find('div')
    else:
        company_url = ''
        div_inside_ul = li_tag.find('div', recursive=False)

    if not div_inside_ul:
        return None

    all_divs = div_inside_ul.find_all('div', recursive=False)
    title_elem = div_inside_ul.find('div', class_='body-medium-bold') or div_inside_ul.find('div', class_='list-item-heading') or all_divs[0] if all_divs else None
    title = clean_string(title_elem.get_text()) if title_elem else ""

    # First try the original logic
    company_name_elem = all_divs[1] if len(all_divs) > 1 and company_url else all_divs[2] if len(all_divs) > 2 else None
    company_name = clean_string(company_name_elem.get_text()) if company_name_elem else ""

    # If company name is empty, try finding it in the body-small div
    if not company_name:
        body_small_div = div_inside_ul.find('div', class_='body-small')
        if body_small_div:
            company_span = body_small_div.find('span', attrs={'dir': 'ltr'})
            company_name = clean_string(company_span.get_text()) if company_span else ""

    # Extract company logo
    company_logo = None
    if a_tag:
        img_tag = a_tag.find('img')
        if img_tag and img_tag.get('src'):
            company_logo = img_tag['src']
    
        # Find duration by looking for div with exactly 4 spans where third is dot-separator
    duration = ""
    for div in div_inside_ul.find_all('div', class_='body-small'):
        spans = div.find_all('span')
        if (len(spans) == 4 and 
            spans[2].get('class') == ['dot-separator'] and 
            spans[2].get('aria-hidden') == 'true'):
            # Get only first two spans which contain the date range
            duration = clean_string(' '.join(span.get_text() for span in spans[:2]))
            break

    # Initialize location and description
    location = ""
    description = ""

    # Try original logic for location and description
    remaining_divs = all_divs[3:]
    if len(remaining_divs) == 1:
        div = remaining_divs[0]
        content = clean_string(div.get_text())
        if div.find(class_=lambda x: x and 'description' in x.lower()):
            description = content
        else:
            location = content
    elif len(remaining_divs) >= 2:
        potential_location = clean_string(remaining_divs[0].get_text())
        potential_description = clean_string(remaining_divs[1].get_text())
        
        if len(potential_location.split()) <= 6:
            location = potential_location
            description = potential_description
        else:
            description = potential_location
            if len(potential_description.split()) <= 6:
                location = potential_description

    # If description is empty, try finding it in the description div
    if not description:
        description_div = div_inside_ul.find('div', class_='description')
        description = clean_string(description_div.get_text()) if description_div else ""

    return {
        "companyUrl": company_url,
        "companyLogo": company_logo,
        "title": title,
        "companyName": company_name,
        "duration": duration,
        "location": location,
        "description": description
    }
    
def extract_recommendations(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    recommendations = []

    recommendation_list = soup.find('ul', class_='recommendation-list')
    if recommendation_list:
        for item in recommendation_list.find_all('li'):
            recommendation_text = item.find('div', class_='recommendation-text')
            recommendation = clean_string(recommendation_text.get_text()) if recommendation_text else ""
            
            recommender_info = item.find('a')
            if recommender_info:
                recommender_name = clean_string(recommender_info.find('dt').get_text()) if recommender_info.find('dt') else ""
                recommender_url = recommender_info.get('href', '').split('?')[0] if recommender_info.get('href') else ''
            else:
                recommender_name = ""
                recommender_url = ""
            
            recommendations.append({
                "recommendationGivenBy": recommender_name,
                "recommendationGivenByUrl": recommender_url,
                "recommendation": recommendation
            })
    
    return recommendations

def extract_accomplishments(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    accomplishments = {}

    accomplishment_section = soup.find('div', id='accomplishment-section')
    if accomplishment_section:
        for accomplishment_type in accomplishment_section.find_all('div', class_='accomplishment-type'):
            type_name = clean_string(accomplishment_type.find('h3').get_text()) if accomplishment_type.find('h3') else ""
            
            if type_name == "Test Scores":
                continue  # Skip Test Scores
            
            if type_name == "Languages":
                languages = []
                language_list = accomplishment_type.find('ul')
                if language_list:
                    for item in language_list.find_all('li', class_='sub-list-item'):
                        language = clean_string(item.find('div', class_='list-item-heading').get_text()) if item.find('div', class_='list-item-heading') else ""
                        languages.append(language)
                accomplishments[type_name] = ", ".join(languages)
            
            elif type_name in ["Courses", "Projects", "Certifications", "Publications", "Honors"]:
                accomplishments[type_name] = []
                accomplishment_list = accomplishment_type.find('ul')
                if accomplishment_list:
                    for item in accomplishment_list.find_all('li', class_='sub-list-item'):
                        name = clean_string(item.find('div', class_='list-item-heading').get_text()) if item.find('div', class_='list-item-heading') else ""
                        details_div = item.find_all('div', class_='body-small')
                        
                        if type_name == "Courses":
                            course_number = clean_string(details_div[0].get_text()) if len(details_div) > 0 else ""
                            associated_with = clean_string(details_div[-1].get_text()) if len(details_div) > 1 else ""
                            accomplishments[type_name].append({
                                "courseName": name,
                                "courseNumber": course_number,
                                "associatedWith": associated_with
                            })
                            
                        elif type_name == "Honors":
                            details_div = item.find('div', class_='body-small')
                            if details_div:
                                # Find the organization (first span without class 'date' or 'dot-separator')
                                org_span = details_div.find('span', {'dir': 'ltr'})
                                org = clean_string(org_span.get_text()) if org_span else ""
                                
                                # Find the date (span with class 'date')
                                date_span = details_div.find('span', class_='date')
                                date = clean_string(date_span.get_text()) if date_span else ""
                            else:
                                org = ""
                                date = ""
                                
                            accomplishments[type_name].append({
                                "accomplishment": name,
                                "accomplishmentFrom": org,
                                "accomplishmentDate": date
                            })
                        elif type_name == "Projects":
                            date = clean_string(details_div[-1].get_text()) if len(details_div) > 0 else ""
                            description = clean_string(details_div[0].get_text()) if len(details_div) > 1 else ""
                            accomplishments[type_name].append({
                                "projectName": name,
                                "date": date,
                                "projectDescription": description
                            })
                        elif type_name == "Certifications":
                            certificate_from = clean_string(details_div[0].get_text()) if len(details_div) > 0 else ""
                            date = clean_string(details_div[-1].get_text()) if len(details_div) > 1 else ""
                            accomplishments[type_name].append({
                                "certificateName": name,
                                "certificateFrom": certificate_from,
                                "date": date
                            })
                        elif type_name == "Publications":
                            publication_spans = details_div[0].find_all('span') if len(details_div) > 0 else []
                            publication = clean_string(publication_spans[0].get_text()) if len(publication_spans) > 0 else ""
                            date = clean_string(publication_spans[2].get_text()) if len(publication_spans) > 2 else ""
                            accomplishments[type_name].append({
                                "topic": name,
                                "publication": publication,
                                "date": date
                            })
            
            else:
                accomplishments[type_name] = []
                accomplishment_list = accomplishment_type.find('ul')
                if accomplishment_list:
                    for item in accomplishment_list.find_all('li', class_='sub-list-item'):
                        name = clean_string(item.find('div', class_='list-item-heading').get_text()) if item.find('div', class_='list-item-heading') else ""
                        
                        details_div = item.find('div', class_='body-small')
                        if details_div:
                            spans = details_div.find_all('span')
                            text_content = ' '.join(span.get_text().strip() for span in spans if not span.get('class', [''])[0] == 'dot-separator')
                            text_content = clean_string(text_content)
                        else:
                            text_content = ""

                        if type_name == "Organizations":
                            accomplishments[type_name].append({
                                "name": name,
                                "date": text_content
                            })
                        else:
                            accomplishments[type_name].append({
                                "accomplishment": name,
                                "accomplishmentFrom": text_content,
                                "accomplishmentDate": ""
                            })
    
    return accomplishments
def find_section_by_heading(soup, heading_text):
    """Find a section by its heading text."""
    for section in soup.find_all('section'):
        h2 = section.find(['h2', 'h3'])
        if h2 and re.search(rf'\b{re.escape(heading_text)}\b', h2.get_text(strip=True), re.IGNORECASE):
            return section
    return None

def fetch_avatar_url(html):
    """Fetch the avatar URL from the profile section and save to Cloudflare."""
    logger.info("Fetching avatar URL from profile section")
    soup = BeautifulSoup(html, "html.parser")
    basic_profile_section = soup.find("section", class_="basic-profile-section")
    
    if basic_profile_section:
        logger.debug("Found basic profile section")
        # Try finding the profile picture container first
        profile_pic_container = basic_profile_section.find('figure', id='profile-picture-container')
        if profile_pic_container:
            logger.debug("Found profile picture container")
            img = profile_pic_container.find('img')
            if img and img.get('src'):
                logger.info("Found profile image in container")
                return img['src']
        
        # Fallback: Look for any profile image in the basic profile section
        logger.debug("Trying fallback profile image search")
        profile_img = basic_profile_section.find('img', attrs={
            'src': lambda x: x and ('profile-displayphoto' in x or 'profile-photo' in x)
        })
        if profile_img:
            logger.info("Found profile image through fallback")
            return profile_img['src']
    
    logger.warning("No profile image found")
    return None

def scrape_profile_data(html_content):
    try:
        logger.info("Starting profile data scraping")
        soup = BeautifulSoup(html_content, 'html.parser')

        logger.info("Fetching avatar URL")
        avatar_url = fetch_avatar_url(html_content)

        logger.info("Fetching bio section")
        bio = fetch_bio_section(html_content)
                
        logger.info("Processing about section")
        about_section = find_about_section(soup)
        if about_section:
            about_text = clean_string(about_section.get_text())
            about_text = clean_about_text(about_text)
            logger.info("About section found and processed")
        else:
            about_section = find_section_by_heading(soup, "About")
            if about_section:
                about_text = clean_string(about_section.get_text())
                about_text = clean_about_text(about_text)
                logger.info("About section found through heading and processed")
            else:
                about_text = None
                logger.info("No about section found")

        logger.info("Processing experience section")
        experience_sections = re.findall(
            r'<section class=".*?experience-container.*?">(.*?)</section>',
            html_content,
            re.DOTALL,
        )
        experience_details_list = extract_experience(experience_sections)
        if not experience_details_list:
            logger.info("No experience found in container, trying alternate method")
            experience_section = find_section_by_heading(soup, "Experience")
            if experience_section:
                experience_details_list = extract_experience([str(experience_section)])
                logger.info("Experience found through heading")
            else:
                logger.info("No experience section found")

        logger.info("Processing education section")
        education_section = soup.find('section', class_=lambda x: x and 'education-container' in x)
        educations = extract_education(education_section)
        if not educations:
            logger.info("No education found in container, trying alternate method")
            education_section = find_section_by_heading(soup, "Education")
            if education_section:
                educations = extract_education(education_section)
                logger.info("Education found through heading")
            else:
                logger.info("No education section found")

        logger.info("Processing contacts section")
        contacts_section = re.search(
            r'<section class=".*?contacts-container.*?">(.*?)</section>',
            html_content,
            re.DOTALL,
        )
        contacts_text = clean_string(clean_html(contacts_section.group(1))) if contacts_section else ""
        contact_info = extract_contact_info(contacts_text)
        if not contact_info:
            logger.info("No contacts found in container, trying alternate method")
            contact_section = find_section_by_heading(soup, "Contact")
            if contact_section:
                contacts_text = clean_string(clean_html(str(contact_section)))
                contact_info = extract_contact_info(contacts_text)
                logger.info("Contacts found through heading")
            else:
                logger.info("No contacts section found")

        logger.info("Processing skills section")
        skills_section = re.search(
            r'<section class=".*?skills-container.*?">(.*?)</section>',
            html_content,
            re.DOTALL,
        )
        skills = extract_skills(skills_section)
        if not skills:
            logger.info("No skills found in container, trying alternate method")
            skills_section = find_section_by_heading(soup, "Skills")
            if skills_section:
                skills_html = str(skills_section)
                skills = extract_skills(re.search(r'<section.*?>(.*?)</section>', skills_html, re.DOTALL))
                logger.info("Skills found through heading")
            else:
                logger.info("No skills section found")

        logger.info("Fetching current location")
        currentLocation = fetch_current_location(html_content)

        logger.info("Processing recommendations section")
        recommendation_section = find_section_by_heading(soup, "Recommendations")
        recommendations = extract_recommendations(str(recommendation_section)) if recommendation_section else []

        logger.info("Processing accomplishments section")
        accomplishments_section = find_section_by_heading(soup, "Accomplishments")
        accomplishments = extract_accomplishments(str(accomplishments_section)) if accomplishments_section else {}

        logger.info("Profile data scraping completed successfully")
        
        # Combine all into a dictionary
        profile_info = {}
        if avatar_url: profile_info["avatarURL"] = avatar_url
        if bio: profile_info["bio"] = bio
        if about_text: profile_info["about"] = about_text
        if currentLocation: profile_info["currentLocation"] = currentLocation
        if experience_details_list: profile_info["workExperience"] = experience_details_list
        if educations: profile_info["education"] = educations
        if skills: profile_info["skills"] = skills
        if recommendations: profile_info["recommendations"] = recommendations
        if accomplishments: profile_info["accomplishments"] = accomplishments
        if contact_info: profile_info["contacts"] = contact_info
        return profile_info
    except Exception as e:
        logger.error(f"Error occurred while scraping profile data: {str(e)}")
        raise



# Add this at the end of the file
if __name__ == "__main__":
    # Read the HTML file
    with open("azhan_new.html", "r", encoding="utf-8") as file:
        html_content = file.read()
    
    # Scrape the profile data
    profile_data = scrape_profile_data(html_content)
    
    # Save the output as JSON
    with open("profile_data_azhan.json", "w", encoding="utf-8") as json_file:
        json.dump(profile_data, json_file, indent=2, ensure_ascii=False)
    
    print("Profile data has been saved to profile_data.json")
