# Place search

Find geographic places — businesses, landmarks, and points of interest — from our index of over 200 million locations worldwide

## Overview

Place Search is built for finding geographic places. Where Web Search finds web pages, Place Search finds locations in the physical world — coffee shops, museums, hotels, parks, and any other point of interest. You can anchor your search to a specific area using coordinates or a location name, or cast a broader net and let the index surface the most relevant matches globally.

With over 200 million indexed places worldwide, the API works well for everything from "find a specific restaurant nearby" to "what are the major landmarks associated with this city".

In addition to individual POIs (`results`), the response can include richer geographic groupings — `cities`, `addresses` (specific street + number locations) and `streets` (entire streets) — together with a `mixed` ordering that tells you how to interleave them on a results page.

## Key Features

Access our comprehensive global index of over 200 million places

Search near coordinates or a location name — with or without a radius constraint

Get detailed information including ratings, hours, contact info, and photos

Discover general places in an area without a specific query

Place Search is part of **Search plan**. [Subscribe](/app/subscriptions/subscribe) to use this feature.

## API Reference

View the complete API reference, including endpoints, parameters, and example requests

## Use Cases

Place Search is a good fit when your goal is geographic discovery:

- **Location-Based Apps**: Build apps that help users discover nearby places                                                                                                               
- **Travel & Tourism**: Find attractions, restaurants, and hotels in any destination                                                                                                       
- **Business Directories**: Create local business listings and discovery features                                                                                                          
- **Mapping Applications**: Populate maps with relevant places                                                                                                                
- **Geofenced Recommendations**: Suggest places based on user location

## Basic Usage

Search for places near a set of coordinates:

```bash
curl "https://api.search.brave.com/res/v1/local/place_search?latitude=37.7749&longitude=-122.4194&q=coffee+shops&radius=1000" \
  -H "X-Subscription-Token: <YOUR_API_KEY>"
```

Or use a location name if you don't have coordinates at hand:

```bash
curl "https://api.search.brave.com/res/v1/local/place_search?location=san+francisco+ca+united+states&q=coffee+shops" \
  -H "X-Subscription-Token: <YOUR_API_KEY>"
```

The response includes a list of matching places with detailed information:

```json
{
  "type": "locations",
  "query": {
    "original": "coffee shops",
    "altered": null,
    "spellcheck_off": false,
    "show_strict_warning": false
  },
  "results": [
    {
      "type": "location_result",
      "id": "loc4FNMQJNOOCVHEB7UBOLN354ZYIDIYJ3RPRETERRY=",
      "title": "Blue Bottle Coffee",
      "url": "https://bluebottlecoffee.com",
      "provider_url": "https://yelp.com/biz/blue-bottle-coffee-sf",
      "coordinates": [37.7825, -122.4095],
      "postal_address": {
        "type": "PostalAddress",
        "displayAddress": "66 Mint St, San Francisco, CA 94103",
        "streetAddress": "66 Mint St",
        "addressLocality": "San Francisco",
        "addressRegion": "CA",
        "postalCode": "94103",
        "country": "US"
      },
      "rating": {
        "ratingValue": 4.5,
        "bestRating": 5.0,
        "reviewCount": 1250
      },
      "opening_hours": {
        "current_day": [
          {
            "abbr_name": "Tue",
            "full_name": "Tuesday",
            "opens": "07:00",
            "closes": "18:00"
          }
        ]
      },
      "distance": {
        "value": 0.3,
        "units": "km"
      },
      "categories": ["Coffee & Tea", "Cafe"],
      "price_range": "$$",
      "thumbnail": {
        "src": "https://example.com/thumb.jpg",
        "original": "https://example.com/original.jpg"
      },
      "timezone": "America/Los_Angeles"
    }
  ],
  "cities": [],
  "addresses": [],
  "streets": [],
  "mixed": [
    { "type": "results", "index": 0, "all": false }
  ],
  "location": {
    "coordinates": [37.7749, -122.4194],
    "name": "San Francisco",
    "country": "US"
  }
}
```

