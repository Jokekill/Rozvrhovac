"""Defaults that must exist in every database: cycle, days, periods, weights."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ConstraintWeight, CycleConfig, Day, Period
from app.models.enums import (
    WEIGHT_CRITICAL,
    WEIGHT_HIGH,
    WEIGHT_LOW,
    WEIGHT_MEDIUM,
    WEIGHT_VERY_LOW,
)

CZECH_DAY_NAMES = ["Pondělí", "Úterý", "Středa", "Čtvrtek", "Pátek", "Sobota", "Neděle"]

# The zeroth hour is a real slot in the grid, just one the solver is told to
# use sparingly (SC18). It ends five minutes before the first hour starts.
DEFAULT_PERIODS = [
    ("0. hodina", 7 * 60 + 10, 7 * 60 + 55),
    ("1. hodina", 8 * 60, 8 * 60 + 45),
    ("2. hodina", 8 * 60 + 55, 9 * 60 + 40),
    ("3. hodina", 9 * 60 + 50, 10 * 60 + 35),
    ("4. hodina", 10 * 60 + 55, 11 * 60 + 40),
    ("5. hodina", 11 * 60 + 50, 12 * 60 + 35),
    ("6. hodina", 12 * 60 + 45, 13 * 60 + 30),
    ("7. hodina", 13 * 60 + 40, 14 * 60 + 25),
    ("8. hodina", 14 * 60 + 35, 15 * 60 + 20),
]

# code, name, default weight, description
CONSTRAINT_CATALOGUE: list[tuple[str, str, int, str]] = [
    ("SC01", "Minimalizovat okna učitelů", WEIGHT_MEDIUM,
     "Penalizuje volné minuty mezi první a poslední hodinou učitele v daném dni."),
    ("SC02", "Minimalizovat okna studentů", WEIGHT_MEDIUM,
     "Penalizuje volné minuty mezi první a poslední hodinou studenta v daném dni."),
    ("SC03", "Preferované časy učitele", WEIGHT_LOW,
     "Penalizuje výskyt mimo okno označené jako PREFERRED u učitele."),
    ("SC04", "Preferované časy studentů", WEIGHT_LOW,
     "Penalizuje výskyt mimo okno označené jako PREFERRED u studenta."),
    ("SC05", "Preferovaná učebna", WEIGHT_LOW,
     "Penalizuje umístění do jiné než preferované učebny."),
    ("SC06", "Minimalizovat změny učeben učitele", WEIGHT_VERY_LOW,
     "Penalizuje každou další učebnu, kterou učitel během dne použije."),
    ("SC07", "Rovnoměrné rozložení předmětu", WEIGHT_LOW,
     "Penalizuje dva výskyty téže aktivity v sousedních dnech."),
    ("SC08", "Ne vícekrát denně", WEIGHT_HIGH,
     "Penalizuje druhý a další výskyt téže aktivity ve stejném dni."),
    ("SC09", "Příliš mnoho hodin studentovi za den", WEIGHT_LOW,
     "Penalizuje minuty nad denní limit studenta."),
    ("SC10", "Příliš mnoho hodin učiteli za den", WEIGHT_LOW,
     "Penalizuje minuty nad max_minutes_per_day a rozpětí nad max_consecutive_minutes."),
    ("SC11", "Přestávka na oběd", WEIGHT_MEDIUM,
     "Penalizuje studenta, který nemá v obědovém okně volný blok."),
    ("SC12", "Individuální výuka v preferovaných blocích", WEIGHT_LOW,
     "Penalizuje individuální lekci mimo preferované okno (typicky odpoledne)."),
    ("SC13", "Velmi brzy nebo velmi pozdě", WEIGHT_LOW,
     "Penalizuje výuku před early_threshold nebo končící po late_threshold."),
    ("SC14", "Přesuny mezi budovami", WEIGHT_LOW,
     "Penalizuje každou další budovu, do které se osoba musí během dne přesunout."),
    ("SC15", "Minimalizovat změny proti výchozímu rozvrhu", WEIGHT_MEDIUM,
     "Při reoptimalizaci penalizuje každou změnu času nebo učebny proti výchozí verzi."),
    ("SC16", "Minimální počet hodin za den", WEIGHT_CRITICAL,
     "Penalizuje každou chybějící hodinu pod min_student_lessons_per_day v den, "
     "kdy student do školy vůbec jde. Den bez výuky se nepenalizuje."),
    ("SC17", "Jádro dne – první hodiny povinně", WEIGHT_CRITICAL,
     "Penalizuje každou z prvních core_block_periods hodin, ve které student nemá "
     "výuku. Platí pro každý vyučovací den a vynucuje společný dopolední blok."),
    ("SC18", "Nultá hodina jen výjimečně", WEIGHT_MEDIUM,
     "Penalizuje každý výskyt, který začíná před core_day_start_minute, aby se "
     "nultá hodina používala méně než zbytek mřížky."),
]


def ensure_cycle(db: Session, days: int = 5, weeks: int = 1) -> CycleConfig:
    config = db.get(CycleConfig, 1)
    if config is None:
        config = CycleConfig(id=1)
        db.add(config)
        db.flush()
    if weeks != config.weeks_in_cycle:
        config.weeks_in_cycle = weeks
    existing = db.execute(select(Day)).scalars().all()
    if not existing:
        ordinal = 0
        for week in range(weeks):
            for weekday in range(days):
                suffix = f" ({'AB'[week]})" if weeks > 1 else ""
                db.add(
                    Day(
                        ordinal=ordinal,
                        week_index=week,
                        weekday=weekday,
                        name=CZECH_DAY_NAMES[weekday % 7] + suffix,
                        start_minute=DEFAULT_PERIODS[0][1],
                        end_minute=19 * 60,
                    )
                )
                ordinal += 1
    if not db.execute(select(Period)).scalars().first():
        for index, (name, start, end) in enumerate(DEFAULT_PERIODS):
            db.add(Period(index=index, name=name, start_minute=start, end_minute=end))
    db.flush()
    return config


def ensure_constraint_weights(db: Session) -> list[ConstraintWeight]:
    existing = {c.code: c for c in db.execute(select(ConstraintWeight)).scalars()}
    created: list[ConstraintWeight] = []
    for code, name, weight, description in CONSTRAINT_CATALOGUE:
        if code in existing:
            continue
        row = ConstraintWeight(
            code=code, name=name, weight=weight, description=description, type="SOFT"
        )
        db.add(row)
        created.append(row)
    db.flush()
    return created


def bootstrap(db: Session) -> None:
    ensure_cycle(db)
    ensure_constraint_weights(db)
    db.commit()
