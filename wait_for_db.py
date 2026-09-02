import os, time, sys, pymysql

host = os.environ.get("DB_HOST", "db")
port = int(os.environ.get("DB_PORT", 3306))
user = os.environ.get("DB_USER", "itguy")
pw = os.environ.get("DB_PASS", "itguypass")

print(f"Waiting for MariaDB at {host}:{port} ...")
deadline = time.time() + 60
while time.time() < deadline:
    try:
        conn = pymysql.connect(host=host, port=port, user=user, password=pw)
        conn.close()
        print("MariaDB is reachable.")
        sys.exit(0)
    except Exception as e:
        time.sleep(2)

print("Timed out waiting for MariaDB:", e)
sys.exit(1)
