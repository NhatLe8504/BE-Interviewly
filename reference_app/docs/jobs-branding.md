# Company branding and job metadata

Company media belongs to job_companies, never to a guessed technology category.
The API exposes company.company_banner_url, company.company_logo_url and the
source / reuse-policy references. Legacy thumbnail_url now means an approved
company banner only; a company logo is not a banner.

## Permission-aware ingestion

No blanket employer-photography reuse permission is configured for these sources.
Recipes therefore leave media reuse disabled by default. Add company_branding
to an existing source recipe only after obtaining an applicable reuse permission:

- reuse_allowed: explicit boolean approval, not inferred from public access.
- license_url: the actual licensing / permission document.
- allowed_image_hosts: exact approved HTTPS image hosts.
- company_name_selector: employer identity when the page lacks JobPosting JSON-LD.
- logo_selectors and banner_selectors: verified employer-specific image selectors.

The crawler requires a matching employer identity, validates image hosts and
persists provenance before publishing media. It never uses a job-board site logo,
generic Open Graph image, technology photo, or invented image URL as a company cover.
ATS enrichment checks at most one permitted detail page per company per batch.
Configure the same approved hosts in NEXT_PUBLIC_COMPANY_IMAGE_HOSTS on the frontend.

Without permission, without an image, or on image failure, the frontend keeps the
banner area and shows a neutral employer-name / approved-logo treatment instead.
This is an explicit missing-media state, not a stock-image placeholder.

## Accurate metadata

- Unspecified seniority / employment / workplace types use unknown.
- A role title takes priority over unrelated mentions of senior colleagues or interns.
- posted_at is only a source publication timestamp, never an ingestion timestamp.
- first_seen_at records discovery; last_synced_at records the crawler's last observation.
- updated_at records local content changes, separately from source publication.
- Default search targets Vietnam and explicitly worldwide remote roles. Other countries
  remain available through the country filter. Remote restricted to US / EMEA / Americas
  is not treated as available worldwide.
- The idempotent metadata migration clears legacy crawler-generated posting dates and
  repairs guessed classifications. It does not delete real jobs or company records.
