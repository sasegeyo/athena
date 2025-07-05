from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import sqlite3
import json
from datetime import datetime
import threading
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*")

# Veritabanı kurulumu
def init_db():
    conn = sqlite3.connect('co_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS co_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            co_level REAL NOT NULL,
            timestamp DATETIME NOT NULL,
            device_id TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# Veritabanına veri ekleme
def insert_co_data(co_level, device_id):
    conn = sqlite3.connect('co_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO co_readings (co_level, timestamp, device_id)
        VALUES (?, ?, ?)
    ''', (co_level, datetime.now(), device_id))
    conn.commit()
    conn.close()

# Son verileri getirme
def get_latest_data(limit=50):
    conn = sqlite3.connect('co_data.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT co_level, timestamp, device_id 
        FROM co_readings 
        ORDER BY timestamp DESC 
        LIMIT ?
    ''', (limit,))
    
    data = []
    for row in cursor.fetchall():
        data.append({
            'co_level': row[0],
            'timestamp': row[1],
            'device_id': row[2]
        })
    
    conn.close()
    return data

# Ana sayfa
@app.route('/')
def index():
    return render_template('index.html')

# ESP32'den veri alma endpoint'i
@app.route('/api/co-data', methods=['POST'])
def receive_co_data():
    try:
        data = request.get_json()
        co_level = float(data['co_level'])
        device_id = data.get('device_id', 'Unknown')
        
        # Veritabanına kaydet
        insert_co_data(co_level, device_id)
        
        # WebSocket ile canlı güncelleme gönder
        socketio.emit('new_co_data', {
            'co_level': co_level,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'device_id': device_id
        })
        
        return jsonify({'status': 'success', 'message': 'Data received'})
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

# Geçmiş verileri API
@app.route('/api/history')
def get_history():
    data = get_latest_data(100)
    return jsonify(data)

# Son veriyi API
@app.route('/api/current')
def get_current():
    data = get_latest_data(1)
    if data:
        return jsonify(data[0])
    return jsonify({'co_level': 0, 'timestamp': '', 'device_id': 'No data'})

# WebSocket bağlantı olayları
@socketio.on('connect')
def handle_connect():
    print('Client connected')
    # Bağlanan client'a son veriyi gönder
    current_data = get_latest_data(1)
    if current_data:
        emit('new_co_data', current_data[0])

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

if __name__ == '__main__':
    init_db()
    print("CO Monitoring Server başlatılıyor...")
    print("Web arayüzü: http://192.168.1.102:5000")
    print("ESP32 endpoint: http://192.168.1.102:5000/api/co_data")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)