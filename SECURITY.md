# **Security Policy**

## **🛡️ Cyber-Physical Integrity**

Project Apex is designed to validate telemetry within a high-performance motorsport environment. Given the sensitivity of race strategy data, security is a core architectural pillar.

### **Reporting a Vulnerability**

This is a research prototype. If you discover a vulnerability (e.g., UDP spoofing, HEC token leakage), please do not open a public issue.

* **Email:** tiharmon@ucsd.edu

### **Operational Security Features**

* **Token Management:** Splunk HEC tokens are ingested via Environment Variables (SPLUNK\_APEX\_TOKEN), never hardcoded in production streams.  
* **SSL/TLS:** The production service (production\_validator\_service\_prod.py) enforces strict SSL certificate verification for data in transit.  
* **Network Isolation:** The ingestion bridge is designed to operate within an air-gapped or VLAN-segmented pit wall network, listening only on localhost or specific internal subnets.

### **Known Limitations (Demo Mode)**

The demo/ scripts intentionally disable SSL verification (verify=False) to facilitate local testing with self-signed Splunk certificates. This configuration is **strictly prohibited** for the MTC production environment.
