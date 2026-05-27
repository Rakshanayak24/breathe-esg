# TRADEOFFS.md — What We Deliberately Did Not Build

## 1. Scope 2 Market-Based Accounting

**What it is**: GHG Protocol allows two methods for Scope 2. Location-based uses the average grid emission factor for the region (what we implemented). Market-based uses the EF from your actual electricity supplier contract, or zero if you've purchased RECs (Renewable Energy Certificates) or I-RECs.

**Why we didn't build it**: Market-based requires a separate data source — supplier invoices, REC registry data, or Power Purchase Agreement (PPA) documentation. None of those come from the three sources specified. The data model has `scope2_market` in the SCOPE_CHOICES enum, and `EmissionRecord` can hold a market-based record, but the ingestion pipeline and emission calculator don't produce one yet.

**What would break if we added it**: Nothing — the model is ready. A new source type `utility_market_based` would need its own parser and EF lookup against a REC registry.

**Cost of not having it**: Clients required to report both location-based and market-based (e.g., for CDP disclosure) will need this. The location-based number is always required; market-based is additive.

---

## 2. Real-Time API Ingestion (SAP OData / Concur API)

**What it is**: Instead of file uploads, pull data directly from SAP via OData REST calls or from Concur/Navan via their OAuth2 APIs.

**Why we didn't build it**:
- SAP OData requires VPN access and SAP BASIS configuration on the client's side. Setup time: weeks, not days.
- Concur's API requires registering an OAuth2 app, getting an enterprise key, and completing their partner review process. This is months of work, not hours.
- For a prototype evaluated in 4 days, file upload delivers the same data model and parsing logic. The parsers are designed to be format-agnostic — they could accept data from an API response instead of a file with minimal changes.

**What it would look like in production**: A `ScheduledPull` model with cron job, OAuth token storage (encrypted), error retry logic, and a webhook endpoint for SAP push. The parsers would be called with the API response data instead of file bytes.

**Cost of not having it**: Analysts must manually export and upload. For a large enterprise doing monthly uploads across 50 sites, that's significant manual effort. This is the correct next feature after launch.

---

## 3. JWT Auth with Refresh Tokens / SSO

**What it is**: Production-grade authentication — JWT tokens with short expiry + refresh tokens in HTTP-only cookies, plus SAML/OIDC integration with the client's identity provider (Okta, Azure AD).

**Why we didn't build it**:
- DRF's `TokenAuthentication` works correctly for a prototype. The token model is simpler to reason about.
- Enterprise clients expect SSO. But SSO integration is client-specific (each IdP has different SAML metadata) and takes significant configuration time.
- HTTP-only cookies require CSRF handling changes throughout the API. JWT requires token blacklisting on logout.

**What we have instead**: Token-based auth with `Authorization: Token <key>` header. Logout deletes the token server-side. Good enough for a prototype with known users.

**Cost of not having it**: Tokens stored in localStorage are accessible to JavaScript (XSS risk). In production, move to HTTP-only cookies + CSRF double-submit pattern. No SSO means enterprise clients' IT teams need to manage separate credentials.

---

## Honorable Mentions (smaller gaps we know about)

- **No pagination on batch rows**: The rows endpoint returns all rows in a batch. For batches with 10,000 rows this will be slow. Fix: add `PageNumberPagination` to the rows action and paginate the React table.
- **No full IATA database**: We carry ~60 airports. A production deployment would load the full OurAirports database (~8,000 airports) at startup. Unknown IATA codes are flagged suspicious — the analyst can manually correct distances.
- **No email notifications**: Analysts get no alert when a new batch lands. A simple Django signal → email via SendGrid would fix this.
- **No export to CSV/Excel**: Analysts can't download the locked emission records. A `/api/emission-records/export/` endpoint returning a CSV would be straightforward to add.
- **No Scope 3.1 (purchased goods) calculation**: SAP procurement rows are parsed and stored but we don't calculate emissions for them — would require a spend-based or supplier-specific emission factor database (Ecoinvent, CBAM factors).
