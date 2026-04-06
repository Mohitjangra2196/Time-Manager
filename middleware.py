import cx_Oracle
from flask import Flask, request, jsonify
from flask_cors import CORS
import datetime

app = Flask(__name__)
CORS(app) 

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

@app.route('/employees', methods=['GET'])
def get_employees():
    conn = get_db_connection()
    if not conn: return jsonify([]), 500
    try:
        cursor = conn.cursor()
        query = """
        SELECT EMP_CODE, EMP_NAME , ( SELECT GROUP_CODE FROM EASY_DEPT WHERE LTRIM(RTRIM (DEPARTMENTCODE)) = LTRIM(RTRIM (DEPT_CODE))  )  DEPT_CODE 
        ,DESIG
        FROM EMP_MST@DB_ORCL_TO_SVR  a  , GRADE_MST@DB_ORCL_TO_SVR b  , EASY_DEPT C
        WHERE 
        LTRIM(RTRIM (A.DEPT_CODE)) = LTRIM(RTRIM (C.DEPARTMENTCODE))
        AND a.grade = b.code
        and STATUS = 'Y'
        AND EMP_TYPE = 'S'
        AND EMP_CODE <> '12981'
        ORDER BY DEPT_RANK ,rank , emp_name
        """  
        cursor.execute(query)
        res = [{"EMP_CODE": r[0], "EMP_NAME": r[1], "DEPT_CODE": r[2]} for r in cursor.fetchall()]
        conn.close()
        return jsonify(res)
    except: return jsonify([]), 500

@app.route('/sync', methods=['POST'])
def sync_data():
    data = request.json
    conn = get_db_connection()
    if not conn: return jsonify({"success": False}), 500
    try:
        cursor = conn.cursor()
        # Note: Ensure your LUNCH_LOGS table has enough columns or map ACTION to your existing schema
        sql = "INSERT INTO LUNCH_LOGS (EMP_ID, ACTION, LOG_TIME) VALUES (:1, :2, TO_DATE(:3, 'YYYY-MM-DD HH24:MI:SS'))"
        cursor.execute(sql, (data['emp_id'], data['action'], data['timestamp']))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)