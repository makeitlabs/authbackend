#!/usr/bin/env python3
"""
Unit test for fiber_candidates.py
Validates candidate qualification scoring, active member filtering,
exclusion of already-authorized members, 1-year lookback, and HTML output.
"""

import os
import sys
import sqlite3
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta


class TestFiberCandidatesReport(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.makeit_path = os.path.join(self.temp_dir.name, "makeit.db")
        self.log_path = os.path.join(self.temp_dir.name, "log.db")

        # Initialize makeit.db
        m_conn = sqlite3.connect(self.makeit_path)
        m_cursor = m_conn.cursor()

        m_cursor.execute("""
            CREATE TABLE resources (
                id INTEGER PRIMARY KEY,
                name VARCHAR(50),
                short VARCHAR(20),
                description VARCHAR(50)
            )
        """)

        # Insert user's resource list
        resources_data = [
            (1, 'frontdoor', 'frontdoor'),
            (2, 'woodshop-general-users', 'woodshop'),
            (3, 'laser-rabbit-users', 'laser'),
            (5, 'tormach-1100-users', 'tormach'),
            (7, 'laser-fullspectrum-users', 'fslaser'),
            (15, 'machineshop-general-users', 'machineshop'),
            (16, 'machineshop-kneemill-users', 'bridgeport'),
            (29, 'laser-mopa-users', 'MOPA Laser'),
            (30, 'laser-epilog-users', 'Epilog Laser'),
            (33, 'machineshop-lathe-enco-users', 'machineshop-lathe-enco'),
            (34, 'machineshop-lathe-jet-users', 'machineshop-lathe-jet'),
            (41, 'machineshop-cnclathe-users', 'LX2'),
            (47, 'laser-uv-users', 'UV'),
            (48, 'laser-kern-users', 'Kern'),
            (49, 'laser-fiber-users', 'xTool Fiber')
        ]
        m_cursor.executemany("INSERT INTO resources (id, name, short) VALUES (?, ?, ?)", resources_data)

        m_cursor.execute("""
            CREATE TABLE members (
                id INTEGER PRIMARY KEY,
                member VARCHAR(50),
                firstname VARCHAR(50),
                lastname VARCHAR(50),
                email VARCHAR(50),
                alt_email VARCHAR(50),
                access_enabled INTEGER DEFAULT 1,
                active INTEGER DEFAULT 1
            )
        """)

        m_cursor.execute("""
            CREATE TABLE subscriptions (
                id INTEGER PRIMARY KEY,
                member_id INTEGER,
                active VARCHAR(10),
                expires_date DATETIME
            )
        """)

        m_cursor.execute("""
            CREATE TABLE accessbymember (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER,
                resource_id INTEGER,
                is_active INTEGER DEFAULT 1,
                level INTEGER DEFAULT 0,
                lockout_reason VARCHAR(255)
            )
        """)

        # Members:
        # 1: Alice - Active, UV + Epilog + MOPA + Machine Shop heavy user (Top candidate)
        # 2: Bob - Active, UV only (High candidate)
        # 3: Charlie - Active, Epilog heavy user (High candidate)
        # 4: Dave - INACTIVE member (active=0, no subscription) -> MUST be excluded!
        # 5: Eve - Active, ALREADY authorized on Fiber laser (id 49) -> MUST be excluded from top candidates!
        # 6: Frank - Active, Machine Shop only (Low-medium candidate)
        # 7: Grace - Active, usage was 2 years ago (Usage should not count)
        members_data = [
            (1, 'alice', 'Alice', 'Smith', 'alice@example.com', '', 1, 1),
            (2, 'bob', 'Bob', 'Jones', 'bob@example.com', '', 1, 1),
            (3, 'charlie', 'Charlie', 'Brown', 'charlie@example.com', '', 1, 1),
            (4, 'dave', 'Dave', 'Miller', 'dave@example.com', '', 1, 0), # Inactive
            (5, 'eve', 'Eve', 'Taylor', 'eve@example.com', '', 1, 1), # Already has Fiber
            (6, 'frank', 'Frank', 'White', 'frank@example.com', '', 1, 1),
            (7, 'grace', 'Grace', 'Hopper', 'grace@example.com', '', 1, 1),
        ]
        # Add 80 more members to test 75 cap
        for i in range(8, 90):
            members_data.append((i, f'user{i}', f'User{i}', 'Test', f'user{i}@example.com', '', 1, 1))

        m_cursor.executemany("""
            INSERT INTO members (id, member, firstname, lastname, email, alt_email, access_enabled, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, members_data)

        # Authorizations:
        auths_data = [
            # Alice has UV, Epilog, MOPA, Machine Shop
            (1, 47, 1, 0, None),
            (1, 30, 1, 0, None),
            (1, 29, 1, 0, None),
            (1, 15, 1, 0, None),
            (1, 16, 1, 0, None),
            # Bob has UV
            (2, 47, 1, 0, None),
            # Charlie has Epilog
            (3, 30, 1, 0, None),
            # Dave (inactive) has UV + Epilog
            (4, 47, 1, 0, None),
            (4, 30, 1, 0, None),
            # Eve has Fiber laser (id 49)
            (5, 49, 1, 0, None),
            (5, 47, 1, 0, None),
            # Frank has Machine Shop general and lathe
            (6, 15, 1, 0, None),
            (6, 33, 1, 0, None),
            # Grace has Epilog
            (7, 30, 1, 0, None),
        ]
        # Give some extra users basic authorizations
        for i in range(8, 30):
            auths_data.append((i, 30, 1, 0, None)) # Epilog
        for i in range(30, 50):
            auths_data.append((i, 15, 1, 0, None)) # Machine shop
        for i in range(50, 70):
            auths_data.append((i, 3, 1, 0, None)) # Rabbit laser

        m_cursor.executemany("""
            INSERT INTO accessbymember (member_id, resource_id, is_active, level, lockout_reason)
            VALUES (?, ?, ?, ?, ?)
        """, auths_data)

        m_conn.commit()
        m_conn.close()

        # Initialize log.db
        l_conn = sqlite3.connect(self.log_path)
        l_cursor = l_conn.cursor()

        l_cursor.execute("""
            CREATE TABLE usagelog (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER,
                tool_id INTEGER,
                resource_id INTEGER,
                time_logged DATETIME,
                time_reported DATETIME,
                idleSecs INTEGER,
                activeSecs INTEGER,
                enabledSecs INTEGER
            )
        """)

        l_cursor.execute("""
            CREATE TABLE log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                member_id INTEGER,
                node_id INTEGER,
                tool_id INTEGER,
                resource_id INTEGER,
                message VARCHAR(100),
                doneby INTEGER,
                time_logged DATETIME,
                time_reported DATETIME,
                event_type INTEGER,
                event_subtype INTEGER
            )
        """)

        now = datetime.now()
        recent_date = (now - timedelta(days=30)).strftime('%Y-%m-%d %H:%M:%S')
        old_date = (now - timedelta(days=450)).strftime('%Y-%m-%d %H:%M:%S') # Older than 1 year

        # Usage logs:
        # Alice: 10 sessions on UV (total 8 hrs), 20 sessions on Epilog (25 hrs), 5 on MOPA, 4 on Machine shop
        usages = []
        for _ in range(10):
            usages.append((1, 47, recent_date, 2880, 2880)) # 10 * 2880s = 8 hrs
        for _ in range(20):
            usages.append((1, 30, recent_date, 4500, 4500)) # 20 * 4500s = 25 hrs
        for _ in range(5):
            usages.append((1, 29, recent_date, 3600, 3600))
        for _ in range(4):
            usages.append((1, 15, recent_date, 1800, 1800))

        # Bob: 8 sessions on UV
        for _ in range(8):
            usages.append((2, 47, recent_date, 3600, 3600))

        # Charlie: 30 sessions on Epilog (40 hrs)
        for _ in range(30):
            usages.append((3, 30, recent_date, 4800, 4800))

        # Dave (inactive): 50 sessions
        for _ in range(50):
            usages.append((4, 47, recent_date, 3600, 3600))

        # Grace: Usage older than 1 year -> should NOT count in past-year metrics
        for _ in range(25):
            usages.append((7, 30, old_date, 3600, 3600))

        l_cursor.executemany("""
            INSERT INTO usagelog (member_id, resource_id, time_logged, activeSecs, enabledSecs)
            VALUES (?, ?, ?, ?, ?)
        """, usages)

        l_conn.commit()
        l_conn.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_fiber_candidates_execution(self):
        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../authlibs/reports/reports/fiber_candidates.py"))
        env = os.environ.copy()
        env['MAKEIT_DB'] = self.makeit_path
        env['LOG_DB'] = self.log_path

        proc = subprocess.run(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True
        )

        self.assertEqual(proc.returncode, 0, f"Script failed with stderr:\n{proc.stderr}")
        output = proc.stdout

        # Verify HTML format
        self.assertTrue(output.startswith("HTML:"), "Output must start with 'HTML:' prefix for reports.html")
        self.assertIn("</pre>", output, "Output must contain '</pre>' at start")
        self.assertIn("<pre>", output, "Output must contain '<pre>' at end")

        # Verify Alice is #1 with top priority score
        self.assertIn("Alice Smith", output)
        self.assertIn("#1", output)
        self.assertIn("92.5", output)
        self.assertIn("Top Priority", output)

        # Verify Bob and Charlie are present
        self.assertIn("Bob Jones", output)
        self.assertIn("Charlie Brown", output)

        # Alice should appear before Bob and Charlie
        alice_idx = output.find("Alice Smith")
        bob_idx = output.find("Bob Jones")
        charlie_idx = output.find("Charlie Brown")
        self.assertTrue(alice_idx < bob_idx, "Alice should be ranked before Bob")
        self.assertTrue(alice_idx < charlie_idx, "Alice should be ranked before Charlie")

        # Verify Dave (inactive member) is NOT in the candidate table
        self.assertNotIn("Dave Miller", output, "Inactive member Dave must not appear in recommendations")

        # Verify Eve (already authorized on Fiber laser) is excluded from candidate table and in already authorized
        self.assertIn("Already Authorized on Fiber Laser", output)
        self.assertIn("Eve Taylor", output)

        # Verify Grace's score does not include her old usage
        # Grace only has Epilog auth (10 pts), no past-year usage
        self.assertIn("Grace Hopper", output)

        # Test REPORT_SINCE override
        env_since = env.copy()
        env_since['REPORT_SINCE'] = (datetime.now() - timedelta(days=600)).strftime('%Y-%m-%d')
        proc_since = subprocess.run(
            [sys.executable, script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env_since,
            text=True
        )
        self.assertEqual(proc_since.returncode, 0)
        # With lookback 600 days, Grace's old usage should now be counted
        self.assertIn("Usage focus: Since <strong>", proc_since.stdout)


if __name__ == "__main__":
    unittest.main()
