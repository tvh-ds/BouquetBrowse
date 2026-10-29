"""Recurring publication stays closed until installed, audited pilot proofs exist."""


def publication_ready(db, configuration):
    from .pilot import readiness

    return readiness(db, configuration)["ready"]
