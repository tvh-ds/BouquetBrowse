"""Private release-review operations. No endpoint invokes a model or collects pages."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import User, require_admin
from .db import get_db
from .pilot import approve_proof, readiness, stage_proof
from .pilot_models import PilotProof
from .schemas import StrictModel

router = APIRouter(prefix="/v1/admin/pilot", dependencies=[Depends(require_admin)])
Database = Annotated[Session, Depends(get_db)]


class ProofBody(StrictModel):
    kind: Literal["conversation", "recognition"]
    dataset_kind: Literal["synthetic", "permitted_real"] = "synthetic"
    values: list[dict] = Field(max_length=500)


class ApprovalBody(StrictModel):
    expected_report_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    permission_reference: str = Field(min_length=1, max_length=160)
    joint_review_confirmed: bool


@router.get("/readiness")
def get_readiness(db: Database):
    return readiness(db)


@router.get("/proofs")
def proofs(db: Database):
    return {
        "items": [
            {
                "id": p.id,
                "kind": p.kind,
                "state": p.state,
                "report_hash": p.report_hash,
                "configuration_hash": p.configuration_hash,
                "report": p.report,
            }
            for p in db.scalars(select(PilotProof).order_by(PilotProof.created_at.desc()).limit(50))
        ]
    }


@router.post("/proofs")
def stage(body: ProofBody, db: Database):
    try:
        proof = stage_proof(db, body.kind, body.values, None, body.dataset_kind)
        db.commit()
        return {"id": proof.id, "report_hash": proof.report_hash, "report": proof.report, "state": proof.state}
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc


@router.post("/proofs/{proof_id}/approve")
def approve(proof_id: str, body: ApprovalBody, db: Database, user: Annotated[User, Depends(require_admin)]):
    try:
        proof = approve_proof(
            db, proof_id, body.expected_report_hash, user.id, body.permission_reference, body.joint_review_confirmed
        )
        db.commit()
        return {"id": proof.id, "state": proof.state}
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc)) from exc


@router.post("/proofs/{proof_id}/revoke")
def revoke(proof_id: str, body: ApprovalBody, db: Database, user: Annotated[User, Depends(require_admin)]):
    proof = db.scalar(select(PilotProof).where(PilotProof.id == proof_id).with_for_update())
    if not proof or proof.report_hash != body.expected_report_hash:
        raise HTTPException(409, detail="Proof changed or does not exist")
    proof.state, proof.actor = "revoked", user.id
    db.commit()
    return {"id": proof.id, "state": proof.state}
