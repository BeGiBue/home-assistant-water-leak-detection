"""Human duration display; seconds remain the automation sensor's numeric state."""

from math import isfinite


def human_duration(seconds: float, language: str = "en") -> str:
    if not isfinite(seconds) or seconds < 0:
        seconds = 0
    seconds = int(seconds)
    de = language.split("-")[0] == "de"
    names = (
        [("Sekunde", "Sekunden"), ("Minute", "Minuten"), ("Stunde", "Stunden"), ("Tag", "Tage")]
        if de
        else [("second", "seconds"), ("minute", "minutes"), ("hour", "hours"), ("day", "days")]
    )
    if seconds < 60:
        parts = [(seconds, 0)]
    elif seconds < 3600:
        parts = [(seconds // 60, 1)]
    elif seconds < 86400:
        parts = [(seconds // 3600, 2), (seconds % 3600 // 60, 1)]
    else:
        parts = [(seconds // 86400, 3), (seconds % 86400 // 3600, 2)]
    return " ".join(
        f"{value} {names[unit][0 if value == 1 else 1]}"
        for value, unit in parts
        if value or seconds == 0
    )
