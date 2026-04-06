import cx_Oracle
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app) 

# Database Configuration
DB_CONFIG = {
    "user": "APPS",
    "password": "WELCOME",
    "dsn": """(DESCRIPTION=(ADDRESS=(PROTOCOL=TCP)(HOST=192.168.1.6)(PORT=1521))(CONNECT_DATA=(SERVER=DEDICATED)(SERVICE_NAME=orcl)))"""
}

def get_db_connection():
    try:
        return cx_Oracle.connect(user=DB_CONFIG["user"], password=DB_CONFIG["password"], dsn=DB_CONFIG["dsn"])
    except cx_Oracle.Error as e:
        print(f"Oracle Error: {e}")
        return None

@app.route('/sync', methods=['POST'])
def sync_data():
    data = request.json
    conn = get_db_connection()
    if not conn: return jsonify({"success": False, "error": "DB Connection Failed"}), 500
    
    try:
        cursor = conn.cursor()
        
        # Parse full timestamp from JS: '2024-05-20 22:00:00'
        dt_obj = datetime.strptime(data['timestamp'], '%Y-%m-%d %H:%M:%S')
        
        # Action specific handling
        action = data['action']
        logic_date = dt_obj
        
        # Night Shift Logic: Subah 7 AM se pehle OUT hone par pichle din ki row update karein
        if action in ['DUTY OUT', 'LUNCH IN'] and dt_obj.hour < 7:
            logic_date = dt_obj - timedelta(days=1)
        
        date_office_str = logic_date.strftime('%Y-%m-%d')
        full_timestamp_str = data['timestamp'] # For the DATE columns
        
        # Column Mapping
        col_name = ""
        if action == 'DUTY IN': col_name = "IN_TIME"
        elif action == 'LUNCH OUT': col_name = "LUNCH_OUT"
        elif action == 'LUNCH IN': col_name = "LUNCH_IN"
        elif action == 'DUTY OUT': col_name = "OUT_TIME"

        if not col_name: return jsonify({"success": False, "error": "Invalid Action"}), 400

        # UPSERT Logic (Check if exists, then Update or Insert)
        check_sql = "SELECT COUNT(*) FROM GATE_REGISTER_DAILY WHERE EMP_CODE = :1 AND DATE_OFFICE = TO_DATE(:2, 'YYYY-MM-DD')"
        cursor.execute(check_sql, (data['emp_id'], date_office_str))
        exists = cursor.fetchone()[0] > 0

        if exists:
            # Update matching row: Timing column is now a DATE type
            final_sql = f"UPDATE GATE_REGISTER_DAILY SET {col_name} = TO_DATE(:1, 'YYYY-MM-DD HH24:MI:SS') WHERE EMP_CODE = :2 AND DATE_OFFICE = TO_DATE(:3, 'YYYY-MM-DD')"
            cursor.execute(final_sql, (full_timestamp_str, data['emp_id'], date_office_str))
        else:
            # Insert new row: DATE_OFFICE and timing column both as DATE types
            final_sql = f"INSERT INTO GATE_REGISTER_DAILY (EMP_CODE, DATE_OFFICE, {col_name}) VALUES (:1, TO_DATE(:2, 'YYYY-MM-DD'), TO_DATE(:3, 'YYYY-MM-DD HH24:MI:SS'))"
            cursor.execute(final_sql, (data['emp_id'], date_office_str, full_timestamp_str))
        
        conn.commit()
        conn.close()
        print(f"Success: {action} (DATE TYPE) recorded for {data['emp_id']}")
        return jsonify({"success": True})
    except Exception as e:
        print(f"Sync Error Detail: {str(e)}")
        if conn: conn.close()
        return jsonify({"success": False, "error": str(e)}), 400

# Employees and Test routes remain same...
@app.route('/employees', methods=['GET'])
def get_employees():
    conn = get_db_connection()
    if not conn: return jsonify([]), 500
    try:
        cursor = conn.cursor()
        query = """
        SELECT EMP_CODE, EMP_NAME, 
               (SELECT GROUP_CODE FROM EASY_DEPT WHERE LTRIM(RTRIM(DEPARTMENTCODE)) = LTRIM(RTRIM(DEPT_CODE))) as DEPT_CODE
        FROM EMP_MST@DB_ORCL_TO_SVR a, GRADE_MST@DB_ORCL_TO_SVR b, EASY_DEPT C
        WHERE LTRIM(RTRIM(A.DEPT_CODE)) = LTRIM(RTRIM(C.DEPARTMENTCODE))
        AND a.grade = b.code AND STATUS = 'Y' AND EMP_TYPE = 'S' AND EMP_CODE <> '12981'
        ORDER BY DEPT_RANK, rank, emp_name
        """  
        cursor.execute(query)
        res = [{"EMP_CODE": r[0], "EMP_NAME": r[1], "DEPT_CODE": r[2]} for r in cursor.fetchall()]
        conn.close()
        return jsonify(res)
    except: return jsonify([]), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)