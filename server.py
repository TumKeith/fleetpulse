#!/usr/bin/env python3
"""
=============================================================================
 FLEETPULSE CENTRAL IT COMMAND SERVER
 Multi-Technician Dispatch, Dynamic Email/Identity Pipeline, SLA MTTR Tracking,
 & Responsive Shift Re-Assignment Engine
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

# Fallback Directory Data
FALLBACK_AD_DIRECTORY = {
    "admin": {"full_name": "System Administrator", "department": "IT Infrastructure", "email": "admin@company.com"},
    "jdoe": {"full_name": "Jane Doe", "department": "Finance", "email": "jdoe@company.com"},
    "mwilson": {"full_name": "Mark Wilson", "department": "Engineering", "email": "mwilson@company.com"},
}

def resolve_department_from_identity(hostname: str, username: str, email: str) -> str:
    """Dynamically infers or resolves department context from email or hostname conventions."""
    if email and "@" in email:
        domain = email.split("@")[-1].lower()
        parts = domain.split(".")
        if len(parts) > 2:
            subdomain = parts[0]
            if subdomain in ["students", "student"]:
                return "Academic / Student Body"
            elif subdomain in ["staff", "faculty"]:
                return "Faculty / Staff"
            elif subdomain in ["eng", "engineering"]:
                return "Engineering"

    host_upper = hostname.upper()
    if host_upper.startswith("FIN"):
        return "Finance & Accounting"
    elif host_upper.startswith("ENG"):
        return "Engineering & R&D"
    elif host_upper.startswith("SALES") or host_upper.startswith("MKT"):
        return "Sales & Marketing"
    elif host_upper.startswith("HR"):
        return "Human Resources"
    elif host_upper.startswith("LOG"):
        return "Logistics & Operations"

    return "General Operations"

def query_active_directory_ldap(username: str) -> dict:
    """Fallback directory profile resolution."""
    return FALLBACK_AD_DIRECTORY.get(
        username,
        {"full_name": username.title() if username else "Unassigned", "department": "General Operations", "email": f"{username}@company.com"}
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
    """Routes critical tasks exclusively to technicians who are ACTIVE on duty."""
    techs = db.get_all_techs()
    on_duty_techs = [t["name"] for t in techs if t["status"] == "ACTIVE"]
    if not on_duty_techs:
        return "Unassigned"

    devices = db.get_all_devices()
    counts = {tech: 0 for tech in on_duty_techs}
    for dev in devices:
        assigned = dev.get("assigned_tech")
        if assigned in counts and dev.get("status") in ["RED", "AMBER", "OFFLINE_NETWORK_DROP"]:
            counts[assigned] += 1

    return min(counts, key=counts.get)

# --- Web Views ---
@app.get("/", response_class=HTMLResponse)
async def render_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html")

@app.get("/tech", response_class=HTMLResponse)
async def render_tech_portal(request: Request):
    return templates.TemplateResponse(request=request, name="tech_portal.html")

# --- Technician Management Endpoints ---
@app.get("/api/techs")
async def get_technicians():
    return {"techs": db.get_all_techs()}

@app.post("/api/techs/create")
async def create_technician(payload: dict):
    name = payload.get("name")
    email = payload.get("email")
    if not name or not email:
        return JSONResponse({"status": "ERROR", "message": "Name and email are required"}, status_code=400)
    
    tech_id = f"TECH_{int(time.time())}"
    try:
        db.add_technician(tech_id, name, email, "ACTIVE")
        db.log_audit_event("SYSTEM", "ADMIN", "TECH_CREATED", f"Created technician {name} ({email})")
        return {"status": "SUCCESS", "tech_id": tech_id}
    except Exception as e:
        return JSONResponse({"status": "ERROR", "message": str(e)}, status_code=400)

@app.post("/api/techs/duty/{tech_id}")
async def toggle_tech_duty(tech_id: str, payload: dict):
    new_status = payload.get("status", "ACTIVE")
    db.update_tech_status(tech_id, new_status)
    db.log_audit_event("SYSTEM", tech_id, "DUTY_CHANGE", f"Status updated to {new_status}")

    # 🚨 DYNAMIC RE-ASSIGNMENT ENGINE
    # If technician goes off-duty, automatically re-route their active tickets
    if new_status in ["OUT_OF_OFFICE", "ON_LEAVE"]:
        techs = db.get_all_techs()
        tech_obj = next((t for t in techs if t["id"] == tech_id), None)
        
        if tech_obj:
            tech_name = tech_obj["name"]
            devices = db.get_all_devices()
            
            for dev in devices:
                if dev.get("assigned_tech") == tech_name and dev.get("status") in ["RED", "AMBER", "OFFLINE_NETWORK_DROP"]:
                    new_tech = auto_assign_technician()
                    dev["assigned_tech"] = new_tech
                    db.save_device(dev)
                    db.log_audit_event(
                        dev["hostname"], 
                        "SYSTEM", 
                        "AUTO_REASSIGN", 
                        f"Reassigned from {tech_name} ({new_status}) to {new_tech}"
                    )

    return {"status": "SUCCESS"}

# --- Telemetry Ingestion ---
@app.post("/api/telemetry/heartbeat")
async def receive_heartbeat(data: dict, authorization: str = Header(None)):
    verify_agent_token(authorization)
    
    hostname = data.get("hostname", "UNKNOWN-PC")
    username = data.get("logged_user", "").lower()
    event_state = data.get("event_state", "ACTIVE")

    ad_profile = query_active_directory_ldap(username)
    
    # Prioritize true Full Name & Real Email reported directly by agent
    agent_fullname = data.get("user_full_name")
    agent_email = data.get("user_email")

    if agent_fullname:
        ad_profile["full_name"] = agent_fullname
    if agent_email:
        ad_profile["email"] = agent_email

    ad_profile["department"] = resolve_department_from_identity(hostname, username, ad_profile.get("email", ""))

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

    # 🚨 SMART CRITICAL ALERTING
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

# --- SLA & Remediation Actions ---
@app.post("/api/admin/remediate/{hostname}")
async def remediate_device(hostname: str):
    devices = {d["hostname"]: d for d in db.get_all_devices()}
    if hostname in devices:
        dev = devices[hostname]
        
        incident_created_at = dev.get("incident_created_at", 0)
        resolution_seconds = 0.0
        if incident_created_at > 0:
            resolution_seconds = time.time() - incident_created_at
            assigned_tech = dev.get("assigned_tech", "Unassigned")
            if assigned_tech != "Unassigned":
                db.record_remediation_metrics(assigned_tech, resolution_seconds)

        dev["status"] = "GREEN"
        dev["incident_created_at"] = 0
        dev["update_info"] = {"pending_updates_count": 0, "reboot_required": False}
        dev["hardware_info"]["free_disk_gb"] = max(dev["hardware_info"].get("free_disk_gb", 50), 50.0)
        
        db.save_device(dev)
        db.log_audit_event(hostname, "TECH", "REMEDIATED", f"Issue marked resolved. SLA time: {round(resolution_seconds, 1)}s")
        return {"status": "SUCCESS"}
    return JSONResponse({"status": "ERROR", "message": "Host not found"}, status_code=404)

@app.get("/api/analytics/sla")
async def get_sla_analytics():
    """Calculates Mean Time to Remediate (MTTR) across all technicians."""
    techs = db.get_all_techs()
    total_resolved = sum(t.get("resolved_count", 0) for t in techs)
    total_time = sum(t.get("total_resolution_time", 0.0) for t in techs)
    
    mttr_seconds = round(total_time / total_resolved, 1) if total_resolved > 0 else 0.0
    return {
        "total_resolved_incidents": total_resolved,
        "mean_time_to_remediate_seconds": mttr_seconds,
        "technician_performance": techs
    }

# --- Manual Fallback / Edit Endpoint ---
@app.post("/api/admin/manual-override")
async def manual_device_override(payload: dict):
    """Allows admins/techs to manually correct user details or assigned technician."""
    hostname = payload.get("hostname")
    if not hostname:
        return JSONResponse({"status": "ERROR", "message": "Missing hostname"}, status_code=400)
    
    devices = {d["hostname"]: d for d in db.get_all_devices()}
    if hostname in devices:
        dev = devices[hostname]
        if "user_full_name" in payload:
            dev["user_details"]["full_name"] = payload["user_full_name"]
        if "department" in payload:
            dev["user_details"]["department"] = payload["department"]
        if "assigned_tech" in payload:
            dev["assigned_tech"] = payload["assigned_tech"]
            
        db.save_device(dev)
        db.log_audit_event(hostname, "ADMIN", "MANUAL_OVERRIDE", f"Updated details for {hostname}")
        return {"status": "SUCCESS"}
    return JSONResponse({"status": "ERROR", "message": "Device not found"}, status_code=404)

# --- Admin & Remote Commands ---
@app.post("/api/admin/reassign")
async def reassign_machine(payload: dict):
    hostname = payload.get("hostname")
    tech_name = payload.get("tech_name")

    if hostname and tech_name:
        db.update_device_tech(hostname, tech_name)
        db.log_audit_event(hostname, "ADMIN", "REASSIGN", f"Assigned to {tech_name}")
        return {"status": "SUCCESS"}
    return JSONResponse({"status": "ERROR", "message": "Missing parameters"}, status_code=400)

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
        }
    ]

    for pc in mock_pcs:
        db.save_device(pc)

    return {"status": "SUCCESS", "added": len(mock_pcs)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8080, reload=True)