## Request Parameters

### Location

Providing a geographic anchor is optional but strongly recommended for most queries. You can use either coordinates (`latitude` + `longitude`) or a `location` string. If neither is given, results are sourced more broadly and may be less precise.

| Parameter | Type | Description |
|-----------|------|-------------|
| `latitude` | float | Latitude of the search center (-90.0 to +90.0). Required together with `longitude`. |
| `longitude` | float | Longitude of the search center (-180.0 to +180.0). Required together with `latitude`. |
| `location` | string | Location name, alternative to coordinates. For US locations use the form `city state country` (e.g., `san francisco ca united states`). For non-US locations use `city country` (e.g., `tokyo japan`). Case-insensitive, no commas needed. Multilingual supported. |

### Search

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` | string | — | What to look for (e.g., `coffee shops`, `pizza`, `museums`). Optional — omit it to get general places in the given area. |
| `radius` | float | — | Search radius bias around the provided coordinates, in meters. **Note**: this biases results towards the area but is not a hard cutoff (the result set may extend beyond it). Search is global if omitted. See [Radius and result quality](#radius-and-result-quality). |
| `count` | int | `20` | Number of results to return (1 to 50) |

### Locale and Preferences

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `country` | string | `US` | Two-letter country code (ISO 3166-1 alpha-2) |
| `search_lang` | string | `en` | Search language (2+ character language code) |
| `ui_lang` | string | `en-US` | UI language for the response (locale code) |
| `units` | string | `metric` | Measurement units: `metric` or `imperial` |
| `safesearch` | string | `strict` | Safe search level: `off`, `moderate`, or `strict` |
| `spellcheck` | bool | `true` | Whether to apply spellcheck to the query |

## Radius and Result Quality

The `radius` parameter controls how tightly the search is anchored to your coordinates. No upper limit is enforced, so you can search a neighborhood or an entire region.

In practice, a tighter radius tends to produce more focused results. When you search within a compact area, the index can confidently surface places that are unambiguously nearby. As the radius grows — or when no radius is given — results are drawn from a wider pool, which works well for well-known or distinctive places but may be less precise for common query types where many candidates exist across a large area.

A few rough guidelines:

- **Under ~20 km**: Results are typically well-matched to the search area. Good for "what's near me" use cases.
- **Larger areas or no radius**: Works best for specific or distinctive queries (a particular museum, a named landmark, a regional specialty). Generic category searches (e.g., `restaurants`, `hotels`) may return a broader set of candidates.

If your use case is finding a specific known place by name or type across a wide region, omitting the radius or using a large one is fine. For density-based searches — "show me all the pharmacies in this district" — a tighter radius will give cleaner results.

## Location String Format

When using the `location` parameter instead of coordinates, follow these conventions:

| Region | Format | Example |
|--------|--------|---------|
| United States | `city state country` | `san francisco ca united states` |
| Other countries | `city country` | `tokyo japan` |
| Multilingual | native or English name | `nueva york` or `new york` |

No commas or special characters are needed, and capitalization does not matter. English or the most popular language for the target city generally works best.

## Explore Mode

Omit `q` to get a general snapshot of places in an area — useful for map views, destination previews, or any feature where you want to show what's around a location rather than answer a specific query:

```bash
curl "https://api.search.brave.com/res/v1/local/place_search?latitude=40.7128&longitude=-74.0060&radius=2000&count=10" \
  -H "X-Subscription-Token: <YOUR_API_KEY>"
```

## Fetching Additional POI Details

Each result includes an `id` that works with the same detail endpoints used for Web Search location results — so the same integration serves both.

### Detailed POI Information

Use `/local/pois` to fetch photos, web result mentions, profiles, and more:

```bash
curl "https://api.search.brave.com/res/v1/local/pois?ids=loc4FNMQJNOOCVHEB7UBOLN354ZYIDIYJ3RPRETERRY=" \
  -H "X-Subscription-Token: <YOUR_API_KEY>"
