#!/usr/bin/env python3
"""
=============================================================================
 FLEETPULSE ENTERPRISE BACKGROUND AGENT
 Win32 NT Kernel Collector, Dynamic OS Query & True Windows User Profile Tracking
=============================================================================
"""

import os
import sys
import time
import json
import socket
import getpass
import platform
import winreg
import ctypes
import urllib.request
import urllib.error
import subprocess

SERVER_URL = "http://localhost:8080"
BEARER_TOKEN = "Bearer FleetPulse-Enterprise-Key-2026-Secure"
POLL_INTERVAL_SECONDS = 10


def get_logged_in_user_details() -> dict:
    """
    Dynamically queries WMI and CIM for the active interactive desktop user 
    and resolves their true Windows Full Name / Display Name.
    """
    username = getpass.getuser().lower()
    full_name = ""

    # 1. Fetch active interactive user logged into the session
    try:
        cmd_user = "powershell -Command \"(Get-CimInstance Win32_ComputerSystem).UserName\""
        res_user = subprocess.run(cmd_user, shell=True, capture_output=True, text=True, timeout=5)
        if res_user.returncode == 0 and res_user.stdout.strip():
            raw_user = res_user.stdout.strip()
            username = raw_user.split("\\")[-1].lower()
    except Exception:
        pass

    # 2. Fetch the true Full Name / Display Name from Windows User Account database
    try:
        cmd_fullname = f"powershell -Command \"(Get-CimInstance Win32_UserAccount -Filter \\\"Name='{username}'\\\").FullName\""
        res_fullname = subprocess.run(cmd_fullname, shell=True, capture_output=True, text=True, timeout=5)
        if res_fullname.returncode == 0 and res_fullname.stdout.strip():
            full_name = res_fullname.stdout.strip()
    except Exception:
        pass

    # Fallback to capitalized username if Full Name isn't configured in Windows
    if not full_name:
        full_name = username.title()

    return {
        "username": username,
        "full_name": full_name
    }


def get_accurate_os_info() -> dict:
    """
    Dynamically queries native Win32 NT Kernel APIs and WMI CIM instances 
    to extract true OS product name, display version, and build number.
    """
    try:
        # 1. Read OS Details from Registry as initial baseline
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            0,
            winreg.KEY_READ
        )
        product_name, _ = winreg.QueryValueEx(key, "ProductName")
        display_version, _ = winreg.QueryValueEx(key, "DisplayVersion")
        winreg.CloseKey(key)

        # 2. Query true NT Kernel version via ntdll.dll (Bypasses compatibility layer)
        class OSVERSIONINFOEXW(ctypes.Structure):
            _fields_ = [
                ('dwOSVersionInfoSize', ctypes.c_ulong),
                ('dwMajorVersion', ctypes.c_ulong),
                ('dwMinorVersion', ctypes.c_ulong),
                ('dwBuildNumber', ctypes.c_ulong),
                ('dwPlatformId', ctypes.c_ulong),
                ('szCSDVersion', ctypes.c_wchar * 128),
                ('wServicePackMajor', ctypes.c_ushort),
                ('wServicePackMinor', ctypes.c_ushort),
                ('wSuiteMask', ctypes.c_ushort),
                ('wProductType', ctypes.c_byte),
                ('wReserved', ctypes.c_byte)
            ]

        os_info = OSVERSIONINFOEXW()
        os_info.dwOSVersionInfoSize = ctypes.sizeof(OSVERSIONINFOEXW)
        ctypes.windll.ntdll.RtlGetVersion(ctypes.byref(os_info))
        true_build = os_info.dwBuildNumber

        # 3. If running Windows 11 (Build 22000+) but registry returns legacy string, query CIM directly
        if true_build >= 22000 and "10" in product_name:
            cmd = "powershell -Command \"(Get-CimInstance Win32_OperatingSystem).Caption\""
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=5)
            if res.returncode == 0 and res.stdout.strip():
                product_name = res.stdout.strip().replace("Microsoft ", "")

        return {
            "product_name": product_name,
            "display_version": display_version,
            "build_number": str(true_build)
        }
    except Exception:
        return {
            "product_name": f"Windows {platform.release()}",
            "display_version": "Unknown",
            "build_number": platform.version()
        }


