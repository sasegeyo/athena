from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import sqlite3
import json
from datetime import datetime
import threading
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'co_monitoring_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*")

# Veritabanı kurulumu
def init_db():
    conn = sqlite3.connect('co_monitoring.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS co_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT,
            co_level REAL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# Veritabanına veri ekleme
def add_co_reading(device_id, co_level):
    conn = sqlite3.connect('co_monitoring.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO co_readings (device_id, co_level)
        VALUES (?, ?)
    ''', (device_id, co_level))
    conn.commit()
    conn.close()

# Geçmiş verileri alma
def get_history(limit=50):
    conn = sqlite3.connect('co_monitoring.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT device_id, co_level, timestamp
        FROM co_readings
        ORDER BY timestamp DESC
        LIMIT ?
    ''', (limit,))
    results = cursor.fetchall()
    conn.close()
    
    return [
        {
            'device_id': row[0],
            'co_level': row[1],
            'timestamp': row[2]
        }
        for row in results
    ]

# Ana sayfa
@app.route('/')
def index():
    return render_template('index.html')

# Geçmiş verileri API endpoint'i
@app.route('/api/history')
def api_history():
    try:
        data = get_history()
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ESP32'den veri alma endpoint'i
@app.route('/api/co_data', methods=['POST'])
def receive_co_data():
    try:
        data = request.get_json()
        
        if not data or 'co_level' not in data:
            return jsonify({'error': 'CO level verisi eksik'}), 400
        
        device_id = data.get('device_id', 'ESP32_CO_Sensor')
        co_level = float(data['co_level'])
        
        # Veritabanına kaydet
        add_co_reading(device_id, co_level)
        
        # Tüm bağlı istemcilere gerçek zamanlı veri gönder
        socketio.emit('new_co_data', {
            'device_id': device_id,
            'co_level': co_level,
            'timestamp': datetime.now().isoformat()
        })
        
        print(f"Yeni CO verisi alındı: {co_level} ppm - {device_id}")
        
        return jsonify({
            'status': 'success',
            'message': 'Veri başarıyla alındı',
            'co_level': co_level
        })
        
    except Exception as e:
        print(f"Veri alma hatası: {str(e)}")
        return jsonify({'error': str(e)}), 500

# WebSocket bağlantı olayları
@socketio.on('connect')
def handle_connect():
    print('İstemci bağlandı')
    emit('status', {'msg': 'Sunucuya bağlandınız'})

@socketio.on('disconnect')
def handle_disconnect():
    print('İstemci bağlantıyı kesti')

# Test verisi gönderme (geliştirme amaçlı)
@app.route('/api/test_data')
def test_data():
    import random
    
    # Rastgele test verisi oluştur
    co_level = random.uniform(0, 150)
    device_id = "TEST_DEVICE"
    
    add_co_reading(device_id, co_level)
    
    socketio.emit('new_co_data', {
        'device_id': device_id,
        'co_level': co_level,
        'timestamp': datetime.now().isoformat()
    })
    
    return jsonify({
        'status': 'Test verisi gönderildi',
        'co_level': co_level
    })

# Sistem durumu kontrolü
@app.route('/api/status')
def system_status():
    try:
        # Son 5 dakikadaki veri sayısını kontrol et
        conn = sqlite3.connect('co_monitoring.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT COUNT(*) FROM co_readings 
            WHERE datetime(timestamp) > datetime('now', '-5 minutes')
        ''')
        recent_count = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM co_readings')
        total_count = cursor.fetchone()[0]
        
        conn.close()
        
        return jsonify({
            'status': 'active',
            'recent_readings': recent_count,
            'total_readings': total_count,
            'last_check': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("CO Gas Monitoring System başlatılıyor...")
    print("HTML dosyasını 'templates' klasörüne koyduğunuzdan emin olun!")
    
    # Veritabanını başlat
    init_db()
    
    # Sunucuyu çalıştır
    socketio.run(app, 
                debug=True, 
                host='0.0.0.0', 
                port=5000,
                allow_unsafe_werkzeug=True)