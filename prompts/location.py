#https://console.anthropic.com/workbench/3d0d2f90-559a-4a85-8d47-95ff0b9c732d
LOCATION_USER_PROMPT = """You are a highly knowledgeable AI assistant tasked with generating detailed location descriptions for vector embedding and cosine matching purposes. You will receive a list of locations and must create informative descriptions for each one.

Here is the list of locations you need to describe:
<locations_list>
{{locations}}
</locations_list>


Instructions:
1. For each location in the provided list, generate a detailed description of approximately 100 words.
2. Each description must include:
   - The location name and any alternative names or nicknames
   - Its geographic context (e.g., country, state, nearby features)
   - Notable characteristics (culture, economy, history)
   - Nearby landmarks or points of interest
3. Format requirements:
   - Each description should be a single paragraph (no line breaks)
   - Start each description with "I am from"
   - Focus on unique and identifying features to maximize potential for cosine matching

Process:
1. For each location, wrap your analysis in <location_analysis> tags. In this analysis:
   a. List key identifying features and unique aspects of the location.
   b. Brainstorm specific details for each required element (geographic context, notable characteristics, nearby landmarks).
   c. Draft a brief outline of the description.
2. After your analysis, provide the final description for each location.
3. Once all descriptions are complete, format the output as an XML document.

Output Format:
Your final output should be structured as follows:

<output>
  <location>
    <name>Location Name</name>
    <description>I am from [Location Name], [rest of the description...]</description>
  </location>
  <!-- Repeat for each location -->
</output>

Remember to focus on creating descriptions that will be effective for vector embedding and cosine matching. Begin your response with the <location_analysis> tag for the first location.
"""
stop_sequences=["</output>"]