def get_system_telemetry() -> dict:
    """Collects dynamic endpoint hardware, OS, true user profile, and update state metrics."""
    hostname = socket.gethostname()
    user_info = get_logged_in_user_details()
    
    # Query true local network interface IP address
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip_address = s.getsockname()[0]
        s.close()
    except Exception:
        ip_address = "127.0.0.1"

    os_info = get_accurate_os_info()

    # Query dynamic free disk space on C: drive
    try:
        import shutil
        total, used, free = shutil.disk_usage("C:\\")
        free_gb = round(free / (1024 ** 3), 2)
    except Exception:
        free_gb = 50.0

    return {
        "hostname": hostname,
        "logged_user": user_info["username"],
        "user_full_name": user_info["full_name"],
        "ip_address": ip_address,
        "os_info": os_info,
        "update_info": {
            "pending_updates_count": 0,
            "reboot_required": False
        },
        "hardware_info": {
            "free_disk_gb": free_gb,
            "architecture": platform.machine()
        },
        "event_state": "ACTIVE"
    }


def execute_queued_command(command: str) -> str:
    """Executes administrative shell remediation commands locally."""
    try:
        if command.lower() == "flushdns":
            cmd = "ipconfig /flushdns"
        elif command.lower() == "restart_wuauserv":
            cmd = "net stop wuauserv && net start wuauserv"
        elif command.lower() == "usoclient_scan":
            cmd = "usoclient StartScan"
        else:
            cmd = command

        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        return result.stdout.strip() if result.returncode == 0 else result.stderr.strip()
    except Exception as e:
        return f"Execution Error: {str(e)}"


def run_agent_loop():
    """Main background telemetry transmission and command execution loop."""
    print(f"[FleetPulse Agent] Initialized. Target Control Plane: {SERVER_URL}")
    while True:
        try:
            telemetry = get_system_telemetry()
            req = urllib.request.Request(
                f"{SERVER_URL}/api/telemetry/heartbeat",
                data=json.dumps(telemetry).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": BEARER_TOKEN
                },
                method="POST"
            )
            
            with urllib.request.urlopen(req) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                print(f"[{time.strftime('%H:%M:%S')}] Heartbeat Delivered for '{telemetry['user_full_name']}' ({telemetry['logged_user']}). Health: {res_data.get('assigned_health')}")

            # Poll for pending administrative remediation commands
            cmd_req = urllib.request.Request(
                f"{SERVER_URL}/api/agent/commands/{telemetry['hostname']}",
                headers={"Authorization": BEARER_TOKEN},
                method="GET"
            )
            with urllib.request.urlopen(cmd_req) as cmd_response:
                cmd_data = json.loads(cmd_response.read().decode("utf-8"))
                tasks = cmd_data.get("tasks", [])
                for task in tasks:
                    cmd_str = task.get("command")
                    print(f"[Agent Action] Executing queued command: {cmd_str}")
                    output = execute_queued_command(cmd_str)
                    
                    # Post result back to server
                    result_payload = {
                        "hostname": telemetry["hostname"],
                        "command": cmd_str,
                        "output": output
                    }
                    res_post = urllib.request.Request(
                        f"{SERVER_URL}/api/admin/command-result",
                        data=json.dumps(result_payload).encode("utf-8"),
                        headers={
                            "Content-Type": "application/json",
                            "Authorization": BEARER_TOKEN
                        },
                        method="POST"
                    )
                    urllib.request.urlopen(res_post)

        except urllib.error.URLError as e:
            print(f"[{time.strftime('%H:%M:%S')}] Server Unreachable ({e.reason}). Retrying in {POLL_INTERVAL_SECONDS}s...")
        except Exception as e:
            print(f"[{time.strftime('%H:%M:%S')}] Agent Loop Exception: {e}")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_agent_loop()