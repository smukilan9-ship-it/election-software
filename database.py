import sqlite3

DB_PATH = "election.db"

def connect_db():
    return sqlite3.connect(DB_PATH)

def init_db():
    con = connect_db()
    cursor = con.cursor()
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS elections (
            election_id INTEGER PRIMARY KEY AUTOINCREMENT,
            e_name      TEXT NOT NULL,
            description TEXT,
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS candidates (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            id_no       TEXT UNIQUE NOT NULL,
            name        TEXT NOT NULL,
            role        TEXT NOT NULL,
            kutumba     TEXT,
            election_id INTEGER,
            FOREIGN KEY (election_id) REFERENCES elections(election_id)
        );

        CREATE TABLE IF NOT EXISTS students (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            id_no   TEXT UNIQUE NOT NULL,
            kutumba TEXT
        );

        CREATE TABLE IF NOT EXISTS election_students (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            election_id INTEGER NOT NULL,
            student_id  INTEGER NOT NULL,
            UNIQUE(election_id, student_id),
            FOREIGN KEY (election_id) REFERENCES elections(election_id),
            FOREIGN KEY (student_id)  REFERENCES students(id)
        );

        CREATE TABLE IF NOT EXISTS votes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id   INTEGER,
            candidate_id INTEGER,
            election_id  INTEGER,
            FOREIGN KEY (student_id)   REFERENCES students(id),
            FOREIGN KEY (candidate_id) REFERENCES candidates(id),
            FOREIGN KEY (election_id)  REFERENCES elections(election_id)
        );
    """)
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_votes_student_election_candidate ON votes(student_id, election_id, candidate_id)"
    )
    con.commit()

    cursor.execute("PRAGMA table_info(students)")
    columns = [row[1] for row in cursor.fetchall()]
    if "name" in columns:
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS students_new (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                id_no   TEXT UNIQUE NOT NULL,
                kutumba TEXT
            );
            INSERT OR IGNORE INTO students_new (id, id_no, kutumba)
                SELECT id, id_no, kutumba FROM students;
            DROP TABLE students;
            ALTER TABLE students_new RENAME TO students;
        """)
        con.commit()

    con.close()

def step1_add(title, description):
    con = connect_db()
    cursor = con.cursor()
    cursor.execute("INSERT INTO elections (e_name, description) VALUES (?, ?)", (title, description))
    election_id = cursor.lastrowid
    con.commit()
    con.close()
    return election_id

def step2_add_many(election_id, candidate_rows):
    con = connect_db()
    cursor = con.cursor()
    rows = [(id_no, name, kutumba, role, election_id) for name, id_no, kutumba, role in candidate_rows]
    cursor.executemany(
        "INSERT INTO candidates (id_no, name, kutumba, role, election_id) VALUES (?, ?, ?, ?, ?)",
        rows
    )
    con.commit()
    con.close()

def list_elections():
    con = connect_db()
    cursor = con.cursor()
    cursor.execute("SELECT election_id, e_name, description, created_at FROM elections ORDER BY election_id DESC")
    rows = cursor.fetchall()
    con.close()
    return [{"election_id": r[0], "e_name": r[1], "description": r[2], "created_at": r[3]} for r in rows]

def get_election(election_id):
    con = connect_db()
    cursor = con.cursor()
    cursor.execute("SELECT election_id, e_name, description, created_at FROM elections WHERE election_id = ?", (election_id,))
    row = cursor.fetchone()
    con.close()
    return {"election_id": row[0], "e_name": row[1], "description": row[2], "created_at": row[3]} if row else None

def get_counts():
    con = connect_db()
    cursor = con.cursor()
    cursor.execute("SELECT COUNT(*) FROM elections")
    elections = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM candidates")
    candidates = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(DISTINCT student_id) FROM election_students")
    students = cursor.fetchone()[0]
    con.close()
    return {"elections": elections, "candidates": candidates, "students": students}

def list_candidates(election_id):
    con = connect_db()
    cursor = con.cursor()
    cursor.execute(
        "SELECT id, id_no, name, role, kutumba FROM candidates WHERE election_id = ? ORDER BY role ASC, name ASC",
        (election_id,)
    )
    rows = cursor.fetchall()
    con.close()
    return [{"id": r[0], "id_no": r[1], "name": r[2], "role": r[3], "kutumba": r[4]} for r in rows]

