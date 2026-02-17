"""
Database Setup Script

WHAT THIS DOES:
- Creates SQLite database (like CREATE DATABASE in MySQL)
- Defines schema (tables, columns, constraints)
- Seeds with dummy data (~50 records)

SQLite vs MySQL/PostgreSQL:
- File-based (no server needed) - perfect for demos
- SQL syntax is 99% the same
- ACID compliant, supports transactions
- Used by: Android, iOS, browsers, embedded systems
"""

import sqlite3
from datetime import datetime, timedelta
import random

def create_database():
    """Create database and tables"""
    
    # Connect to database (creates file if doesn't exist)
    # Similar to: DriverManager.getConnection() in Java
    conn = sqlite3.connect('data/database.db')
    cursor = conn.cursor()
    
    # Drop tables if they exist (for clean setup)
    cursor.execute('DROP TABLE IF EXISTS task_runs')
    cursor.execute('DROP TABLE IF EXISTS tasks')
    cursor.execute('DROP TABLE IF EXISTS projects')
    
    print("Creating tables...")
    
    # ========================================================================
    # PROJECTS TABLE
    # Stores project information (like your Informatica projects/domains)
    # ========================================================================
    cursor.execute('''
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            created_date DATE NOT NULL,
            status TEXT CHECK(status IN ('active', 'archived', 'maintenance')) DEFAULT 'active'
        )
    ''')
    
    # ========================================================================
    # TASKS TABLE
    # Individual tasks within projects (like workflows/mappings)
    # ========================================================================
    cursor.execute('''
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            task_type TEXT CHECK(task_type IN ('build', 'test', 'deploy', 'backup', 'migration')) NOT NULL,
            description TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id),
            UNIQUE(project_id, name)
        )
    ''')
    
    # ========================================================================
    # TASK_RUNS TABLE
    # Execution history (like workflow runs)
    # This is where analytics queries will run
    # ========================================================================
    cursor.execute('''
        CREATE TABLE task_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            start_time DATETIME NOT NULL,
            end_time DATETIME,
            status TEXT CHECK(status IN ('success', 'failed', 'running', 'cancelled')) NOT NULL,
            error_message TEXT,
            duration_seconds INTEGER,
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        )
    ''')
    
    # Create indexes for faster queries
    # Similar to: @Index annotation in JPA
    cursor.execute('CREATE INDEX idx_task_runs_status ON task_runs(status)')
    cursor.execute('CREATE INDEX idx_task_runs_start_time ON task_runs(start_time)')
    cursor.execute('CREATE INDEX idx_tasks_type ON tasks(task_type)')
    
    conn.commit()
    print("[OK] Tables created")
    
    return conn, cursor

