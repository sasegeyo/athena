from flask import Flask, request, jsonify
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from datetime import datetime

from co_monitor_py import process_sensor_data

app = Flask(__name__)

# Logging yapılandırması
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Kritik eşik değerleri
CO_CRITICAL_LIMIT = 300.0  # ppm - Kritik CO seviyesi
TEMP_LIMIT = 50.0  # °C - Sıcaklık limiti

# SMTP Ayarları
SMTP_CONFIG = {
    "server": "smtp.gmail.com",
    "port": 587,
    "email": "athenaproje21@gmail.com",
    "password": "dlji kmff zfbc kiak",
    "receiver": "habibiskanoglu01@gmail.com"
}

# Her cihaz için alarm durumunu takip etmek için dictionary
device_alarm_status = {}

def send_email(subject, body, is_html=True):
    """E-posta gönderme fonksiyonu"""
    try:
        logger.info(f"E-posta gönderiliyor: {subject}")
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = SMTP_CONFIG['email']
        msg['To'] = SMTP_CONFIG['receiver']
        
        # HTML içeriği ekle
        if is_html:
            html_part = MIMEText(body, 'html', 'utf-8')
            msg.attach(html_part)
        else:
            text_part = MIMEText(body, 'plain', 'utf-8')
            msg.attach(text_part)
        
        # SMTP sunucusuna bağlan ve e-posta gönder
        with smtplib.SMTP(SMTP_CONFIG['server'], SMTP_CONFIG['port']) as server:
            server.starttls()
            server.login(SMTP_CONFIG['email'], SMTP_CONFIG['password'])
            server.send_message(msg)
        
        logger.info("E-posta başarıyla gönderildi")
        return True
        
    except Exception as e:
        logger.error(f"E-posta gönderme hatası: {str(e)}")
        return False

