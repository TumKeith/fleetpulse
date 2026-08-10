# FleetPulse Control Plane 🖥️⚡

An enterprise-grade **Remote Monitoring & Management (RMM)** platform built with Python (FastAPI), Windows Native Win32 APIs, and Tailwind CSS. **FleetPulse** provides exception-based IT fleet triage, real-time Windows update auditing, Active Directory user mapping, and one-click Remote Desktop (RDP) remediation.

---

## 🌟 Key Features

- **🚨 Priority Triage Matrix:** Exception-based UI separating Critical, Warning, Connectivity Drops, and Compliant Fleet rows.
- **📡 Smart Connectivity Diagnostics:** Automatically distinguishes graceful off-shift user shutdowns from unexpected network drops.
- **🛠️ Instant IT Remediation:** One-click remote commands (*Flush DNS*, *Restart Windows Update Service*, *Force Update Scan*).
- **🖥️ Native Remote Desktop Launcher:** One-click mstsc.exe spawning directly targeting endpoint IP addresses.
- **👥 Active Directory Mapping:** Links every computer automatically to its assigned employee, email, and IP phone extension.
- **🔄 Auto-Enforcement Guardrails:** Agent re-evaluates minimum system thresholds on every heartbeat, automatically overriding premature manual remediation if issues persist.

---

## 🏛️ System Architecture

`	ext
 ┌────────────────────────────────────────────────────────────────────────┐
 │                      FLEETPULSE CONTROL PLANE                          │
 │         (FastAPI Server • Active Directory Sync • Tailwind UI)         │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │
         ┌───────────────────────────┼───────────────────────────┐
         │ (Telemetry Heartbeats)    │ (Command Execution)       │ (Native RDP Session)
         ▼                           ▼                           ▼
┌──────────────────┐        ┌──────────────────┐        ┌──────────────────┐
│ Windows Agent    │        │ Subprocess Shell │        │ mstsc.exe        │
│ (Win32 / Registry│        │ (USOClient/DNS)  │        │ Direct Connection│
└──────────────────┘        └──────────────────┘        └──────────────────┘
🚀 Quick Start
1. Installation
PowerShell
cd C:\FleetPulse
python -m venv venv
.\venv\Scripts\activate
pip install fastapi uvicorn jinja2 requests pywin32
2. Run the Command Server
PowerShell
python server.py
# Access dashboard at http://localhost:8080
3. Run Endpoint Telemetry Agent
PowerShell
python agent.py
