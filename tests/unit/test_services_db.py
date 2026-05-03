from pathlib import Path

from services.db import connect


def test_connect_returns_dict_rows(tmp_db: Path) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO users(id, user_name, first_name, balance, reg_date) "
            "VALUES (?, ?, ?, ?, ?)",
            (7, "x", "X", 50, "2026-05-02"),
        )
        con.commit()
        row = con.execute("SELECT id, balance FROM users WHERE id = 7").fetchone()
    assert row == {"id": 7, "balance": 50}


def test_connect_uses_current_path_db(tmp_db: Path) -> None:
    """Если monkeypatch path_db меняет путь — connect должен его подхватить."""
    with connect() as con:
        rows = con.execute("PRAGMA table_info(orders)").fetchall()
    assert len(rows) == 8
