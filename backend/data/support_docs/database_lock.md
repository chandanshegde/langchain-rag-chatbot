# Database Lock Timeout

## Problem
Tasks fail with "Database lock timeout" when trying to access database.

## Symptoms
- Multiple tasks running concurrently
- Error: `database is locked`
- Error: `could not obtain lock on row`
- Long-running queries blocking other operations

## Root Causes
1. **Long-running transactions** - Transactions holding locks too long
2. **Deadlocks** - Two transactions waiting for each other
3. **Missing indexes** - Slow queries holding locks longer
4. **High concurrency** - Too many concurrent write operations
5. **SQLite limitations** - Single writer at a time

## Resolution Steps

### Step 1: Identify Blocking Queries
```sql
-- PostgreSQL: Find blocking queries
SELECT pid, usename, query, state
FROM pg_stat_activity
WHERE state = 'active';

-- Find locks
SELECT * FROM pg_locks WHERE granted = false;
```

### Step 2: Kill Blocking Sessions
```sql
-- PostgreSQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE pid = <blocking_pid>;

-- MySQL
SHOW PROCESSLIST;
KILL <process_id>;
```

### Step 3: Optimize Queries
```sql
-- Add indexes for frequently queried columns
CREATE INDEX idx_task_runs_status ON task_runs(status);
CREATE INDEX idx_task_runs_start_time ON task_runs(start_time);

-- Use shorter transactions
BEGIN;
  UPDATE tasks SET status = 'running' WHERE id = 1;
COMMIT;  -- Commit immediately
```

### Step 4: Increase Timeout
```python
# SQLite: Increase busy timeout
conn.execute("PRAGMA busy_timeout = 30000")  # 30 seconds

# PostgreSQL: Set statement timeout
SET statement_timeout = '60s';
```

### Step 5: Implement Retry Logic
```python
import time

def execute_with_retry(query, max_retries=3):
    for attempt in range(max_retries):
        try:
            return cursor.execute(query)
        except DatabaseLocked:
            if attempt == max_retries - 1:
                raise
            time.sleep(0.1 * (2 ** attempt))  # Exponential backoff
```

## Prevention
- Keep transactions short
- Add appropriate indexes
- Use READ COMMITTED isolation level
- Implement connection pooling
- Consider using a multi-writer database (PostgreSQL, MySQL)
- Queue write operations

## Related Issues
- Connection timeout
- Performance degradation
- Deadlock errors
