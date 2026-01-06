# SMTP Tunnel - Technical Documentation

This document provides in-depth technical details about the SMTP Tunnel Proxy, including protocol design, DPI evasion techniques, security analysis, and implementation details.

> For basic setup and usage, see [README.md](README.md).

---

## Table of Contents

- [Why SMTP?](#why-smtp)
- [How It Bypasses DPI](#how-it-bypasses-dpi)
- [Why It's Fast](#why-its-fast)
- [Architecture](#architecture)
- [Protocol Design](#protocol-design)
- [Component Details](#component-details)
- [Security Analysis](#security-analysis)
- [Domain vs IP Address](#domain-name-vs-ip-address-security-implications)
- [Advanced Configuration](#advanced-configuration)

---

## Why SMTP?

SMTP (Simple Mail Transfer Protocol) is the protocol used for sending emails. It's an excellent choice for tunneling because:

### 1. Ubiquitous Traffic
- Email is essential infrastructure - blocking it breaks legitimate services
- SMTP traffic on port 587 (submission) is expected and normal
- Millions of emails traverse networks every second

### 2. Expected to be Encrypted
- STARTTLS is standard for SMTP - encrypted email is normal
- DPI systems expect to see TLS-encrypted SMTP traffic
- No red flags for encrypted content

### 3. Flexible Protocol
- SMTP allows large data transfers (attachments)
- Binary data is normal (MIME-encoded attachments)
- Long-lived connections are acceptable

### 4. Hard to Block
- Blocking port 587 would break email for everyone
- Can't easily distinguish tunnel from real email after TLS
- Would require blocking all encrypted email

---

## How It Bypasses DPI

Deep Packet Inspection (DPI) systems analyze network traffic to identify and block certain protocols or content. Here's how SMTP Tunnel evades detection:

### Phase 1: The Deception (Plaintext)

```
┌──────────────────────────────────────────────────────────────┐
│                    DPI CAN SEE THIS                          │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Server: 220 mail.example.com ESMTP Postfix (Ubuntu)         │
│  Client: EHLO client.local                                   │
│  Server: 250-mail.example.com                                │
│          250-STARTTLS                                        │
│          250-AUTH PLAIN LOGIN                                │
│          250 8BITMIME                                        │
│  Client: STARTTLS                                            │
│  Server: 220 2.0.0 Ready to start TLS                        │
│                                                              │
│  DPI Analysis: "This is a normal email server connection"    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**What DPI sees:**
- Standard SMTP greeting from "Postfix" mail server
- Normal capability negotiation
- STARTTLS upgrade (expected for secure email)

**What makes it convincing:**
- Greeting matches real Postfix servers
- Capabilities list is realistic
- Proper RFC 5321 compliance
- Port 587 is standard SMTP submission port

### Phase 2: TLS Handshake

```
┌──────────────────────────────────────────────────────────────┐
│                    DPI CAN SEE THIS                          │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  [TLS 1.2/1.3 Handshake]                                     │
│  - Client Hello                                              │
│  - Server Hello                                              │
│  - Certificate Exchange                                      │
│  - Key Exchange                                              │
│  - Finished                                                  │
│                                                              │
│  DPI Analysis: "Normal TLS for email encryption"             │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**What DPI sees:**
- Standard TLS handshake
- Server certificate for mail domain
- Normal cipher negotiation

### Phase 3: Encrypted Tunnel (Invisible)

```
┌──────────────────────────────────────────────────────────────┐
│                   DPI CANNOT SEE THIS                        │
│                   (Encrypted with TLS)                       │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Client: EHLO client.local                                   │
│  Server: 250-mail.example.com                                │
│          250-AUTH PLAIN LOGIN                                │
│          250 8BITMIME                                        │
│  Client: AUTH PLAIN <token>                                  │
│  Server: 235 2.7.0 Authentication successful                 │
│  Client: BINARY                                              │
│  Server: 299 Binary mode activated                           │
│                                                              │
│  [Binary streaming begins - raw TCP tunnel]                  │
│                                                              │
│  DPI Analysis: "Encrypted email session, cannot inspect"     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**What DPI sees:**
- Encrypted TLS traffic
- Packet sizes and timing consistent with email
- Cannot inspect content

**What actually happens:**
- Authentication with pre-shared key
- Switch to binary streaming mode
- Full-speed TCP tunneling

### Why DPI Can't Detect It

| DPI Technique | Why It Fails |
|---------------|--------------|
| **Port Analysis** | Uses standard SMTP port 587 |
| **Protocol Detection** | Initial handshake is valid SMTP |
| **TLS Fingerprinting** | Standard Python SSL library |
| **Packet Size Analysis** | Variable sizes, similar to email |
| **Timing Analysis** | No distinctive patterns |
| **Deep Inspection** | Content encrypted with TLS |

---

## Why It's Fast

Previous versions used SMTP commands for every data packet, requiring:
- 4 round-trips per data chunk (MAIL FROM → RCPT TO → DATA → response)
- Base64 encoding (33% overhead)
- MIME wrapping (more overhead)

### The New Approach: Protocol Upgrade

```
┌─────────────────────────────────────────────────────────────┐
│                    HANDSHAKE PHASE                          │
│                    (One time only)                          │
├─────────────────────────────────────────────────────────────┤
│  EHLO → STARTTLS → TLS → EHLO → AUTH → BINARY               │
│                                                             │
│  Time: ~200-500ms (network latency dependent)               │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    STREAMING PHASE                          │
│                    (Rest of session)                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────┬────────────┬────────────┬─────────────┐        │
│  │  Type   │ Channel ID │   Length   │   Payload   │        │
│  │ 1 byte  │  2 bytes   │  2 bytes   │  N bytes    │        │
│  └─────────┴────────────┴────────────┴─────────────┘        │
│                                                             │
│  - Full duplex - send and receive simultaneously            │
│  - No waiting for responses                                 │
│  - 5 bytes overhead per frame (vs hundreds for SMTP)        │
│  - Raw binary - no base64 encoding                          │
│  - Speed limited only by network bandwidth                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Performance Comparison

| Metric | Old SMTP Method | New Binary Method |
|--------|-----------------|-------------------|
| **Overhead per packet** | ~500+ bytes | 5 bytes |
| **Round trips per send** | 4 | 0 (streaming) |
| **Encoding overhead** | 33% (base64) | 0% |
| **Duplex mode** | Half-duplex | Full-duplex |
| **Effective speed** | ~10-50 KB/s | Limited by bandwidth |

---

## Architecture

### System Components

```
YOUR COMPUTER                           YOUR VPS                        INTERNET
┌────────────────────┐                  ┌────────────────────┐          ┌─────────┐
│                    │                  │                    │          │         │
│  ┌──────────────┐  │                  │  ┌──────────────┐  │          │ Website │
│  │   Browser    │  │                  │  │    Server    │  │          │   API   │
│  │   or App     │  │                  │  │   server.py  │  │          │ Service │
│  └──────┬───────┘  │                  │  └──────┬───────┘  │          │         │
│         │          │                  │         │          │          └────┬────┘
│         │ SOCKS5   │                  │         │ TCP      │               │
│         ▼          │                  │         ▼          │               │
│  ┌──────────────┐  │   TLS Tunnel     │  ┌──────────────┐  │               │
│  │    Client    │◀─┼──────────────────┼─▶│   Outbound   │◀─┼───────────────┘
│  │   client.py  │  │   Port 587       │  │  Connector   │  │
│  └──────────────┘  │                  │  └──────────────┘  │
│                    │                  │                    │
└────────────────────┘                  └────────────────────┘
     Censored Network                      Free Internet
```

### Data Flow

```
1. Browser wants to access https://example.com

2. Browser → SOCKS5 (client.py:1080)
   "CONNECT example.com:443"

3. Client → Server (port 587, looks like SMTP)
   [FRAME: CONNECT, channel=1, "example.com:443"]

4. Server → example.com:443
   [Opens real TCP connection]

5. Server → Client
   [FRAME: CONNECT_OK, channel=1]

6. Browser ↔ Client ↔ Server ↔ example.com
   [Bidirectional data streaming]
```

---

## Protocol Design

### Frame Format (Binary Mode)

All communication after handshake uses this simple binary frame format:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
├─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┼─┤
│     Type      │          Channel ID           │    Length     │
├───────────────┼───────────────────────────────┼───────────────┤
│    Length     │            Payload...                         │
├───────────────┼───────────────────────────────────────────────┤
│                        Payload (continued)                    │
└───────────────────────────────────────────────────────────────┘

Type (1 byte):
  0x01 = DATA         - Tunnel data
  0x02 = CONNECT      - Open new channel
  0x03 = CONNECT_OK   - Connection successful
  0x04 = CONNECT_FAIL - Connection failed
  0x05 = CLOSE        - Close channel

Channel ID (2 bytes): Identifies the connection (supports 65535 simultaneous connections)
Length (2 bytes): Payload size (max 65535 bytes)
Payload (variable): The actual data
```

### CONNECT Payload Format

```
┌───────────────┬─────────────────────────┬───────────────┐
│  Host Length  │         Host            │     Port      │
│   (1 byte)    │    (variable, UTF-8)    │   (2 bytes)   │
└───────────────┴─────────────────────────┴───────────────┘
```

### Session State Machine

```
                    ┌─────────┐
                    │  START  │
                    └────┬────┘
                         │
                         ▼
              ┌─────────────────────┐
              │   TCP Connected     │
              └──────────┬──────────┘
                         │ 220 greeting
                         ▼
              ┌─────────────────────┐
              │   EHLO Exchange     │
              └──────────┬──────────┘
                         │ 250 OK
                         ▼
              ┌─────────────────────┐
              │     STARTTLS        │
              └──────────┬──────────┘
                         │ 220 Ready
                         ▼
              ┌─────────────────────┐
              │   TLS Handshake     │
              └──────────┬──────────┘
                         │ Success
                         ▼
              ┌─────────────────────┐
              │   EHLO (post-TLS)   │
              └──────────┬──────────┘
                         │ 250 OK
                         ▼
              ┌─────────────────────┐
              │   AUTH PLAIN        │
              └──────────┬──────────┘
                         │ 235 Success
                         ▼
              ┌─────────────────────┐
              │   BINARY Command    │
              └──────────┬──────────┘
                         │ 299 OK
                         ▼
              ┌─────────────────────┐
              │   Binary Streaming  │◀──────┐
              │   (Full Duplex)     │───────┘
              └─────────────────────┘
```

---

## Component Details

### server.py - Server Component

**Purpose:** Runs on your VPS in an uncensored network. Accepts tunnel connections and forwards traffic to the real internet.

**What it does:**
- Listens on port 587 (SMTP submission)
- Presents itself as a Postfix mail server
- Handles SMTP handshake (EHLO, STARTTLS, AUTH)
- Switches to binary streaming mode after authentication
- Manages multiple tunnel channels
- Forwards data to destination servers
- Sends responses back through the tunnel

**Key Classes:**
| Class | Description |
|-------|-------------|
| `TunnelServer` | Main server, accepts connections |
| `TunnelSession` | Handles one client connection |
| `Channel` | Represents one tunneled TCP connection |

### client.py - Client Component

**Purpose:** Runs on your local computer. Provides a SOCKS5 proxy interface and tunnels traffic through the server.

**What it does:**
- Runs SOCKS5 proxy server on localhost:1080
- Connects to tunnel server on port 587
- Performs SMTP handshake to look legitimate
- Switches to binary streaming mode
- Multiplexes multiple connections over single tunnel
- Handles SOCKS5 CONNECT requests from applications

**Key Classes:**
| Class | Description |
|-------|-------------|
| `TunnelClient` | Manages connection to server |
| `SOCKS5Server` | Local SOCKS5 proxy |
| `Channel` | One proxied connection |

### common.py - Shared Utilities

**Purpose:** Code shared between client and server.

**What it contains:**
| Component | Description |
|-----------|-------------|
| `TunnelCrypto` | Handles authentication tokens |
| `TrafficShaper` | Padding and timing (optional stealth) |
| `SMTPMessageGenerator` | Generates realistic email content (legacy) |
| `FrameBuffer` | Parses binary frames from stream |
| `load_config()` | YAML configuration loader |
| `ServerConfig` | Server configuration dataclass |
| `ClientConfig` | Client configuration dataclass |

### generate_certs.py - Certificate Generator

**Purpose:** Creates TLS certificates for the tunnel.

**What it generates:**
| File | Description |
|------|-------------|
| `ca.key` | Certificate Authority private key |
| `ca.crt` | Certificate Authority certificate |
| `server.key` | Server private key |
| `server.crt` | Server certificate (signed by CA) |

**Features:**
- Customizable hostname in certificate
- Configurable key size (default 2048-bit RSA)
- Configurable validity period
- Includes proper extensions for TLS server auth

---

## Security Analysis

### Authentication Flow

```
┌─────────────────────────────────────────────────────────────┐
│                  Authentication Flow                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Client generates timestamp                              │
│                                                             │
│  2. Client computes:                                        │
│     HMAC-SHA256(secret, "smtp-tunnel-auth:" + timestamp)    │
│                                                             │
│  3. Client sends: AUTH PLAIN base64(timestamp + ":" + hmac) │
│                                                             │
│  4. Server verifies:                                        │
│     - Timestamp within 5 minutes (prevents replay)          │
│     - HMAC matches (proves knowledge of secret)             │
│                                                             │
│  5. Server responds: 235 Authentication successful          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Encryption Layers

| Layer | Protection |
|-------|------------|
| **TLS 1.2+** | All traffic after STARTTLS |
| **Pre-shared Key** | Authentication |
| **HMAC-SHA256** | Token integrity |

### Threat Model

| Threat | Mitigation |
|--------|------------|
| Passive eavesdropping | TLS encryption |
| Active MITM | Certificate verification (requires domain) |
| Replay attacks | Timestamp validation (5-minute window) |
| Unauthorized access | Pre-shared key authentication |
| Protocol detection | SMTP mimicry during handshake |

### Security Recommendations

1. **Use a strong secret:** Generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`

2. **Keep secret secure:** Never commit to version control, share securely

3. **Use certificate verification:** Copy `ca.crt` to client and set `ca_cert` in config

4. **Restrict server access:** Use whitelist to limit source IPs if possible

5. **Monitor logs:** Watch for failed authentication attempts

6. **Update regularly:** Keep Python and dependencies updated

---

## Domain Name vs IP Address: Security Implications

### Understanding TLS Certificate Verification

TLS certificates are digital documents that prove a server's identity. When your client connects to a server, it can verify:

1. **The certificate is signed by a trusted authority** (in our case, your own CA)
2. **The certificate matches who you're connecting to** (hostname/IP verification)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     TLS Certificate Verification Process                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Client wants to connect to: mail.example.com                               │
│                                                                             │
│  Step 1: Server presents certificate                                        │
│          ┌─────────────────────────────────────┐                            │
│          │ Certificate Contents:               │                            │
│          │   Subject: mail.example.com         │                            │
│          │   SAN: DNSName=mail.example.com     │                            │
│          │   Signed by: Your CA                │                            │
│          └─────────────────────────────────────┘                            │
│                                                                             │
│  Step 2: Client checks                                                      │
│          - Is certificate signed by trusted CA? → YES                       │
│          - Does "mail.example.com" match SAN?   → YES                       │
│                                                                             │
│  Step 3: Connection established securely                                    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### The IP Address Problem

TLS certificates store identifiers in specific fields within the **Subject Alternative Name (SAN)** extension:

| Identifier Type | SAN Field Type | Example |
|-----------------|----------------|---------|
| Domain name | `DNSName` | `mail.example.com` |
| IP address | `IPAddress` | `192.168.1.100` |

**These are different field types.** A certificate generated with `--hostname 192.168.1.100` creates:

```
SAN: DNSName = "192.168.1.100"    ← This is what happens
SAN: IPAddress = 192.168.1.100   ← This is what would be needed
```

When the TLS library verifies a connection to an IP address, it looks for a matching `IPAddress` field, **not** a `DNSName` field. Even if the values are identical, the types don't match, so verification fails.

### Man-in-the-Middle Attack Explained

When certificate verification is disabled, an attacker can intercept your connection:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Man-in-the-Middle Attack Scenario                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  WITHOUT Certificate Verification (ca_cert not set):                        │
│                                                                             │
│  ┌────────┐       ┌────────────┐       ┌────────────┐       ┌────────┐     │
│  │ Client │──────▶│  Attacker  │──────▶│  Firewall  │──────▶│ Server │     │
│  │        │◀──────│  (MITM)    │◀──────│   (DPI)    │◀──────│        │     │
│  └────────┘       └────────────┘       └────────────┘       └────────┘     │
│       │                 │                                                   │
│       │    Attacker presents          Attacker decrypts your traffic,      │
│       │    their own certificate      reads everything, re-encrypts        │
│       │                               and forwards to real server          │
│       │                 │                                                   │
│       │    Client accepts it                                                │
│       │    (no verification!)                                               │
│       │                                                                     │
│       ▼                                                                     │
│    YOUR TRAFFIC IS COMPLETELY EXPOSED TO THE ATTACKER                       │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  WITH Certificate Verification (ca_cert set + domain name):                 │
│                                                                             │
│  ┌────────┐       ┌────────────┐                                            │
│  │ Client │──────▶│  Attacker  │                                            │
│  │        │   X   │  (MITM)    │                                            │
│  └────────┘       └────────────┘                                            │
│       │                 │                                                   │
│       │    Attacker presents          Client checks certificate:           │
│       │    their own certificate      "This isn't signed by my CA!"        │
│       │                               CONNECTION REFUSED                    │
│       │                 │                                                   │
│       │    Attack blocked!                                                  │
│       │                                                                     │
│       ▼                                                                     │
│    Client connects directly to real server (or not at all)                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Security Options Comparison

| Configuration | MITM Protected? | Works? | Recommended? |
|---------------|-----------------|--------|--------------|
| Domain + `ca_cert` set | **YES** | YES | **BEST** |
| Domain + no `ca_cert` | NO | YES | Not ideal |
| IP address + `ca_cert` set | — | NO | Won't work |
| IP address + no `ca_cert` | NO | YES | Vulnerable |

### Risk Assessment

| Threat | With Verification | Without Verification |
|--------|-------------------|----------------------|
| Passive eavesdropping | Protected (TLS) | Protected (TLS) |
| Active MITM by ISP | Protected | **Vulnerable** |
| Active MITM by government | Protected | **Vulnerable** |
| Server impersonation | Protected | **Vulnerable** |
| DPI bypass | Works | Works |

**Bottom line:** TLS encryption protects against passive eavesdropping in both cases. But only with certificate verification are you protected against **active** attacks where someone intercepts and impersonates your server.

---

## Advanced Configuration

### Full Configuration Reference

```yaml
# ============================================================================
# Server Configuration (for server.py on VPS)
# ============================================================================
server:
  # Interface to listen on
  # "0.0.0.0" = all interfaces (recommended)
  # "127.0.0.1" = localhost only
  host: "0.0.0.0"

  # Port to listen on
  # 587 = SMTP submission (recommended, expected for email)
  # 465 = SMTPS (alternative)
  # 25 = SMTP (often blocked)
  port: 587

  # Hostname for SMTP greeting and TLS certificate
  # Should match your server's DNS name for authenticity
  hostname: "mail.example.com"

  # Pre-shared secret for authentication
  # MUST be identical on client and server
  # Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
  secret: "CHANGE-ME-TO-RANDOM-SECRET"

  # TLS certificate files
  cert_file: "server.crt"
  key_file: "server.key"

  # IP whitelist (optional)
  # Empty list = allow all connections
  # Supports individual IPs and CIDR notation
  whitelist: []
  # whitelist:
  #   - "192.168.1.100"
  #   - "10.0.0.0/8"

# ============================================================================
# Client Configuration (for client.py on local machine)
# ============================================================================
client:
  # Server domain name (FQDN required for certificate verification)
  # Use free DNS: DuckDNS, No-IP, FreeDNS, Dynu, or CloudFlare
  server_host: "yourdomain.duckdns.org"

  # Server port (must match server config)
  server_port: 587

  # Local SOCKS5 proxy port
  socks_port: 1080

  # Local SOCKS5 bind address
  # "127.0.0.1" = localhost only (recommended)
  # "0.0.0.0" = allow external connections (use with caution!)
  socks_host: "127.0.0.1"

  # Pre-shared secret (MUST match server!)
  secret: "CHANGE-ME-TO-RANDOM-SECRET"

  # CA certificate for server verification (RECOMMENDED)
  # Required to prevent Man-in-the-Middle attacks
  # Copy ca.crt from server to client
  ca_cert: "ca.crt"

# ============================================================================
# Stealth Configuration (optional, for legacy SMTP mode)
# ============================================================================
stealth:
  # Random delay range between messages (milliseconds)
  min_delay_ms: 50
  max_delay_ms: 500

  # Message padding sizes
  pad_to_sizes:
    - 4096
    - 8192
    - 16384

  # Probability of dummy messages
  dummy_message_probability: 0.1
```

### SMTP Protocol Compliance

The tunnel implements these SMTP RFCs during handshake:
- **RFC 5321** - Simple Mail Transfer Protocol
- **RFC 3207** - SMTP Service Extension for Secure SMTP over TLS
- **RFC 4954** - SMTP Service Extension for Authentication

### Multiplexing

Multiple TCP connections are multiplexed over a single tunnel:

```
┌─────────────────────────────────────────────────────────────┐
│                    Single TLS Connection                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Channel 1: Browser Tab 1 → google.com:443                  │
│  Channel 2: Browser Tab 2 → github.com:443                  │
│  Channel 3: curl → ifconfig.me:443                          │
│  Channel 4: SSH → remote-server:22                          │
│  ...                                                        │
│  Channel 65535: Maximum concurrent connections              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Memory Usage

- **Server:** ~50MB base + ~1MB per active connection
- **Client:** ~30MB base + ~0.5MB per active channel

### Concurrency Model

Both client and server use Python's `asyncio` for efficient handling of multiple simultaneous connections without threads.

---

## Version Information

- **Current Version:** 1.0.0
- **Protocol Version:** Binary streaming v1
- **Minimum Python:** 3.8
