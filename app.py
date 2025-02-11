import pymysql
pymysql.install_as_MySQLdb()

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sock import Sock
import json
import os

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes
sock = Sock(app)  # WebSocket setup

# Database configuration (update with correct values)
app.config["MYSQL_HOST"] = "sql7.freesqldatabase.com"
app.config["MYSQL_USER"] = "sql7753033"
app.config["MYSQL_PASSWORD"] = "BRNRDdUJuV"
app.config["MYSQL_DB"] = "sql7753033"
app.config["MYSQL_PORT"] = 3306

from flask_mysqldb import MySQL
mysql = MySQL(app)

# Helper function to validate table names
def validate_table_name(table_name):
    allowed_chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
    if all(char in allowed_chars for char in table_name):
        return table_name
    raise ValueError("Invalid table name")

# Root route
@app.route("/")
def home():
    return "Welcome to the Vending Machine API. WebSocket is running."

# Route to fetch vending machines
@app.route("/vendingmachines", methods=["GET"])
def get_vending_machines():
    cursor = None
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("SELECT vendingMachineCode AS code, vendingMachineName AS name FROM vendingmachines")
        vending_machines = cursor.fetchall()
        return jsonify([{ "code": row[0], "name": row[1] } for row in vending_machines])
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()

# WebSocket route
@sock.route('/ws')
def websocket_connection(ws):
    while True:
        try:
            message = ws.receive()
            if not message:
                break

            data = json.loads(message)
            event = data.get("event")
            payload = data.get("data")

            if event == "sell_product":
                handle_sell_product(ws, payload)
            elif event == "update_price":
                handle_update_price(ws, payload)
            elif event == "custom_command":
                handle_custom_command(ws, payload)
            else:
                ws.send(json.dumps({"error": "Invalid event type"}))

        except Exception as e:
            ws.send(json.dumps({"error": str(e)}))
            break

# Sell product functionality
def handle_sell_product(ws, data):
    vending_machine_code = data.get("vendingMachineCode")
    uid = data.get("uid")
    password = data.get("password")
    product_code = data.get("productCode")
    product_price = data.get("productPrice")

    cursor = None
    try:
        cursor = mysql.connection.cursor()

        # Verify vending machine
        cursor.execute("SELECT vendingMachineId FROM vendingmachines WHERE vendingMachineCode = %s", (vending_machine_code,))
        vending_machine = cursor.fetchone()
        if not vending_machine:
            ws.send(json.dumps({"sell_response": "Invalid vending machine code"}))
            return
        vending_machine_id = vending_machine[0]

        # Verify user
        cursor.execute("SELECT userId, balance FROM users WHERE uid = %s AND password = %s", (uid, password))
        user = cursor.fetchone()
        if not user:
            ws.send(json.dumps({"sell_response": "Invalid user credentials"}))
            return
        user_id, balance = user

        # Check balance
        if balance < product_price:
            ws.send(json.dumps({"sell_response": f"Insufficient balance, {balance}"}))
            return

        # Update user's balance
        new_balance = balance - product_price
        cursor.execute("UPDATE users SET balance = %s WHERE userId = %s", (new_balance, user_id))

        # Record the sale
        sale_table = validate_table_name(f"sales{vending_machine_id}")
        cursor.execute(
            f"INSERT INTO {sale_table} (productName, SalePrice, saleTime) VALUES (%s, %s, NOW())",
            (product_code, product_price)
        )

        # Record the purchase
        purchase_table = validate_table_name(f"purchases{user_id}")
        cursor.execute(
            f"INSERT INTO {purchase_table} (price, date) VALUES (%s, NOW())",
            (product_price,)
        )

        mysql.connection.commit()
        ws.send(json.dumps({"sell_response": f"Sale successful, {balance}"}))

    except Exception as e:
        ws.send(json.dumps({"sell_response": str(e)}))

    finally:
        if cursor:
            cursor.close()

# Update price functionality
def handle_update_price(ws, data):
    vending_machine_code = data.get("vendingMachineCode")
    product_code = data.get("productCode")
    new_price = data.get("newPrice")

    cursor = None
    try:
        cursor = mysql.connection.cursor()

        # Verify vending machine
        cursor.execute("SELECT vendingMachineId FROM vendingmachines WHERE vendingMachineCode = %s", (vending_machine_code,))
        vending_machine = cursor.fetchone()
        if not vending_machine:
            ws.send(json.dumps({"update_response": "Invalid vending machine code"}))
            return
        vending_machine_id = vending_machine[0]

        # Update product price
        query = """
            UPDATE products 
            SET productPrice = %s 
            WHERE vendingMachineId = %s AND productCode = %s
        """
        cursor.execute(query, (new_price, vending_machine_id, product_code))
        mysql.connection.commit()
        ws.send(json.dumps({"update_response": "Product price updated successfully"}))

    except Exception as e:
        ws.send(json.dumps({"update_response": str(e)}))

    finally:
        if cursor:
            cursor.close()

# Custom command functionality
def handle_custom_command(ws, data):
    vending_machine_code = data.get("vendingMachineCode")
    command = data.get("command")
    try:
        ws.send(json.dumps({"custom_command_response": f"Command '{command}' sent to vending machine '{vending_machine_code}'"}))
    except Exception as e:
        ws.send(json.dumps({"error": str(e)}))

# Run the Flask app
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=os.getenv('PORT', 3000), debug=True)
