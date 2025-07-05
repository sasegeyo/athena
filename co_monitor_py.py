from flask import Flask, request, jsonify
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)

# Kritik eşik değerleri
CO_CRITICAL_LIMIT = 300.0  # ppm
TEMP_LIMIT = 50.0          # °C

# E-posta ayarları
SMTP_CONFIG = {
    "sender": "athenaproje21@gmail.com",
    "password": "dlji kmff zfbc kiak",  # Gmail app password
    "receiver": "habibiskanoglu01@gmail.com",
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587
}

# Cihazlara özel alarm takibi
device_alarm_status = {}

# E-posta gönderme fonksiyonu
def send_email(subject, body):
    try:
        msg = MIMEText(body, "html")
        msg["Subject"] = subject
        msg["From"] = SMTP_CONFIG["sender"]
        msg["To"] = SMTP_CONFIG["receiver"]

        server = smtplib.SMTP(SMTP_CONFIG["smtp_server"], SMTP_CONFIG["smtp_port"])
        server.starttls()
        server.login(SMTP_CONFIG["sender"], SMTP_CONFIG["password"])
        server.send_message(msg)
        server.quit()
        print("✅ E-posta gönderildi.")
        return True
    except Exception as e:
        print("❌ E-posta gönderilemedi:", e)
        return False

# Sensör verilerini işleme
def process_sensor_data(co, temp, humid, alarm, device_id):
    if device_id not in device_alarm_status:
        device_alarm_status[device_id] = {
            "co_alarm": False,
            "temp_alarm": False,
            "general_alarm": False
        }

    current = device_alarm_status[device_id]
    email_sent = False

    if co > CO_CRITICAL_LIMIT and not current["co_alarm"]:
        subject = f"🚨 CO Kritik Seviyesi Aşıldı - {device_id}"
        body = f"<h3>CO Seviyesi: {co} ppm - Kritik eşik ({CO_CRITICAL_LIMIT}) aşıldı!</h3>"
        if send_email(subject, body):
            current["co_alarm"] = True
            email_sent = True

    elif temp > TEMP_LIMIT and not current["temp_alarm"]:
        subject = f"🔥 Yüksek Sıcaklık Uyarısı - {device_id}"
        body = f"<h3>Sıcaklık: {temp} °C - Limit ({TEMP_LIMIT} °C) aşıldı!</h3>"
        if send_email(subject, body):
            current["temp_alarm"] = True
            email_sent = True

    elif alarm and not current["general_alarm"]:
        subject = f"⚠️ Genel Alarm - {device_id}"
        body = "<h3>Cihaz genel alarm verdi!</h3>"
        if send_email(subject, body):
            current["general_alarm"] = True
            email_sent = True

    # Normale döndüğünde sıfırlama
    if co <= CO_CRITICAL_LIMIT and current["co_alarm"]:
        current["co_alarm"] = False
        send_email(f"✅ CO Normale Döndü - {device_id}", f"<p>CO seviyesi tekrar güvenli seviyede: {co} ppm</p>")

    if temp <= TEMP_LIMIT and current["temp_alarm"]:
        current["temp_alarm"] = False

    if not alarm and current["general_alarm"]:
        current["general_alarm"] = False

    return {
        "status": "ok",
        "email_sent": email_sent,
        "device_status": current
    }

# Veri alımı
@app.route("/api/co_data", methods=["POST"])
def receive_data():
    data = request.get_json()
    return jsonify(process_sensor_data(
        co=data.get("co_level", 0),
        temp=data.get("temperature", 0),
        humid=data.get("humidity", 0),
        alarm=data.get("alarm_status", False),
        device_id=data.get("device_id", "Unknown")
    ))

# Sistem durumu
@app.route("/api/status", methods=["GET"])
def get_status():
    return jsonify({
        "device_alarm_status": device_alarm_status,
        "limits": {
            "co_limit": CO_CRITICAL_LIMIT,
            "temp_limit": TEMP_LIMIT
        }
    })

# Alarm test endpoint'i (350 ppm)
@app.route("/api/test_critical_alert", methods=["POST"])
def test_critical_alert():
    test_data = {
        "co_level": 350.0,
        "temperature": 25.0,
        "humidity": 60.0,
        "alarm_status": False,
        "device_id": "TEST_DEVICE"
    }
    result = process_sensor_data(**test_data)
    return jsonify({"message": "Test CO alarm triggered", "result": result})

# Güvenli test endpoint'i (250 ppm)
@app.route("/api/test_safe_alert", methods=["POST"])
def test_safe_alert():
    test_data = {
        "co_level": 250.0,
        "temperature": 25.0,
        "humidity": 60.0,
        "alarm_status": False,
        "device_id": "TEST_DEVICE"
    }
    result = process_sensor_data(**test_data)
    return jsonify({"message": "CO güvenli seviyeye döndü", "result": result})

# Alarm reset
@app.route("/api/reset_alarms", methods=["POST"])
def reset_alarms():
    global device_alarm_status
    device_alarm_status = {}
    return jsonify({"status": "Tüm alarmlar sıfırlandı"}), 200

# Sunucuyu başlat
if __name__ == "__main__":
    print("=" * 60)
    print("🚨 CO İzleme Sistemi Başlatılıyor")
    print("=" * 60)
    print(f"📊 Kritik CO Limiti: {CO_CRITICAL_LIMIT} ppm")
    print(f"🌡️ Sıcaklık Limiti: {TEMP_LIMIT} °C")
    print(f"📧 E-posta Alıcısı: {SMTP_CONFIG['receiver']}")
    print(f"🔗 Test URL: http://192.168.1.102:5000")
    print("=" * 60)
    print("✅ Sistem hazır - CO değerlerini izlemeye başlandı")
    print("⚠️  300 ppm aşıldığında otomatik e-posta gönderilecek")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=True)
