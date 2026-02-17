# Out of Memory Error

## Problem
Tasks fail with "Out of memory: Java heap space" or similar memory exhaustion errors.

## Symptoms
- Task runs successfully initially
- Memory usage gradually increases
- System becomes unresponsive
- Task crashes with OOM error
- `java.lang.OutOfMemoryError: Java heap space`

## Root Causes
1. **Insufficient heap memory** - JVM heap size too small for workload
2. **Memory leak** - Objects not being garbage collected
3. **Large data processing** - Loading too much data into memory at once
4. **Inefficient algorithms** - O(n²) or worse complexity
5. **Too many concurrent operations** - Parallel tasks exhausting memory

## Resolution Steps

### Step 1: Increase Heap Memory
```bash
# For Java applications
export JAVA_OPTS="-Xms512m -Xmx2048m"

# In application config
java -Xms1g -Xmx4g -jar application.jar
```

### Step 2: Analyze Memory Usage
```bash
# Get heap dump when OOM occurs
java -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/tmp/dumps

# Analyze heap dump
jmap -heap <pid>
jstat -gc <pid> 1000
```

### Step 3: Optimize Processing
```python
# Bad: Load all data into memory
data = load_entire_dataset()  # DON'T DO THIS
process(data)

# Good: Process in chunks
for chunk in load_data_in_chunks(chunk_size=1000):
    process(chunk)
    del chunk  # Free memory
```

### Step 4: Enable Garbage Collection Logging
```bash
java -Xlog:gc*:file=gc.log \
     -XX:+UseG1GC \
     -XX:MaxGCPauseMillis=200 \
     -jar application.jar
```

### Step 5: Reduce Concurrency
```yaml
# Limit parallel tasks
max_concurrent_tasks: 5  # Reduce from 20
```

## Prevention
- Monitor memory usage with metrics
- Set up alerts for high memory utilization
- Use streaming/iterative processing for large datasets
- Profile application to identify memory leaks
- Set appropriate heap sizes based on workload
- Implement circuit breakers for cascading failures

## Related Issues
- Disk full errors
- Resource exhaustion
- Performance degradation