def create_critical_co_alert_email(device_id, co_level, temp, humidity):
    """300 ppm aşıldığında kritik CO alarm e-postası oluşturur"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    subject = f"🚨 KRİTİK ALARM: CO Seviyesi 300 PPM Aşıldı - {device_id}"
    
    body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Kritik CO Alarmı</title>
    </head>
    <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
        <div style="max-width: 600px; margin: 0 auto; background-color: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            
            <!-- Header -->
            <div style="background-color: #dc3545; color: white; padding: 20px; text-align: center;">
                <h1 style="margin: 0; font-size: 24px;">🚨 KRİTİK CO ALARMI 🚨</h1>
                <p style="margin: 5px 0 0 0; font-size: 16px;">ACİL DURUM - DERHAL MÜDAHALE GEREKİYOR</p>
            </div>
            
            <!-- Ana İçerik -->
            <div style="padding: 20px;">
                <div style="background-color: #fff3cd; border: 2px solid #ffc107; border-radius: 8px; padding: 15px; margin-bottom: 20px;">
                    <h2 style="color: #856404; margin: 0 0 10px 0;">⚠️ UYARI ⚠️</h2>
                    <p style="color: #856404; font-weight: bold; margin: 0; font-size: 16px;">
                        CO seviyesi 300 ppm kritik eşiğini aştı!
                    </p>
                </div>
                
                <!-- Cihaz Bilgileri -->
                <h3 style="color: #333; border-bottom: 2px solid #dc3545; padding-bottom: 5px;">Cihaz Bilgileri</h3>
                <table style="width: 100%; border-collapse: collapse; margin: 15px 0;">
                    <tr style="background-color: #f8f9fa;">
                        <td style="padding: 12px; border: 1px solid #dee2e6; font-weight: bold; width: 40%;">Cihaz ID</td>
                        <td style="padding: 12px; border: 1px solid #dee2e6;">{device_id}</td>
                    </tr>
                    <tr style="background-color: #fff5f5;">
                        <td style="padding: 12px; border: 1px solid #dee2e6; font-weight: bold;">CO Seviyesi</td>
                        <td style="padding: 12px; border: 1px solid #dee2e6; color: #dc3545; font-weight: bold; font-size: 16px;">
                            {co_level:.1f} ppm (Kritik Limit: {CO_CRITICAL_LIMIT} ppm)
                        </td>
                    </tr>
                    <tr style="background-color: #f8f9fa;">
                        <td style="padding: 12px; border: 1px solid #dee2e6; font-weight: bold;">Sıcaklık</td>
                        <td style="padding: 12px; border: 1px solid #dee2e6;">{temp:.1f} °C</td>
                    </tr>
                    <tr style="background-color: #fff5f5;">
                        <td style="padding: 12px; border: 1px solid #dee2e6; font-weight: bold;">Nem</td>
                        <td style="padding: 12px; border: 1px solid #dee2e6;">{humidity:.1f} %</td>
                    </tr>
                    <tr style="background-color: #f8f9fa;">
                        <td style="padding: 12px; border: 1px solid #dee2e6; font-weight: bold;">Alarm Zamanı</td>
                        <td style="padding: 12px; border: 1px solid #dee2e6;">{timestamp}</td>
                    </tr>
                </table>
                
                <!-- Acil Eylem Planı -->
                <div style="background-color: #dc3545; color: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="margin: 0 0 15px 0;">🚨 ACİL EYLEM PLANI</h3>
                    <ul style="margin: 0; padding-left: 20px; line-height: 1.6;">
                        <li><strong>DERHAL alanı terk edin</strong></li>
                        <li><strong>Tüm kapı ve pencereleri açın</strong></li>
                        <li><strong>Havalandırma sistemini maksimuma çıkarın</strong></li>
                        <li><strong>CO kaynağını durdurun (mümkünse güvenli bir şekilde)</strong></li>
                        <li><strong>Gerekirse 112 Acil Servisi arayın</strong></li>
                        <li><strong>Alanı boşaltın ve güvenli bir yere geçin</strong></li>
                    </ul>
                </div>
                
                <!-- Tehlike Bilgisi -->
                <div style="background-color: #f8d7da; border: 1px solid #f5c6cb; border-radius: 8px; padding: 15px; margin: 20px 0;">
                    <h4 style="color: #721c24; margin: 0 0 10px 0;">💀 CO Zehirlenmesi Tehlikesi</h4>
                    <p style="color: #721c24; margin: 0; font-size: 14px;">
                        300 ppm CO seviyesi ciddi sağlık riskleri oluşturur. Baş ağrısı, bulantı, 
                        bayılma ve ölümcül sonuçlar doğurabilir. Hemen müdahale gereklidir!
                    </p>
                </div>
            </div>
            
            <!-- Footer -->
            <div style="background-color: #6c757d; color: white; padding: 15px; text-align: center;">
                <p style="margin: 0; font-size: 12px;">
                    Bu kritik bir güvenlik alarmıdır. Lütfen ciddi bir şekilde değerlendirin.<br>
                    Sistem otomatik olarak izlemeye devam edecektir.
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return subject, body

def create_safe_level_email(device_id, co_level, temp, humidity):
    """CO seviyesi 300 ppm altına düştüğünde güvenli seviye e-postası"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    subject = f"✅ GÜVENLİ: CO Seviyesi 300 PPM Altına Düştü - {device_id}"
    
    body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>CO Seviyesi Güvenli</title>
    </head>
    <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
        <div style="max-width: 600px; margin: 0 auto; background-color: white; border-radius: 10px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            
            <!-- Header -->
            <div style="background-color: #28a745; color: white; padding: 20px; text-align: center;">
                <h1 style="margin: 0; font-size: 24px;">✅ CO SEVİYESİ GÜVENLİ</h1>
                <p style="margin: 5px 0 0 0; font-size: 16px;">Tehlike geçti - Normal seviyeye döndü</p>
            </div>
            
            <!-- Ana İçerik -->
            <div style="padding: 20px;">
                <div style="background-color: #d4edda; border: 2px solid #28a745; border-radius: 8px; padding: 15px; margin-bottom: 20px;">
                    <h2 style="color: #155724; margin: 0 0 10px 0;">✅ DURUM GÜVENLİ</h2>
                    <p style="color: #155724; font-weight: bold; margin: 0; font-size: 16px;">
                        CO seviyesi 300 ppm altına düştü - Güvenli seviyede
                    </p>
                </div>
                
                <!-- Cihaz Bilgileri -->
                <h3 style="color: #333; border-bottom: 2px solid #28a745; padding-bottom: 5px;">Güncel Değerler</h3>
                <table style="width: 100%; border-collapse: collapse; margin: 15px 0;">
                    <tr style="background-color: #f8f9fa;">
                        <td style="padding: 12px; border: 1px solid #dee2e6; font-weight: bold; width: 40%;">Cihaz ID</td>
                        <td style="padding: 12px; border: 1px solid #dee2e6;">{device_id}</td>
                    </tr>
                    <tr style="background-color: #f0fff4;">
                        <td style="padding: 12px; border: 1px solid #dee2e6; font-weight: bold;">CO Seviyesi</td>
                        <td style="padding: 12px; border: 1px solid #dee2e6; color: #28a745; font-weight: bold; font-size: 16px;">
                            {co_level:.1f} ppm (Güvenli - {CO_CRITICAL_LIMIT} ppm altında)
                        </td>
                    </tr>
                    <tr style="background-color: #f8f9fa;">
                        <td style="padding: 12px; border: 1px solid #dee2e6; font-weight: bold;">Sıcaklık</td>
                        <td style="padding: 12px; border: 1px solid #dee2e6;">{temp:.1f} °C</td>
                    </tr>
                    <tr style="background-color: #f0fff4;">
                        <td style="padding: 12px; border: 1px solid #dee2e6; font-weight: bold;">Nem</td>
                        <td style="padding: 12px; border: 1px solid #dee2e6;">{humidity:.1f} %</td>
                    </tr>
                    <tr style="background-color: #f8f9fa;">
                        <td style="padding: 12px; border: 1px solid #dee2e6; font-weight: bold;">Güvenli Seviye Zamanı</td>
                        <td style="padding: 12px; border: 1px solid #dee2e6;">{timestamp}</td>
                    </tr>
                </table>
                
                <!-- Bilgi Notu -->
                <div style="background-color: #cff4fc; border: 1px solid #9eeaf9; border-radius: 8px; padding: 15px; margin: 20px 0;">
                    <h4 style="color: #055160; margin: 0 0 10px 0;">ℹ️ Bilgi</h4>
                    <p style="color: #055160; margin: 0; font-size: 14px;">
                        Sistem izlemeye devam edecektir. Herhangi bir anormal durum tekrar tespit edilirse 
                        otomatik olarak bildirilecektir.
                    </p>
                </div>
            </div>
            
            <!-- Footer -->
            <div style="background-color: #6c757d; color: white; padding: 15px; text-align: center;">
                <p style="margin: 0; font-size: 12px;">
                    CO İzleme Sistemi - Güvenliğiniz için sürekli izleme
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return subject, body

