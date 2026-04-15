# Exa API Setup Guide

## Your Configuration

| Setting | Value |
|---------|-------|
| Coding Tool | Other |
| Framework | Other |
| Use Case | Coding agent |
| Search Type | Deep - Multi-query deep search with structured outputs (4-12s) |
| Content | Compact |
**Project Description:** (Not provided)


---

## API Key Setup

### Environment Variable

```bash
export EXA_API_KEY="YOUR_API_KEY"
```

### .env File

```env
EXA_API_KEY=YOUR_API_KEY
```

---

## 🔌 Exa MCP Server

Give your AI coding assistant real-time web search with Exa MCP.

**Remote MCP URL (with your API key):**
```
https://mcp.exa.ai/mcp?exaApiKey=d387a596-d887-40d7-8f67-ace85ae70866
```

**Tool enablement (optional):**
Add a `tools=` query param to the MCP URL.

Enable specific tools:
```
https://mcp.exa.ai/mcp?exaApiKey=d387a596-d887-40d7-8f67-ace85ae70866&tools=web_search_exa,get_code_context_exa,people_search_exa
```

Enable all tools:
```
https://mcp.exa.ai/mcp?exaApiKey=d387a596-d887-40d7-8f67-ace85ae70866&tools=web_search_exa,web_search_advanced_exa,get_code_context_exa,crawling_exa,company_research_exa,people_search_exa,deep_researcher_start,deep_researcher_check
```

