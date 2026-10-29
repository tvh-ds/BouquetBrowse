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
        "command",
        choices=[
            "demo",
            "member",
            "openapi",
            "discovery-init",
            "browser-login",
            "evaluate-images",
            "pilot-status",
            "pilot-stage",
            "operations-ready",
            "deletion-export",
            "deletion-replay",
            "backup-media",
            "evaluation-export",
            "evaluation-run",
            "evaluation-status",
        ],
    )
    parser.add_argument("--user-id")
    parser.add_argument("--dataset-id")
    parser.add_argument("--expected-version", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--configuration-hash")
    parser.add_argument("--dataset-kind", choices=["synthetic", "permitted_real"], default="synthetic")
    parser.add_argument("--proof-kind", choices=["conversation", "recognition"])
    parser.add_argument("--role", choices=["tester", "reviewer", "admin"], default="tester")
    args = parser.parse_args()
    if args.command in {"evaluation-export", "evaluation-run", "evaluation-status"}:
        from sqlalchemy import select

        from .db import aware, utcnow
        from .evaluation import export_dataset, queue_dataset
        from .research_models import EvaluationDataset, EvaluationItem

        if not args.dataset_id:
            parser.error("--dataset-id is required")
        with SessionLocal() as db:
            dataset = db.get(EvaluationDataset, args.dataset_id)
            if not dataset or aware(dataset.retention_until) <= utcnow():
                parser.error("Evaluation is missing or expired")
            if args.command == "evaluation-export":
                path = export_dataset(db, dataset)
                db.commit()
                print(str(path))
            elif args.command == "evaluation-run":
                if args.expected_version != dataset.version:
                    parser.error("Inspect the dataset and pass its --expected-version")
                ids = queue_dataset(db, dataset)
                db.commit()
                print(json.dumps({"execution_ids": ids, "evaluation_only": True}))
            else:
                print(
                    json.dumps(
                        {
                            "id": dataset.id,
                            "version": dataset.version,
                            "items": [
                                {
                                    "id": item.id,
                                    "state": item.state,
                                    "cost_microusd": item.cost_microusd,
                                    "latency_ms": item.latency_ms,
                                }
                                for item in db.scalars(
                                    select(EvaluationItem).where(EvaluationItem.dataset_id == dataset.id)
                                )
                            ],
                        }
                    )
                )
    elif args.command == "operations-ready":
        from .discovery import settings_row
        from .local_schedule import collection_ready

        with SessionLocal() as db:
            print(
                json.dumps(
                    {
                        "ready": collection_ready(db, get_settings(), settings_row(db)),
                        "note": "No browsing or model call was made.",
                    }
                )
            )
    elif args.command in {"deletion-export", "deletion-replay", "backup-media"}:
        from .recovery import export_deletions, replay_deletions

        with SessionLocal() as db:
            if args.command == "deletion-export":
                if args.output:
                    print(f"Exported {export_deletions(db, args.output)} content-free deletion records.")
                else:
                    from sqlalchemy import select

                    from .operations_models import DeletionRecord

                    for record in db.scalars(select(DeletionRecord)):
                        print(
                            json.dumps(
                                {
                                    "subject_kind": record.subject_kind,
                                    "subject_id": record.subject_id,
                                    "reason": record.reason,
                                }
                            )
                        )
            elif args.command == "deletion-replay":
                if not args.input or args.input.stat().st_size > 20 * 1024 * 1024:
                    parser.error("Provide a content-free deletion ledger smaller than 20 MB")
                values = [
                    json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()
                ]
                count = replay_deletions(db, values)
                db.commit()
                print(
                    f"Replayed {count} deletion records. Drain delete-media/checkpoint jobs before serving a restored database."
                )
            else:
                import io
                import sys
                import tarfile

                from sqlalchemy import select

                from .db import utcnow
                from .models import MediaAsset
                from .storage import get_media_bytes, validate_key

                keys = list(
                    db.scalars(
                        select(MediaAsset.storage_key)
                        .where(
                            MediaAsset.state == "ready",
                            MediaAsset.storage_key.is_not(None),
                            MediaAsset.retention_until > utcnow(),
                        )
                        .distinct()
                    )
                )
                db.commit()
                with tarfile.open(fileobj=sys.stdout.buffer, mode="w|") as archive:
                    for key in keys:
                        content = get_media_bytes(validate_key(key))
                        entry = tarfile.TarInfo(key)
                        entry.size, entry.mode = len(content), 0o600
                        archive.addfile(entry, io.BytesIO(content))
    elif args.command in {"pilot-status", "pilot-stage"}:
        from .pilot import readiness, stage_proof

        with SessionLocal() as db:
            if args.command == "pilot-stage":
                if not args.input or not args.proof_kind:
                    parser.error("--input and --proof-kind are required")
                if args.input.stat().st_size > 10 * 1024 * 1024:
                    parser.error("Evaluation input exceeds 10 MB")
                values = [
                    json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()
                ]
                proof = stage_proof(db, args.proof_kind, values, None, args.dataset_kind)
                db.commit()
                print(
                    json.dumps(
                        {"id": proof.id, "report_hash": proof.report_hash, "report": proof.report},
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                print(json.dumps(readiness(db), ensure_ascii=False, indent=2))
    elif args.command == "evaluate-images":
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
