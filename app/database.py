import sqlite3
import os
from datetime import datetime
from typing import Optional

from app.models import Subtitle, VoicePreset


class ProjectDB:
    """SQLite-backed project storage."""

    def __init__(self, db_path: str = "samray_projects.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        cur = self.conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            video_path TEXT DEFAULT '',
            language TEXT DEFAULT 'Khmer',
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS subtitles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            idx INTEGER NOT NULL,
            start_ms INTEGER NOT NULL,
            end_ms INTEGER NOT NULL,
            text TEXT DEFAULT '',
            gender TEXT DEFAULT 'Female',
            audio_path TEXT DEFAULT '',
            selected INTEGER DEFAULT 1,
            monologue INTEGER DEFAULT 0,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS voice_presets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            engine TEXT DEFAULT 'edge',
            voice_id TEXT DEFAULT 'km-KH-PisethNeural',
            gender TEXT DEFAULT 'Female',
            speed REAL DEFAULT 1.0,
            pitch REAL DEFAULT 0.0,
            volume REAL DEFAULT 1.0,
            emotion TEXT DEFAULT 'neutral',
            style TEXT DEFAULT 'general'
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """)
        self.conn.commit()

        # Older projects were created before subtitle checkboxes existed.
        # Default every existing subtitle to checked so nothing disappears
        # from the user's current voice-generation workflow.
        columns = {
            row["name"]
            for row in self.conn.execute("PRAGMA table_info(subtitles)")
        }
        if "selected" not in columns:
            self.conn.execute(
                "ALTER TABLE subtitles ADD COLUMN selected INTEGER DEFAULT 1"
            )
            self.conn.commit()
        if "monologue" not in columns:
            self.conn.execute(
                "ALTER TABLE subtitles ADD COLUMN monologue INTEGER DEFAULT 0"
            )
            self.conn.commit()

        self._seed_default_preset()

    def _seed_default_preset(self):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM voice_presets")
        if cur.fetchone()[0] == 0:
            presets = [
                ("Khmer Female – Sophea", "edge", "km-KH-SreymomNeural",
                 "Female", 1.0, 0.0, 1.0, "neutral", "general"),
                ("Khmer Male – Piseth", "edge", "km-KH-PisethNeural",
                 "Male", 1.0, 0.0, 1.0, "neutral", "general"),
                ("English Female – Jenny", "edge", "en-US-JennyNeural",
                 "Female", 1.0, 0.0, 1.0, "friendly", "general"),
                ("English Male – Andrew", "edge", "en-US-AndrewNeural",
                 "Male", 1.0, 0.0, 1.0, "calm", "general"),
            ]
            cur.executemany(
                "INSERT INTO voice_presets(name,engine,voice_id,gender,speed,pitch,volume,emotion,style)"
                " VALUES(?,?,?,?,?,?,?,?,?)", presets)
            self.conn.commit()

    # ---------------- Projects ----------------
    def create_project(self, name: str, video_path: str = "", language: str = "Khmer") -> int:
        now = datetime.now().isoformat()
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO projects(name,video_path,language,created_at,updated_at) VALUES(?,?,?,?,?)",
            (name, video_path, language, now, now))
        self.conn.commit()
        return cur.lastrowid

    def update_project(self, project_id: int, **kwargs):
        if not kwargs:
            return
        kwargs["updated_at"] = datetime.now().isoformat()
        keys = ", ".join(f"{k}=?" for k in kwargs)
        vals = list(kwargs.values()) + [project_id]
        self.conn.execute(f"UPDATE projects SET {keys} WHERE id=?", vals)
        self.conn.commit()

    def get_project(self, project_id: int) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return dict(row) if row else None

    def latest_project(self) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM projects ORDER BY updated_at DESC LIMIT 1").fetchone()
        return dict(row) if row else None

    # ---------------- Subtitles ----------------
    def load_subtitles(self, project_id: int) -> list[Subtitle]:
        rows = self.conn.execute(
            "SELECT * FROM subtitles WHERE project_id=? ORDER BY idx", (project_id,)
        ).fetchall()
        return [Subtitle(id=r["id"], idx=r["idx"], start_ms=r["start_ms"],
                         end_ms=r["end_ms"], text=r["text"], gender=r["gender"],
                         audio_path=r["audio_path"],
                         selected=bool(r["selected"]) if "selected" in r.keys() else True,
                         monologue=bool(r["monologue"]) if "monologue" in r.keys() else False)
                for r in rows]

    def replace_subtitles(self, project_id: int, subs: list[Subtitle]):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM subtitles WHERE project_id=?", (project_id,))
        for i, s in enumerate(subs):
            cur.execute(
                "INSERT INTO subtitles(project_id,idx,start_ms,end_ms,text,gender,audio_path,selected,monologue)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (project_id, i, s.start_ms, s.end_ms, s.text, s.gender,
                 s.audio_path, int(bool(s.selected)), int(bool(s.monologue))))
        self.conn.commit()

    def update_subtitle(self, sub: Subtitle):
        self.conn.execute(
            "UPDATE subtitles SET start_ms=?, end_ms=?, text=?, gender=?,"
            " audio_path=?, selected=?, monologue=? WHERE id=?",
            (sub.start_ms, sub.end_ms, sub.text, sub.gender, sub.audio_path,
             int(bool(sub.selected)), int(bool(sub.monologue)), sub.id))
        self.conn.commit()

    # ---------------- Voice presets ----------------
    def list_presets(self) -> list[VoicePreset]:
        rows = self.conn.execute("SELECT * FROM voice_presets ORDER BY name").fetchall()
        return [VoicePreset(
            id=r["id"], name=r["name"], engine=r["engine"], voice_id=r["voice_id"],
            gender=r["gender"], speed=r["speed"], pitch=r["pitch"],
            volume=r["volume"], emotion=r["emotion"], style=r["style"]) for r in rows]

    def save_preset(self, preset: VoicePreset) -> int:
        if preset.id:
            self.conn.execute(
                "UPDATE voice_presets SET name=?,engine=?,voice_id=?,gender=?,speed=?,"
                "pitch=?,volume=?,emotion=?,style=? WHERE id=?",
                (preset.name, preset.engine, preset.voice_id, preset.gender,
                 preset.speed, preset.pitch, preset.volume, preset.emotion,
                 preset.style, preset.id))
            self.conn.commit()
            return preset.id
        cur = self.conn.execute(
            "INSERT INTO voice_presets(name,engine,voice_id,gender,speed,pitch,volume,emotion,style)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (preset.name, preset.engine, preset.voice_id, preset.gender,
             preset.speed, preset.pitch, preset.volume, preset.emotion, preset.style))
        self.conn.commit()
        return cur.lastrowid

    def delete_preset(self, preset_id: int):
        self.conn.execute("DELETE FROM voice_presets WHERE id=?", (preset_id,))
        self.conn.commit()

    # ---------------- Settings ----------------
    def get_setting(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        self.conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        self.conn.commit()

    def close(self):
        self.conn.close()