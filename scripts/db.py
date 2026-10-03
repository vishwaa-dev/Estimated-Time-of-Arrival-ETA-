"""Quick viewer for the RailCast AI SQLite database (no installs needed).

Usage (from anywhere):
    python scripts/db.py                 -> overview: tables + row counts
    python scripts/db.py trains          -> all trains with latest known delay
    python scripts/db.py predictions     -> latest prediction per train
    python scripts/db.py events          -> most recent 20 events
    python scripts/db.py sql "SELECT ..."-> run any read-only query

The file it reads: backend/railcast.db (override: python scripts/db.py <cmd> --db path).
Safe to run while the app is running (read-only access).
"""
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / "backend" / "railcast.db"


def connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        sys.exit(f"Database not found: {db_path}\nStart the app once to create it.")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)  # read-only
    conn.row_factory = sqlite3.Row
    return conn


def show_overview(conn: sqlite3.Connection) -> None:
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )]
    print(f"Tables in {DEFAULT_DB.name}:\n")
    for t in tables:
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:24} {n:>6} rows")


def show_trains(conn: sqlite3.Connection) -> None:
    rows = conn.execute("""
        SELECT tr.train_number, tr.train_name, tr.live_enabled, tr.status,
               s.current_station_name AS location, s.current_delay_minutes AS delay,
               s.timestamp AS updated
        FROM trains tr
        LEFT JOIN train_state_snapshots s ON s.id = (
            SELECT MAX(id) FROM train_state_snapshots WHERE train_id = tr.id)
        ORDER BY tr.train_number
    """)
    print(f"{'Number':7} {'Name':34} {'Live':5} {'Status':12} {'Delay':7} {'Location'}")
    for r in rows:
        live = "ON" if r["live_enabled"] else "off"
        delay = "on time" if not r["delay"] else f"+{r['delay']:.0f} min"
        print(f"{r['train_number']:7} {(r['train_name'] or '')[:34]:34} {live:5} {r['status'] or '?':12} {delay:7} {r['location'] or '-'}")


def show_predictions(conn: sqlite3.Connection) -> None:
    rows = conn.execute("""
        SELECT tr.train_number, p.timestamp, p.current_delay, p.predicted_additional_delay,
               p.recovery_minutes, p.final_predicted_delay, p.confidence, p.prediction_mode
        FROM prediction_snapshots p JOIN trains tr ON tr.id = p.train_id
        WHERE p.id = (SELECT MAX(id) FROM prediction_snapshots WHERE train_id = p.train_id)
        ORDER BY tr.train_number
    """)
    print(f"{'Number':7} {'Current':8} {'Addl':6} {'Recovery':9} {'Final':6} {'Conf':5} Method")
    for r in rows:
        f = lambda v, w=6: f"{v:>{w}.1f}" if v is not None else "  -   "
        print(f"{r['train_number']:7} {f(r['current_delay'],8)} {f(r['predicted_additional_delay'])} "
              f"{f(r['recovery_minutes'],9)} {f(r['final_predicted_delay'])} {r['confidence'] or 0:4.0f}% {r['prediction_mode']}")


def show_events(conn: sqlite3.Connection) -> None:
    rows = conn.execute("""
        SELECT e.timestamp, tr.train_number, e.event_type, e.message
        FROM event_log e JOIN trains tr ON tr.id = e.train_id
        ORDER BY e.timestamp DESC LIMIT 20
    """)
    for r in rows:
        sim = " [SIM]" if conn.execute("SELECT is_simulated FROM event_log WHERE timestamp=? AND train_id=?",
                                       (r["timestamp"], r["train_number"])).fetchone()[0] else ""
        print(f"{r['timestamp'][:19]}  {r['train_number']:6} {r['event_type']:11} {r['message'][:80]}{sim}")


def run_sql(conn: sqlite3.Connection, query: str) -> None:
    q = query.strip().lstrip(";").lower()
    if not q.startswith("select"):
        sys.exit("Only SELECT queries are allowed (read-only viewer).")
    cur = conn.execute(query)
    cols = [d[0] for d in cur.description]
    print(" | ".join(cols))
    print("-" * len(" | ".join(cols)))
    for row in cur.fetchall()[:100]:
        print(" | ".join(str(v) for v in row))


if __name__ == "__main__":
    args = sys.argv[1:]
    db_path = DEFAULT_DB
    if "--db" in args:
        i = args.index("--db")
        db_path = Path(args[i + 1])
        args = args[:i] + args[i + 2:]
    cmd = args[0] if args else "overview"
    conn = connect(db_path)
    try:
        if cmd == "overview":
            show_overview(conn)
        elif cmd == "trains":
            show_trains(conn)
        elif cmd == "predictions":
            show_predictions(conn)
        elif cmd == "events":
            show_events(conn)
        elif cmd == "sql":
            if len(args) < 2:
                sys.exit('Provide a query: python scripts/db.py sql "SELECT ..."')
            run_sql(conn, args[1])
        else:
            print(__doc__)
    finally:
        conn.close()
