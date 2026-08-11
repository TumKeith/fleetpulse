#!/usr/bin/env python3
"""
=============================================================================
 FLEETPULSE DATABASE ENGINE (SQLite)
 Persistent Storage for Fleet Inventory, Tech Shift Rosters & Audit Logs
=============================================================================
"""

import sqlite3
import json
import time
from typing import Dict, List, Optional

DB_FILE = "fleetpulse.db"


def get_db_connection():
    """Returns a connection to the SQLite database with row dict factory."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes tables and populates default technician roster if empty."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Devices Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            hostname TEXT PRIMARY KEY,
            logged_user TEXT,
            ip_address TEXT,
            status TEXT,
            event_state TEXT,
            assigned_tech TEXT,
            last_seen REAL,
            is_mock INTEGER,
            os_info TEXT,
            update_info TEXT,
            hardware_info TEXT,
            user_details TEXT
        )
    """)

    # 2. Technicians Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS technicians (
            id TEXT PRIMARY KEY,
            name TEXT,
            role TEXT,
            status TEXT
        )
    """)

    # 3. Audit Logs Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            hostname TEXT,
            actor TEXT,
            action TEXT,
            details TEXT
        )
    """)

    # Populate default technicians if table is empty
    cursor.execute("SELECT COUNT(*) FROM technicians")
    if cursor.fetchone()[0] == 0:
        default_techs = [
            ("tech1", "Kevin Vance", "Desktop Support", "ON_DUTY"),
            ("tech2", "Sarah Connor", "Network Engineer", "ON_DUTY"),
            ("tech3", "David Miller", "Systems Admin", "ON_LEAVE")
        ]
        cursor.executemany("INSERT INTO technicians VALUES (?, ?, ?, ?)", default_techs)

    conn.commit()
    conn.close()


def save_device(data: dict):
    """Upserts a device record into the database."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO devices (
            hostname, logged_user, ip_address, status, event_state, 
            assigned_tech, last_seen, is_mock, os_info, update_info, hardware_info, user_details
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(hostname) DO UPDATE SET
            logged_user=excluded.logged_user,
            ip_address=excluded.ip_address,
            status=excluded.status,
            event_state=excluded.event_state,
            assigned_tech=COALESCE(excluded.assigned_tech, devices.assigned_tech),
            last_seen=excluded.last_seen,
            is_mock=excluded.is_mock,
            os_info=excluded.os_info,
            update_info=excluded.update_info,
            hardware_info=excluded.hardware_info,
            user_details=excluded.user_details
    """, (
        data["hostname"],
        data.get("logged_user", ""),
        data.get("ip_address", "127.0.0.1"),
        data.get("status", "GREEN"),
        data.get("event_state", "ACTIVE"),
        data.get("assigned_tech", "Unassigned"),
        data.get("last_seen", time.time()),
        1 if data.get("is_mock") else 0,
        json.dumps(data.get("os_info", {})),
        json.dumps(data.get("update_info", {})),
        json.dumps(data.get("hardware_info", {})),
        json.dumps(data.get("user_details", {}))
    ))

    conn.commit()
    conn.close()


def get_all_devices() -> List[dict]:
    """Retrieves all devices, parsing JSON fields back into dicts."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM devices")
    rows = cursor.fetchall()
    conn.close()

    devices = []
    for row in rows:
        d = dict(row)
        d["os_info"] = json.loads(d["os_info"]) if d["os_info"] else {}
        d["update_info"] = json.loads(d["update_info"]) if d["update_info"] else {}
        d["hardware_info"] = json.loads(d["hardware_info"]) if d["hardware_info"] else {}
        d["user_details"] = json.loads(d["user_details"]) if d["user_details"] else {}
        d["is_mock"] = bool(d["is_mock"])
        devices.append(d)

    return devices


def update_device_status(hostname: str, new_status: str):
    """Updates device health status directly."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE devices SET status = ? WHERE hostname = ?", (new_status, hostname))
    conn.commit()
    conn.close()


def update_device_tech(hostname: str, tech_name: str):
    """Reassigns a device to a new technician."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE devices SET assigned_tech = ? WHERE hostname = ?", (tech_name, hostname))
    conn.commit()
    conn.close()


def get_all_techs() -> List[dict]:
    """Retrieves all technician profiles."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM technicians")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_tech_status(tech_id: str, new_status: str):
    """Updates a technician's shift status."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE technicians SET status = ? WHERE id = ?", (new_status, tech_id))
    conn.commit()
    conn.close()


def log_audit_event(hostname: str, actor: str, action: str, details: str = ""):
    """Records an audit trail event."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO audit_logs (timestamp, hostname, actor, action, details) VALUES (?, ?, ?, ?, ?)",
        (time.time(), hostname, actor, action, details)
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("[+] Database initialized successfully.")