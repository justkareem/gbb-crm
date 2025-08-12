"""
Database models for the Sales Request Management System
"""
import sqlite3
import hashlib
import random
import string
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List

DATABASE_PATH = 'requests.db'

def simple_hash(password: str) -> str:
    """Simple password hashing using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()

def get_connection():
    """Get a database connection with row factory"""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_service_slug(service_type: str) -> str:
    """Get service slug for custom ID generation"""
    service_slugs = {
        'Internet Service': 'IS',
        'Lease line': 'LL', 
        'Dark Fibre': 'DF',
        'Network Monitoring': 'NM',
        'Others - Connectivity (Renewal, Upgrade, IT Device, IP Addresses, Consultation, Support etc)': 'OC',
        'Collocation': 'CS',
        'Cross Connection': 'CC',
        'Collocation & Cross-connect Renewal': 'CR',
        'ECS': 'EC',
        'Disaster Recovery': 'DR',
        'Backup Service': 'BS',
        'Object Storage': 'OS',
        'Email Service': 'ES',
        'Others - Cloud (Renewal, Upgrade of Cloud Resources, IP Address, Licenses etc)': 'OR',
        'Document Management System - EDMS': 'DM',
        'Capacity Building - Training': 'CB',
        'Network Security': 'NS',
        'Security Renewal': 'SR'
    }
    return service_slugs.get(service_type, 'OT')  # Default to 'OT' for Other

def generate_custom_id(service_type: str = 'Internet Service') -> str:
    """Generate custom request ID in format GBB_SDA_MMYY_[SERVICE_SLUG]_[SEQUENTIAL_NUMBER]"""
    now = datetime.now()
    mmyy = now.strftime('%m%y')
    service_slug = get_service_slug(service_type)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get the next sequential number for this service type and month/year
    prefix = f"GBB_SDA_{mmyy}_{service_slug}_"
    
    cursor.execute('''
        SELECT custom_id FROM requests 
        WHERE custom_id LIKE ? 
        ORDER BY custom_id DESC 
        LIMIT 1
    ''', (f'{prefix}%',))
    
    result = cursor.fetchone()
    
    if result:
        # Extract the sequential number from the last ID
        last_id = result['custom_id']
        try:
            last_number = int(last_id.split('_')[-1])
            next_number = last_number + 1
        except (ValueError, IndexError):
            next_number = 1
    else:
        next_number = 1
    
    # Format with 3-digit zero padding
    custom_id = f"{prefix}{next_number:03d}"
    
    conn.close()
    return custom_id

def calculate_working_days(start_date: str, end_date: Optional[str] = None) -> int:
    """Calculate working days between two dates (excluding weekends)"""
    if end_date is None:
        end_date = date.today().strftime('%Y-%m-%d')
    
    start = datetime.strptime(start_date, '%Y-%m-%d').date()
    end = datetime.strptime(end_date, '%Y-%m-%d').date()
    
    # If start date is same as end date, return 1 (same day duration)
    if start == end:
        return 1
    
    # Calculate working days excluding weekends
    working_days = 0
    current_date = start + timedelta(days=1)  # Start from the day after start date
    
    while current_date <= end:
        # Monday = 0, Sunday = 6. Skip Saturday (5) and Sunday (6)
        if current_date.weekday() < 5:
            working_days += 1
        current_date += timedelta(days=1)
    
    # Add 1 for the start date (partial or full day counts as duration)
    return working_days + 1

class Request:
    """Request model"""
    
    # Service type options (replaces project types)
    SERVICE_TYPES = [
        'Internet Service',
        'Lease line',
        'Dark Fibre',
        'Network Monitoring',
        'Others - Connectivity (Renewal, Upgrade, IT Device, IP Addresses, Consultation, Support etc)',
        'Collocation',
        'Cross Connection',
        'Collocation & Cross-connect Renewal',
        'ECS',
        'Disaster Recovery',
        'Backup Service',
        'Object Storage',
        'Email Service',
        'Others - Cloud (Renewal, Upgrade of Cloud Resources, IP Address, Licenses etc)',
        'Document Management System - EDMS',
        'Capacity Building - Training',
        'Network Security',
        'Security Renewal'
    ]
    
    # Legacy project type options (kept for backward compatibility)
    PROJECT_TYPES = [
        'Cloud Service',
        'Connectivity (New & Upgrade)', 
        'Multiple Services',
        'Data Center Set Up',
        'Security',
        'Service Relocation',
        'Colocation',
        'IP Address',
        'Review',
        'Power System'
    ]
    
    # Status options
    STATUSES = [
        'in_progress',  # Default status
        'Pending with Presales',
        'Pending review',
        'Pending approval',
        'Closed Request'
    ]
    
    @staticmethod
    def create_table():
        """Create the requests table with proper schema"""
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                custom_id TEXT UNIQUE,
                customer_name TEXT NOT NULL,
                description TEXT NOT NULL,
                project_type TEXT NOT NULL,
                service_type TEXT DEFAULT 'Internet Service',
                status TEXT NOT NULL DEFAULT 'in_progress',
                boq_cost DECIMAL(10,2),
                requester_name TEXT,
                department TEXT,
                date_request_received DATE NOT NULL,
                target_days INTEGER,
                sent_out_date DATE,
                duration_days INTEGER DEFAULT 0,
                team_member_involved TEXT NOT NULL,
                comment TEXT,
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    @staticmethod
    def create(data: Dict) -> int:
        """Create a new request"""
        conn = get_connection()
        cursor = conn.cursor()
        
        # Generate custom ID based on service type
        service_type = data.get('service_type', 'Internet Service')
        custom_id = generate_custom_id(service_type)
        
        # Calculate initial duration
        duration = calculate_working_days(data['date_request_received'])
        
        cursor.execute('''
            INSERT INTO requests (
                custom_id, customer_name, description, project_type, service_type, status, boq_cost,
                requester_name, department, date_request_received, target_days,
                team_member_involved, comment, duration_days
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            custom_id,
            data['customer_name'],
            data['description'],
            data.get('project_type', ''),  # Keep for backward compatibility
            service_type,
            'in_progress',  # Default status
            data.get('boq_cost'),
            data.get('requester_name'),
            data.get('department'),
            data['date_request_received'],
            data.get('target_days'),
            data['team_member_involved'],
            data.get('comment', ''),
            duration
        ))
        
        request_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return request_id
    
    @staticmethod
    def get_status_sort_order(status: str) -> int:
        """Get sort order for status (lower number = higher priority)"""
        status_order = {
            'Closed Request': 1,
            'Pending with Presales': 2,
            'Pending review': 3,
            'Pending approval': 4,
            'in_progress': 5
        }
        return status_order.get(status, 999)  # Unknown statuses go to the end

    @staticmethod
    def get_all(date_from=None, date_to=None, overdue_only=False) -> List[Dict]:
        """Get all requests with optional filters"""
        conn = get_connection()
        cursor = conn.cursor()
        
        # Build query with filters
        query = 'SELECT * FROM requests'
        params = []
        conditions = []
        
        if date_from:
            conditions.append('date_request_received >= ?')
            params.append(date_from)
            
        if date_to:
            conditions.append('date_request_received <= ?')
            params.append(date_to)
            
        if overdue_only:
            conditions.append('target_days IS NOT NULL AND duration_days > target_days AND status != "Closed Request"')
        
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
            
        query += ' ORDER BY created_date DESC'
        
        cursor.execute(query, params)
        
        requests = []
        for row in cursor.fetchall():
            request_dict = dict(row)
            # Update duration for non-closed requests
            if request_dict['status'] != 'Closed Request':
                new_duration = calculate_working_days(request_dict['date_request_received'])
                request_dict['duration_days'] = new_duration
            requests.append(request_dict)
        
        conn.close()
        return requests
    
    @staticmethod
    def get_by_id(request_id: int) -> Optional[Dict]:
        """Get request by ID"""
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM requests WHERE id = ?', (request_id,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    @staticmethod
    def update(request_id: int, data: Dict, user_id: int = None, user_name: str = None) -> bool:
        """Update a request with activity logging"""
        conn = get_connection()
        cursor = conn.cursor()
        
        # Get current request data for logging
        current_request = Request.get_by_id(request_id)
        if not current_request:
            conn.close()
            return False
        
        # Auto-set sent_out_date if status is Closed Request
        if data.get('status') == 'Closed Request':
            if not data.get('sent_out_date'):
                data['sent_out_date'] = date.today().strftime('%Y-%m-%d')
        
        # Calculate updated duration
        if 'date_request_received' in data:
            end_date = data.get('sent_out_date') if data.get('status') == 'Closed Request' else None
            data['duration_days'] = calculate_working_days(data['date_request_received'], end_date)
        
        # Build dynamic update query
        fields = []
        values = []
        for key, value in data.items():
            if key != 'id':
                fields.append(f"{key} = ?")
                values.append(value)
        
        values.append(request_id)
        
        cursor.execute(f'''
            UPDATE requests 
            SET {", ".join(fields)}, updated_date = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', values)
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        # Log changes if user info provided
        if success and user_id and user_name:
            # Field mapping for readable names
            field_labels = {
                'status': 'Status',
                'customer_name': 'Customer Name',
                'description': 'Description',
                'project_type': 'Project Type',
                'boq_cost': 'BOQ Cost',
                'requester_name': 'BM Name',
                'department': 'Department',
                'date_request_received': 'Date Request Received',
                'target_days': 'Target Days',
                'sent_out_date': 'Sent Out Date',
                'team_member_involved': 'Team Member Involved',
                'comment': 'Comment'
            }
            
            # Log each changed field (exclude automatically calculated fields)
            excluded_fields = ['duration_days', 'updated_date', 'created_date']
            
            for field, new_value in data.items():
                if field != 'id' and field in current_request and field not in excluded_fields:
                    old_value = current_request[field]
                    if str(old_value) != str(new_value):
                        field_label = field_labels.get(field, field)
                        action = f"Changed {field_label} from '{old_value}' to '{new_value}'"
                        RequestLog.create_log(
                            request_id=request_id,
                            user_id=user_id,
                            user_name=user_name,
                            action=action,
                            field_name=field,
                            old_value=str(old_value) if old_value else None,
                            new_value=str(new_value) if new_value else None
                        )
        
        return success
    
    @staticmethod
    def delete(request_id: int) -> bool:
        """Delete a request"""
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM requests WHERE id = ?', (request_id,))
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return success
    
    @staticmethod
    def get_stats() -> Dict:
        """Get dashboard statistics"""
        conn = get_connection()
        cursor = conn.cursor()
        
        # Total requests
        cursor.execute('SELECT COUNT(*) as total FROM requests')
        total = cursor.fetchone()['total']
        
        # Requests by status
        cursor.execute('SELECT status, COUNT(*) as count FROM requests GROUP BY status')
        status_counts = {row['status']: row['count'] for row in cursor.fetchall()}
        
        # Overdue requests (duration > target_days) - including closed requests
        # Calculate overdue with real-time duration for non-closed requests
        cursor.execute('''
            SELECT id, status, date_request_received, target_days, duration_days 
            FROM requests 
            WHERE target_days IS NOT NULL
        ''')
        
        overdue = 0
        for row in cursor.fetchall():
            request = dict(row)
            current_duration = request['duration_days']
            
            # Use real-time calculation for non-closed requests
            if request['status'] != 'Closed Request':
                current_duration = calculate_working_days(request['date_request_received'])
            
            target_days = request['target_days']
            if target_days:
                try:
                    target_days_int = int(target_days) if isinstance(target_days, str) else target_days
                    if target_days_int > 0 and current_duration > target_days_int:
                        overdue += 1
                except (ValueError, TypeError):
                    pass  # Skip invalid target_days values
        
        # Closed this week
        cursor.execute('''
            SELECT COUNT(*) as closed_week FROM requests 
            WHERE status = 'Closed Request' 
            AND sent_out_date >= date('now', '-7 days')
        ''')
        closed_week = cursor.fetchone()['closed_week']
        
        conn.close()
        
        return {
            'total': total,
            'in_progress': status_counts.get('in_progress', 0),
            'pending': sum(status_counts.get(status, 0) for status in [
                'Pending with Presales', 'Pending review', 'Pending approval'
            ]),
            'closed': status_counts.get('Closed Request', 0),
            'overdue': overdue,
            'closed_week': closed_week
        }
    
    @staticmethod
    def get_daily_report(target_date: str) -> Dict:
        """Get daily report data"""
        conn = get_connection()
        cursor = conn.cursor()
        
        # Requests created today
        cursor.execute('''
            SELECT COUNT(*) as created FROM requests 
            WHERE DATE(created_date) = ?
        ''', (target_date,))
        created = cursor.fetchone()['created']
        
        # Requests completed today
        cursor.execute('''
            SELECT COUNT(*) as completed FROM requests 
            WHERE DATE(sent_out_date) = ? AND status = 'Closed Request'
        ''', (target_date,))
        completed = cursor.fetchone()['completed']
        
        # Current in progress
        cursor.execute('''
            SELECT COUNT(*) as in_progress FROM requests 
            WHERE status = 'in_progress'
        ''')
        in_progress = cursor.fetchone()['in_progress']
        
        # Current overdue
        cursor.execute('''
            SELECT COUNT(*) as overdue FROM requests 
            WHERE target_days IS NOT NULL 
            AND duration_days > target_days 
        ''')
        overdue = cursor.fetchone()['overdue']
        
        # Today's activities from logs
        cursor.execute('''
            SELECT rl.*, r.customer_name 
            FROM request_logs rl
            JOIN requests r ON rl.request_id = r.id
            WHERE DATE(rl.timestamp) = ?
            ORDER BY rl.timestamp DESC
            LIMIT 50
        ''', (target_date,))
        activities = [dict(row) for row in cursor.fetchall()]
        
        # All active requests + requests closed on this day
        cursor.execute('''
            SELECT * FROM requests 
            WHERE status != 'Closed Request' 
            OR DATE(sent_out_date) = ?
        ''', (target_date,))
        requests = [dict(row) for row in cursor.fetchall()]
        
        # Sort by status priority (Closed, Pending with Presales, Pending review, Pending approval, in_progress)
        requests.sort(key=lambda x: Request.get_status_sort_order(x['status']))
        
        conn.close()
        
        return {
            'created': created,
            'completed': completed,
            'in_progress': in_progress,
            'overdue': overdue,
            'activities': activities,
            'requests': requests
        }
    
    @staticmethod
    def get_weekly_report(year: int, week: int) -> Dict:
        """Get weekly report data"""
        conn = get_connection()
        cursor = conn.cursor()
        
        # Calculate week start and end dates
        from datetime import datetime, timedelta
        jan_1 = datetime(year, 1, 1)
        week_start = jan_1 + timedelta(weeks=week-1) - timedelta(days=jan_1.weekday())
        week_end = week_start + timedelta(days=6)
        
        start_date = week_start.strftime('%Y-%m-%d')
        end_date = week_end.strftime('%Y-%m-%d')
        
        # Requests created this week
        cursor.execute('''
            SELECT COUNT(*) as created FROM requests 
            WHERE DATE(created_date) BETWEEN ? AND ?
        ''', (start_date, end_date))
        created = cursor.fetchone()['created']
        
        # Requests completed this week
        cursor.execute('''
            SELECT COUNT(*) as completed FROM requests 
            WHERE DATE(sent_out_date) BETWEEN ? AND ? AND status = 'Closed Request'
        ''', (start_date, end_date))
        completed = cursor.fetchone()['completed']
        
        # Current in progress
        cursor.execute('''
            SELECT COUNT(*) as in_progress FROM requests 
            WHERE status = 'in_progress'
        ''')
        in_progress = cursor.fetchone()['in_progress']
        
        # Current overdue
        cursor.execute('''
            SELECT COUNT(*) as overdue FROM requests 
            WHERE target_days IS NOT NULL 
            AND duration_days > target_days 
        ''')
        overdue = cursor.fetchone()['overdue']
        
        # Status breakdown
        cursor.execute('''
            SELECT status, COUNT(*) as count FROM requests 
            WHERE DATE(created_date) BETWEEN ? AND ?
            GROUP BY status
        ''', (start_date, end_date))
        status_breakdown = [{'name': row['status'], 'count': row['count']} for row in cursor.fetchall()]
        
        # Team performance
        cursor.execute('''
            SELECT team_member_involved as name, 
                   COUNT(CASE WHEN status = 'Closed Request' THEN 1 END) as completed
            FROM requests 
            WHERE DATE(created_date) BETWEEN ? AND ?
            GROUP BY team_member_involved
        ''', (start_date, end_date))
        team_performance = [dict(row) for row in cursor.fetchall()]
        
        # Week's activities from logs
        cursor.execute('''
            SELECT rl.*, r.customer_name 
            FROM request_logs rl
            JOIN requests r ON rl.request_id = r.id
            WHERE DATE(rl.timestamp) BETWEEN ? AND ?
            ORDER BY rl.timestamp DESC
            LIMIT 100
        ''', (start_date, end_date))
        activities = [dict(row) for row in cursor.fetchall()]
        
        # All active requests + requests closed this week
        cursor.execute('''
            SELECT * FROM requests 
            WHERE status != 'Closed Request' 
            OR DATE(sent_out_date) BETWEEN ? AND ?
        ''', (start_date, end_date))
        requests = [dict(row) for row in cursor.fetchall()]
        
        # Sort by status priority (Closed, Pending with Presales, Pending review, Pending approval, in_progress)
        requests.sort(key=lambda x: Request.get_status_sort_order(x['status']))
        
        conn.close()
        
        return {
            'created': created,
            'completed': completed,
            'in_progress': in_progress,
            'overdue': overdue,
            'status_breakdown': status_breakdown,
            'team_performance': team_performance,
            'activities': activities,
            'requests': requests
        }
    
    @staticmethod
    def get_monthly_report(year: int, month: int) -> Dict:
        """Get monthly report data"""
        conn = get_connection()
        cursor = conn.cursor()
        
        # Calculate month start and end
        from calendar import monthrange
        start_date = f"{year}-{month:02d}-01"
        _, last_day = monthrange(year, month)
        end_date = f"{year}-{month:02d}-{last_day}"
        
        # Requests created this month
        cursor.execute('''
            SELECT COUNT(*) as created FROM requests 
            WHERE DATE(created_date) BETWEEN ? AND ?
        ''', (start_date, end_date))
        created = cursor.fetchone()['created']
        
        # Completed requests this month
        cursor.execute('''
            SELECT COUNT(*) as completed FROM requests 
            WHERE DATE(sent_out_date) BETWEEN ? AND ? AND status = 'Closed Request'
        ''', (start_date, end_date))
        completed = cursor.fetchone()['completed']
        
        # Current in progress
        cursor.execute('''
            SELECT COUNT(*) as in_progress FROM requests 
            WHERE status = 'in_progress'
        ''')
        in_progress = cursor.fetchone()['in_progress']
        
        # Current overdue
        cursor.execute('''
            SELECT COUNT(*) as overdue FROM requests 
            WHERE target_days IS NOT NULL 
            AND duration_days > target_days 
        ''')
        overdue = cursor.fetchone()['overdue']
        
        # Project type analysis
        cursor.execute('''
            SELECT 
                project_type as name,
                COUNT(*) as count,
                AVG(duration_days) as avg_days
            FROM requests 
            WHERE DATE(created_date) BETWEEN ? AND ?
            GROUP BY project_type
            ORDER BY count DESC
        ''', (start_date, end_date))
        project_types = [{'name': row['name'], 'count': row['count'], 'avg_days': round(row['avg_days'] or 0, 1)} for row in cursor.fetchall()]
        
        # Department analysis
        cursor.execute('''
            SELECT 
                department as name,
                COUNT(*) as requests,
                AVG(duration_days) as avg_response
            FROM requests 
            WHERE DATE(created_date) BETWEEN ? AND ?
            GROUP BY department
            ORDER BY requests DESC
        ''', (start_date, end_date))
        departments = [{'name': row['name'], 'requests': row['requests'], 'avg_response': f"{round(row['avg_response'] or 0, 1)} days"} for row in cursor.fetchall()]
        
        # Month's activities from logs
        cursor.execute('''
            SELECT rl.*, r.customer_name 
            FROM request_logs rl
            JOIN requests r ON rl.request_id = r.id
            WHERE DATE(rl.timestamp) BETWEEN ? AND ?
            ORDER BY rl.timestamp DESC
            LIMIT 200
        ''', (start_date, end_date))
        activities = [dict(row) for row in cursor.fetchall()]
        
        # All active requests + requests closed this month
        cursor.execute('''
            SELECT * FROM requests 
            WHERE status != 'Closed Request' 
            OR DATE(sent_out_date) BETWEEN ? AND ?
        ''', (start_date, end_date))
        requests = [dict(row) for row in cursor.fetchall()]
        
        # Sort by status priority (Closed, Pending with Presales, Pending review, Pending approval, in_progress)
        requests.sort(key=lambda x: Request.get_status_sort_order(x['status']))
        
        conn.close()
        
        return {
            'created': created,
            'completed': completed,
            'in_progress': in_progress,
            'overdue': overdue,
            'project_types': project_types,
            'departments': departments,
            'activities': activities,
            'requests': requests
        }

class RequestLog:
    """Request activity log model"""
    
    @staticmethod
    def create_table():
        """Create the request_logs table"""
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS request_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                user_name TEXT NOT NULL,
                action TEXT NOT NULL,
                field_name TEXT,
                old_value TEXT,
                new_value TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (request_id) REFERENCES requests (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    @staticmethod
    def create_log(request_id: int, user_id: int, user_name: str, action: str, 
                   field_name: str = None, old_value: str = None, new_value: str = None):
        """Create a new log entry"""
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO request_logs (request_id, user_id, user_name, action, field_name, old_value, new_value)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (request_id, user_id, user_name, action, field_name, old_value, new_value))
        
        conn.commit()
        conn.close()
    
    @staticmethod
    def get_logs_for_request(request_id: int) -> List[Dict]:
        """Get all logs for a specific request"""
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM request_logs 
            WHERE request_id = ? 
            ORDER BY timestamp DESC
        ''', (request_id,))
        
        logs = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return logs

class User:
    """User model"""
    
    ROLES = ['admin', 'user']
    
    @staticmethod
    def create_table():
        """Create the users table"""
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                email TEXT,
                department TEXT,
                role TEXT DEFAULT 'user',
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    @staticmethod
    def create(username: str, password: str, full_name: str, email: str = None, 
               department: str = None, role: str = 'user') -> int:
        """Create a new user"""
        conn = get_connection()
        cursor = conn.cursor()
        
        password_hash = simple_hash(password)
        
        cursor.execute('''
            INSERT INTO users (username, password_hash, full_name, email, department, role)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (username, password_hash, full_name, email, department, role))
        
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return user_id
    
    @staticmethod
    def get_by_username(username: str) -> Optional[Dict]:
        """Get user by username"""
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    @staticmethod
    def get_by_id(user_id: int) -> Optional[Dict]:
        """Get user by ID"""
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    @staticmethod
    def get_all() -> List[Dict]:
        """Get all users"""
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users ORDER BY full_name')
        users = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return users
    
    @staticmethod
    def verify_password(stored_hash: str, password: str) -> bool:
        """Verify password against stored hash"""
        return stored_hash == simple_hash(password)

def migrate_status_values():
    """Migrate old status values to new ones"""
    conn = get_connection()
    cursor = conn.cursor()
    
    print("Starting status migration...")
    
    # Check current status counts before migration
    cursor.execute("SELECT status, COUNT(*) FROM requests GROUP BY status")
    before_counts = cursor.fetchall()
    print("\nStatus counts before migration:")
    for row in before_counts:
        print(f"  {row['status']}: {row['COUNT(*)']}")
    
    # Update the status values
    updates = [
        ("Pending with jane", "Pending review"),
        ("Pending Review with mahmud", "Pending approval")
    ]
    
    total_updated = 0
    for old_status, new_status in updates:
        cursor.execute("UPDATE requests SET status = ? WHERE status = ?", (new_status, old_status))
        updated_count = cursor.rowcount
        total_updated += updated_count
        print(f"\nUpdated {updated_count} records from '{old_status}' to '{new_status}'")
    
    # Commit the changes
    conn.commit()
    
    # Check status counts after migration
    cursor.execute("SELECT status, COUNT(*) FROM requests GROUP BY status")
    after_counts = cursor.fetchall()
    print("\nStatus counts after migration:")
    for row in after_counts:
        print(f"  {row['status']}: {row['COUNT(*)']}")
    
    conn.close()
    
    print(f"\nMigration completed! Total records updated: {total_updated}")
    return total_updated

def init_database():
    """Initialize database with proper schema"""
    Request.create_table()
    User.create_table()
    RequestLog.create_table()
    
    # Create default admin user if it doesn't exist
    if not User.get_by_username('admin'):
        User.create('admin', 'admin123', 'Administrator', 'admin@company.com', 'IT', 'admin')
    
    print("Database initialized successfully!")

if __name__ == '__main__':
    init_database()