# School Timetable Optimizer

Open-source webová aplikace pro automatickou tvorbu školních rozvrhů.
Není to nástroj jen pro klasickou ZŠ/SŠ – od základu je navržená pro školu
s rozsáhlou uměleckou výukou, kde vedle běžných tříd běží individuální
hodiny 1 : 1, sbor, orchestr a dramatické skupiny složené ze studentů
z různých tříd a ročníků.

**Klíčové rozhodnutí:** plánovacím zdrojem je *student*, ne třída.
Pokud je Adam členem Kvinty, skupiny Informatika B, Drama středa i Sboru,
solver mu nikdy nenaplánuje dvě z těchto aktivit současně.

---

## Co systém umí

* klasické třídy, dělené skupiny, skupiny napříč ročníky, individuální výuku,
* specializované učebny s vlastnostmi (`piano`, `stage`, `computers`, …),
* různé délky bloků (30 / 45 / 60 / 90 minut) i mimo klasickou mřížku hodin,
* omezení dostupnosti studentů, učitelů i učeben,
* pevně zadané hodiny, preferované časy, paralelní výuku,
* ruční drag & drop editaci s okamžitou kontrolou konfliktů,
* uzamčení části rozvrhu (zvlášť čas, zvlášť učebnu) a reoptimalizaci zbytku,
* verzování rozvrhu, porovnání verzí a publikaci,
* import CSV/XLSX a export CSV/XLSX/PDF/ICS.

## Architektura

```text
React + TypeScript  ──REST──▶  FastAPI  ──▶  PostgreSQL
                                  │
                                  └──▶ Redis + RQ ──▶ Solver worker (OR-Tools CP-SAT)
```

Optimalizace není vlastní heuristika: model je postavený nad
`ortools.sat.python.cp_model` (intervalové proměnné, `AddNoOverlap`,
optional intervals pro učebny).

Podrobný datový model, ER diagram, solver model a seznam constraintů:
[`docs/architecture.md`](docs/architecture.md).

## Rychlý start (Docker)

```bash
docker compose up --build
```

* API + OpenAPI dokumentace: <http://localhost:8000/docs>
* Frontend: <http://localhost:5173>

Kontejner `api` při startu spustí migrace a (při `SEED_DEMO=true`) naplní
DEMO dataset: 3 třídy, 60 studentů, 12 učitelů, 10 učeben, 15 individuálních
hudebních lekcí, 2 dramatické skupiny napříč třídami, sbor a půlenou informatiku.

## Vývoj bez Dockeru

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt

cd backend
export DATABASE_URL="sqlite:///./dev.db"   # nebo PostgreSQL
export RUN_SOLVER_INLINE=true              # solver bez Redis
alembic upgrade head
python manage.py seed-demo
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Testy

```bash
cd backend
pytest -q
```

Sada obsahuje povinné testy solveru podle zadání: konflikt studenta,
konflikt učitele, konflikt učebny, smíšené skupiny, vlastnosti učebny,
dostupnost učitele, pevná hodina, uzamčená hodina, paralelní hodiny
a korektní hlášení neřešitelného zadání.

## Stav implementace

| Fáze | Obsah | Stav |
| ---- | ----- | ---- |
| 1 | Doménový model, migrace, CRUD API, seed, testy | hotovo |
| 2 | Minimální CP-SAT solver (hard constraints) | hotovo |
| 3 | Webové zobrazení rozvrhu | hotovo |
| 4 | Soft constraints a skórování | hotovo |
| 5 | Ruční editace, lock, reoptimalizace | hotovo |
| 6 | Import/export | hotovo |
| 7 | Pokročilé constraints | hotovo |
| 8 | Autentizace OIDC / Entra ID | připravené rozhraní |

## GDPR

Systém ukládá pouze jméno, příjmení, externí ID, třídu a členství ve
skupinách. Datum narození, adresa ani telefon v datovém modelu neexistují.

## Licence

MIT – viz [`LICENSE`](LICENSE).
