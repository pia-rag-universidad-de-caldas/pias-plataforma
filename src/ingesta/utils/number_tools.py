"""Number tools."""

import statistics
from collections.abc import Sequence

from ingesta.models import NumericSummary


def numeric_summary(values: Sequence[float]) -> NumericSummary:
    """Inclusive quartiles and 90th percentile; whiskers and outliers with the 1.5×IQR rule. Needs at least one
    value."""
    v = sorted(values)
    if len(v) > 1:
        cuts = statistics.quantiles(v, n=20, method="inclusive")  # every 5 %
        q1, median, q3, p90 = cuts[4], cuts[9], cuts[14], cuts[17]
    else:
        q1 = median = q3 = p90 = float(v[0])
    lower, upper = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
    return NumericSummary(
        casos=len(v),
        total=sum(v),
        min=v[0],
        q1=q1,
        mediana=median,
        media=statistics.fmean(v),
        q3=q3,
        p90=p90,
        max=v[-1],
        desviacion=statistics.pstdev(v),
        bigote_inf=min(x for x in v if x >= lower),
        bigote_sup=max(x for x in v if x <= upper),
        atipicos=sum(1 for x in v if not lower <= x <= upper),
    )
