# **Project Apex: Telemetry Validation Engine (v1.0)**

![Status](https://img.shields.io/badge/Status-Deployment%20Ready-success?style=for-the-badge)
![Target](https://img.shields.io/badge/Target-F1%202026%20Regulations-orange?style=for-the-badge)
![Stack](https://img.shields.io/badge/Tech-Python%20%7C%20Splunk%20HEC%20%7C%20UDP-blue?style=for-the-badge)
![License](https://img.shields.io/badge/License-Apache%202.0-lightgrey?style=for-the-badge)

**Strategic Objective:** Mitigate 2026 "Cold Start" data risks by benchmarking synthetic physics baselines against active aero regulation constraints prior to physical track testing.

## **1.0 Executive Summary**

The 2026 regulatory reset renders historical vehicle telemetry obsolete, creating a critical validation gap prior to the MCL40 physical launch. **Project Apex** bridges this gap by utilizing the Simulation environment as the "Ground Truth."

The system pipelines high-frequency physics telemetry (60Hz) directly into **Splunk Enterprise** via the HTTP Event Collector (HEC). This enables a real-time "Mission Control" environment to validate ride-height stability and detect sub-second latency oscillation (porpoising) anomalies.

## **2.0 Technical Demonstration**

**Proof of Concept:** Real-time detection of a critical aerodynamic instability event at 250 KPH.

[![Project Apex Demo](https://img.youtube.com/vi/4t1N5uW8Gqk/0.jpg)](https://youtu.be/4t1N5uW8Gqk)

## **3.0 System Architecture**

The solution utilizes a modular **Adapter Pattern**. The logic core remains constant, while the ingestion layer is hot-swappable between Simulation (Dev) and Track (Prod) environments.

```mermaid
graph LR  
    subgraph Data Sources  
    A\[Simulator / iRacing\] \--\>|UDP 60Hz| B(Ingestion Bridge)  
    A2\[MTC Telemetry Bus\] \-.-\>|Kafka / ATLAS| B  
    end  
      
    subgraph Logic Core  
    B \--\>|JSON Serialization| C{Physics Validator}  
    C \--\>|Energy Calculation| D\[Constraint Engine\]  
    end  
      
    subgraph Mission Control  
    D \--\>|Critical Alerts| E((Splunk HEC))  
    E \--\>|Real-Time| F\[Dashboard Visualization\]  
    end  
      
    style A fill:\#f9f,stroke:\#333,stroke-width:2px  
    style E fill:\#FF8000,stroke:\#333,stroke-width:2px,color:\#fff
```

### **3.1 Production Core (/src)**

*Target Environment: MTC / Pit Wall*

* **production\_atlas\_bridge.py**: Enterprise-grade ingestor designed to interface with the proprietary ATLAS telemetry bus.  
* **production\_validator\_service\_prod.py**: The hardened logic engine. Features SSL verification, environment-variable security, and multi-car concurrency state management.

### **3.2 Simulation Harness (/demo)**

*Target Environment: Local Development / iRacing*

* **iracing\_feed.py**: A custom UDP bridge that creates a 1:1 "Digital Twin" data stream, enforcing the 2026 driver narrative (CAR\_1).  
* **production\_validator\_service\_v3.py**: The local version of the logic core, configured for the demo environment (includes HEC throttling to prevent localhost latency).  
* **ghost\_piastri.py**: Traffic simulator (CAR\_81) used to validate the dashboard's ability to handle multi-vehicle concurrency.

### **3.3 Visualization (/dashboards)**

* **apex\_dashboard\_universal.xml**: The Splunk XML source for the "Mission Control" interface.  
  * **Capabilities:** Head-to-Head Telemetry, Real-Time Porpoising Detection, and Historical Replay.  
  * **Tech:** Utilizes robust Regex extraction to handle nested JSON payloads from HEC with sub-second latency.

## **4.0 Deployment Protocol**

### **4.1 Prerequisites**

* Python 3.10+ environment  
* Splunk Enterprise (Local or Cloud) with HEC enabled (Port 8088\)  
* iRacing Simulator (for live physics generation)

### **4.2 Configuration**

1. **Clone Repository:**  
```Python
    git clone \[https://github.com/your-username/project-apex-telemetry.git\](https://github.com/your-username/project-apex-telemetry.git)  
   cd project-apex-telemetry
```

3. **Install Dependencies:**  
```Python
   pip install requests irsdk
```

4. **Splunk Setup:**  
   * Import dashboards/apex\_dashboard\_universal.xml into a new Classic Dashboard.  
   * Generate HEC Token (Source Type: \_json).  
   * Update the SPLUNK\_HEC\_TOKEN variable in demo/production\_validator\_service\_v2.py.
      
5. **Execution (Demo Mode):**  
   \# Terminal 1: Start the Logic Core
```Python  
   python demo/production\_validator\_service\_v2.py
```

   \# Terminal 2: Start the Simulation Bridge  
```Python
   python demo/iracing\_feed.py
```

## **5.0 Attribution**

Copyright © 2026 Timothy D. Harmon, CISSP  
Licensed under the Apache 2.0 License.  
**Author Credentials:**

* **M.A.S. Data Science and Engineering**  
* **Motorsport UK Licensed** (RS Clubman & Esports)  
* **SCCA Operations Volunteer**

*Built for the 2026 Era.*
