from typing import Annotated, Literal

from pydantic import Field, model_validator

from .offer_contracts import OfferInterpretation
from .schemas import StrictModel

Unit = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class RegionBounds(StrictModel):
    left: Unit
    top: Unit
    right: Unit
    bottom: Unit

    @model_validator(mode="after")
    def ordered(self):
        if self.left >= self.right or self.top >= self.bottom:
            raise ValueError("Region bounds must have positive area")
        if (self.right - self.left) * (self.bottom - self.top) < 0.002:
            raise ValueError("Region is too small for reliable analysis")
        return self

    def coordinates(self):
        return [self.left, self.top, self.right, self.bottom]


class FlowerVisual(StrictModel):
    flower: str = Field(min_length=1, max_length=80)
    state: Literal["present", "tentative", "alternative"]
    view_ids: list[str] = Field(min_length=1, max_length=12)
    alternatives: list[str] = Field(default_factory=list, max_length=6)


class RegionProposal(StrictModel):
    media_id: str
    bounds: RegionBounds
    reason: Literal["small_fillers", "occlusion", "conflict", "multi_product"]
    alternatives: list[str] = Field(default_factory=list, max_length=6)


class RecognitionResult(StrictModel):
    interpretation: OfferInterpretation | None
    flowers: list[FlowerVisual] = Field(default_factory=list, max_length=24)
    regions: list[RegionProposal] = Field(default_factory=list, max_length=8)
    arrangement: Literal["bouquet", "basket", "box", "vase"] | None
    colors: list[Literal["pink", "white", "yellow", "red", "purple", "orange", "green"]] = Field(
        default_factory=list, max_length=7
    )
    multi_product: bool
    warnings: list[str] = Field(default_factory=list, max_length=10)
