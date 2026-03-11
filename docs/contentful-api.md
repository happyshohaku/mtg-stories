# Contentful API & Token Documentation

## Overview

Wizards of the Coast uses Contentful as their headless CMS to manage Magic: The Gathering story content. The application accesses this API to retrieve story metadata without scraping the website directly.

## API Details

### Endpoint
```
https://cdn.contentful.com/spaces/s5n2t79q9icq/environments/master/entries
```

### Authentication

The API uses a Bearer token for authentication:

```
Authorization: Bearer CPET-V_EFhnj_qi1lfps9BH3Se6V1B_bxE1J1VYi7qo
```

**Important Notes:**
- This is a **public read-only** Content Delivery API token
- It provides access only to published content
- The token is embedded in the public-facing website's JavaScript
- It cannot be used to modify content (that requires a Management API token)
- The token may change if Wizards of the Coast rotates their credentials

### Finding/Updating the Token

If the token stops working:

1. Go to https://magic.wizards.com/en/story
2. Open browser Developer Tools (F12)
3. Go to Network tab
4. Filter by "contentful"
5. Look for requests to `cdn.contentful.com`
6. Check the `Authorization` header for the new token

Alternatively, search the page's JavaScript files for `contentful` or `Bearer`.

## Content Types

### storyGroup

Represents a collection of stories (e.g., "Edge of Eternities", "Outlaws of Thunder Junction").

**Query Parameters:**
```
content_type=storyGroup
locale=en
include=10
fields.firstStoryYear[in]={YEAR}
```

**Response Structure:**
```json
{
  "items": [
    {
      "sys": {
        "id": "unique-id"
      },
      "fields": {
        "name": "Edge of Eternities",
        "firstStoryYear": 2025,
        "archiveThumbnail": {
          "sys": {
            "type": "Link",
            "linkType": "Asset",
            "id": "asset-id"
          }
        },
        "stories": [
          {
            "sys": {
              "type": "Link",
              "linkType": "Entry",
              "id": "story-entry-id"
            }
          }
        ]
      }
    }
  ],
  "includes": {
    "Entry": [...],
    "Asset": [...]
  }
}
```

### article

Individual story content (newer format, ~2020+). Used in two ways:
1. **Linked from storyGroup** — referenced as a story entry within a curated set
2. **Standalone** — queried directly via `content_type=article&fields.category=magic-story` to find stories not in any storyGroup

**Fields:**
- `title` - Story title (often formatted as "Set Name | Episode Title")
- `slug` - URL slug
- `category` - Usually "magic-story"
- `publishedDate` - Publication date (format: "YYYY-MM-DD HH:MM:SS")
- `authors` - Array of links to `author` entries
- `excerpt` - HTML excerpt/description
- `metaDescription` - Fallback description if excerpt is empty

**URL Pattern:**
```
https://magic.wizards.com/en/news/{category}/{slug}
```

**Standalone Article Query:**
```
content_type=article
fields.category=magic-story
locale=en
order=-sys.createdAt
limit=100
skip={offset}
include=1
```

The `include=1` resolves linked `author` entries so author names can be extracted. Pagination is required since Contentful limits responses to 100 items max. There are ~464 total magic-story articles.

**Title Prefix Grouping:**
Article titles often follow the pattern `"Set Name | Story Title"`. The application splits on `" | "` to group articles into story sets (e.g., "Secrets of Strixhaven | Off the Record" → set "Secrets of Strixhaven").

### storyEntry

Individual story content (older format, pre-2020).

**Fields:**
- `title` - Story title
- `cta` - Call-to-action link containing the URL

**CTA Structure:**
```json
{
  "cta": {
    "sys": {
      "type": "Link",
      "linkType": "Entry",
      "id": "cta-entry-id"
    }
  }
}
```

The CTA entry contains:
```json
{
  "fields": {
    "link": "https://magic.wizards.com/en/articles/archive/..."
  }
}
```

## Linked Content Resolution

Contentful uses a linking system where entries reference other entries/assets by ID. The `include` parameter determines how many levels of linked content to resolve.

```
include=10  # Resolve up to 10 levels of nested links
```

Linked content appears in the `includes` object:
- `includes.Entry[]` - Linked entries (stories, CTAs)
- `includes.Asset[]` - Linked assets (images)

### Building Lookup Maps

```python
entries_map = {}
assets_map = {}

for entry in data.get("includes", {}).get("Entry", []):
    entries_map[entry["sys"]["id"]] = entry

for asset in data.get("includes", {}).get("Asset", []):
    assets_map[asset["sys"]["id"]] = asset
```

## Asset URLs

Image assets return URLs without the protocol:

```json
{
  "fields": {
    "file": {
      "url": "//images.ctfassets.net/s5n2t79q9icq/..."
    }
  }
}
```

Prepend `https:` to make them valid URLs:

```python
if image_url.startswith("//"):
    image_url = "https:" + image_url
```

## External Links

Some story groups contain links to external e-books (Amazon, etc.) instead of website stories. These are identified by:

1. Content type is `storyEntry`
2. CTA link does not contain `magic.wizards.com`

Example external link:
```
https://www.amazon.com/dp/B09XYZ123/
```

These are stored separately and opened in the browser rather than converted to EPUB.

## Rate Limiting

The Contentful CDN doesn't have strict rate limits, but the application adds a 0.5-second delay between story page requests to be respectful:

```python
time.sleep(0.5)
```

## Error Handling

Common API errors:

| Status | Meaning | Action |
|--------|---------|--------|
| 401 | Invalid token | Update token (see above) |
| 404 | Content not found | Check content type/year |
| 429 | Rate limited | Add delays between requests |
| 500+ | Server error | Retry later |

## Example Request

```bash
curl -H "Authorization: Bearer CPET-V_EFhnj_qi1lfps9BH3Se6V1B_bxE1J1VYi7qo" \
  "https://cdn.contentful.com/spaces/s5n2t79q9icq/environments/master/entries?content_type=storyGroup&locale=en&include=10&fields.firstStoryYear[in]=2025"
```
