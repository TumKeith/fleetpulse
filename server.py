#!/usr/bin/env python3
"""
=============================================================================
 FLEETPULSE CENTRAL IT COMMAND SERVER
 Dispatch Plane, MAC OUI Fingerprinting, Rogue IP Discovery, & Blacklist Isolation
=============================================================================
"""

import os
import json
import time
import socket
import subprocess
import threading
from typing import Dict, List, Set
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

import database as db
import notifier

app = FastAPI(title="FleetPulse IT Management Console")

db.init_db()

os.makedirs("templates", exist_ok=True)
templates = Jinja2Templates(directory="templates")

EXPECTED_AGENT_TOKEN = "Bearer FleetPulse-Enterprise-Key-2026-Secure"

COMMAND_QUEUE: Dict[str, List[dict]] = {}
COMMAND_RESULTS: Dict[str, List[dict]] = {}
DISCOVERED_UNMANAGED_DEVICES: List[dict] = []
WHITELISTS_APPLIANCES: Set[str] = set()
BLACKLISTED_DEVICES: Set[str] = set()

FALLBACK_AD_DIRECTORY = {
    "admin": {"full_name": "System Administrator", "department": "IT Infrastructure", "email": "admin@company.com"},
    "jdoe": {"full_name": "Jane Doe", "department": "Finance", "email": "jdoe@company.com"},
    "mwilson": {"full_name": "Mark Wilson", "department": "Engineering", "email": "mwilson@company.com"},
}

MAC_VENDOR_PREFIXES = {
    "00:50:56": "VMware Virtual Machine",
    "00:0C:29": "VMware ESXi Host",
    "00:15:5D": "Microsoft Hyper-V",
    "00:11:32": "Synology NAS Server",
    "00:04:F2": "Polycom VoIP Phone",
    "B8:27:EB": "Raspberry Pi Foundation",
    "DC:A6:32": "Raspberry Pi Trading",
    "FC:FB:FB": "Cisco Systems",
    "AC:D1:B8": "Apple Inc.",
    "F4:D4:88": "Apple Inc.",
    "3C:D9:2B": "Hewlett Packard",
    "00:1A:4B": "Hewlett Packard",
    "70:8BCD": "Dell Inc.",
    "00:1A:6B": "Intel Corporation"
}

def identify_vendor_by_mac(mac: str) -> str:
    clean_mac = mac.upper().replace("-", ":")
    prefix = ":".join(clean_mac.split(":")[:3]) if len(clean_mac.split(":")) >= 3 else ""
    return MAC_VENDOR_PREFIXES.get(prefix, "Generic Network Device")

def probe_open_ports(ip: str) -> str:
    common_ports = {
        80: "Web Service / Router UI",
        443: "Secure Web Portal",
        9100: "Network Printer (JetDirect)",
        22: "Linux/SSH Server",
        3389: "Unmanaged RDP Endpoint"
    }
    for port, label in common_ports.items():
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.01)
            result = sock.connect_ex((ip, port))
            sock.close()
            if result == 0:
                return label
        except Exception:
            pass
    return "Unknown Endpoint Service"

def isolate_network_ip(ip: str):
    """Executes network routing isolation commands for blacklisted endpoints."""
    try:
        cmd = f"route add {ip} mask 255.255.255.255 127.0.0.1 metric 1"
        subprocess.run(cmd, shell=True, capture_output=True, text=True)
    except Exception as e:
        print(f"[Isolation Error] {e}")

def run_unmanaged_network_discovery():
    global DISCOVERED_UNMANAGED_DEVICES
    while True:
        try:
            cmd = "arp -a"
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                managed_ips = {d.get("ip_address") for d in db.get_all_devices()}
                unmanaged = []
                
                for line in res.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 3 and parts[0].count(".") == 3:
                        ip = parts[0]
                        mac = parts[1]
                        if not ip.startswith("224.") and not ip.startswith("239.") and not ip.endswith(".255") and ip != "127.0.0.1":
                            if ip in BLACKLISTED_DEVICES:
                                isolate_network_ip(ip)
                            elif ip not in managed_ips and ip not in WHITELISTS_APPLIANCES:
                                vendor = identify_vendor_by_mac(mac)
                                service = probe_open_ports(ip)
                                unmanaged.append({
                                    "ip_address": ip,
                                    "mac_address": mac,
                                    "vendor": vendor,
                                    "detected_service": service,
                                    "status": "UNMANAGED"
                                })
                DISCOVERED_UNMANAGED_DEVICES = unmanaged
        except Exception as e:
            print(f"[Discovery Error] {e}")
        time.sleep(30)

threading.Thread(target=run_unmanaged_network_discovery, daemon=True).start()

def query_active_directory_ldap(username: str) -> dict:
    return FALLBACK_AD_DIRECTORY.get(
        username,
        {"full_name": username.title() if username else "Unassigned", "department": "General Operations", "email": f"{username}@company.com"}
    )

def verify_agent_token(authorization: str = Header(None)):
    if authorization != EXPECTED_AGENT_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized Agent Access")

