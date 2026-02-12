from datetime import date
from typing import Optional


def current_season(today: Optional[date] = None) -> str:
    """Return current season name: spring, summer, fall, winter.

    Seasons are determined by northern hemisphere approximate dates:
      - Spring: Mar 20 - Jun 20
      - Summer: Jun 21 - Sep 21
      - Fall: Sep 22 - Dec 20
      - Winter: Dec 21 - Mar 19
    """
    if today is None:
        today = date.today()

    y = today.year
    # Define season start dates
    spring_start = date(y, 3, 20)
    summer_start = date(y, 6, 21)
    fall_start = date(y, 9, 22)
    winter_start = date(y, 12, 21)

    if spring_start <= today < summer_start:
        return "spring"
    if summer_start <= today < fall_start:
        return "summer"
    if fall_start <= today < winter_start:
        return "fall"
    # winter spans year boundary
    return "winter"
