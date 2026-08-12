#!/usr/bin/env python3
"""
=============================================================================
 FLEETPULSE CENTRAL IT COMMAND SERVER
 Multi-Technician Dispatch, SQLite Storage, LDAP Active Directory & Email Alerts
=============================================================================
"""

import os
import json
import time
import subprocess
import threading
from typing import Dict, List
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

import database as db
import notifier

app = FastAPI(title="FleetPulse IT Management Console")

db.init_db()

os.makedirs("templates", exist_ok=True)
templates = Jinja2Templates(directory="templates")

# Expected Agent Bearer Token
EXPECTED_AGENT_TOKEN = "Bearer FleetPulse-Enterprise-Key-2026-Secure"

COMMAND_QUEUE: Dict[str, List[dict]] = {}
COMMAND_RESULTS: Dict[str, List[dict]] = {}

# Active Directory Domain Controller LDAP Settings (Optional Configuration)
AD_LDAP_SERVER = os.getenv("AD_LDAP_SERVER", "ldap://domaincontroller.company.local")
AD_DOMAIN_SUFFIX = "@company.com"

FALLBACK_AD_DIRECTORY = {
    "admin": {"full_name": "System Administrator", "department": "IT Infrastructure", "email": "admin@company.com", "phone_ext": "4000"},
    "jdoe": {"full_name": "Jane Doe", "department": "Finance", "email": "jdoe@company.com", "phone_ext": "4401"},
    "mwilson": {"full_name": "Mark Wilson", "department": "Engineering", "email": "mwilson@company.com", "phone_ext": "4402"},
    "akarr": {"full_name": "Alex Karr", "department": "Human Resources", "email": "akarr@company.com", "phone_ext": "4403"},
    "cwilliams": {"full_name": "Claire Williams", "department": "Legal", "email": "cwilliams@company.com", "phone_ext": "4404"},
    "bmbatha": {"full_name": "Bernard Mbatha", "department": "Sales", "email": "bmbatha@company.com", "phone_ext": "4405"},
    "dchen": {"full_name": "David Chen", "department": "Logistics", "email": "dchen@company.com", "phone_ext": "4406"},
}

def query_active_directory_ldap(username: str) -> dict:
    """
    Attempts a live LDAP query against Active Directory Domain Controller.
    Falls back to structured AD directory mapping if LDAP is unconfigured or offline.
    """
    try:
        import ldap3
        server = ldap3.Server(AD_LDAP_SERVER, get_info=ldap3.ALL)
        conn = ldap3.Connection(server, auto_bind=True)
        search_filter = f"(sAMAccountName={username})"
        conn.search("dc=company,dc=local", search_filter, attributes=['displayName', 'department', 'mail', 'telephoneNumber'])
        
        if conn.entries:
            entry = conn.entries[0]
            return {
                "full_name": str(entry.displayName) if 'displayName' in entry else username,
                "department": str(entry.department) if 'department' in entry else "General",
                "email": str(entry.mail) if 'mail' in entry else f"{username}{AD_DOMAIN_SUFFIX}",
                "phone_ext": str(entry.telephoneNumber) if 'telephoneNumber' in entry else "N/A"
            }
    except Exception:
        pass  # Graceful fallback to cached AD profile

    return FALLBACK_AD_DIRECTORY.get(
        username,
        {"full_name": username.title() if username else "Unassigned", "department": "General Domain User", "email": f"{username}{AD_DOMAIN_SUFFIX}", "phone_ext": "N/A"}
    )

def verify_agent_token(authorization: str = Header(None)):
    """Verifies that incoming agent requests contain a valid Authorization token."""
    if authorization != EXPECTED_AGENT_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized Agent Access")

def calculate_health_status(os_info: dict, update_info: dict, hw_info: dict, event_state: str) -> str:
    if event_state == "GRACEFUL_SHUTDOWN":
        return "OFFLINE_SHUTDOWN"

    pending_updates = update_info.get("pending_updates_count", 0)
    reboot_needed = update_info.get("reboot_required", False)
    free_disk_gb = hw_info.get("free_disk_gb", 100)

    if free_disk_gb < 10 or pending_updates > 10:
        return "RED"
    if reboot_needed or pending_updates > 0:
        return "AMBER"
    return "GREEN"