def calculate_health_status(os_info: dict, update_info: dict, hw_info: dict, event_state: str) -> str:
    if event_state == "GRACEFUL_SHUTDOWN":
        return "OFFLINE_SHUTDOWN"

    pending_updates = update_info.get("pending_updates_count", 0)
    reboot_needed = update_info.get("reboot_required", False)
    free_disk_gb = hw_info.get("free_disk_gb", 100)
    cpu_percent = hw_info.get("cpu_percent", 0.0)

    if free_disk_gb < 10 or pending_updates > 10 or cpu_percent > 90.0:
        return "RED"
    if reboot_needed or pending_updates > 0 or cpu_percent > 70.0:
        return "AMBER"
    return "GREEN"

def auto_assign_technician() -> str:
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
        return JSONResponse({"status": "ERROR", "message": "Name and email required"}, status_code=400)
    
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
                    db.log_audit_event(dev["hostname"], "SYSTEM", "AUTO_REASSIGN", f"Reassigned from {tech_name} ({new_status}) to {new_tech}")

    return {"status": "SUCCESS"}

# --- Telemetry Ingestion ---
@app.post("/api/telemetry/heartbeat")
async def receive_heartbeat(data: dict, authorization: str = Header(None)):
    verify_agent_token(authorization)
    
    hostname = data.get("hostname", "UNKNOWN-PC")
    username = data.get("logged_user", "").lower()
    event_state = data.get("event_state", "ACTIVE")

    ad_profile = query_active_directory_ldap(username)
    
    agent_fullname = data.get("user_full_name")
    agent_email = data.get("user_email")

    if agent_fullname:
        ad_profile["full_name"] = agent_fullname
    if agent_email:
        ad_profile["email"] = agent_email

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

    if status == "RED" and previous_status != "RED":
        pending_updates = data.get("update_info", {}).get("pending_updates_count", 0)
        free_disk = data.get("hardware_info", {}).get("free_disk_gb", "N/A")
        cpu_load = data.get("hardware_info", {}).get("cpu_percent", "N/A")
        issue_summary = f"CPU: {cpu_load}% | Free Disk: {free_disk}GB | Pending Updates: {pending_updates}"

        alert_thread = threading.Thread(
            target=notifier.send_critical_alert,
            args=(hostname, data.get("ip_address", "127.0.0.1"), ad_profile.get("full_name", username), issue_summary)
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

@app.get("/api/fleet/unmanaged")
async def get_unmanaged_devices():
    return {"unmanaged": DISCOVERED_UNMANAGED_DEVICES}

@app.post("/api/admin/unmanaged/whitelist")
async def whitelist_unmanaged_device(payload: dict):
    ip = payload.get("ip")
    if ip:
        WHITELISTS_APPLIANCES.add(ip)
        db.log_audit_event(ip, "ADMIN", "WHITELIST_APPLIANCE", f"Tagged IP {ip} as authorized network appliance")
        return {"status": "SUCCESS"}
    return JSONResponse({"status": "ERROR", "message": "Missing IP"}, status_code=400)

@app.post("/api/admin/unmanaged/blacklist")
async def blacklist_unmanaged_device(payload: dict):
    """Adds rogue IP address to persistent isolation list and triggers network blocks."""
    ip = payload.get("ip")
    if ip:
        BLACKLISTED_DEVICES.add(ip)
        isolate_network_ip(ip)
        db.log_audit_event(ip, "ADMIN", "BLACK_LIST_ISOLATE", f"Severed & Blacklisted rogue IP {ip}")
        return {"status": "SUCCESS", "message": f"IP {ip} blacklisted and isolated"}
    return JSONResponse({"status": "ERROR", "message": "Missing IP"}, status_code=400)

@app.get("/api/admin/audit-logs")
async def get_audit_logs():
    conn = db.get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 100")
    rows = cursor.fetchall()
    conn.close()
    return {"logs": [dict(r) for r in rows]}

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
        dev["hardware_info"]["cpu_percent"] = 15.0
        
        db.save_device(dev)
        db.log_audit_event(hostname, "TECH", "REMEDIATED", f"Issue resolved. SLA time: {round(resolution_seconds, 1)}s")
        return {"status": "SUCCESS"}
    return JSONResponse({"status": "ERROR", "message": "Host not found"}, status_code=404)

@app.get("/api/analytics/sla")
async def get_sla_analytics():
    techs = db.get_all_techs()
    total_resolved = sum(t.get("resolved_count", 0) for t in techs)
    total_time = sum(t.get("total_resolution_time", 0.0) for t in techs)
    mttr_seconds = round(total_time / total_resolved, 1) if total_resolved > 0 else 0.0
    return {"total_resolved_incidents": total_resolved, "mean_time_to_remediate_seconds": mttr_seconds, "technician_performance": techs}

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
            "hardware_info": {"free_disk_gb": 8.2, "cpu_percent": 94.5, "ram_percent": 88.0, "architecture": "x86_64"},
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
            "hardware_info": {"free_disk_gb": 240.5, "cpu_percent": 42.0, "ram_percent": 60.0, "architecture": "x86_64"},
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