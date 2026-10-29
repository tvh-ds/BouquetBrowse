import argparse
import json
from pathlib import Path

from .config import get_settings
from .db import Base, SessionLocal, engine
from .models import AppUser
from .seed import seed_demo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=["demo", "member", "openapi", "discovery-init", "browser-login", "evaluate-images"]
    )
    parser.add_argument("--user-id")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--configuration-hash")
    parser.add_argument("--dataset-kind", choices=["synthetic", "permitted_real"], default="synthetic")
    parser.add_argument("--role", choices=["tester", "reviewer", "admin"], default="tester")
    args = parser.parse_args()
    if args.command == "evaluate-images":
        from .config import ROOT
        from .recognition_evaluation import evaluate_images

        if not args.input or not args.output or not args.configuration_hash:
            parser.error("--input, --output and --configuration-hash are required")
        output = args.output.resolve()
        if output.is_relative_to(ROOT) and not output.is_relative_to(ROOT / ".data"):
            parser.error("Keep evaluation exports under ignored .data or outside the public repository")
        if args.input.stat().st_size > 10 * 1024 * 1024:
            parser.error("Evaluation input exceeds 10 MB")
        rows = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
        report = evaluate_images(rows, args.configuration_hash, args.dataset_kind)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(
            f"Evaluated {report['images']} images; dataset gate: {report['dataset_ready']}. No models called or publication enabled."
        )
    elif args.command == "browser-login":
        from .browser import open_browser

        print("Sign in directly in the dedicated browser. No cookies are copied; close the window to cancel.")
        with open_browser(get_settings().discovery_profile_dir, headless=False) as browser:
            browser.page.goto("https://www.threads.com/", wait_until="domcontentloaded")
            browser.page.wait_for_function(
                """() => [...document.querySelectorAll('a[href^="/@"]')].some(a =>
                /profile/i.test(a.getAttribute('aria-label')||'') || a.querySelector('[aria-label="Profile"]'))""",
                timeout=900000,
            )
            print(
                "Dedicated Threads session is ready. Browser discovery still requires PostgreSQL and operator resume."
            )
    elif args.command == "discovery-init":
        if engine.dialect.name != "postgresql":
            raise SystemExit("Discovery requires PostgreSQL and migration-owner checkpoint setup first.")
        from .discovery import seed_frontier, settings_row

        with SessionLocal() as db:
            settings_row(db)
            seed_frontier(db)
            db.commit()
        print("Discovery initialized in paused state; no recurring publication is enabled.")
    elif args.command == "demo":
        if get_settings().app_mode != "demo":
            raise SystemExit("Never seed demo data into pilot mode.")
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            print(seed_demo(db))
    elif args.command == "member":
        if not args.user_id:
            parser.error("--user-id is required")
        with SessionLocal() as db:
            member = db.get(AppUser, args.user_id)
            if member:
                member.role = args.role
            else:
                db.add(AppUser(id=args.user_id, role=args.role))
            db.commit()
        print("Membership recorded; this does not create or email an Auth user.")
    else:
        from .api import app

        schema = json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.write_text(schema, encoding="utf-8", newline="\n")
        else:
            print(schema, end="")


if __name__ == "__main__":
    main()