def auto_assign_technician() -> str:
    techs = db.get_all_techs()
    on_duty_techs = [t["name"] for t in techs if t["status"] == "ON_DUTY"]
    if not on_duty_techs:
        return "Unassigned"

    devices = db.get_all_devices()
    counts = {tech: 0 for tech in on_duty_techs}
    for dev in devices:
        assigned = dev.get("assigned_tech")
        if assigned in counts and dev.get("status") in ["RED", "AMBER", "OFFLINE_NETWORK_DROP"]:
            counts[assigned] += 1

    return min(counts, key=counts.get)

@app.get("/", response_class=HTMLResponse)
async def render_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html")

@app.get("/tech", response_class=HTMLResponse)
async def render_tech_portal(request: Request):
    return templates.TemplateResponse(request=request, name="tech_portal.html")

@app.get("/api/techs")
async def get_technicians():
    return {"techs": db.get_all_techs()}

@app.post("/api/techs/duty/{tech_id}")
async def toggle_tech_duty(tech_id: str, payload: dict):
    new_status = payload.get("status", "ON_DUTY")
    db.update_tech_status(tech_id, new_status)
    db.log_audit_event("SYSTEM", tech_id, "DUTY_CHANGE", f"Status changed to {new_status}")
    return {"status": "SUCCESS"}

@app.post("/api/telemetry/heartbeat")
async def receive_heartbeat(data: dict, authorization: str = Header(None)):
    verify_agent_token(authorization)
    
    hostname = data.get("hostname", "UNKNOWN-PC")
    username = data.get("logged_user", "").lower()
    event_state = data.get("event_state", "ACTIVE")

    # Fetch AD Profile baseline
    ad_profile = query_active_directory_ldap(username)
    
    # 🎯 DYNAMIC OVERRIDE: Prioritize true Full Name fetched directly from local Windows User Account
    agent_fullname = data.get("user_full_name")
    if agent_fullname:
        ad_profile["full_name"] = agent_fullname

    status = calculate_health_status(
        data.get("os_info", {}),
        data.get("update_info", {}),
        data.get("hardware_info", {}),
        event_state
    )

    existing_devices = {d["hostname"]: d for d in db.get_all_devices()}
    previous_device = existing_devices.get(hostname, {})
    previous_status = previous_device.get("status", "UNKNOWN")
    existing_tech = previous_device.get("assigned_tech")
    
    if not existing_tech or existing_tech == "Unassigned":
        assigned_tech = auto_assign_technician() if status in ["RED", "AMBER", "OFFLINE_NETWORK_DROP"] else "Unassigned"
    else:
        assigned_tech = existing_tech

    device_payload = {
        "hostname": hostname,
        "logged_user": username,
        "user_details": ad_profile,
        "os_info": data.get("os_info", {}),
        "update_info": data.get("update_info", {}),
        "hardware_info": data.get("hardware_info", {}),
        "ip_address": data.get("ip_address", "127.0.0.1"),
        "status": status,
        "event_state": event_state,
        "assigned_tech": assigned_tech,
        "last_seen": time.time(),
        "is_mock": False
    }

    db.save_device(device_payload)

    # 🚨 SMART CRITICAL ALERTING: Non-blocking email alert triggered ONLY on state transition into RED
    if status == "RED" and previous_status != "RED":
        pending_updates = data.get("update_info", {}).get("pending_updates_count", 0)
        free_disk = data.get("hardware_info", {}).get("free_disk_gb", "N/A")
        issue_summary = f"Disk Space: {free_disk}GB Free | Pending Updates: {pending_updates}"

        alert_thread = threading.Thread(
            target=notifier.send_critical_alert,
            args=(
                hostname,
                data.get("ip_address", "127.0.0.1"),
                ad_profile.get("full_name", username),
                issue_summary
            )
        )
        alert_thread.start()

    return {"status": "SUCCESS", "assigned_health": status}