@app.route("/api/co_data", methods=["POST"])
def receive_data():
    """CO verilerini al ve kritik seviyeyi kontrol et"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Veri bulunamadı"}), 400
        
        # Veri çıkarma
        co_level = float(data.get("co_level", 0))
        temperature = float(data.get("temperature", 0))
        humidity = float(data.get("humidity", 0))
        alarm_status = data.get("alarm_status", False)
        device_id = data.get("device_id", "Unknown")
        
        logger.info(f"📡 Veri alındı - Cihaz: {device_id}, CO: {co_level} ppm, Temp: {temperature} °C")
        
        # Cihaz alarm durumunu başlat
        if device_id not in device_alarm_status:
            device_alarm_status[device_id] = {
                "co_critical_alarm": False,
                "temp_alarm": False,
                "general_alarm": False,
                "last_alert_time": None
            }
        
        current_status = device_alarm_status[device_id]
        email_sent = False
        alert_type = None
        
        # KRİTİK: CO seviyesi 300 ppm'i geçtiğinde
        if co_level > CO_CRITICAL_LIMIT:
            if not current_status["co_critical_alarm"]:
                logger.warning(f"🚨 KRİTİK ALARM: CO seviyesi {co_level} ppm (300 ppm aşıldı) - {device_id}")
                
                subject, body = create_critical_co_alert_email(device_id, co_level, temperature, humidity)
                
                if send_email(subject, body):
                    current_status["co_critical_alarm"] = True
                    current_status["last_alert_time"] = datetime.now().isoformat()
                    email_sent = True
                    alert_type = "critical_co"
                    logger.info(f"✅ Kritik CO alarm e-postası gönderildi: {device_id}")
                else:
                    logger.error(f"❌ Kritik CO alarm e-postası gönderilemedi: {device_id}")
        
        # CO seviyesi güvenli seviyeye döndüğünde
        elif co_level <= CO_CRITICAL_LIMIT and current_status["co_critical_alarm"]:
            logger.info(f"✅ CO seviyesi güvenli seviyeye döndü: {co_level} ppm - {device_id}")
            
            subject, body = create_safe_level_email(device_id, co_level, temperature, humidity)
            
            if send_email(subject, body):
                current_status["co_critical_alarm"] = False
                current_status["last_alert_time"] = datetime.now().isoformat()
                email_sent = True
                alert_type = "safe_level"
                logger.info(f"✅ Güvenli seviye e-postası gönderildi: {device_id}")
        
        # Sıcaklık kontrolü
        if temperature > TEMP_LIMIT and not current_status["temp_alarm"]:
            logger.warning(f"🌡️ Yüksek sıcaklık: {temperature} °C - {device_id}")
            current_status["temp_alarm"] = True
        elif temperature <= TEMP_LIMIT and current_status["temp_alarm"]:
            current_status["temp_alarm"] = False
            logger.info(f"✅ Sıcaklık normale döndü: {temperature} °C - {device_id}")
        
        # Genel alarm kontrolü
        if alarm_status and not current_status["general_alarm"]:
            current_status["general_alarm"] = True
            logger.warning(f"⚠️ Genel alarm aktif: {device_id}")
        elif not alarm_status and current_status["general_alarm"]:
            current_status["general_alarm"] = False
            logger.info(f"✅ Genel alarm devre dışı: {device_id}")
        
        # Başarılı yanıt
        response_data = {
            "status": "success",
            "device_id": device_id,
            "co_level": co_level,
            "temperature": temperature,
            "humidity": humidity,
            "email_sent": email_sent,
            "alert_type": alert_type,
            "device_status": current_status,
            "limits": {
                "co_critical_limit": CO_CRITICAL_LIMIT,
                "temp_limit": TEMP_LIMIT
            },
            "timestamp": datetime.now().isoformat()
        }
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"Veri işleme hatası: {str(e)}")
        return jsonify({"error": f"Veri işleme hatası: {str(e)}"}), 500

@app.route("/api/test_critical_alert", methods=["POST"])
def test_critical_alert():
    """300 ppm kritik CO alarmını test et"""
    test_data = {
        "co_level": 350.0,
        "temperature": 25.0,
        "humidity": 60.0,
        "alarm_status": False,
        "device_id": "TEST_DEVICE_CRITICAL"
    }
    
    logger.info("🧪 Kritik CO alarmı test ediliyor...")
    
    # Test verisini işlemek için receive_data fonksiyonunu çağır
    with app.test_request_context('/api/co_data', method='POST', json=test_data):
        response = receive_data()
        
    return jsonify({
        "message": "Kritik CO alarmı test edildi (350 ppm)",
        "test_data": test_data,
        "response": response[0].get_json() if hasattr(response[0], 'get_json') else str(response)
    }), 200

@app.route("/api/test_safe_alert", methods=["POST"])
def test_safe_alert():
    """Güvenli seviye e-postasını test et"""
    # Önce kritik seviyeyi simüle et
    device_id = "TEST_DEVICE_SAFE"
    device_alarm_status[device_id] = {
        "co_critical_alarm": True,
        "temp_alarm": False,
        "general_alarm": False,
        "last_alert_time": datetime.now().isoformat()
    }
    
    test_data = {
        "co_level": 250.0,  # 300 ppm altında
        "temperature": 25.0,
        "humidity": 60.0,
        "alarm_status": False,
        "device_id": device_id
    }
    
    logger.info("🧪 Güvenli seviye e-postası test ediliyor...")
    
    with app.test_request_context('/api/co_data', method='POST', json=test_data):
        response = receive_data()
        
    return jsonify({
        "message": "Güvenli seviye e-postası test edildi (250 ppm)",
        "test_data": test_data,
        "response": response[0].get_json() if hasattr(response[0], 'get_json') else str(response)
    }), 200

@app.route("/api/status", methods=["GET"])
def get_status():
    """Sistem durumunu görüntüle"""
    return jsonify({
        "system_status": "active",
        "device_count": len(device_alarm_status),
        "device_alarm_status": device_alarm_status,
        "limits": {
            "co_critical_limit": CO_CRITICAL_LIMIT,
            "temp_limit": TEMP_LIMIT
        },
        "smtp_config": {
            "server": SMTP_CONFIG["server"],
            "port": SMTP_CONFIG["port"],
            "sender": SMTP_CONFIG["email"],
            "receiver": SMTP_CONFIG["receiver"]
        },
        "timestamp": datetime.now().isoformat()
    }), 200

@app.route("/api/reset_alarms", methods=["POST"])
def reset_alarms():
    """Tüm alarm durumlarını sıfırla"""
    global device_alarm_status
    old_count = len(device_alarm_status)
    device_alarm_status = {}
    
    logger.info(f"🔄 Tüm alarm durumları sıfırlandı ({old_count} cihaz)")
    
    return jsonify({
        "status": "success",
        "message": f"Tüm alarm durumları sıfırlandı ({old_count} cihaz)",
        "timestamp": datetime.now().isoformat()
    }), 200

@app.route("/", methods=["GET"])
def home():
    """Ana sayfa - sistem bilgileri"""
    return jsonify({
        "service": "CO Monitoring System",
        "version": "2.0",
        "critical_co_limit": f"{CO_CRITICAL_LIMIT} ppm",
        "temp_limit": f"{TEMP_LIMIT} °C",
        "status": "active",
        "endpoints": {
            "data_input": "/api/co_data (POST)",
            "status": "/api/status (GET)",
            "reset_alarms": "/api/reset_alarms (POST)",
            "test_critical": "/api/test_critical_alert (POST)",
            "test_safe": "/api/test_safe_alert (POST)"
        },
        "timestamp": datetime.now().isoformat()
    }), 200
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

@app.route("/api/test_critical_alert", methods=["POST"])
def test_critical_alert():
    test_data = {
        "co_level": 350.0,
        "temperature": 25.0,
        "humidity": 60.0,
        "alarm_status": False,
        "device_id": "TEST_DEVICE"
    }
    result = process_sensor_data(
        co=test_data["co_level"],
        temp=test_data["temperature"],
        humid=test_data["humidity"],
        alarm=test_data["alarm_status"],
        device_id=test_data["device_id"]
    )
    return jsonify({
        "message": "Test CO alarm triggered",
        "data": test_data,
        "result": result
    }), 200
    

