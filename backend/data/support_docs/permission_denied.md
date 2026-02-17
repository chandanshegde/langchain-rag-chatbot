# Permission Denied Error

## Problem
Tasks fail with "Permission denied: access forbidden" or similar authorization errors.

## Symptoms
- Error: `Permission denied`
- Error: `Access forbidden`
- HTTP 403 Forbidden
- File system: `EACCES` error

## Root Causes
1. **Insufficient file permissions** - User lacks read/write/execute permissions
2. **Wrong user context** - Task running as wrong user
3. **Missing IAM roles** - Cloud resources lack proper roles
4. **API key issues** - Invalid or expired API credentials
5. **SELinux/AppArmor** - Security policies blocking access

## Resolution Steps

### Step 1: Check File Permissions
```bash
# Check current permissions
ls -la /path/to/file

# Fix permissions
chmod 644 file.txt      # rw-r--r--
chmod 755 script.sh     # rwxr-xr-x
chmod -R 755 directory/

# Change ownership
chown user:group file.txt
```

### Step 2: Verify User Context
```bash
# Check current user
whoami
id

# Run as different user
sudo -u targetuser ./script.sh

# Check process owner
ps aux | grep process-name
```

### Step 3: Check Cloud IAM Roles
```bash
# AWS: Check IAM roles
aws sts get-caller-identity
aws iam get-user

# Azure: Check role assignments
az role assignment list --assignee <user-email>

# GCP: Check permissions
gcloud projects get-iam-policy <project-id>
```

### Step 4: Verify API Credentials
```python
# Check environment variables
import os
print(os.getenv('API_KEY'))

# Verify API key validity
curl -H "Authorization: Bearer $API_KEY" https://api.example.com/verify
```

### Step 5: Check SELinux/AppArmor
```bash
# SELinux: Check status
getenforce

# View denials
ausearch -m avc -ts recent

# Set permissive mode (temporary)
sudo setenforce 0

# AppArmor: Check status
sudo aa-status
```

## Prevention
- Use principle of least privilege
- Implement proper IAM roles
- Rotate credentials regularly
- Use service accounts for automated tasks
- Document required permissions
- Test with minimal permissions first

## Related Issues
- Authentication failures
- File not found errors
- Network unreachable errors