@app.get("/api/fleet/devices")
async def get_fleet_devices():
    now = time.time()
    devices = db.get_all_devices()
    for device in devices:
        if device.get("is_mock"):
            if device["status"] not in ["OFFLINE_NETWORK_DROP", "OFFLINE_SHUTDOWN"]:
                device["last_seen"] = now
                db.save_device(device)
        else:
            if device["status"] != "OFFLINE_SHUTDOWN" and (now - device["last_seen"]) > 25:
                device["status"] = "OFFLINE_NETWORK_DROP"
                db.save_device(device)

    return {"devices": devices}

@app.post("/api/admin/reassign")
async def reassign_machine(payload: dict):
    hostname = payload.get("hostname")
    tech_name = payload.get("tech_name")

    if hostname and tech_name:
        db.update_device_tech(hostname, tech_name)
        db.log_audit_event(hostname, "ADMIN", "REASSIGN", f"Assigned to {tech_name}")
        return {"status": "SUCCESS"}
    return JSONResponse({"status": "ERROR", "message": "Missing parameters"}, status_code=400)

@app.post("/api/admin/remediate/{hostname}")
async def remediate_device(hostname: str):
    devices = {d["hostname"]: d for d in db.get_all_devices()}
    if hostname in devices:
        dev = devices[hostname]
        dev["status"] = "GREEN"
        dev["update_info"] = {"pending_updates_count": 0, "reboot_required": False}
        dev["hardware_info"]["free_disk_gb"] = max(dev["hardware_info"].get("free_disk_gb", 50), 50.0)
        db.save_device(dev)
        db.log_audit_event(hostname, "TECH", "REMEDIATED", "Marked issue as resolved")
        return {"status": "SUCCESS"}
    return JSONResponse({"status": "ERROR", "message": "Host not found"}, status_code=404)

@app.post("/api/admin/command")
async def queue_admin_command(payload: dict):
    hostname = payload.get("hostname")
    command = payload.get("command")

    if not hostname or not command:
        return JSONResponse({"status": "ERROR", "message": "Missing parameters"}, status_code=400)

    if hostname not in COMMAND_QUEUE:
        COMMAND_QUEUE[hostname] = []

    COMMAND_QUEUE[hostname].append({"command": command, "timestamp": time.time()})
    db.log_audit_event(hostname, "ADMIN", "COMMAND_QUEUED", command)
    return {"status": "QUEUED", "hostname": hostname, "command": command}

@app.post("/api/admin/command-result")
async def store_command_result(payload: dict, authorization: str = Header(None)):
    verify_agent_token(authorization)
    hostname = payload.get("hostname")
    if hostname:
        if hostname not in COMMAND_RESULTS:
            COMMAND_RESULTS[hostname] = []
        COMMAND_RESULTS[hostname].insert(0, payload)
        db.log_audit_event(hostname, "AGENT", "COMMAND_EXECUTED", f"{payload.get('command')}: {payload.get('output')}")
    return {"status": "RECORDED"}

@app.get("/api/admin/command-result/{hostname}")
async def get_command_results(hostname: str):
    return {"results": COMMAND_RESULTS.get(hostname, [])}

@app.get("/api/agent/commands/{hostname}")
async def get_agent_commands(hostname: str, authorization: str = Header(None)):
    verify_agent_token(authorization)
    tasks = COMMAND_QUEUE.get(hostname, [])
    COMMAND_QUEUE[hostname] = []
    return {"tasks": tasks}

@app.post("/api/admin/launch-rdp")
async def launch_rdp_session(payload: dict):
    target_ip = payload.get("ip")
    if not target_ip:
        return JSONResponse({"status": "ERROR", "message": "No IP address provided"}, status_code=400)

    try:
        subprocess.Popen(f"mstsc.exe /v:{target_ip}", shell=True)
        db.log_audit_event(target_ip, "ADMIN", "RDP_LAUNCH", f"RDP session opened to {target_ip}")
        return {"status": "SUCCESS", "message": f"RDP session initiated to {target_ip}"}
    except Exception as e:
        return JSONResponse({"status": "ERROR", "message": str(e)}, status_code=500)