def delete_candidate(candidate_id):
    con = connect_db()
    cursor = con.cursor()
    cursor.execute("DELETE FROM votes WHERE candidate_id = ?", (candidate_id,))
    cursor.execute("DELETE FROM candidates WHERE id = ?", (candidate_id,))
    con.commit()
    con.close()

def delete_election(election_id):
    con = connect_db()
    cursor = con.cursor()
    cursor.execute("DELETE FROM votes WHERE election_id = ?", (election_id,))
    cursor.execute("DELETE FROM candidates WHERE election_id = ?", (election_id,))
    cursor.execute("DELETE FROM election_students WHERE election_id = ?", (election_id,))
    cursor.execute("DELETE FROM elections WHERE election_id = ?", (election_id,))
    cursor.execute("DELETE FROM students WHERE id NOT IN (SELECT student_id FROM election_students)")
    con.commit()
    con.close()

def import_voters_for_election(election_id, voter_rows):
    con = connect_db()
    cursor = con.cursor()
    imported = 0
    skipped = 0

    valid_rows = []
    for row in voter_rows:
        id_no = str(row.get("id_no") or "").strip()
        kutumba = str(row.get("kutumba") or "").strip()
        if id_no:
            valid_rows.append((id_no, kutumba))
        else:
            skipped += 1

    for id_no, kutumba in valid_rows:
        cursor.execute(
            "INSERT INTO students (id_no, kutumba) VALUES (?, ?) ON CONFLICT(id_no) DO UPDATE SET kutumba=excluded.kutumba",
            (id_no, kutumba)
        )
        cursor.execute("SELECT id FROM students WHERE id_no = ?", (id_no,))
        student_id = cursor.fetchone()[0]
        cursor.execute(
            "SELECT id FROM election_students WHERE election_id = ? AND student_id = ?",
            (election_id, student_id)
        )
        if cursor.fetchone():
            skipped += 1
        else:
            cursor.execute(
                "INSERT INTO election_students (election_id, student_id) VALUES (?, ?)",
                (election_id, student_id)
            )
            imported += 1

    con.commit()
    con.close()
    return imported, skipped

def list_voters_for_election(election_id):
    con = connect_db()
    cursor = con.cursor()
    cursor.execute(
        """SELECT s.id, s.id_no, s.kutumba
           FROM students s
           JOIN election_students es ON es.student_id = s.id
           WHERE es.election_id = ?
           ORDER BY s.id_no ASC""",
        (election_id,)
    )
    rows = cursor.fetchall()
    con.close()
    return [{"id": r[0], "id_no": r[1], "kutumba": r[2]} for r in rows]

def remove_voter_from_election(election_id, student_id):
    con = connect_db()
    cursor = con.cursor()
    cursor.execute(
        "DELETE FROM election_students WHERE election_id = ? AND student_id = ?",
        (election_id, student_id)
    )
    cursor.execute("DELETE FROM students WHERE id NOT IN (SELECT student_id FROM election_students)")
    con.commit()
    con.close()

def student_login_for_election(id_no, election_id):
    con = connect_db()
    cursor = con.cursor()
    cursor.execute(
        """SELECT s.id, s.id_no, s.kutumba
           FROM students s
           JOIN election_students es ON es.student_id = s.id
           WHERE s.id_no = ? AND es.election_id = ?""",
        (id_no, election_id)
    )
    row = cursor.fetchone()
    con.close()
    return {"id": row[0], "id_no": row[1], "kutumba": row[2]} if row else None

def ballot_for_election(election_id, student_kutumba=None):
    con = connect_db()
    cursor = con.cursor()
    cursor.execute(
        "SELECT id, id_no, name, role, kutumba FROM candidates WHERE election_id = ? ORDER BY role ASC, name ASC",
        (election_id,)
    )
    rows = cursor.fetchall()
    con.close()
    ballot = {}
    for r in rows:
        cid, id_no, name, role, kutumba = r
        is_sports = "Sports Captain" in role
        if student_kutumba:
            if not is_sports and kutumba != student_kutumba:
                continue
        if role not in ballot:
            ballot[role] = []
        ballot[role].append({"id": cid, "id_no": id_no, "name": name, "role": role, "kutumba": kutumba})
    return ballot

