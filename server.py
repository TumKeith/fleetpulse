#!/usr/bin/env python3
"""
=============================================================================
 FLEETPULSE CENTRAL IT COMMAND SERVER
 Enterprise Fleet Health Monitoring, RDP Session Launcher & Command Engine
=============================================================================
"""

import os
import json
import time
import subprocess
from typing import Dict, List
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="FleetPulse IT Management Console")

os.makedirs("templates", exist_ok=True)
templates = Jinja2Templates(directory="templates")

FLEET_DB: Dict[str, dict] = {}
COMMAND_QUEUE: Dict[str, List[dict]] = {}
COMMAND_RESULTS: Dict[str, List[dict]] = {}

MOCK_AD_DIRECTORY = {
    "admin": {"full_name": "System Administrator", "department": "IT Infrastructure", "email": "admin@company.com", "phone_ext": "4000"},
    "jdoe": {"full_name": "Jane Doe", "department": "Finance", "email": "jdoe@company.com", "phone_ext": "4401"},
    "mwilson": {"full_name": "Mark Wilson", "department": "Engineering", "email": "mwilson@company.com", "phone_ext": "4402"},
    "akarr": {"full_name": "Alex Karr", "department": "Human Resources", "email": "akarr@company.com", "phone_ext": "4403"},
    "cwilliams": {"full_name": "Claire Williams", "department": "Legal", "email": "cwilliams@company.com", "phone_ext": "4404"},
    "bmbatha": {"full_name": "Bernard Mbatha", "department": "Sales", "email": "bmbatha@company.com", "phone_ext": "4405"},
    "dchen": {"full_name": "David Chen", "department": "Logistics", "email": "dchen@company.com", "phone_ext": "4406"},
}


def calculate_health_status(os_info: dict, update_info: dict, hw_info: dict, event_state: str) -> str:
    if event_state == "GRACEFUL_SHUTDOWN":
        return "OFFLINE_SHUTDOWN"

    pending_updates = update_info.get("pending_updates_count", 0)
    reboot_needed = update_info.get("reboot_required", False)
    free_disk_gb = hw_info.get("free_disk_gb", 100)

    # Re-evaluates exact minimum thresholds on every heartbeat
    if free_disk_gb < 10 or pending_updates > 10:
        return "RED"
    if reboot_needed or pending_updates > 0:
        return "AMBER"
    return "GREEN"


@app.get("/", response_class=HTMLResponse)
async def render_dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html")


@app.post("/api/telemetry/heartbeat")
async def receive_heartbeat(data: dict):
    hostname = data.get("hostname", "UNKNOWN-PC")
    username = data.get("logged_user", "").lower()
    event_state = data.get("event_state", "ACTIVE")

    ad_profile = MOCK_AD_DIRECTORY.get(
        username, 
        {"full_name": username or "Unassigned", "department": "General", "email": f"{username}@company.com", "phone_ext": "N/A"}
    )

    # Server re-calculates compliance automatically on heartbeat arrival
    status = calculate_health_status(
        data.get("os_info", {}),
        data.get("update_info", {}),
        data.get("hardware_info", {}),
        event_state
    )

    FLEET_DB[hostname] = {
        "hostname": hostname,
        "logged_user": username,
        "user_details": ad_profile,
        "os_info": data.get("os_info", {}),
        "update_info": data.get("update_info", {}),
        "hardware_info": data.get("hardware_info", {}),
        "ip_address": data.get("ip_address", "127.0.0.1"),
        "status": status,
        "event_state": event_state,
        "last_seen": time.time(),
        "is_mock": False
    }

    return {"status": "SUCCESS", "assigned_health": status}


@app.get("/api/fleet/devices")
async def get_fleet_devices():
    now = time.time()
    for hostname, device in FLEET_DB.items():
        if device.get("is_mock"):
            if device["status"] not in ["OFFLINE_NETWORK_DROP", "OFFLINE_SHUTDOWN"]:
                device["last_seen"] = now
        else:
            if device["status"] != "OFFLINE_SHUTDOWN" and (now - device["last_seen"]) > 25:
                device["status"] = "OFFLINE_NETWORK_DROP"

    return {"devices": list(FLEET_DB.values())}


@app.post("/api/admin/remediate/{hostname}")
async def remediate_device(hostname: str):
    """Temporary manual override. If real metrics still violate thresholds, next heartbeat reverts status."""
    if hostname in FLEET_DB:
        FLEET_DB[hostname]["status"] = "GREEN"
        FLEET_DB[hostname]["update_info"] = {"pending_updates_count": 0, "reboot_required": False}
        FLEET_DB[hostname]["hardware_info"]["free_disk_gb"] = max(FLEET_DB[hostname]["hardware_info"].get("free_disk_gb", 50), 50.0)
        return {"status": "SUCCESS", "message": f"{hostname} marked as Healthy"}
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
    return {"status": "QUEUED", "hostname": hostname, "command": command}


