"""Build only the public policy site, never the private application or its configuration."""

import argparse
import html
import re
import shutil
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def build(email: str, output: Path) -> None:
    if not re.fullmatch(
        r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", email
    ):
        raise ValueError("Provide the operator's approved public contact email.")
    if output.exists():
        raise ValueError("Choose a new empty output directory.")
    contact = (
        f'<a href="mailto:{html.escape(email, quote=True)}">{html.escape(email)}</a>'
    )
    updated = date.today().isoformat()
    pages = {
        "": (
            "finding your flowers",
            f"""
<p class="intro">BouquetBrowse is a flower discovery and advertised-price comparison project for Hanoi.</p>
<p>We are developing a private research pilot that helps invited testers explore permitted seller listings, inspect source evidence, and distinguish visually similar bouquets from qualified price comparisons.</p>
<div class="notice">The research application is not publicly available. This site provides project information, our privacy notice, and instructions for requesting data deletion. Platform approval and live catalog coverage are not established by this website.</div>
<ul class="links"><li><a href="/privacy/">Read our privacy policy</a></li><li><a href="/data-deletion/">Request data deletion</a></li></ul>
<h2>Contact the project</h2><address>BouquetBrowse project operator: {contact}</address>
""",
        ),
        "privacy": (
            "Privacy policy",
            f"""
<p class="meta">Updated {updated}</p>
<p class="intro">This notice explains how the BouquetBrowse project handles information in its private research pilot and on this public information site.</p>
<p>BouquetBrowse is operated by the project administrator reachable at {contact}. The public information site and private application have different functions; publishing this notice does not open the research application to the public.</p>
<h2>Information we process</h2>
<ul><li><strong>Public site visits.</strong> Cloudflare hosts these pages and processes request information, such as IP addresses and browser details, to deliver and protect the site. These pages have no advertising, analytics scripts, forms, application login, or tracking cookies added by BouquetBrowse. See <a href="https://www.cloudflare.com/privacypolicy/">Cloudflare's privacy policy</a>.</li>
<li><strong>Invited pilot participants.</strong> When the private application is enabled, we process account identifiers, email addresses, access roles, and authentication/session information to manage invited access. Password authentication is handled by the configured authentication provider rather than stored as plaintext by BouquetBrowse.</li>
<li><strong>Permitted catalog records.</strong> We may process seller business names, social account identifiers, profile and post links, captions, permitted photos, publication dates, advertised prices and fulfillment claims, source-access permissions, and derived catalog attributes, embeddings, and review records. We do not assume that public visibility grants unrestricted collection or reuse.</li>
<li><strong>Support and operations.</strong> We process information you send with a correction or deletion request, together with minimal job, security, and administrative audit records. We do not intentionally collect personal search histories.</li></ul>
<h2>Why we use information</h2>
<p>We use it to operate the private pilot, display attributable permitted listings to authorized testers, search and compare bouquets, review extraction accuracy, maintain source permissions, protect access, and handle correction or deletion requests. An extraction review does not verify seller inventory or product availability.</p>
<h2>Platforms, service providers, and AI</h2>
<p>Meta APIs are used only where the required permissions and applicable use authorization are available. We do not use them to publish posts, send messages, or manage comments for this catalog workflow. We do not sell personal information or use Meta-derived data for advertising audiences.</p>
<p>The pilot is designed to use managed database, authentication, and private storage services from Supabase and application hosting infrastructure. When API-based AI enrichment is enabled, permitted captions and selected images may be sent to OpenAI to extract structured attributes and create search embeddings. OpenAI extraction requests are configured with storage disabled where supported; this does not guarantee zero provider retention. Local image processing may also generate derivatives and embeddings. Demonstration mode uses fictional data. Live provider use depends on configuration and source permissions.</p>
<p>Service providers process information according to their applicable terms and controls. Hosting or processing can occur outside your country. We do not claim that a production location, international-transfer arrangement, or live processing deployment has already been established.</p>
<h2>How long we keep information</h2>
<p>Pilot defaults are up to 30 days for raw source payloads and operational logs, 90 days for permitted media and vectors, and 12 months for accepted catalog facts. Shorter source requirements or valid deletion requests override those defaults. Account data is kept while needed for authorized access, and request/audit records may be retained where needed to document handling or meet applicable obligations. Backup copies require separate expiry or deletion handling; removal records must be replayed before restored data is returned to use.</p>
<h2>Your choices and requests</h2>
<p>You can contact {contact} to request access, correction, deletion, or withdrawal from the pilot. Include only the account or source links needed to locate the relevant information. We may ask for proportionate evidence that you control the affected account or content. Do not send passwords, API tokens, or identity documents unless a justified verification method has first been agreed.</p>
<p>Follow the <a href="/data-deletion/">data-deletion instructions</a> to disconnect a Threads connection and request removal of retained data. Revoking a platform connection stops the authorization but does not, by itself, delete information already retained by the project. Requests are handled by the project operator; this site does not submit requests automatically.</p>
<h2>Security and changes</h2>
<p>The private pilot uses restricted access, role-based administration, private media storage, and source-linked review and removal workflows. No system can guarantee absolute security. We update this page when the project's data practices change and revise the date above. Contact {contact} with privacy questions.</p>
""",
        ),
        "data-deletion": (
            "Data deletion",
            f"""
<p class="meta">Updated {updated}</p><p class="intro">Request removal of your pilot account, connected Threads data, or source-linked seller content.</p>
<h2>Send a deletion request</h2>
<ol><li>Email {contact} with the subject <strong>BouquetBrowse data deletion</strong>.</li><li>Identify the pilot account email, Threads username, or specific source-post/profile links you want removed. Tell us whether the request covers an account, individual posts, or all content associated with a seller account.</li><li>If you are writing for someone else, explain your authority. The operator may ask for a proportionate ownership check before deleting another person's information.</li></ol>
<p>Never include a password, access token, app secret, or unnecessary personal documents. Avoid posting private deletion requests in a public GitHub issue.</p>
<h2>Disconnect Threads access</h2>
<p>In Threads, open Settings and find Website permissions. Remove BouquetBrowse from the active connected applications if it appears there. Platform menu names may change. Disconnecting revokes the connection; email the operator as well to request removal of previously retained project data.</p>
<h2>What happens next</h2>
<p>The operator identifies the affected records, verifies the scope where needed, suppresses applicable catalog content, and processes deletion of retained source text, photos and derivatives, extracted attributes, commercial observations, search vectors, caches, and affected comparison records. Account deletion also requires removal from the authentication provider and application membership. Shared assets need to be checked against the full request scope.</p>
<p>We aim to acknowledge requests within seven days and explain the expected completion time after verification. If a legal obligation or technical dependency prevents immediate deletion, the operator will explain the reason, affected scope, and next step. Minimal records documenting the request or preventing withdrawn content from being reimported may remain where necessary.</p>
<p>Backups are handled separately: affected copies must expire or be removed under the applicable backup process, and deletion records must be applied before any restored data is used again. The operator will explain any remaining backup limitation when confirming the request.</p>
<p>This page does not delete the original post or your account on Instagram or Threads. Those remain controlled through the original platform. Read our <a href="/privacy/">privacy policy</a> for more detail.</p>
""",
        ),
    }
    shutil.copytree(ROOT / "public-site", output)
    for route, (title, body) in pages.items():
        nav = "".join(
            f'<a href="{path}"'
            + (' aria-current="page"' if route == key else "")
            + f">{label}</a>"
            for key, path, label in [
                ("", "/", "Project"),
                ("privacy", "/privacy/", "Privacy"),
                ("data-deletion", "/data-deletion/", "Data deletion"),
            ]
        )
        document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="description" content="BouquetBrowse project information, privacy policy, and data-deletion instructions."><title>{html.escape(title)} · BouquetBrowse</title><link rel="stylesheet" href="/style.css"></head><body><a class="skip" href="#content">Skip to content</a><header><a class="brand" href="/">BouquetBrowse</a><nav aria-label="Main navigation">{nav}</nav></header><main id="content"><h1>{html.escape(title)}</h1>{body}</main><footer>BouquetBrowse · finding your flowers<br>Private research pilot · Hanoi</footer></body></html>"""
        directory = output / route
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "index.html").write_text(document, encoding="utf-8")
    (output / "404.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>Page not found · BouquetBrowse</title><link rel="stylesheet" href="/style.css"><main><h1>Page not found</h1><p><a href="/">Return to BouquetBrowse</a></p></main></html>',
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--contact-email", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.contact_email, args.output.resolve())
