import argparse
import json
from pathlib import Path

from .config import get_settings
from .db import Base, SessionLocal, engine
from .models import AppUser
from .seed import seed_demo


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["demo", "member", "openapi"])
    parser.add_argument("--user-id")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--role", choices=["tester", "reviewer", "admin"], default="tester")
    args = parser.parse_args()
    if args.command == "demo":
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
