# Disk Full Error

## Problem
Tasks fail with "Resource exhausted: disk full" or "No space left on device" errors.

## Symptoms
- Error: `No space left on device`
- Error: `disk full`
- Unable to write files
- Database write failures
- Log rotation stops working

## Root Causes
1. **Log files growing uncontrolled** - No log rotation
2. **Temp files not cleaned** - /tmp directory full
3. **Database growth** - Large tables or indexes
4. **Docker images/containers** - Unused images consuming space
5. **Failed cleanups** - Cleanup jobs not running

## Resolution Steps

### Step 1: Check Disk Usage
```bash
# Check disk space
df -h

# Find largest directories
du -sh /* | sort -hr | head -10
du -sh /var/log/* | sort -hr | head -20

# Find large files
find / -type f -size +100M -exec ls -lh {} \;
```

### Step 2: Clean Log Files
```bash
# Rotate logs immediately
logrotate -f /etc/logrotate.conf

# Truncate large logs (don't delete running logs!)
> /var/log/application.log

# Remove old logs
find /var/log -name "*.log.*" -mtime +30 -delete
```

### Step 3: Clean Temporary Files
```bash
# Clean /tmp
rm -rf /tmp/*

# Clean package caches
apt-get clean        # Debian/Ubuntu
yum clean all        # RedHat/CentOS
```

### Step 4: Clean Docker Resources
```bash
# Remove unused images
docker system prune -a

# Remove dangling volumes
docker volume prune

# Check Docker disk usage
docker system df
```

### Step 5: Increase Disk Space
```bash
# Resize partition (if VM)
# AWS: Extend EBS volume
# Azure: Resize managed disk
# GCP: Resize persistent disk

# Then extend filesystem
resize2fs /dev/sda1
xfs_growfs /
```

## Prevention
- Implement log rotation (daily/weekly)
- Set up disk space monitoring (alert at 80%)
- Schedule cleanup jobs
- Use external log aggregation (CloudWatch, Splunk)
- Implement retention policies
- Add more storage proactively

## Related Issues
- Out of memory errors
- Performance degradation
- Backup failures
