from typing import Optional
import config
from core.models import ConfirmationEvent, FVG


def compute_confidence(
    mss: Optional[ConfirmationEvent],
    bos: Optional[ConfirmationEvent],
    displacement: Optional[ConfirmationEvent],
    fvg: Optional[FVG],
    h1_ema_aligned: bool = False,
) -> int:
    """
    ICT confidence scoring:
        Base            : 50  (signal passed all hard gates)
        H1 EMA200 aligned : +10  (H4 structure and H1 EMA200 agree)
        MSS confirmed   : +15
        BOS confirmed   : +10
        Displacement    : +10
        FVG present     : +10
        Max cap: CONFIDENCE_CAP (95)

    Without H1 alignment, a signal needs 2+ confirmations to reach 80.
    With H1 alignment, 1 confirmation is enough.
    """
    score = config.CONFIDENCE_BASE

    if h1_ema_aligned:
        score += 10

    if mss is not None:
        score += 15

    if bos is not None:
        score += 10

    if displacement is not None:
        score += 10

    if fvg is not None:
        score += 10

    return min(score, config.CONFIDENCE_CAP)
