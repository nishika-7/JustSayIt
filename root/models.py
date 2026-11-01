from typing import Literal
from pydantic import BaseModel, Field


class Hunk(BaseModel):
    id: str                  # "h1", "h2", ...
    file: str
    header: str              # function/class context from the @@ line
    added: list[str]
    removed: list[str]
    text: str                # full hunk text shown to the LLM


class Claim(BaseModel):
    id: str                  # "c1", "c2", ...
    text: str


class ClaimList(BaseModel):
    claims: list[Claim]


class Verdict(BaseModel):
    claim_id: str
    label: Literal["supported", "unsupported", "contradicted"]
    evidence_hunk_ids: list[str] = Field(default_factory=list)
    reason: str


class VerifierOutput(BaseModel):
    verdicts: list[Verdict]


class Result(BaseModel):
    claims: list[Claim]
    verdicts: list[Verdict]
    undeclared_hunk_ids: list[str]   # hunks no verdict points to
    warnings: list[str]              # sanity-check problems in the LLM output
    splitter_version: str = ""
    verifier_version: str = ""