```

### AI-Generated Descriptions

Use `/local/descriptions` to get AI-generated descriptions for locations:

```bash
curl "https://api.search.brave.com/res/v1/local/descriptions?ids=loc4FNMQJNOOCVHEB7UBOLN354ZYIDIYJ3RPRETERRY=" \
  -H "X-Subscription-Token: <YOUR_API_KEY>"
```

You can request details for up to 20 POIs in a single request by providing multiple `ids` parameters.

**POI IDs are interchangeable**: The same IDs work whether they came from Place Search or Web Search location results, making it straightforward to build unified experiences across both.

POI IDs are ephemeral and expire after approximately **8 hours**. Do not store them for later use.

## Response Fields

### Top-Level Fields

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"locations"` |
| `query` | object | Query information including original and spell-corrected forms |
| `query.original` | string | The original query that was requested |
| `query.altered` | string? | The spell-corrected query, if spellcheck was applied. `null` if no correction was made |
| `query.spellcheck_off` | bool? | Whether spellcheck was disabled for this query |
| `query.show_strict_warning` | bool? | Whether strict safesearch filtered results |
| `results` | array | List of `LocationResult` objects (individual POIs) |
| `cities` | array | List of `EnhancedPlaceResult` objects — cities, countries, or regions matched by the query, each enriched with a description and a curated set of POIs |
| `addresses` | array | List of `AddressResult` objects with `type: "address"` — specific street + number locations matched by the query |
| `streets` | array | List of `AddressResult` objects with `type: "street"` — full streets matched by the query |
| `mixed` | array | Ordering hints (`ResultReference` objects) for interleaving entries from `results`, `cities`, `addresses`, and `streets` on a single results page |
| `location` | object | Resolved location information (present when coordinates were provided or resolved) |
| `location.coordinates` | [float, float] | Latitude and longitude of the resolved search center |
| `location.name` | string | Resolved location name (e.g., `"San Francisco"`) |
| `location.country` | string | Two-letter country code (e.g., `"US"`) |

The `results`, `cities`, `addresses`, and `streets` arrays are all optional: any of them may be `null` or omitted depending on what the query matched. For straightforward POI-style queries, only `results` is typically populated.

### LocationResult Fields

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"location_result"` |
| `id` | string | Temporary identifier for fetching additional details (valid ~8 hours) |
| `title` | string | Name of the location |
| `url` | string | Canonical URL |
| `provider_url` | string | Provider page URL |
| `description` | string | Short description |
| `coordinates` | [float, float] | Latitude and longitude |
| `postal_address` | object | Address with `displayAddress`, `streetAddress`, `addressLocality`, `addressRegion`, `postalCode`, `country` |
| `opening_hours` | object | Business hours with `current_day` and `days` arrays |
| `contact` | object | Contact info with `telephone` and `email` |
| `rating` | object | Ratings with `ratingValue`, `bestRating`, `reviewCount` |
| `price_range` | string | Price classification (e.g., `"$$"`) |
| `distance` | object | Distance from search center with `value` and `units` |
| `categories` | array | Category classifications |
| `serves_cuisine` | array | Cuisine types (for restaurants) |
| `thumbnail` | object | Primary image with `src` and `original` |
| `pictures` | object | Additional photos |
| `profiles` | array | External profiles (`name`, `url`, `long_name`, `img`) |
| `timezone` | string | IANA timezone identifier (e.g., `"America/Los_Angeles"`) |

### EnhancedPlaceResult Fields (`cities`)

`EnhancedPlaceResult` represents a city, country, or region matched by the query. Use it to render an "about this place" panel alongside POI results.

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always `"enhanced_place"` |
| `name` | string | Place name |
| `country` | string | Country of the place |
| `coordinates` | [float, float] | Latitude and longitude |
| `kind` | string | One of `city`, `country`, or `region` |
| `thumbnail` | object | Primary image for the place (`src`, `alt`, `width`, `height`) |
| `short_description` | string | Short description suitable for a list view |
| `description` | string | Long-form description |
| `description_ai` | string | AI-generated description |
| `description_src` | string | Source attribution for the description |
| `pois` | array | `LocationResult` objects representing notable POIs in/of this place |
| `attributes` | array | Key/value attributes (factsheet-style), each entry is `[label, value]` |

### AddressResult Fields (`addresses` and `streets`)

`AddressResult` represents either a specific street + number (`type: "address"`) or an entire street (`type: "street"`). The `addresses` array contains entries with `type: "address"`, while the `streets` array contains entries with `type: "street"`.

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | `"address"` for entries in `addresses`, `"street"` for entries in `streets` |
| `name` | string | Display name of the address or street |
| `coordinates` | [float, float] | Latitude and longitude |
| `pois` | array | `LocationResult` objects located **at** this address/street |
| `pois_nearby` | array | `LocationResult` objects located **nearby** |
| `zoom_level` | int | Suggested map zoom level (default `15`) |
| `distance` | object? | Distance from the user's geolocation, if available (`value`, `units`) |
| `postal_address` | object? | Structured postal address |

### Mixed Ordering (`mixed`)

`mixed` is an ordered list of `ResultReference` objects describing how to interleave entries from the various result buckets on a SERP. Each entry has:

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Which bucket to draw from: `results`, `cities`, `addresses`, or `streets` |
| `index` | int? | 0-based index of the item to place at this position. May be `null` when `all` is `true`. |
| `all` | bool | When `true`, all items from the named bucket should be placed at this position |

Clients that only care about a single bucket (e.g., POIs) can ignore `mixed` and read `results` directly.

## Example: Building a Nearby Places Feature

```python
import requests

