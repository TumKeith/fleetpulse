#!/usr/bin/env python3
"""
=============================================================================
 FLEETPULSE ENDPOINT TELEMETRY & COMMAND AGENT
 Windows Native Service Agent with Token Authentication
=============================================================================
"""

import os
import socket
import platform
import time
import subprocess
import signal
import sys
import requests

try:
    import winreg
except ImportError:
    winreg = None

# Shared Secret Token for API Authentication
AGENT_AUTH_TOKEN = "FleetPulse-Enterprise-Key-2026-Secure"

SERVER_URL = "http://localhost:8080/api/telemetry/heartbeat"
COMMAND_URL = "http://localhost:8080/api/agent/commands"
FEEDBACK_URL = "http://localhost:8080/api/admin/command-result"

HEADERS = {
    "Authorization": f"Bearer {AGENT_AUTH_TOKEN}",
    "Content-Type": "application/json"
}


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip_addr = s.getsockname()[0]
        s.close()
        return ip_addr
    except Exception:
        return "127.0.0.1"


def get_windows_registry_info():
    if not winreg:
        return {"product_name": platform.system(), "display_version": "N/A", "build_number": platform.release()}

    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
        product_name, _ = winreg.QueryValueEx(key, "ProductName")
        try:
            display_version, _ = winreg.QueryValueEx(key, "DisplayVersion")
        except FileNotFoundError:
            display_version = "Unknown"
        current_build, _ = winreg.QueryValueEx(key, "CurrentBuild")
        return {
            "product_name": product_name,
            "display_version": display_version,
            "build_number": current_build
        }
    except Exception as e:
        return {"error": str(e), "product_name": "Windows 10 Pro", "display_version": "23H2", "build_number": "22631"}


def get_update_and_reboot_status():
    reboot_pending = False
    if winreg:
        try:
            reboot_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired"
            winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reboot_key)
            reboot_pending = True
        except FileNotFoundError:
            reboot_pending = False

    return {
        "pending_updates_count": 0,
        "reboot_required": reboot_pending
    }


def get_hardware_info():
    free_gb = 50
    try:
        if platform.system() == "Windows":
            import shutil
            total, used, free = shutil.disk_usage("C:\\")
            free_gb = round(free / (1024 ** 3), 1)
    except Exception:
        pass

    return {
        "free_disk_gb": free_gb,
        "architecture": platform.machine()
    }


def send_shutdown_signal():
    hostname = socket.gethostname()
    payload = {
        "hostname": hostname,
        "logged_user": os.getlogin() if hasattr(os, "getlogin") else "admin",
        "ip_address": get_local_ip(),
        "os_info": get_windows_registry_info(),
        "update_info": get_update_and_reboot_status(),
        "hardware_info": get_hardware_info(),
        "event_state": "GRACEFUL_SHUTDOWN"
    }
    try:
        requests.post(SERVER_URL, json=payload, headers=HEADERS, timeout=2)
    except Exception:
        pass


def handle_exit_signals(sig, frame):
    send_shutdown_signal()
    sys.exit(0)


signal.signal(signal.SIGINT, handle_exit_signals)
signal.signal(signal.SIGTERM, handle_exit_signals)


def process_pending_commands(hostname: str):
    try:
        res = requests.get(f"{COMMAND_URL}/{hostname}", headers=HEADERS, timeout=3)
        if res.status_code == 200:
            tasks = res.json().get("tasks", [])
            for task in tasks:
                cmd_type = task.get("command")

                output_text = ""
                success = False

                if cmd_type == "FLUSH_DNS":
                    cmd_res = subprocess.run("ipconfig /flushdns", shell=True, capture_output=True, text=True)
                    output_text = cmd_res.stdout or cmd_res.stderr
                    success = (cmd_res.returncode == 0)

                elif cmd_type == "RESTART_WUAUSERV":
                    cmd_res = subprocess.run("net stop wuauserv && net start wuauserv", shell=True, capture_output=True, text=True)
                    output_text = cmd_res.stdout or cmd_res.stderr
                    success = (cmd_res.returncode == 0)

                elif cmd_type == "CHECK_UPDATES":
                    cmd_res = subprocess.run("usoctl StartScan", shell=True, capture_output=True, text=True)
                    output_text = "Windows Update Scan triggered via USOClient."
                    success = True

                feedback_payload = {
                    "hostname": hostname,
                    "command": cmd_type,
                    "success": success,
                    "output": output_text.strip()
                }
                requests.post(FEEDBACK_URL, json=feedback_payload, headers=HEADERS, timeout=3)
    except Exception:
        pass


def send_telemetry():
    hostname = socket.gethostname()
    logged_user = os.getlogin() if hasattr(os, "getlogin") else "admin"
    ip_addr = get_local_ip()

    payload = {
        "hostname": hostname,
        "logged_user": logged_user,
        "ip_address": ip_addr,
        "os_info": get_windows_registry_info(),
        "update_info": get_update_and_reboot_status(),
        "hardware_info": get_hardware_info(),
        "event_state": "ACTIVE"
    }

    try:
        res = requests.post(SERVER_URL, json=payload, headers=HEADERS, timeout=5)
        if res.status_code == 200:
            process_pending_commands(hostname)
    except Exception:
        pass


if __name__ == "__main__":
    while True:
        send_telemetry()
        time.sleep(10)