import sqlite3
import os
import time

DB_PATH = "fleetpulse.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    # 1. Devices Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            hostname TEXT PRIMARY KEY,
            logged_user TEXT,
            user_details TEXT,
            os_info TEXT,
            update_info TEXT,
            hardware_info TEXT,
            ip_address TEXT,
            status TEXT,
            event_state TEXT,
            assigned_tech TEXT,
            last_seen REAL,
            is_mock INTEGER DEFAULT 0,
            incident_created_at REAL DEFAULT 0
        )
    """)

    # 🛠️ AUTO-MIGRATION: Ensure incident_created_at exists on older device tables
    cursor.execute("PRAGMA table_info(devices)")
    device_columns = [row[1] for row in cursor.fetchall()]
    if "incident_created_at" not in device_columns:
        cursor.execute("ALTER TABLE devices ADD COLUMN incident_created_at REAL DEFAULT 0")

    # 2. Technicians Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS technicians (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            status TEXT DEFAULT 'ACTIVE',
            resolved_count INTEGER DEFAULT 0,
            total_resolution_time REAL DEFAULT 0.0
        )
    """)

    # 🛠️ AUTO-MIGRATION: Ensure email & SLA columns exist on older technician tables
    cursor.execute("PRAGMA table_info(technicians)")
    tech_columns = [row[1] for row in cursor.fetchall()]
    if "email" not in tech_columns:
        cursor.execute("ALTER TABLE technicians ADD COLUMN email TEXT")
    if "resolved_count" not in tech_columns:
        cursor.execute("ALTER TABLE technicians ADD COLUMN resolved_count INTEGER DEFAULT 0")
    if "total_resolution_time" not in tech_columns:
        cursor.execute("ALTER TABLE technicians ADD COLUMN total_resolution_time REAL DEFAULT 0.0")

    # 3. Audit Logs Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hostname TEXT,
            actor TEXT,
            action TEXT,
            details TEXT,
            timestamp REAL
        )
    """)

    # Populate Default Technicians if table is empty
    cursor.execute("SELECT COUNT(*) FROM technicians")
    if cursor.fetchone()[0] == 0:
        default_techs = [
            ("TECH_01", "Kevin Vance", "kvance@company.com", "ACTIVE"),
            ("TECH_02", "Sarah Connor", "sconnor@company.com", "ACTIVE"),
            ("TECH_03", "Alex Mercer", "amercer@company.com", "OUT_OF_OFFICE")
        ]
        cursor.executemany("""
            INSERT INTO technicians (id, name, email, status) VALUES (?, ?, ?, ?)
        """, default_techs)

    conn.commit()
    conn.close()

def get_all_devices():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM devices ORDER BY last_seen DESC")
    rows = cursor.fetchall()
    conn.close()
    
    import json
    devices = []
    for r in rows:
        d = dict(r)
        d['user_details'] = json.loads(d['user_details']) if d['user_details'] else {}
        d['os_info'] = json.loads(d['os_info']) if d['os_info'] else {}
        d['update_info'] = json.loads(d['update_info']) if d['update_info'] else {}
        d['hardware_info'] = json.loads(d['hardware_info']) if d['hardware_info'] else {}
        d['is_mock'] = bool(d['is_mock'])
        devices.append(d)
    return devices

def save_device(device: dict):
    conn = get_db()
    cursor = conn.cursor()
    import json
    
    status = device.get("status", "GREEN")
    current_time = time.time()
    
    cursor.execute("SELECT status, incident_created_at FROM devices WHERE hostname = ?", (device["hostname"],))
    row = cursor.fetchone()
    
    if row:
        prev_status, prev_created_at = row[0], row[1]
        if status in ["RED", "AMBER"] and prev_status not in ["RED", "AMBER"]:
            incident_created_at = current_time
        elif status in ["RED", "AMBER"]:
            incident_created_at = prev_created_at if prev_created_at and prev_created_at > 0 else current_time
        else:
            incident_created_at = 0
    else:
        incident_created_at = current_time if status in ["RED", "AMBER"] else 0

    cursor.execute("""
        INSERT INTO devices (hostname, logged_user, user_details, os_info, update_info, hardware_info, ip_address, status, event_state, assigned_tech, last_seen, is_mock, incident_created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(hostname) DO UPDATE SET
            logged_user=excluded.logged_user,
            user_details=excluded.user_details,
            os_info=excluded.os_info,
            update_info=excluded.update_info,
            hardware_info=excluded.hardware_info,
            ip_address=excluded.ip_address,
            status=excluded.status,
            event_state=excluded.event_state,
            assigned_tech=excluded.assigned_tech,
            last_seen=excluded.last_seen,
            is_mock=excluded.is_mock,
            incident_created_at=excluded.incident_created_at
    """, (
        device["hostname"],
        device.get("logged_user", ""),
        json.dumps(device.get("user_details", {})),
        json.dumps(device.get("os_info", {})),
        json.dumps(device.get("update_info", {})),
        json.dumps(device.get("hardware_info", {})),
        device.get("ip_address", "127.0.0.1"),
        status,
        device.get("event_state", "ACTIVE"),
        device.get("assigned_tech", "Unassigned"),
        device.get("last_seen", current_time),
        1 if device.get("is_mock") else 0,
        incident_created_at
    ))
    conn.commit()
    conn.close()

def get_all_techs():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM technicians")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_technician(tech_id: str, name: str, email: str, status: str = "ACTIVE"):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO technicians (id, name, email, status) VALUES (?, ?, ?, ?)
    """, (tech_id, name, email, status))
    conn.commit()
    conn.close()

def update_tech_status(tech_id: str, status: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE technicians SET status = ? WHERE id = ?", (status, tech_id))
    conn.commit()
    conn.close()

def record_remediation_metrics(tech_name: str, resolution_seconds: float):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE technicians 
        SET resolved_count = resolved_count + 1,
            total_resolution_time = total_resolution_time + ?
        WHERE name = ?
    """, (resolution_seconds, tech_name))
    conn.commit()
    conn.close()

def update_device_tech(hostname: str, tech_name: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE devices SET assigned_tech = ? WHERE hostname = ?", (tech_name, hostname))
    conn.commit()
    conn.close()

def log_audit_event(hostname: str, actor: str, action: str, details: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO audit_logs (hostname, actor, action, details, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (hostname, actor, action, details, time.time()))
    conn.commit()
    conn.close()