"""
Database Setup Script for Multi-Tenant Support

WHAT THIS DOES:
- Creates SQLite database
- Defines completely different schemas based on TENANT_NAME environment variable
- Seeds with dummy data
"""

import sqlite3
import os
from datetime import datetime, timedelta
import random

def create_database(tenant_name: str):
    os.makedirs('data', exist_ok=True)
    conn = sqlite3.connect('data/database.db')
    cursor = conn.cursor()
    
    if "Tenant A" in tenant_name:
        cursor.execute('DROP TABLE IF EXISTS task_runs')
        cursor.execute('DROP TABLE IF EXISTS tasks')
        cursor.execute('DROP TABLE IF EXISTS projects')
        
        print(f"[{tenant_name}] Creating Tenant A schema (Projects/Tasks)...")
        cursor.execute('''
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                created_date DATE NOT NULL,
                status TEXT CHECK(status IN ('active', 'archived', 'maintenance')) DEFAULT 'active'
            )
        ''')
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
        conn.commit()
        seed_tenant_a(conn, cursor)
        
    else: # Tenant B
        cursor.execute('DROP TABLE IF EXISTS tickets')
        cursor.execute('DROP TABLE IF EXISTS employees')
        cursor.execute('DROP TABLE IF EXISTS departments')
        
        print(f"[{tenant_name}] Creating Tenant B schema (HR/Ticketing)...")
        cursor.execute('''
            CREATE TABLE departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                budget_code TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                department_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                email TEXT UNIQUE,
                FOREIGN KEY (department_id) REFERENCES departments(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                issue_category TEXT CHECK(issue_category IN ('IT', 'HR', 'Facilities')) NOT NULL,
                description TEXT,
                status TEXT CHECK(status IN ('open', 'in_progress', 'resolved', 'closed')) DEFAULT 'open',
                created_at DATETIME NOT NULL,
                resolved_at DATETIME,
                FOREIGN KEY (employee_id) REFERENCES employees(id)
            )
        ''')
        conn.commit()
        seed_tenant_b(conn, cursor)
        
    return conn, cursor

def seed_tenant_a(conn, cursor):
    print("Seeding data for Tenant A...")
    projects = [
        ('Apollo', 'Customer data processing pipeline', 'active'),
        ('Titan', 'Real-time analytics platform', 'active'),
        ('Voyager', 'Legacy data migration', 'maintenance')
    ]
    for name, desc, status in projects:
        cursor.execute(
            'INSERT INTO projects (name, description, created_date, status) VALUES (?, ?, ?, ?)',
            (name, desc, datetime.now().date(), status)
        )
    
    cursor.execute("INSERT INTO tasks (project_id, name, task_type, description) VALUES (1, 'Migrate DB', 'migration', 'Database pipeline migration')")
    cursor.execute("INSERT INTO tasks (project_id, name, task_type, description) VALUES (2, 'Deploy Cluster', 'deploy', 'Deploy Titan cluster')")
    
    cursor.execute("INSERT INTO task_runs (task_id, start_time, end_time, status, duration_seconds) VALUES (1, '2026-02-21 10:00:00', '2026-02-21 10:05:00', 'success', 300)")
    cursor.execute("INSERT INTO task_runs (task_id, start_time, end_time, status, error_message, duration_seconds) VALUES (2, '2026-02-22 08:00:00', '2026-02-22 08:01:00', 'failed', 'Timeout error', 60)")
    conn.commit()
    print("[OK] Tenant A data seeded.")

def seed_tenant_b(conn, cursor):
    print("Seeding data for Tenant B...")
    depts = [
        ('Engineering', 'ENG-001'),
        ('Human Resources', 'HR-001'),
        ('Marketing', 'MKT-001')
    ]
    for name, budget in depts:
        cursor.execute("INSERT INTO departments (name, budget_code) VALUES (?, ?)", (name, budget))
    
    cursor.execute("INSERT INTO employees (department_id, name, role, email) VALUES (1, 'Alice Smith', 'Senior Engineer', 'alice@example.com')")
    cursor.execute("INSERT INTO employees (department_id, name, role, email) VALUES (2, 'Bob Johnson', 'HR Manager', 'bob@example.com')")
    
    cursor.execute("INSERT INTO tickets (employee_id, issue_category, description, status, created_at) VALUES (1, 'IT', 'Laptop battery replacement', 'open', '2026-02-15 09:30:00')")
    cursor.execute("INSERT INTO tickets (employee_id, issue_category, description, status, created_at, resolved_at) VALUES (2, 'Facilities', 'Air conditioning broken', 'resolved', '2026-02-18 10:00:00', '2026-02-18 14:00:00')")
    conn.commit()
    print("[OK] Tenant B data seeded.")

def main():
    tenant_name = os.environ.get("TENANT_NAME", "Tenant A Default")
    print("="*60)
    print(f"CREATING SQLITE DATABASE: {tenant_name}")
    print("="*60)
    
    conn, cursor = create_database(tenant_name)
    conn.close()
    
    print("\n[OK] Database created successfully: data/database.db")

if __name__ == '__main__':
    main()
