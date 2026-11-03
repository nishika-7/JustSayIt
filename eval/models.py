from typing import Literal

from pydantic import BaseModel, Field


class GoldClaim(BaseModel):
    text: str
    hunk_ids: list[str]


class GoldClaims(BaseModel):
    claims: list[GoldClaim]


class Case(BaseModel):
    id: str
    commit: str                      # file stem of the diff in data/commits/
    split: Literal["dev", "holdout"]
    kind: Literal["clean", "omission", "false_claim", "contradiction", "comment_trap", "partial_claim"]
    narration: str
    gold_undeclared: list[str] = Field(default_factory=list)
    diff_file: str = ""   # set when the case uses a modified copy of the diff (path under the data folder)
