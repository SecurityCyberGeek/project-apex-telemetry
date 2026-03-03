# Security Policy

## 🛡️ Cyber-Physical Integrity

Project Apex is designed to validate telemetry within a high-performance motorsport
environment. Given the sensitivity of race strategy data, security is a core
architectural pillar — not an afterthought.

---

## Reporting a Vulnerability

This is a research prototype targeting production F1 infrastructure. If you discover
a vulnerability (e.g., UDP spoofing, HEC token leakage, replay attack surface),
please **do not open a public issue**.

**Contact:** info@securitycybergeek.com  
Response target: 48 hours

---

## Threat Model

| Threat | Vector | Mitigation |
|--------|--------|------------|
| Telemetry Spoofing | Malicious UDP packets injecting false sensor data | Binary struct validation — malformed packets dropped immediately |
| Token Exfiltration | HEC token exposed in logs or environment | `os.getenv` only; default token gate halts all transmission |
| Man-in-the-Middle | Interception of Splunk HEC traffic | HTTPS enforced; CA bundle path configurable for internal PKI |
| Resource Exhaustion | UDP flood causing OOM crash | Bounded queue (2048 packets) with tail-drop strategy |
| Replay Attack | Injecting stale telemetry packets | Timestamp freshness validation on struct unpack (1s window) |

---

## Operational Security Features

- **Token Management:** Splunk HEC tokens are injected exclusively via
  Environment Variables (`SPLUNK_APEX_TOKEN`). The service will log a
  security warning and halt all data transmission if the default placeholder
  token is detected at runtime.
- **SSL/TLS:** Production deployments must supply a CA bundle path via the
  `SSL_CA_BUNDLE` environment variable. Encryption in transit is enforced
  in all production configurations.
- **Network Isolation:** The ingestion bridge is designed to operate within
  an air-gapped or VLAN-segmented pit wall network, listening only on
  `localhost` or a specified internal subnet.
- **Non-Root Execution:** The Docker container runs as a non-privileged user
  (`apexuser`, UID 1001) to minimize privilege escalation risk.

---

## Known Limitations (Demo Mode)

The `demo/` scripts intentionally use `verify=False` to facilitate local
testing with self-signed Splunk certificates.

**This configuration is strictly prohibited for MTC production deployment.**
Production containers must mount a valid CA bundle and set:

```bash
export SSL_CA_BUNDLE="/path/to/ca-bundle.crt"
