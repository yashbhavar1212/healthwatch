"""Risk engine.

A report is scored by adding points for each factor. The total decides the
risk level. The rules are deliberately simple so they can be explained to
health workers and checked against surveillance guidance.

    Factor                      Points
    --------------------------  ------------------------------------------
    Diarrhea cases              <5 : 0   | 5-10 : 2   | 11-25 : 3 | >25 : 4
    Fever cases                 <15: 0   | 15-40: 1   | >40 : 2
    Rainfall                    Low 0    | Medium 1   | High 2
    Drinking water quality      Good 0   | Doubtful 1 | Contaminated 2
    Rising trend (bonus)        +1 if diarrhea is >= 1.5x the previous report
                                (and at least 5 cases)

    Score 0-2 Low | 3-4 Moderate | 5-6 High | 7+ Critical

The original project rule "diarrhea > 10 AND rainfall High = High Risk" is
still true here: that combination always scores at least 5.
"""

RAINFALL_POINTS = {"Low": 0, "Medium": 1, "High": 2}
WATER_POINTS = {"Good": 0, "Doubtful": 1, "Contaminated": 2}
LEVELS = ["Low", "Moderate", "High", "Critical"]
MAX_SCORE = 11  # 4 + 2 + 2 + 2 + 1

ADVICE = {
    "Low": "Keep routine surveillance and continue daily reporting.",
    "Moderate": "Increase monitoring. Check the village water source and remind families to boil or chlorinate drinking water.",
    "High": "Alert the PHC medical officer. Start water chlorination, keep ORS stock ready and visit affected households.",
    "Critical": "Possible outbreak. Notify the district health officer today, arrange water testing and set up an ORS and treatment point.",
}


def diarrhea_points(cases: int) -> int:
    if cases < 5:
        return 0
    if cases <= 10:
        return 2
    if cases <= 25:
        return 3
    return 4


def fever_points(cases: int) -> int:
    if cases < 15:
        return 0
    if cases <= 40:
        return 1
    return 2


def level_for(score: int) -> str:
    if score <= 2:
        return "Low"
    if score <= 4:
        return "Moderate"
    if score <= 6:
        return "High"
    return "Critical"


def is_rising(diarrhea: int, previous_diarrhea) -> bool:
    if previous_diarrhea is None or diarrhea < 5:
        return False
    if previous_diarrhea == 0:
        return True
    return diarrhea >= previous_diarrhea * 1.5


def assess(diarrhea: int, fever: int, rainfall: str, water_quality: str = "Good",
           previous_diarrhea=None) -> dict:
    """Return score, level, per-factor breakdown and advice for one report."""
    breakdown = {
        "diarrhea": diarrhea_points(diarrhea),
        "fever": fever_points(fever),
        "rainfall": RAINFALL_POINTS[rainfall],
        "water": WATER_POINTS[water_quality],
        "trend": 0,
    }
    rising = is_rising(diarrhea, previous_diarrhea)
    if rising:
        breakdown["trend"] = 1
    score = sum(breakdown.values())
    level = level_for(score)
    return {
        "score": score,
        "max_score": MAX_SCORE,
        "level": level,
        "rising": rising,
        "breakdown": breakdown,
        "advice": ADVICE[level],
    }
