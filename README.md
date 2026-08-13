# ⚡ FleetPulse IT Management Console & Threat Remediation Plane

An enterprise-grade **Remote Monitoring & Management (RMM)** and **IT Dispatch Engine** built natively for Windows environments using Python (FastAPI), SQLite, Win32 APIs, and Tailwind CSS. **FleetPulse** provides exception-based fleet triage, real-time threat telemetry, dynamic Win32 user identity resolution, technician shift dispatching, rogue network asset discovery, and automated device isolation.

---

## 🌟 Key Capabilities

### 🏢 1. Master SOC Control Plane (`/`)
- **🚨 Priority-Based Exception Triage:** Compact, scannable views segregating **Priority 1 Critical / Threat Activity**, **Priority 2 Warnings**, and **Priority 3 Compliant Fleet** rows.
- **📡 Smart Connectivity Diagnostics:** Automatically distinguishes graceful user shutdowns from unexpected network drops.
- **🛡️ Behavioral Threat Telemetry:** Monitors real-time CPU load (%) and RAM utilization (%) via native Win32 APIs—automatically flagging endpoints as **RED (Critical)** if CPU spikes above 90% (detecting potential cryptojacking, ransomware loops, or rogue processes).
- **📊 SQLite Database Persistence:** Machine telemetry, technician profiles, SLA analytics, and audit trail logs persist reliably across server restarts (`fleetpulse.db`).

### 👥 2. Multi-Technician Workload Dispatch & Shift Engine
- **📊 Automated Load Balancing:** Automatically routes new critical issues to active, **ON_DUTY** technicians based on lowest current workload.
- **📅 Shift & Duty Roster:** Tracks technician statuses (`🟢 Active`, `🟡 Out of Office`, `🔴 On Leave`).
- **🔄 Dynamic Shift Re-Assignment:** When a technician toggles their state to *Out of Office* or *On Leave*, all open active incidents in their queue automatically re-route to available on-duty technicians.
- **📈 SLA & MTTR Tracking:** Calculates live Mean Time to Remediate (MTTR) performance across all resolved incidents.

### 👥 3. Dedicated Technician Desk (`/tech`)
- **🔐 Individual Tech Workspaces:** Features a profile login modal so support technicians access a workspace showing *only* their assigned queue.
- **🖥️ One-Click Native RDP Launch:** Spawns native Windows Remote Desktop (`mstsc.exe`) directly targeting the endpoint IP.
- **⚡ Remote Shell Remediation:** Triggers instant remote remediation commands (*Flush DNS*, *Restart Windows Update Service*, *Force Scan*).
- **💬 Direct Comms Integration:** Built-in 1-click links to launch Outlook emails or Microsoft Teams chats directly with the endpoint owner.

### 🔍 4. Rogue Asset Discovery & Device Isolation
- **🌐 Subnet ARP Scanning:** Background discovery worker scans local ARP tables to detect online IPs lacking active `agent.py` heartbeats.
- **🏷️ MAC OUI Vendor Fingerprinting:** Automatically identifies hardware vendors (Apple, Cisco, HP, Synology, Raspberry Pi, Dell, Intel) from MAC address prefixes.
- **🔎 Port Fingerprinting:** Probes common administrative ports (80, 443, 9100, 22, 3389) to classify unmanaged appliances (Printers, Web Routers, SSH hosts).
- **🚫 Blacklist & Network Isolation:** Admins can tag authorized appliances, trigger remote agent deployments, or execute network blacklisting to sever rogue device connectivity.

### 🔒 5. Enterprise Agent & Win32 User Identity Pipeline
- **🔑 Pure Win32 Registry Email Extractor:** Native `winreg` scanner inspects `HKEY_USERS\<SID>\Software\Microsoft\IdentityCRL` to resolve registered Microsoft 365, Azure AD, and institutional emails directly from active desktop sessions.
- **📦 Windows Background Service:** Automated PowerShell setup (`install_service.ps1`) using NSSM to run `agent.py` on system boot without user login.
- **🛡️ Bearer Token Authentication:** All telemetry heartbeats and command polling endpoints are protected via shared bearer token verification (`FleetPulse-Enterprise-Key-2026-Secure`).
- **📜 System Audit Trail:** Logs all admin overrides, technician shift changes, remote commands, and device isolations into a searchable audit trail modal.

---

## 🏛️ System Architecture

```text
┌────────────────────────────────────────────────────────────────────────┐
│                      FLEETPULSE CONTROL PLANE                          │
│   (FastAPI Server • SQLite Database • Rogue ARP Scanner • Bearer Auth)  │
└───────────────────┬────────────────────────────────┬───────────────────┘
                    │                                │
 (1. Telemetry Heartbeats - Bearer Auth)      (2. Tech Portal Dispatch)
                    ▼                                ▼
┌──────────────────────────┐        ┌──────────────────────────┐
│ FleetPulseAgent Service  │        │ Technician Desk (/tech)  │
│ (NSSM / Win32 winreg)    │        │ (Dedicated Task Queue)   │
└────────────┬─────────────┘        └────────────┬─────────────┘
             │                                   │
             └───────────────┬───────────────────┘
                             │ (3. Direct Remediate / RDP / Blacklist)
                             ▼
              ┌─────────────────────────────┐
              │   Target Endpoint / Network │
              │   (mstsc.exe / Route Block) │
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
🧪 Operational Test Endpoints
Audit Trail Logs API: http://localhost:8080/api/admin/audit-logs

Unmanaged Rogue Assets API: http://localhost:8080/api/fleet/unmanaged

SLA MTTR Performance API: http://localhost:8080/api/analytics/sla


---              