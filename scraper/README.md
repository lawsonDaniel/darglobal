# How the data was collected

Collected 18-19 Nov 2026 with Firecrawl's scrape tool, one public page at a time, at a gentle pace.

## DarGlobal (darglobal.co.uk)
1. Read `https://darglobal.co.uk/projects` for the list of 38 projects (name, location, page link).
2. Opened each project page and extracted property types, bedrooms, unit sizes, completion, status, units and amenities.
3. Checked a sample of values against each page's meta description. No page shows a price or payment plan.

## Wasalt (wasalt.sa)
1. Read the category page "villas for sale in <city>" for nine cities, e.g. `https://wasalt.sa/فلل-للبيع-في-الرياض`.
2. Each page shows its total result count and about 25-30 listing cards. Image carousels were stripped so the full card list fits in one read.
3. For each card: listing id, price (SAR), title (area, facing, street width), location (district, sector, city), bedrooms, bathrooms, "new" tag.
4. Checked against a deterministic parse of the Riyadh page (25 of 25 cards matched) and against three individual listing pages.
5. Contact details (phones, WhatsApp links, agent or owner names) were skipped on purpose.

## Company contacts (contacts.json, darglobal_company.json)
- DarGlobal: read the home, about and investor pages, and the home page as seen from the UAE, Saudi Arabia, the UK and the US, to record which phone and WhatsApp numbers the site shows. `/contact` and `/contact-us` return 404, and no email or office address appeared on the pages read. Brand partners and press headlines come from the home page's links.
- Wasalt: the customer-service number published in `wasalt.sa/llms.txt`. Individual agents' and owners' numbers were not collected.

## Rules followed
- `wasalt.sa/llms.txt`: extraction of public listing content only, no commercial use, moderate crawl rate, attribution "Source: Wasalt.sa", and no scraping of internal search results. That is why only the first results page per city was collected.
- DarGlobal requested this data as part of the assignment.

`probe.py` in this folder is an earlier Playwright probe, kept for reference.
