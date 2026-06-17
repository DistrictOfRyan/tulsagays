# Tulsa Gays Events API (v1)

Public, read-only JSON feed of LGBTQ+ events in Tulsa, OK. Free to consume with
attribution. This is the seed of a wider queer-local events graph.

- **Endpoint:** `https://www.tulsagays.com/api/events.json`
- **Format:** JSON, UTF-8
- **License:** CC BY 4.0 — attribute Tulsa Gays (tulsagays.com)
- **Updated:** weekly (and whenever the site refreshes), `generated_at` is the stamp.

## Shape
```json
{
  "api_version": "1",
  "city": "Tulsa, OK",
  "publisher": "Tulsa Gays",
  "generated_at": "<ISO8601 UTC>",
  "license": "...",
  "count": <int>,
  "events": [
    {
      "name": "string",
      "date": "YYYY-MM-DD",
      "time": "string (human, e.g. '9:00 PM')",
      "venue": "string",
      "url": "string (event or source URL, may be empty)",
      "lgbtq_relevant": true,
      "city": "Tulsa, OK"
    }
  ]
}
```

## Using it
```bash
curl -s https://www.tulsagays.com/api/events.json | jq '.events[] | .name'
```

Attribution required: link back to tulsagays.com. Want a richer feed (recurring rules,
geo, categories) or another city? That is the roadmap — partner inquiries via the site.
