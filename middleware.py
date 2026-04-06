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
        dt_obj = datetime.strptime(data['timestamp'], '%Y-%m-%d %H:%M:%S')
        action = data['action']
        logic_date = dt_obj
        
        # Night Shift Logic
        if action in ['DUTY OUT', 'LUNCH IN'] and dt_obj.hour < 7:
            logic_date = dt_obj - timedelta(days=1)
        
        date_office_str = logic_date.strftime('%Y-%m-%d')
        full_timestamp_str = data['timestamp']
        
        col_name = ""
        if action == 'DUTY IN': col_name = "IN_TIME"
        elif action == 'LUNCH OUT': col_name = "LUNCH_OUT"
        elif action == 'LUNCH IN': col_name = "LUNCH_IN"
        elif action == 'DUTY OUT': col_name = "OUT_TIME"

        if not col_name: return jsonify({"success": False, "error": "Invalid Action"}), 400

        check_sql = "SELECT COUNT(*) FROM GATE_REGISTER_DAILY WHERE EMP_CODE = :1 AND DATE_OFFICE = TO_DATE(:2, 'YYYY-MM-DD')"
        cursor.execute(check_sql, (data['emp_id'], date_office_str))
        exists = cursor.fetchone()[0] > 0

        if exists:
            final_sql = f"UPDATE GATE_REGISTER_DAILY SET {col_name} = TO_DATE(:1, 'YYYY-MM-DD HH24:MI:SS') WHERE EMP_CODE = :2 AND DATE_OFFICE = TO_DATE(:3, 'YYYY-MM-DD')"
            cursor.execute(final_sql, (full_timestamp_str, data['emp_id'], date_office_str))
        else:
            final_sql = f"INSERT INTO GATE_REGISTER_DAILY (EMP_CODE, DATE_OFFICE, {col_name}) VALUES (:1, TO_DATE(:2, 'YYYY-MM-DD'), TO_DATE(:3, 'YYYY-MM-DD HH24:MI:SS'))"
            cursor.execute(final_sql, (data['emp_id'], date_office_str, full_timestamp_str))
        
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        if conn: conn.close()
        return jsonify({"success": False, "error": str(e)}), 400

@app.route('/employees', methods=['GET'])
def get_employees():
    conn = get_db_connection()
    if not conn: return jsonify([]), 500
    try:
        cursor = conn.cursor()
        # Aaj ki date office logic ke liye
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        # Query updated to LEFT JOIN with GATE_REGISTER_DAILY to get current status
        query = f"""
        SELECT a.EMP_CODE, a.EMP_NAME, 
               (SELECT GROUP_CODE FROM EASY_DEPT WHERE LTRIM(RTRIM(DEPARTMENTCODE)) = LTRIM(RTRIM(a.DEPT_CODE))) as DEPT_CODE,
               TO_CHAR(g.IN_TIME, 'HH24:MI') as IN_T,
               TO_CHAR(g.LUNCH_OUT, 'HH24:MI') as L_OUT,
               TO_CHAR(g.LUNCH_IN, 'HH24:MI') as L_IN,
               TO_CHAR(g.OUT_TIME, 'HH24:MI') as OUT_T
        FROM EMP_MST@DB_ORCL_TO_SVR a
        JOIN GRADE_MST@DB_ORCL_TO_SVR b ON a.grade = b.code
        JOIN EASY_DEPT C ON LTRIM(RTRIM(A.DEPT_CODE)) = LTRIM(RTRIM(C.DEPARTMENTCODE))
        LEFT JOIN GATE_REGISTER_DAILY g ON a.EMP_CODE = g.EMP_CODE AND g.DATE_OFFICE = TO_DATE('{today_str}', 'YYYY-MM-DD')
        WHERE STATUS = 'Y' AND EMP_TYPE = 'S' AND a.EMP_CODE <> '12981'
        ORDER BY DEPT_RANK, rank, emp_name
        """  
        cursor.execute(query)
        res = []
        for r in cursor.fetchall():
            res.append({
                "EMP_CODE": r[0], 
                "EMP_NAME": r[1], 
                "DEPT_CODE": r[2],
                "IN_TIME": r[3],
                "LUNCH_OUT": r[4],
                "LUNCH_IN": r[5],
                "OUT_TIME": r[6]
            })
        conn.close()
        return jsonify(res)
    except Exception as e:
        print(e)
        return jsonify([]), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)