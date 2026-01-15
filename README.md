# **Project Apex: F1 2026 Telemetry Validation Engine**

> **Author:** Timothy D. Harmon, CISSP
> **Copyright:** © 2026 Timothy D. Harmon, CISSP. All Rights Reserved.
> **Status:** Portfolio Technical Demonstration.

**NOTICE:** This codebase is a conceptual prototype designed specifically for the F1 2026 Regulatory Environment. While open for review, it is not authorized for commercial redistribution or uncredited use.
==============================================================================================================================================================================================================
**Project Apex** is a physics-based validation system designed to solve the "Cold Start" data challenge presented by the 2026 Formula 1 regulations. With historical data rendered obsolete, this system treats the Simulator as the "Ground Truth," validating active aero performance constraints in real-time before the physical chassis undergoes shakedown.

## **🏁 Mission Architecture**

The system bridges the gap between the virtual car (Simulation) and Mission Control (Splunk) using a low-latency, modular architecture.

* **Ingest:** Python UDP Bridge captures physics telemetry at 60Hz.  
* **Transport:** Data is serialized to JSON and pipelined via **Splunk HTTP Event Collector (HEC)**.  
* **Logic:** A local validator engine calculates vertical oscillation energy to detect porpoising events (\>100 Joules).  
* **Visualization:** "Mission Control" Dashboard for real-time monitoring of development vs. baseline chassis.

## **📂 Repository Structure**

### **/demo (Simulation Environment)**

Scripts used to demonstrate the system using iRacing as a high-fidelity physics proxy.

* iracing\_feed.py: Captures live telemetry, enforces "CAR\_1" ID, and creates synthetic porpoising events for validation testing.  
* ghost\_piastri.py: Simulates a stable baseline car ("CAR\_81") for multi-vehicle dashboard testing.  
* production\_validator\_service\_v2.py: The local server that processes incoming UDP packets and forwards them to Splunk.

### **/src (Production/MTC Deployment)**

Hardened scripts designed for deployment on the pit wall or MTC data center.

* production\_atlas\_bridge.py: Replaces the iRacing feed. Connects to the ATLAS Telemetry Server / Kafka Bus.  
* production\_validator\_service\_prod.py: Enterprise-grade service with SSL verification, environment variable security, and optimized indexing.

### **/dashboards**

* apex\_dashboard\_universal.xml: Source XML for the Splunk Mission Control interface. Features Regex-based extraction for universal compatibility and dual-stream (Head-to-Head) visualization.

## **🚀 Quick Start (Demo Mode)**

**Prerequisites:**

* Python 3.9+  
* Splunk Enterprise (Local or Cloud) with HEC enabled on port 8088\.  
* iRacing (for live physics generation).

**Installation:**

```pip install \-r requirements.txt```

**Execution:**

1. **Start the Service:**

   ```python demo/production\_validator\_service\_v2.py```

   *Note: Update SPLUNK\_HEC\_TOKEN in the script before running.*
   
3. **Start the Bridge:**  

   ```python demo/iracing\_feed.py```

5. **(Optional) Start Ghost Car:**  

   ```python demo/ghost\_piastri.py```

## **🛡️ License & Certification**

Built by **Timothy D. Harmon, CISSP**.

* Master of Advanced Studies in Data Science & Engineering 
* Motorsport UK Licensed (RS Clubman & Esports)  
* SCCA Operations Volunteer
