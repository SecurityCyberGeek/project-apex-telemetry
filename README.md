# **Project Apex: MCL40 Active Aero Validation Engine**

![Status](https://img.shields.io/badge/Status-Deployment%20Ready-success?style=for-the-badge)
![Target](https://img.shields.io/badge/Target-F1%202026%20Regulations-orange?style=for-the-badge)
![Stack](https://img.shields.io/badge/Tech-Python%20%7C%20Splunk%20HEC%20%7C%20UDP-blue?style=for-the-badge)
![License](https://img.shields.io/badge/License-Apache%202.0-lightgrey?style=for-the-badge)

## **🏁 Executive Summary**

**Project Apex** is a real-time telemetry validation framework engineered to solve the **"Cold Start" data challenge** for the 2026 Season. It acts as an automated logic gate between the **ATLAS** telemetry stream and **Splunk Mission Control**, validating vehicle compliance against the **FIA \>100J Vertical Oscillation Limit** in real-time.

Crucially, **v2.0** introduces specific logic to detect **Thermally-Induced Aero Squat** (The "Mercedes Loophole"), cross-referencing engine oil temperature with ride-height compression to identify non-linear aerodynamic instability.

## **🚨 V2.0 Critical Updates (Feb 2026\)**

### **1\. Thermal-Aero Coupling Logic ("The Loophole")**

* **Problem:** 2026 Engines running High-Compression maps (18:1 CR) at temps \>105°C generate excess torque, causing unmodeled rear squat (\~2mm).  
* **Solution:** The Edge Validator now correlates Engine\_Oil\_Temp \> 105°C with Rear\_Ride\_Height drops to flag **"CRITICAL: THERMAL\_SQUAT"** events before they trigger a floor stall.

### **2\. CISSP Security Hardening**

* **Credentials:** All hardcoded API tokens have been removed. Secrets are now injected via os.getenv for secure deployment within **Cisco IOx** or **Docker** containers at the MTC.  
* **Network:** UDP Receive Buffer increased to **1MB** to prevent packet loss during high-frequency telemetry bursts (300kph+ cornering).

### **3\. Head-to-Head A/B Validation**

* **Capability:** The pipeline now handles simultaneous streams for **CAR\_1 (Lando)** and **CAR\_81 (Oscar)**, allowing Race Engineers to benchmark experimental aero maps against a stable control group in real-time.

## **🏗 Architecture**

The system follows a decoupled **Edge Compute** architecture designed for the MTC Network:

``` mermaid
graph LR  
    subgraph "Trackside / MTC Edge"  
    A\[ATLAS Forwarder\] \--\>|"UDP (60Hz)"| B(Edge Validator Service)  
    end  
      
    subgraph "Logic Core"  
    B \--\>|"Thermal Check (\>105C)"| C{Compliance Gate}  
    C \--\>|"Stable"| D\[Discard/Log\]  
    C \--\>|"Violation (\>100J)"| E\[Splunk HEC\]  
    end  
      
    subgraph "Mission Control"  
    E \--\>|"HTTPS (JSON)"| F\[Dashboard Visualization\]  
    end

    style E fill:\#FF8000,stroke:\#333,stroke-width:2px,color:\#fff
```

* **Ingest:** Raw UDP Stream from ATLAS (Trackside/MTC).  
* **Compute:** Python 3.10 Service running on Cisco Edge / Local Server.  
* **Visualization:** Splunk Enterprise (Dark Mode Mission Control).

## **📂 Project Structure**

| File | Purpose |
| :---- | :---- |
| **production\_validator\_service\_prod.py** | **\[PRODUCTION\]** The main Edge Logic. Listens for live car data, applies the 100J/Thermal logic, and transmits to Splunk. |
| **mission\_control\_dashboard.xml** | **\[UI\]** The Splunk XML definition for the dashboard, including the "Ghost Panel" for thermal alerts. |
| **requirements.txt** | Dependency manifest for the Python environment. |
| **simulation\_tools/** | *Folder containing production\_atlas\_bridge.py for "Digital Twin" validation and head-to-head simulations.* |

## **🚀 Deployment Guide (MTC/Trackside)**

### **Prerequisites**

* Python 3.10+ environment  
* Network access to the ATLAS Forwarding Port (UDP 20777\)  
* Splunk HEC Token (Injected via Environment Variable)

### **1\. Setup Environment**

export SPLUNK\_HEC\_URL="\[https://splunk-hec.mclaren.internal:8088/services/collector\](https://splunk-hec.mclaren.internal:8088/services/collector)"  
export SPLUNK\_TOKEN="\[SECURE\_TOKEN\_INJECTED\_BY\_IT\]"  
export LISTEN\_PORT=20777

### **2\. Launch Validator Service**

python3 production\_validator\_service\_prod.py

### **3\. Verification**

Monitor standard output for the initiation handshake:

\[\*\] PROJECT APEX: LIVE VALIDATOR SERVICE STARTED ON PORT 20777

\[\*\] LOGIC PROFILE: MCL40\_THERMAL\_AERO\_V2

## 📚 Operations Manual (SOP)

For detailed operational protocols, incident response playbooks, and the "Mercedes Loophole" physics breakdown, refer to the official documentation.

[**View Project Apex: MCL40 Operations Manual (v2.1) on Notion ↗**]([Project Apex Operational Manual](https://www.notion.so/Project-Apex-MCL40-Operations-Manual-3011300163bc80caaeabf7c81d3ab233?source=copy_link))

## **🎥 Concept Demonstration**

**Digital Twin Validation (Shadow Mode):** Watch the 90-second Tech Demo visualizing the oscillation logic in action.

[![Project Apex Demo](https://img.youtube.com/vi/4t1N5uW8Gqk/0.jpg)](https://youtu.be/4t1N5uW8Gqk)

## **👤 Author**

**Timothy D. Harmon, CISSP**

* **Role:** Senior Active Aero Validation Engineer (Proposed)  
* **Specialty:** Telemetry Data Analysis & Systems Security  
* **Credential:** Cisco Insider Champion | BMMC Marshal

*Built on the **Splunk Operational Intelligence** platform.*