@app.post("/api/admin/command-result")
async def store_command_result(payload: dict):
    hostname = payload.get("hostname")
    if hostname:
        if hostname not in COMMAND_RESULTS:
            COMMAND_RESULTS[hostname] = []
        COMMAND_RESULTS[hostname].insert(0, payload)
    return {"status": "RECORDED"}


@app.get("/api/admin/command-result/{hostname}")
async def get_command_results(hostname: str):
    return {"results": COMMAND_RESULTS.get(hostname, [])}


@app.get("/api/agent/commands/{hostname}")
async def get_agent_commands(hostname: str):
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
        return {"status": "SUCCESS", "message": f"RDP session initiated to {target_ip}"}
    except Exception as e:
        return JSONResponse({"status": "ERROR", "message": str(e)}, status_code=500)


@app.post("/api/demo/populate-mock")
async def populate_mock_fleet():
    mock_pcs = [
        {
            "hostname": "FIN-DESK-042",
            "logged_user": "jdoe",
            "user_details": MOCK_AD_DIRECTORY["jdoe"],
            "os_info": {"product_name": "Windows 10 Pro", "display_version": "21H2", "build_number": "19044"},
            "update_info": {"pending_updates_count": 12, "reboot_required": True},
            "hardware_info": {"free_disk_gb": 8.2, "architecture": "x86_64"},
            "ip_address": "10.14.20.105",
            "status": "RED",
            "event_state": "ACTIVE",
            "last_seen": time.time(),
            "is_mock": True
        },
        {
            "hostname": "ENG-WORKSTATION-01",
            "logged_user": "mwilson",
            "user_details": MOCK_AD_DIRECTORY["mwilson"],
            "os_info": {"product_name": "Windows 11 Pro", "display_version": "23H2", "build_number": "22631"},
            "update_info": {"pending_updates_count": 3, "reboot_required": False},
            "hardware_info": {"free_disk_gb": 240.5, "architecture": "x86_64"},
            "ip_address": "10.14.20.112",
            "status": "AMBER",
            "event_state": "ACTIVE",
            "last_seen": time.time(),
            "is_mock": True
        },
        {
            "hostname": "SALES-LAPTOP-04",
            "logged_user": "bmbatha",
            "user_details": MOCK_AD_DIRECTORY["bmbatha"],
            "os_info": {"product_name": "Windows 11 Pro", "display_version": "23H2", "build_number": "22631"},
            "update_info": {"pending_updates_count": 0, "reboot_required": False},
            "hardware_info": {"free_disk_gb": 95.0, "architecture": "x86_64"},
            "ip_address": "10.14.20.130",
            "status": "OFFLINE_NETWORK_DROP",
            "event_state": "UNEXPECTED_DROP",
            "last_seen": time.time() - 300,
            "is_mock": True
        },
        {
            "hostname": "LOGISTICS-DESK-01",
            "logged_user": "dchen",
            "user_details": MOCK_AD_DIRECTORY["dchen"],
            "os_info": {"product_name": "Windows 10 Pro", "display_version": "22H2", "build_number": "19045"},
            "update_info": {"pending_updates_count": 0, "reboot_required": False},
            "hardware_info": {"free_disk_gb": 150.0, "architecture": "x86_64"},
            "ip_address": "10.14.20.145",
            "status": "OFFLINE_SHUTDOWN",
            "event_state": "GRACEFUL_SHUTDOWN",
            "last_seen": time.time() - 1200,
            "is_mock": True
        },
        {
            "hostname": "HR-LAPTOP-09",
            "logged_user": "akarr",
            "user_details": MOCK_AD_DIRECTORY["akarr"],
            "os_info": {"product_name": "Windows 11 Pro", "display_version": "23H2", "build_number": "22631"},
            "update_info": {"pending_updates_count": 0, "reboot_required": False},
            "hardware_info": {"free_disk_gb": 115.0, "architecture": "x86_64"},
            "ip_address": "10.14.20.118",
            "status": "GREEN",
            "event_state": "ACTIVE",
            "last_seen": time.time(),
            "is_mock": True
        }
    ]

    for pc in mock_pcs:
        FLEET_DB[pc["hostname"]] = pc

    return {"status": "SUCCESS", "added": len(mock_pcs)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8080, reload=True)