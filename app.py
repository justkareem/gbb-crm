from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, send_file
from models import User, Request, RequestLog
from report_exporters import PDFExporter, ExcelExporter
from functools import wraps
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-this-in-production')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    if 'user_id' not in session:
        return None
    return User.get_by_id(session['user_id'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.get_by_username(username)
        
        if user and User.verify_password(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            flash('Login successful!', 'success')
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/add-request')
@login_required
def add_request():
    return render_template('add-request.html')

@app.route('/requests')
@login_required
def requests():
    return render_template('requests.html')

@app.route('/reports')
@login_required
def reports():
    return render_template('reports.html')

# API Routes
@app.route('/api/requests', methods=['GET'])
def get_requests():
    # Get query parameters for filtering
    date_from = request.args.get('date_from')
    date_to = request.args.get('date_to')
    overdue_only = request.args.get('overdue_only') == 'true'
    
    return jsonify(Request.get_all(date_from=date_from, date_to=date_to, overdue_only=overdue_only))

@app.route('/api/requests', methods=['POST'])
@login_required
def create_request():
    data = request.get_json()
    current_user = get_current_user()
    
    # Team member should be selected from frontend, no auto-assignment
    
    try:
        request_id = Request.create(data)
        return jsonify({'id': request_id, 'message': 'Request created successfully'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/requests/<int:request_id>', methods=['PUT'])
@login_required
def update_request(request_id):
    data = request.get_json()
    current_user = get_current_user()
    
    try:
        success = Request.update(request_id, data, current_user['id'], current_user['full_name'])
        if success:
            return jsonify({'message': 'Request updated successfully'})
        else:
            return jsonify({'error': 'Request not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/requests/<int:request_id>', methods=['DELETE'])
@login_required
def delete_request(request_id):
    try:
        success = Request.delete(request_id)
        if success:
            return jsonify({'message': 'Request deleted successfully'})
        else:
            return jsonify({'error': 'Request not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/requests/<int:request_id>/logs', methods=['GET'])
@login_required
def get_request_logs(request_id):
    try:
        logs = RequestLog.get_logs_for_request(request_id)
        return jsonify(logs)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/users', methods=['GET'])
@login_required
def get_users():
    all_users = User.get_all()
    # Filter out Mahmud from team member selection
    filtered_users = [user for user in all_users if user['full_name'].lower() != 'mahmud']
    return jsonify(filtered_users)

@app.route('/api/service-types', methods=['GET'])
@login_required
def get_service_types():
    return jsonify(Request.SERVICE_TYPES)

@app.route('/api/dashboard/stats', methods=['GET'])
@login_required
def get_dashboard_stats():
    return jsonify(Request.get_stats())

@app.route('/api/reports/daily', methods=['GET'])
@login_required
def get_daily_report():
    target_date = request.args.get('date')
    if not target_date:
        from datetime import date
        target_date = date.today().strftime('%Y-%m-%d')
    
    try:
        data = Request.get_daily_report(target_date)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/weekly', methods=['GET'])
@login_required
def get_weekly_report():
    week_str = request.args.get('week')
    if not week_str:
        from datetime import date
        today = date.today()
        year = today.year
        week = today.isocalendar()[1]
    else:
        # Parse format like "2024-W52"
        year, week_part = week_str.split('-W')
        year = int(year)
        week = int(week_part)
    
    try:
        data = Request.get_weekly_report(year, week)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/monthly', methods=['GET'])
@login_required
def get_monthly_report():
    month_str = request.args.get('month')
    if not month_str:
        from datetime import date
        today = date.today()
        year = today.year
        month = today.month
    else:
        # Parse format like "2024-12"
        year, month = month_str.split('-')
        year = int(year)
        month = int(month)
    
    try:
        data = Request.get_monthly_report(year, month)
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Export endpoints
@app.route('/api/reports/daily/export/<format_type>', methods=['GET'])
@login_required
def export_daily_report(format_type):
    """Export daily report as PDF or Excel"""
    target_date = request.args.get('date')
    if not target_date:
        from datetime import date
        target_date = date.today().strftime('%Y-%m-%d')
    
    try:
        # Get report data
        data = Request.get_daily_report(target_date)
        period = f"Daily Report - {target_date}"
        
        if format_type.lower() == 'pdf':
            exporter = PDFExporter()
            buffer = exporter.create_report_pdf(data, 'daily', period)
            return send_file(
                buffer,
                as_attachment=True,
                download_name=f'daily_report_{target_date}.pdf',
                mimetype='application/pdf'
            )
        elif format_type.lower() == 'excel':
            exporter = ExcelExporter()
            buffer = exporter.create_report_excel(data, 'daily', period)
            return send_file(
                buffer,
                as_attachment=True,
                download_name=f'daily_report_{target_date}.xlsx',
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        else:
            return jsonify({'error': 'Invalid format type'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/weekly/export/<format_type>', methods=['GET'])
@login_required
def export_weekly_report(format_type):
    """Export weekly report as PDF or Excel"""
    week_str = request.args.get('week')
    if not week_str:
        from datetime import date
        today = date.today()
        year = today.year
        week = today.isocalendar()[1]
    else:
        # Parse format like "2024-W52"
        year, week_part = week_str.split('-W')
        year = int(year)
        week = int(week_part)
    
    try:
        # Get report data
        data = Request.get_weekly_report(year, week)
        period = f"Weekly Report - Week {week}, {year}"
        
        if format_type.lower() == 'pdf':
            exporter = PDFExporter()
            buffer = exporter.create_report_pdf(data, 'weekly', period)
            return send_file(
                buffer,
                as_attachment=True,
                download_name=f'weekly_report_{year}_W{week:02d}.pdf',
                mimetype='application/pdf'
            )
        elif format_type.lower() == 'excel':
            exporter = ExcelExporter()
            buffer = exporter.create_report_excel(data, 'weekly', period)
            return send_file(
                buffer,
                as_attachment=True,
                download_name=f'weekly_report_{year}_W{week:02d}.xlsx',
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        else:
            return jsonify({'error': 'Invalid format type'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/monthly/export/<format_type>', methods=['GET'])
@login_required
def export_monthly_report(format_type):
    """Export monthly report as PDF or Excel"""
    month_str = request.args.get('month')
    if not month_str:
        from datetime import date
        today = date.today()
        year = today.year
        month = today.month
    else:
        # Parse format like "2024-12"
        year, month = month_str.split('-')
        year = int(year)
        month = int(month)
    
    try:
        # Get report data
        data = Request.get_monthly_report(year, month)
        period = f"Monthly Report - {datetime(year, month, 1).strftime('%B %Y')}"
        
        if format_type.lower() == 'pdf':
            exporter = PDFExporter()
            buffer = exporter.create_report_pdf(data, 'monthly', period)
            return send_file(
                buffer,
                as_attachment=True,
                download_name=f'monthly_report_{year}_{month:02d}.pdf',
                mimetype='application/pdf'
            )
        elif format_type.lower() == 'excel':
            exporter = ExcelExporter()
            buffer = exporter.create_report_excel(data, 'monthly', period)
            return send_file(
                buffer,
                as_attachment=True,
                download_name=f'monthly_report_{year}_{month:02d}.xlsx',
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
        else:
            return jsonify({'error': 'Invalid format type'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)