API_KEY = "<YOUR_API_KEY>"
BASE_URL = "https://api.search.brave.com/res/v1"

def find_nearby_places(lat, lng, query="", radius=5000):
    """Search for places near a location."""
    params = {
        "q": query,
        "latitude": lat,
        "longitude": lng,
        "radius": radius,
        "count": 20
    }

    response = requests.get(
        f"{BASE_URL}/local/place_search",
        params=params,
        headers={"X-Subscription-Token": API_KEY}
    )
    return response.json()

def find_places_by_name(location, query="", country="US"):
    """Search for places using a location name instead of coordinates."""
    params = {
        "q": query,
        "location": location,
        "country": country,
        "count": 20
    }

    response = requests.get(
        f"{BASE_URL}/local/place_search",
        params=params,
        headers={"X-Subscription-Token": API_KEY}
    )
    return response.json()

def get_poi_details(poi_ids):
    """Fetch detailed information for places."""
    response = requests.get(
        f"{BASE_URL}/local/pois",
        params=[("ids", pid) for pid in poi_ids],
        headers={"X-Subscription-Token": API_KEY}
    )
    return response.json()

def get_poi_descriptions(poi_ids):
    """Fetch AI-generated descriptions for places."""
    response = requests.get(
        f"{BASE_URL}/local/descriptions",
        params=[("ids", pid) for pid in poi_ids],
        headers={"X-Subscription-Token": API_KEY}
    )
    return response.json()

# Find coffee shops near San Francisco using coordinates
places = find_nearby_places(37.7749, -122.4194, query="coffee")

# Or find museums in Paris using a location name
places = find_places_by_name("paris france", query="museums", country="FR")

# Get IDs from results
poi_ids = [p["id"] for p in places.get("results", []) if p.get("id")]

# Fetch additional details and descriptions
if poi_ids:
    details = get_poi_details(poi_ids[:20])
    descriptions = get_poi_descriptions(poi_ids[:20])
```

## Rate Limits and Billing

Place Search requests are billed separately from Web Search. Check your [subscription dashboard](/app/subscriptions) for current limits and usage.

## Changelog

- **2026-03-04** Lifted radius restrictions. Radius now defaults to none.
- **2026-01-15** Add Place Search endpoint for geographic POI discovery.