def seed_data(conn, cursor):
    """Insert dummy data"""
    
    print("\nSeeding data...")
    
    # ========================================================================
    # SEED PROJECTS (5 projects with space theme)
    # ========================================================================
    projects = [
        ('Apollo', 'Customer data processing pipeline', 'active'),
        ('Titan', 'Real-time analytics platform', 'active'),
        ('Voyager', 'Legacy data migration', 'maintenance'),
        ('Phoenix', 'Disaster recovery system', 'active'),
        ('Orion', 'Data warehouse ETL', 'archived')
    ]
    
    project_ids = {}
    for i, (name, desc, status) in enumerate(projects, 1):
        created_date = (datetime.now() - timedelta(days=random.randint(180, 365))).date()
        cursor.execute(
            'INSERT INTO projects (name, description, created_date, status) VALUES (?, ?, ?, ?)',
            (name, desc, created_date, status)
        )
        project_ids[name] = cursor.lastrowid  # Get auto-generated ID
    
    print(f"[OK] Inserted {len(projects)} projects")
    
    # ========================================================================
    # SEED TASKS (~30 tasks across all projects)
    # ========================================================================
    task_templates = [
        ('build', ['Build Docker image', 'Compile source code', 'Package artifacts']),
        ('test', ['Run unit tests', 'Execute integration tests', 'Performance testing']),
        ('deploy', ['Deploy to staging', 'Deploy to production', 'Rollback deployment']),
        ('backup', ['Database backup', 'File system backup', 'Backup verification']),
        ('migration', ['Schema migration', 'Data migration', 'Rollback migration'])
    ]
    
    task_ids = []
    for project_name, project_id in project_ids.items():
        # Each project gets 5-7 random tasks
        num_tasks = random.randint(5, 7)
        used_names = set()
        
        for _ in range(num_tasks):
            task_type = random.choice(['build', 'test', 'deploy', 'backup', 'migration'])
            templates = [t for task_t, templates in task_templates if task_t == task_type for t in templates]
            task_name = random.choice(templates)
            
            # Ensure unique task names per project
            counter = 1
            original_name = task_name
            while task_name in used_names:
                task_name = f"{original_name} {counter}"
                counter += 1
            used_names.add(task_name)
            
            cursor.execute(
                'INSERT INTO tasks (project_id, name, task_type, description) VALUES (?, ?, ?, ?)',
                (project_id, task_name, task_type, f'{task_type} task for {project_name}')
            )
            task_ids.append(cursor.lastrowid)
    
    print(f"[OK] Inserted {len(task_ids)} tasks")
    
    # ========================================================================
    # SEED TASK_RUNS (~100-150 execution records)
    # This is where the interesting analytics data is!
    # ========================================================================
    statuses = ['success', 'failed', 'running', 'cancelled']
    status_weights = [0.7, 0.2, 0.05, 0.05]  # 70% success, 20% failed, etc.
    
    error_messages = [
        'Connection timeout after 30 seconds',
        'Out of memory: Java heap space',
        'Database lock timeout',
        'Permission denied: access forbidden',
        'Network unreachable: host not found',
        'Invalid configuration: missing required field',
        'Dependency failure: upstream task failed',
        'Resource exhausted: disk full'
    ]
    
    total_runs = 0
    now = datetime.now()
    
    for task_id in task_ids:
        # Each task has 3-8 historical runs
        num_runs = random.randint(3, 8)
        
        for i in range(num_runs):
            # Runs are spread over last 30 days
            days_ago = random.randint(0, 30)
            hours_offset = random.randint(0, 23)
            start_time = now - timedelta(days=days_ago, hours=hours_offset, minutes=random.randint(0, 59))
            
            # Pick status (weighted random)
            status = random.choices(statuses, weights=status_weights)[0]
            
            # Calculate duration and end time
            if status == 'running':
                end_time = None
                duration = None
                error_msg = None
            else:
                duration = random.randint(10, 600)  # 10 seconds to 10 minutes
                end_time = start_time + timedelta(seconds=duration)
                error_msg = random.choice(error_messages) if status == 'failed' else None
            
            cursor.execute('''
                INSERT INTO task_runs 
                (task_id, start_time, end_time, status, error_message, duration_seconds)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (task_id, start_time, end_time, status, error_msg, duration))
            
            total_runs += 1
    
    print(f"[OK] Inserted {total_runs} task runs")
    
    conn.commit()

def print_statistics(cursor):
    """Print database statistics"""
    
    print("\n" + "="*60)
    print("DATABASE STATISTICS")
    print("="*60)
    
    # Count records
    cursor.execute('SELECT COUNT(*) FROM projects')
    print(f"Projects: {cursor.fetchone()[0]}")
    
    cursor.execute('SELECT COUNT(*) FROM tasks')
    print(f"Tasks: {cursor.fetchone()[0]}")
    
    cursor.execute('SELECT COUNT(*) FROM task_runs')
    print(f"Task runs: {cursor.fetchone()[0]}")
    
    # Status breakdown
    print("\nTask run status breakdown:")
    cursor.execute('''
        SELECT status, COUNT(*) as count 
        FROM task_runs 
        GROUP BY status 
        ORDER BY count DESC
    ''')
    for row in cursor.fetchall():
        print(f"  {row[0]:12s}: {row[1]}")
    
    # Recent failures
    print("\nRecent failed runs (last 3):")
    cursor.execute('''
        SELECT 
            p.name as project,
            t.name as task,
            tr.start_time,
            tr.error_message
        FROM task_runs tr
        JOIN tasks t ON tr.task_id = t.id
        JOIN projects p ON t.project_id = p.id
        WHERE tr.status = 'failed'
        ORDER BY tr.start_time DESC
        LIMIT 3
    ''')
    for row in cursor.fetchall():
        print(f"  [{row[0]}] {row[1]}")
        print(f"    Time: {row[2]}")
        print(f"    Error: {row[3]}")
    
    print("="*60)

def main():
    print("="*60)
    print("CREATING SQLITE DATABASE")
    print("="*60)
    
    # Create tables
    conn, cursor = create_database()
    
    # Seed data
    seed_data(conn, cursor)
    
    # Show statistics
    print_statistics(cursor)
    
    # Close connection
    conn.close()
    
    print("\n[OK] Database created successfully: data/database.db")
    print("\nYou can now:")
    print("1. Query it using Python: sqlite3.connect('data/database.db')")
    print("2. View it using CLI: sqlite3 data/database.db")
    print("3. Use with MCP server's execute_sql tool")

if __name__ == '__main__':
    main()
