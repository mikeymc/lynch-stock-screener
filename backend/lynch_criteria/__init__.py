# ABOUTME: Package entry point composing LynchCriteria from mixin classes.
# ABOUTME: Re-exports the composed class plus scoring constants.

from lynch_criteria.core import LynchCriteriaCore, ALGORITHM_METADATA, SCORE_THRESHOLDS
from lynch_criteria.scoring import ScoringMixin
from lynch_criteria.batch import BatchScoringMixin


class LynchCriteria(LynchCriteriaCore, ScoringMixin, BatchScoringMixin):
    pass
