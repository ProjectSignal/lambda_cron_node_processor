#https://console.anthropic.com/workbench/c1b12986-66d0-4e03-994c-a330918ac214

ORGSTRING_SYSTEM_PROMPT = """You are an AI assistant that extracts well-known abbreviations or alternative names for organizations, companies, schools, and other entities."""

ORGSTRING_USER_PROMPT = """You are a highly knowledgeable AI assistant tasked with generating alternative names and abbreviations for organizations, companies, schools, and other entities. You will receive a list of entities and must identify their common abbreviations and alternative names.

Here is the list of entities you need to process:
<entities>
{entities}
</entities>

Instructions:
1. For each entity, perform a detailed analysis including:
   a. Full entity name
   b. Obvious abbreviations
   c. Industry-specific abbreviations
   d. Alternative names and variations

2. Format requirements:
   - First provide detailed analysis in a structured format
   - Then provide final output in XML format
   - Include both original name and all variations
   - No duplicates allowed
   - Only include English language variations

3. Output Structure:
   The final output should be in XML format with:
   - <organizations> as root element
   - Each entity wrapped in <organization> tags
   - Original name in <orgName> tags
   - Variations in <orgSynonyms> with each synonym in <synonym> tags

Example input:
<entities>
<entity>McMahon Services</entity>
</entities>

Example output:
<output>
<organizations>
    <organization>
        <orgName>McMahon Services</orgName>
        <orgSynonyms>
            <synonym>McMahon Services</synonym>
            <synonym>McMahon</synonym>
            <synonym>Mc Mahon</synonym>
            <synonym>Mcmahon</synonym>
        </orgSynonyms>
    </organization>
</organizations>
</output>

Begin your response with detailed entity analysis followed by the XML output in <output> tags."""

stop_sequences = ["</output>"]