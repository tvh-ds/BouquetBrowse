# Public information site

The static site is separate from the private Next.js/FastAPI application. It publishes only project information, a privacy notice, and manual data-deletion instructions. It does not provide OAuth, API ingestion, application login, or Meta approval. Never upload the repository root, `.env`, `.data`, database exports, or seller media to the static host.

## Build and deploy

The operator approved `viethoangtran.ds@gmail.com` as the public privacy/deletion contact. It is a build input rather than a hidden application setting. No JavaScript, analytics, third-party fonts, or dependencies run on the information site. Font files are copied from the application's installed Fontsource packages, with their licenses included.

From the repository root, choose a **new** output directory:

```powershell
python deploy/build_public_site.py --contact-email viethoangtran.ds@gmail.com --output .data/public-site-release
```

The builder refuses to overwrite an existing directory. Review the generated copy before publishing. Create a ZIP containing only the contents of that output directory, with `index.html` at the ZIP root. Use Cloudflare Pages Free / Direct Upload for the project. No paid plan, custom domain, Worker, storage bucket, or private application deployment is required. Dashboard-upload projects can subsequently use Wrangler deployments; switching to Git integration requires a new project.

After deployment verify HTTPS, `/`, `/privacy/`, `/data-deletion/`, a missing-path 404, contact links, and the headers from `_headers`. Record the actual `pages.dev` URL after verification. In Meta Basic settings, use `/privacy/` for Privacy policy URL and `/data-deletion/` for User data deletion instructions URL. These settings do not grant `threads_keyword_search` approval. Review remaining app requirements separately.

## Privacy operations

Monitor the published mailbox. Verify requests proportionately, identify the full seller/source/account scope, suppress and purge applicable records through the application's takedown workflow, and handle Auth membership/accounts and backups separately. Do not claim a completed erasure until all applicable stores are checked. Update the notice if providers, collection, retention, or deployment arrangements change.

## Scope and validation

Public inputs are static documents only. Security headers deny scripts, framing, forms, and device permissions. Email is validated and escaped at build time. There are no credentials in the artifact. A public contact mailbox is intentional; operational data remains private. Cloudflare processes request metadata for hosting/security under its own privacy policy.

This site is prepared to remove the missing-policy-URL blocker. It does not resolve the platform's business-app eligibility restriction or substitute for an App Review demonstration of the actual integration.

Reference: [Cloudflare Direct Upload](https://developers.cloudflare.com/pages/get-started/direct-upload/).