def submit_vote(student_id, election_id, candidate_id):
    con = connect_db()
    cursor = con.cursor()
    cursor.execute("SELECT role, kutumba FROM candidates WHERE id = ? AND election_id = ?", (candidate_id, election_id))
    row = cursor.fetchone()
    if not row:
        con.close()
        return {"ok": False, "message": "Invalid candidate."}
    role, candidate_kutumba = row
    is_sports = "Sports Captain" in role
    if not is_sports:
        cursor.execute("SELECT kutumba FROM students WHERE id = ?", (student_id,))
        student_row = cursor.fetchone()
        student_kutumba = student_row[0] if student_row else None
        if student_kutumba != candidate_kutumba:
            con.close()
            return {"ok": False, "message": "You can only vote for candidates from your own kutumba."}
    cursor.execute(
        "SELECT v.id FROM votes v JOIN candidates c ON c.id = v.candidate_id WHERE v.student_id = ? AND v.election_id = ? AND c.role = ? LIMIT 1",
        (student_id, election_id, role)
    )
    if cursor.fetchone():
        con.close()
        return {"ok": False, "message": f"Already voted for: {role}."}
    cursor.execute(
        "INSERT INTO votes (student_id, candidate_id, election_id) VALUES (?, ?, ?)",
        (student_id, candidate_id, election_id)
    )
    con.commit()
    con.close()
    return {"ok": True, "message": "Vote submitted."}

def get_results_for_election(election_id):
    con = connect_db()
    cursor = con.cursor()
    cursor.execute(
        """SELECT c.role, c.name, c.kutumba, COUNT(v.id) as vote_count
           FROM candidates c
           LEFT JOIN votes v ON v.candidate_id = c.id AND v.election_id = c.election_id
           WHERE c.election_id = ?
           GROUP BY c.id
           ORDER BY c.role ASC, vote_count DESC""",
        (election_id,)
    )
    rows = cursor.fetchall()
    cursor.execute(
        "SELECT COUNT(DISTINCT student_id) FROM votes WHERE election_id = ?",
        (election_id,)
    )
    total_votes = cursor.fetchone()[0]
    cursor.execute(
        "SELECT COUNT(*) FROM election_students WHERE election_id = ?",
        (election_id,)
    )
    total_voters = cursor.fetchone()[0]
    con.close()
    results = {}
    for r in rows:
        role = r[0]
        if role not in results:
            results[role] = []
        results[role].append({"name": r[1], "kutumba": r[2], "votes": r[3]})
    return {"results": results, "total_votes": total_votes, "total_voters": total_voters}

def get_winners_for_election(election_id):
    con = connect_db()
    cursor = con.cursor()
    cursor.execute(
        """SELECT c.role, c.name, c.kutumba, COUNT(v.id) as vote_count
           FROM candidates c
           LEFT JOIN votes v ON v.candidate_id = c.id AND v.election_id = c.election_id
           WHERE c.election_id = ?
           GROUP BY c.id
           ORDER BY c.role ASC, vote_count DESC""",
        (election_id,)
    )
    rows = cursor.fetchall()
    con.close()

    by_role = {}
    for r in rows:
        role, name, kutumba, votes = r
        if role not in by_role:
            by_role[role] = []
        by_role[role].append({"name": name, "kutumba": kutumba, "votes": votes})

    winners = []

    for role, candidates in by_role.items():
        is_sports = "Sports Captain" in role
        if is_sports:
            top = candidates[0]
            winners.append({
                "role": role,
                "kutumba": None,
                "name": top["name"],
                "votes": top["votes"],
            })
        else:
            by_kutumba = {}
            for c in candidates:
                k = c["kutumba"]
                if k not in by_kutumba:
                    by_kutumba[k] = c
            for kutumba, top in sorted(by_kutumba.items()):
                winners.append({
                    "role": role,
                    "kutumba": kutumba,
                    "name": top["name"],
                    "votes": top["votes"],
                })

    return winners