@app.post("/api/demo/populate-mock")
async def populate_mock_fleet():
    mock_pcs = [
        {
            "hostname": "FIN-DESK-042",
            "logged_user": "jdoe",
            "user_details": FALLBACK_AD_DIRECTORY["jdoe"],
            "os_info": {"product_name": "Windows 10 Pro", "display_version": "21H2", "build_number": "19044"},
            "update_info": {"pending_updates_count": 12, "reboot_required": True},
            "hardware_info": {"free_disk_gb": 8.2, "architecture": "x86_64"},
            "ip_address": "10.14.20.105",
            "status": "RED",
            "event_state": "ACTIVE",
            "assigned_tech": "Kevin Vance",
            "last_seen": time.time(),
            "is_mock": True
        },
        {
            "hostname": "ENG-WORKSTATION-01",
            "logged_user": "mwilson",
            "user_details": FALLBACK_AD_DIRECTORY["mwilson"],
            "os_info": {"product_name": "Windows 11 Pro", "display_version": "23H2", "build_number": "22631"},
            "update_info": {"pending_updates_count": 3, "reboot_required": False},
            "hardware_info": {"free_disk_gb": 240.5, "architecture": "x86_64"},
            "ip_address": "10.14.20.112",
            "status": "AMBER",
            "event_state": "ACTIVE",
            "assigned_tech": "Sarah Connor",
            "last_seen": time.time(),
            "is_mock": True
        },
        {
            "hostname": "SALES-LAPTOP-04",
            "logged_user": "bmbatha",
            "user_details": FALLBACK_AD_DIRECTORY["bmbatha"],
            "os_info": {"product_name": "Windows 11 Pro", "display_version": "23H2", "build_number": "22631"},
            "update_info": {"pending_updates_count": 0, "reboot_required": False},
            "hardware_info": {"free_disk_gb": 95.0, "architecture": "x86_64"},
            "ip_address": "10.14.20.130",
            "status": "OFFLINE_NETWORK_DROP",
            "event_state": "UNEXPECTED_DROP",
            "assigned_tech": "Kevin Vance",
            "last_seen": time.time() - 300,
            "is_mock": True
        },
        {
            "hostname": "LOGISTICS-DESK-01",
            "logged_user": "dchen",
            "user_details": FALLBACK_AD_DIRECTORY["dchen"],
            "os_info": {"product_name": "Windows 10 Pro", "display_version": "22H2", "build_number": "19045"},
            "update_info": {"pending_updates_count": 0, "reboot_required": False},
            "hardware_info": {"free_disk_gb": 150.0, "architecture": "x86_64"},
            "ip_address": "10.14.20.145",
            "status": "OFFLINE_SHUTDOWN",
            "event_state": "GRACEFUL_SHUTDOWN",
            "assigned_tech": "Unassigned",
            "last_seen": time.time() - 1200,
            "is_mock": True
        },
        {
            "hostname": "HR-LAPTOP-09",
            "logged_user": "akarr",
            "user_details": FALLBACK_AD_DIRECTORY["akarr"],
            "os_info": {"product_name": "Windows 11 Pro", "display_version": "23H2", "build_number": "22631"},
            "update_info": {"pending_updates_count": 0, "reboot_required": False},
            "hardware_info": {"free_disk_gb": 115.0, "architecture": "x86_64"},
            "ip_address": "10.14.20.118",
            "status": "GREEN",
            "event_state": "ACTIVE",
            "assigned_tech": "Unassigned",
            "last_seen": time.time(),
            "is_mock": True
        }
    ]

    for pc in mock_pcs:
        db.save_device(pc)

    return {"status": "SUCCESS", "added": len(mock_pcs)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8080, reload=True)