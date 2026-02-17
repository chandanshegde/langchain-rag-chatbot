# Connection Timeout Error

## Problem
Tasks fail with "Connection timeout after 30 seconds" error message.

## Symptoms
- Task starts successfully
- Hangs during execution
- Fails after 30 seconds with timeout error
- Network connectivity appears normal

## Root Causes
1. **Firewall blocking outbound connections** - Port 443 or 80 may be blocked
2. **DNS resolution failure** - Cannot resolve target hostname
3. **Target service is down** - Remote service not responding
4. **Network latency** - High latency causes timeout before response
5. **Proxy configuration** - Incorrect or missing proxy settings

## Resolution Steps

### Step 1: Check Firewall Rules
```bash
# Check if ports are open
telnet target-host 443
nc -zv target-host 443

# Check firewall rules (Linux)
sudo iptables -L -n | grep 443

# Check firewall rules (Windows)
netsh advfirewall firewall show rule name=all
```

### Step 2: Verify DNS Resolution
```bash
# Test DNS lookup
nslookup target-host
dig target-host

# Try with alternate DNS
nslookup target-host 8.8.8.8
```

### Step 3: Test Network Connectivity
```bash
# Ping target
ping target-host

# Trace route
traceroute target-host  # Linux
tracert target-host     # Windows

# Check network latency
mtr target-host
```

### Step 4: Increase Timeout Value
Edit task configuration and increase timeout from 30 to 60 seconds:
```yaml
tasks:
  - name: your-task
    timeout: 60  # seconds
```

### Step 5: Configure Proxy (if applicable)
```bash
# Set environment variables
export HTTP_PROXY=http://proxy.company.com:8080
export HTTPS_PROXY=http://proxy.company.com:8080
export NO_PROXY=localhost,127.0.0.1
```

## Prevention
- Monitor network latency regularly
- Set up alerts for connection timeouts
- Implement retry logic with exponential backoff
- Use connection pooling to reuse connections
- Configure appropriate timeout values based on network conditions

## Related Issues
- Network unreachable error
- Permission denied error
- DNS resolution failures