**Your API key:** `d387a596-d887-40d7-8f67-ace85ae70866`
Manage keys at [dashboard.exa.ai/api-keys](https://dashboard.exa.ai/api-keys).

**Available tools (enabled by default):**
- `web_search_exa`
- `get_code_context_exa`
- `company_research_exa`

**Optional tools (enable via `tools=`):**
- `web_search_advanced_exa`
- `crawling_exa`
- `people_search_exa`
- `deep_researcher_start`
- `deep_researcher_check`

**Troubleshooting:** if tools don’t appear, restart your MCP client after updating the config.

**JSON config (Cursor, Windsurf, etc.):**
```json
{
  "mcpServers": {
    "exa": {
      "url": "https://mcp.exa.ai/mcp?exaApiKey=d387a596-d887-40d7-8f67-ace85ae70866"
    }
  }
}
```

**Claude Desktop:**
Exa is available as a built-in Claude Connector. Go to **Settings** (or **Customize**) → **Connectors**, search for **Exa**, and click **+** to add it. No config files needed.

📖 Full docs: [docs.exa.ai/reference/exa-mcp](https://docs.exa.ai/reference/exa-mcp)

---

## Quick Start

### cURL

```bash
curl -X POST 'https://api.exa.ai/search' \
  -H 'x-api-key: YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
  "query": "React hooks best practices 2024",
  "type": "deep",
  "num_results": 10,
  "contents": {
    "highlights": {
      "max_characters": 4000
    }
  }
}'
```

---

## Search Type Reference

| Type | Best For | Speed | Depth |
|------|----------|-------|-------|
| `fast` | Real-time apps, autocomplete, quick lookups | Fastest | Basic |
| `auto` | Most queries - balanced relevance & speed | Medium | Smart |
| `deep` | Research, enrichment, thorough results | Slow | Deep | ← your selection
| `deep-reasoning` | Complex research, multi-step reasoning | Slowest | Deepest |

**Tip:** `type="deep"` and `type="deep-reasoning"` support structured outputs via `outputSchema`. Use `deep` for enrichment and research; use `deep-reasoning` for complex multi-step reasoning tasks.

---

## Structured Outputs (Deep Search)

Deep search types (`deep`, `deep-reasoning`) support structured outputs via `outputSchema` (`output_schema` in Python). Define the shape of the data you want back, and Exa returns web-grounded structured JSON with field-level citations.

**Schema controls:** `type`, `description`, `required`, `properties`, `items`

```bash
curl -X POST 'https://api.exa.ai/search' \
  -H 'x-api-key: YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
  "query": "articles about GPUs",
  "type": "deep",
  "outputSchema": {
    "type": "object",
    "description": "Companies mentioned in articles",
    "required": ["companies"],
    "properties": {
      "companies": {
        "type": "array",
        "description": "List of companies mentioned",
        "items": {
          "type": "object",
          "required": ["name"],
          "properties": {
            "name": { "type": "string", "description": "Name of the company" },
            "description": { "type": "string", "description": "Short description of what the company does" }
          }
        }
      }
    }
  },
  "contents": {
    "highlights": { "max_characters": 4000 }
  }
}'
```

### Response Shape

Deep responses include:
- `output.content` — synthesized structured JSON matching your schema
- `output.grounding` — field-level citations with source URLs and confidence

```json
{
  "output": {
    "content": {
      "companies": [
        {"name": "Nvidia", "description": "GPU and AI chip manufacturer"},
        {"name": "AMD", "description": "Semiconductor company producing GPUs and CPUs"}
      ]
    },
    "grounding": [
      {
        "field": "companies[0].name",
        "citations": [{"url": "https://...", "title": "Source"}],
        "confidence": "high"
      }
    ]
  }
}
```

### When to Use Structured Outputs

- **Enrichment workflows** — extract specific fields (company info, people data, product details)
- **Data pipelines** — get structured data directly instead of parsing free text
- **Grounded facts** — every field comes with citations and confidence scores
- Use `deep-reasoning` over `deep` when the query requires multi-step reasoning or synthesis across many sources

<details>
<summary>Python</summary>

```python
from exa_py import Exa

exa = Exa(api_key="YOUR_API_KEY")

results = exa.search(
    "articles about GPUs",
    type="deep",
    output_schema={
        "type": "object",
        "description": "Companies mentioned in articles",
        "required": ["companies"],
        "properties": {
            "companies": {
                "type": "array",
                "description": "List of companies mentioned",
                "items": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the company"
                        },
                        "description": {
                            "type": "string",
                            "description": "Short description of what the company does"
                        }
                    }
                }
            }
        }
    },
    contents={
        "highlights": {
            "max_characters": 4000
        }
    }
)

# Access structured output
print(results.output.content)   # {"companies": [{"name": "Nvidia", "description": "..."}]}
print(results.output.grounding) # Field-level citations and confidence
```
</details>

<details>
<summary>JavaScript</summary>

```javascript
import Exa from "exa-js";

const exa = new Exa("YOUR_API_KEY");

const results = await exa.search("articles about GPUs", {
  type: "deep",
  outputSchema: {
    type: "object",
    description: "Companies mentioned in articles",
    required: ["companies"],
    properties: {
      companies: {
        type: "array",
        description: "List of companies mentioned",
        items: {
          type: "object",
          required: ["name"],
          properties: {
            name: { type: "string", description: "Name of the company" },
            description: { type: "string", description: "Short description of what the company does" }
          }
        }
      }
    }
  },
  contents: {
    highlights: { maxCharacters: 4000 }
  }
});

// Access structured output
console.log(results.output.content);   // {"companies": [{"name": "Nvidia", ...}]}
console.log(results.output.grounding); // Field-level citations and confidence
```
</details>

---

## Content Configuration

Choose ONE content type per request (not both):

| Type | Config | Best For |
|------|--------|----------|
| Text | `"text": {"max_characters": 20000}` | Full content extraction, RAG |
| Highlights | `"highlights": {"max_characters": 4000}` | Snippets, summaries, lower cost | ← your selection

**⚠️ Token usage warning:** Using `text: true` (full page text) can significantly increase token count, leading to slower and more expensive LLM calls. To mitigate:
- Add `max_characters` limit: `"text": {"max_characters": 10000}`
- Use `highlights` instead if you don't need contiguous text

**When to use text vs highlights:**
- **Text** - When you need untruncated, contiguous content (e.g., code snippets, full articles, documentation)
- **Highlights** - When you need key excerpts and don't need the full context (e.g., summaries, Q&A, general research)

---

## Domain Filtering (Optional)

Usually not needed - Exa's neural search finds relevant results without domain restrictions.

**When to use:**
- Targeting specific authoritative sources
- Excluding low-quality domains from results

**Example:**
```json
{
  "includeDomains": ["arxiv.org", "github.com"],
  "excludeDomains": ["pinterest.com"]
}
```

**Note:** `includeDomains` and `excludeDomains` can be used together to include a broad domain while excluding specific subdomains (e.g., `"includeDomains": ["vercel.com"], "excludeDomains": ["community.vercel.com"]`).

---

## Coding Agent

```json
{
  "query": "React hooks best practices 2024",
  "num_results": 10,
  "contents": {
    "text": {
      "max_characters": 20000
    }
  }
}
```

**Tips:**
- Use `type: "auto"` for balanced results
- Great for documentation lookup, API references, code examples

---

## Category Examples

Use category filters to search dedicated indexes. Each category returns only that content type.

**Note:** Categories can be restrictive. If you're not getting enough results, try searching without a category first, then add one if needed.

### People Search (`category: "people"`)
Find people by role, expertise, or what they work on

```bash
curl -X POST 'https://api.exa.ai/search' \
  -H 'x-api-key: YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
  "query": "software engineer distributed systems",
  "category": "people",
  "type": "auto",
  "num_results": 10
}'
```

**Tips:**
  - Use SINGULAR form
  - Describe what they work on
  - No date/text filters supported

### Company Search (`category: "company"`)
Find companies by industry, criteria, or attributes

```bash
curl -X POST 'https://api.exa.ai/search' \
  -H 'x-api-key: YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
  "query": "AI startup healthcare",
  "category": "company",
  "type": "auto",
  "num_results": 10
}'
```

**Tips:**
  - Use SINGULAR form
  - Simple entity queries
  - Returns company objects, not articles

### News Search (`category: "news"`)
News articles

```bash
curl -X POST 'https://api.exa.ai/search' \
  -H 'x-api-key: YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
  "query": "OpenAI announcements",
  "category": "news",
  "type": "auto",
  "num_results": 10,
  "contents": {
    "text": {
      "max_characters": 20000
    }
  }
}'
```

**Tips:**
  - Use livecrawl: "preferred" for breaking news
  - Avoid date filters unless required

### Research Papers (`category: "research paper"`)
Academic papers

```bash
curl -X POST 'https://api.exa.ai/search' \
  -H 'x-api-key: YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
  "query": "transformer architecture improvements",
  "category": "research paper",
  "type": "auto",
  "num_results": 10,
  "contents": {
    "text": {
      "max_characters": 20000
    }
  }
}'
```

**Tips:**
  - Use type: "auto" for most queries
  - Includes arxiv.org, paperswithcode.com, and other academic sources

---

## Content Freshness (maxAgeHours)

`maxAgeHours` sets the maximum acceptable age (in hours) for cached content. If the cached version is older than this threshold, Exa will livecrawl the page to get fresh content.

| Value | Behavior | Best For |
|-------|----------|----------|
| 24 | Use cache if less than 24 hours old, otherwise livecrawl | Daily-fresh content |
| 1 | Use cache if less than 1 hour old, otherwise livecrawl | Near real-time data |
| 0 | Always livecrawl (ignore cache entirely) | Real-time data where cached content is unusable |
| -1 | Never livecrawl (cache only) | Maximum speed, historical/static content |
| *(omit)* | Default behavior (livecrawl as fallback if no cache exists) | **Recommended** — balanced speed and freshness |

**When LiveCrawl Isn't Necessary:**
Cached data is sufficient for many queries, especially for historical topics or educational content. These subjects rarely change, so reliable cached results can provide accurate information quickly.

See [maxAgeHours docs](https://exa.ai/docs/reference/livecrawling-contents#maxAgeHours) for more details.

---

## Other Endpoints

Beyond `/search`, Exa offers these endpoints:

| Endpoint | Description | Docs |
|----------|-------------|------|
| `/contents` | Get contents for known URLs | [Docs](https://exa.ai/docs/reference/get-contents) |
| `/answer` | Q&A with citations from web search | [Docs](https://exa.ai/docs/reference/answer) |

### /contents — Get Contents for Known URLs

Use `/contents` when you already have URLs and need their content. Unlike `/search` (which finds and optionally retrieves content), `/contents` is purely for content extraction from known URLs.

**When to use `/contents` vs `/search`:**
- URLs from another source (database, user input, RSS feeds) → `/contents`
- Need to refresh stale content for URLs you already have → `/contents` with `maxAgeHours`
- Need to find AND get content in one call → `/search` with `contents`

```bash
curl -X POST 'https://api.exa.ai/contents' \
  -H 'x-api-key: YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
  "urls": ["https://example.com/article", "https://example.com/blog-post"],
  "text": { "max_characters": 20000 }
}'
```

**Content retrieval options** (choose one per request):

| Option | Config | Best For |
|--------|--------|----------|
| Text | `"text": {"max_characters": 20000}` | Full content extraction, RAG |
| Highlights | `"highlights": {"max_characters": 4000}` | Key excerpts, lower token usage |

**Highlights example** (token-efficient excerpts with relevance query):
```json
{
  "urls": ["https://example.com/article"],
  "highlights": { "max_characters": 4000, "query": "key findings" }
}
```

**Freshness control:** Add `maxAgeHours` to ensure content is fresh:
- `24` — livecrawl if cached content is older than 24 hours
- `0` — always livecrawl (ignore cache)
- Omit — use cache when available, livecrawl as fallback

<details>
<summary>Python</summary>

```python
from exa_py import Exa

exa = Exa(api_key="YOUR_API_KEY")

results = exa.get_contents(
    ["https://example.com/article", "https://example.com/blog-post"],
    text={"max_characters": 20000}
)

for result in results.results:
    print(result.title, result.url)
    print(result.text[:500])  # First 500 chars
```
</details>

<details>
<summary>JavaScript</summary>

```javascript
import Exa from "exa-js";

const exa = new Exa("YOUR_API_KEY");

const results = await exa.getContents(
  ["https://example.com/article", "https://example.com/blog-post"],
  { text: { maxCharacters: 20000 } }
);

results.results.forEach(result => {
  console.log(result.title, result.url);
  console.log(result.text?.substring(0, 500));
});
```
</details>

---

## Troubleshooting

**⚠️ COMMON PARAMETER MISTAKES — avoid these:**
- `useAutoprompt` → **deprecated**, remove it entirely
- `includeUrls` / `excludeUrls` → **do not exist**. Use `includeDomains` / `excludeDomains`
- `stream: true` → **not supported** on /search or /contents
- `text`, `summary`, `highlights` at the top level of /search → **must be nested** inside `contents` (e.g. `"contents": {"text": true}`). On /contents they ARE top-level — don't confuse the two.
- `numSentences`, `highlightsPerUrl` → **deprecated** highlights params. Use `maxCharacters` instead
- `tokensNum` → **does not exist**. Use `maxCharacters` to limit text length
- `livecrawl` → **deprecated**. Use `maxAgeHours` instead (`maxAgeHours: 0` = always livecrawl)

**Results not relevant?**
1. Try `type: "auto"` - most balanced option
2. Try `type: "deep"` - runs multiple query variations and ranks the combined results
3. Refine query - use singular form, be specific
4. Check category matches your use case

**Need structured data from search?**
1. Use `type: "deep"` or `type: "deep-reasoning"` with `outputSchema`
2. Define the fields you need in the schema — Exa returns grounded JSON with citations

**Results too slow?**
1. Use `type: "fast"`
2. Reduce `num_results`
3. Skip contents if you only need URLs

**No results?**
1. Remove filters (date, domain restrictions)
2. Simplify query
3. Try `type: "auto"` - has fallback mechanisms

---

## Resources

- Docs: https://exa.ai/docs
- Dashboard: https://dashboard.exa.ai
- API Status: https://status.exa.ai