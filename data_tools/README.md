# Site Enrichment Pipeline

Offline script that enriches URLs from `sites_raw.csv` and writes `sites_enriched.csv`.

## How enrichment works

See the module docstring in `enrich_sites.py` for full details. Summary:

1. **Fetch** – For each URL, fetch HTML and extract title, meta description, and body text.
2. **Platforms** – Scan HTML for known CMS/framework signatures (WordPress, Webflow, Shopify, Next.js, etc.). Multiple matches allowed; each gets a confidence score 0–1.
3. **Industries** – Score visible text against keyword lists (SaaS, E‑commerce, Agency, etc.). Multiple industries above a threshold are kept with confidence 0–1.
4. **Tags** – Frequent meaningful words from the page; confidence from rank (top ≈ 1.0, then decay).
5. **Colors** – `meta theme-color`, `msapplication-TileColor`, then inline `style` and `<style>` blocks. First two distinct hex colors become `primary` and `secondary`. Graceful fallback if none found.

Output keeps legacy columns (`platform`, `industry`, `tags`) for display and adds JSON columns: `platforms`, `industries`, `colors`, `tag_confidence`, `last_enriched_at`.

## Run

From the project root:

```bash
python data_tools/enrich_sites.py
```

Requires: `requests`, `beautifulsoup4`. Input: `data_tools/sites_raw.csv` (column `website_url`). Output: `data_tools/sites_enriched.csv`.

## Example enriched row (JSON-ish)

```json
{
  "website_url": "https://example.com",
  "platform": "Webflow, Next.js",
  "industry": "SaaS, Agency",
  "tags": "pricing, hero, features",
  "platforms": ["Webflow", "Next.js"],
  "industries": ["SaaS", "Agency"],
  "colors": {"primary": "#0070f3", "secondary": "#7928ca"},
  "tag_confidence": {"pricing": 0.92, "hero": 0.78, "features": 0.65},
  "last_enriched_at": "2025-01-27T12:00:00Z"
}
```

Import `sites_enriched.csv` via the app’s CSV upload (owner-only) or any bulk import that accepts these columns.
