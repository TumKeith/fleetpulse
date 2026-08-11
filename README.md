# FleetPulse Control & Dispatch Plane 🖥️⚡

An enterprise-grade **Remote Monitoring & Management (RMM)** and **IT Dispatch Engine** built natively for Windows environments using Python (FastAPI), SQLite, Win32 APIs, and Tailwind CSS. **FleetPulse** provides exception-based fleet triage, real-time Windows update auditing, Active Directory user mapping, technician shift dispatching, background service telemetry, and one-click Remote Desktop (RDP) remediation.

---

## 🌟 Key Capabilities

### 🏢 1. Master SOC Control Plane (/)
- **🚨 Priority-Based Exception Triage:** Compact, scannable lists segregating **Critical**, **Warning**, **Network Outages**, and **Compliant Fleet** rows.
- **📡 Smart Connectivity Diagnostics:** Automatically distinguishes graceful off-shift user shutdowns from unexpected active network drops.
- **🔄 Auto-Enforcement Guardrails:** Re-evaluates compliance thresholds on every heartbeat—automatically overriding manual remediation if underlying system issues persist.
- **📊 SQLite Database Persistence:** All machine telemetry, technician shifts, and audit logs persist reliably across server restarts (leetpulse.db).

### 👥 2. Multi-Technician Workload Dispatch
- **📊 Automated Load Balancing:** Automatically routes new critical issues to active, **ON_DUTY** technicians based on lowest current workload.
- **📅 Shift & Duty Roster:** Tracks technician status (**ON DUTY**, **OFF DUTY**, **ON LEAVE**), instantly bypassing off-shift techs.
- **🔄 Manual Ticket Reassignment:** SOC Leads can manually reassign machines between technicians directly from the modal interface.

### 🛠️ 3. Dedicated Technician Desk (/tech)
- **🔐 Individual Tech Workspaces:** Distraction-free portal showing *only* the specific workstation tasks assigned to the logged-in technician.
- **🖥️ One-Click Native RDP Launch:** Spawns native Windows Remote Desktop (mstsc.exe) directly targeting the endpoint IP.
- **⚡ Background Shell Remediation:** Triggers remote shell actions (*Flush DNS*, *Restart Windows Update Service*, *Force USOClient Scan*).

### 🔒 4. Enterprise Agent Security & Windows Service
- **📦 Windows Background Service:** Automated PowerShell setup (install_service.ps1) using NSSM to run gent.py on system boot without user login.
- **🛡️ Bearer Token Authentication:** All telemetry heartbeats and command polling endpoints are protected via shared bearer token verification (FleetPulse-Enterprise-Key-2026-Secure).
- **📜 Comprehensive Audit Logging:** Tracks all technician actions, RDP launches, and command executions into a structured audit log table.

---

## 🏛️ System Architecture

`	ext
 ┌────────────────────────────────────────────────────────────────────────┐
 │                      FLEETPULSE CONTROL PLANE                          │
 │      (FastAPI Server • SQLite Database • AD Sync • Bearer Auth)        │
 └───────────────────┬────────────────────────────────┬───────────────────┘
                     │                                │
 (1. Telemetry Heartbeats - Bearer Auth)      (2. Tech Portal Dispatch)
                     ▼                                ▼
┌──────────────────────────┐        ┌──────────────────────────┐
│ FleetPulseAgent Service  │        │ Technician Desk (/tech)  │
│ (NSSM / Win32 Registry)  │        │ (Dedicated Task Queue)   │
└────────────┬─────────────┘        └────────────┬─────────────┘
             │                                   │
             └───────────────┬───────────────────┘
                             │ (3. Direct Remediate / RDP)
                             ▼
              ┌─────────────────────────────┐
              │  Target Endpoint Workstation│
              │  (mstsc.exe / USOClient)    │
              └─────────────────────────────┘
🚀 Quick Start Guide
1. Installation & Environment Setup
PowerShell
cd C:\FleetPulse
python -m venv venv
.\venv\Scripts\activate
pip install fastapi uvicorn jinja2 requests pywin32
2. Launch Central Control Server
PowerShell
.\venv\Scripts\activate
python server.py
Master Admin Dashboard: http://localhost:8080

Technician Desk Portal: http://localhost:8080/tech

3. Install & Start Background Agent Service (Admin Terminal)
PowerShell
# Open PowerShell as Administrator
cd C:\FleetPulse
.\install_service.ps1
