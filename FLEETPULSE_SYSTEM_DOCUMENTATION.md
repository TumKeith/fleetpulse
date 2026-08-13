# ⚡ FLEETPULSE CENTRAL IT COMMAND SERVER & EDR AGENT
### Technical System Architecture & Endpoint Telemetry Specification

---

## 1. Executive Summary
FleetPulse is an enterprise-grade Remote Monitoring & Management (RMM) and Endpoint Detection & Response (EDR) platform engineered specifically for modern Windows NT desktop and server fleets. It provides sub-second exception triage, dynamic technician workload balancing, native Win32 user profile extraction, and automated network threat isolation—all operating within an ultra-lightweight footprint.

---

## 2. Platform Architecture & Data Flow

```text
┌────────────────────────────────────────────────────────────────────────┐
│                      FLEETPULSE CONTROL PLANE                          │
│   (FastAPI Server • SQLite Persistence • Rogue Scanner • Bearer Auth)  │
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

3. Comprehensive Data Telemetry Matrix
The background agent.py service collects the following structured telemetry during every heartbeat cycle (every 10 seconds):

A. Identity & Session Context
System Username: Active desktop interactive user logged into Windows (Win32_ComputerSystem).

Active User Full Name: Retrieved from local SAM account database (Win32_UserAccount).

Session Email Address: Extracted natively via winreg from Windows Identity stores (HKEY_USERS\<SID>\Software\Microsoft\IdentityCRL\UserExtendedProperties). Resolves true Microsoft 365, Azure AD, and institutional emails without Active Directory overhead.

B. Hardware & Operating System Metrics
Exact OS Build & Version: Extracted using native C-bindings via ntdll.dll (RtlGetVersion) to bypass Windows 11 compatibility shims.

CPU Load Percentage: Real-time processor utilization sampled via WMI CIM instances.

Physical Memory (RAM) Load: Sampled via native Win32 kernel API GlobalMemoryStatusEx.

Primary Disk Metrics: Free disk space calculation on system root drive (C:\).

C. Network & System State
IP Address Resolution: Primary local IPv4 address bound to network interface.

Windows Update Compliance: Pending OS updates count and reboot flags.

Event State: Active system state vs. graceful shutdown events.

4. Key Platform Features
🏢 SOC Dispatch Console (/)
Priority Triage: Segregates machines into Priority 1 (Critical & High CPU > 90%), Priority 2 (Warnings & Pending Updates), and Priority 3 (Healthy).

Rogue Network Asset Explorer: Scans local ARP tables every 30 seconds to detect unmanaged online IPs lacking agent heartbeats. Resolves hardware manufacturers using IEEE MAC OUI vendor lookups and probes administrative services.

Network Isolation Engine: Allows 1-click blacklisting of rogue endpoints by executing dead-end routing blocks (route add).

👥 Technician Workstation Portal (/tech)
Isolated Queue Views: Dedicated workspace allowing support staff to view only their assigned incident tickets.

Automated Shift Re-Assignment Engine: Toggling a technician's shift status to Out of Office or On Leave automatically re-routes active tickets to on-duty personnel.

1-Click Remote Remediation: Instant native RDP session launch (mstsc.exe), direct Teams/Outlook communication links, and remote shell action queuing (Flush DNS, Restart WU, USOClient).

5. Technology Stack & Dependencies
Language: Python 3.10+

Backend Framework: FastAPI, Uvicorn

Database: SQLite3 (fleetpulse.db) with full transactional persistence

Frontend UI: HTML5, Jinja2 Templates, Tailwind CSS (CDN), FontAwesome 6

Windows System Libraries: ctypes, winreg, subprocess, platform, socket

Service Manager: NSSM (Non-Sucking Service Manager)              