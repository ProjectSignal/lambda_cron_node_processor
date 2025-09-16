#https://console.anthropic.com/workbench/9050b537-673a-4bd2-9ce3-71a0de05c2a3
CANHELP_USER_PROMPT = """You are an expert system designed to analyze professional profiles and extract core areas of expertise. Your task is to generate 10-12 core expertise keywords and a list of unique titles/positions for the given profile.

Here is the profile you need to analyze:

<profile>
{{input}}
</profile>

Please follow these steps to complete the task:

1. Initial Data Collection:
Analyze the profile and collect relevant information. Use <thought_process> tags to show your thought process for each step. For each category, provide at least two specific examples from the profile.

<thought_process>
a) Extract explicitly mentioned skills from the "about" section
   Example 1: [Quote from profile]
   Example 2: [Quote from profile]

b) List all job titles and roles from work experience
   Example 1: [Job title and company]
   Example 2: [Job title and company]

c) Note educational qualifications and specialized courses
   Example 1: [Degree or course name]
   Example 2: [Degree or course name]

d) Record any certifications and accomplishments
   Example 1: [Certification or accomplishment]
   Example 2: [Certification or accomplishment]

e) Review recommendations for validated skills (if present)
   Example 1: [Quote from recommendation]
   Example 2: [Quote from recommendation]

f) Examine company descriptions for domain context
   Example 1: [Quote from company description]
   Example 2: [Quote from company description]
</thought_process>

2. Analysis Process:
Analyze the collected data to identify core areas of expertise. Use <thought_process> tags for each category. List potential keywords and provide supporting evidence for each.

<thought_process>
a) Current Expertise (Higher Priority):
   Potential Keyword 1: [Keyword]
   Supporting Evidence: [Quote or reference from profile]
   Potential Keyword 2: [Keyword]
   Supporting Evidence: [Quote or reference from profile]

b) Historical Expertise:
   Potential Keyword 1: [Keyword]
   Supporting Evidence: [Quote or reference from profile]
   Potential Keyword 2: [Keyword]
   Supporting Evidence: [Quote or reference from profile]

c) Domain Knowledge:
   Potential Keyword 1: [Keyword]
   Supporting Evidence: [Quote or reference from profile]
   Potential Keyword 2: [Keyword]
   Supporting Evidence: [Quote or reference from profile]

d) Leadership & Management:
   Potential Keyword 1: [Keyword]
   Supporting Evidence: [Quote or reference from profile]
   Potential Keyword 2: [Keyword]
   Supporting Evidence: [Quote or reference from profile]
</thought_process>

3. Validation and Consolidation:
Apply validation rules and consolidate your findings. Use <thought_process> tags to show your process. Explicitly apply each validation rule to the potential keywords.

<thought_process>
Validation Rules Application:
1. Two-section support rule:
   Keyword: [Keyword]
   Section 1 support: [Evidence]
   Section 2 support: [Evidence]

2. Technical skills evidence:
   Keyword: [Keyword]
   Work experience evidence: [Quote or reference]
   OR
   Formal education evidence: [Quote or reference]

3. Domain expertise backing:
   Keyword: [Keyword]
   Relevant industry experience: [Quote or reference]

4. Leadership keywords evidence:
   Keyword: [Keyword]
   Role-based evidence: [Quote or reference]

5. Explicit support check:
   [List any keywords removed due to lack of explicit support]

Consolidation Process:
1. Combined technical skills: [List of combined skills]
2. Grouped domain-specific skills: [List of grouped skills]
3. Merged leadership/management skills: [List of merged skills]
4. Prioritized list based on criteria: [List of prioritized skills]
</thought_process>

4. Generate Keywords:
Based on your analysis, generate 10-12 core expertise keywords. Each keyword should:
- Be 2-4 words maximum
- Capture a distinct area of expertise
- Be specific enough to be meaningful but broad enough to cover related skills
- Be supported by clear evidence from the profile

5. Title/Position Analysis:
Extract and categorize all unique professional titles and positions from the profile. Use <thought_process> tags to show your analysis.

<thought_process>
a) Extract all job titles:
   - List each unique title
   - Note variations of similar titles
   - Identify hierarchy levels (e.g., Senior, Lead, Head of)

b) Categorize positions:
   - Group by function (e.g., Technical, Management, Creative)
   - Identify industry-specific roles
   - Note cross-functional positions

c) Standardize titles:
   - Convert specific titles to standard industry terminology
   - Remove company-specific terminology
   - Ensure titles are searchable
</thought_process>

6. Quality Checks:
Perform the following quality checks on your generated keywords and titles:
- Ensure each keyword and title has clear supporting evidence
- Verify no contradictions exist in the profile
- Check that keywords represent both breadth and depth of expertise
- Confirm keywords align with career progression
- Validate against recommendations if available
- Verify titles are standardized and searchable

7. Final Output:
Present your final list of core expertise keywords and unique titles/positions in the following XML format:

<output>
<core_expertise>
  <keyword>Example Keyword 1</keyword>
  <keyword>Example Keyword 2</keyword>
  ...
  <keyword>Example Keyword 12</keyword>
</core_expertise>

<unique_titles>
  <title>Example Title 1</title>
  <title>Example Title 2</title>
  ...
</unique_titles>
</output>

Remember:
- Keywords should accurately represent the person's expertise, be backed by profile evidence, cover both technical and soft skills where applicable, reflect current capabilities while acknowledging valuable past experience, and be useful for matching with opportunities or needs.
- Titles should be standardized, searchable, and accurately reflect the positions held.
- Only include skills, expertise, and titles that are clearly evidenced in the profile. Do not infer or assume capabilities without supporting information."""
stop_sequences = ["</output>"]