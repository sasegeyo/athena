from flask import Flask, render_template, jsonify, request
import requests
import pandas as pd
import json
from datetime import datetime, timedelta
import threading
import time
import logging
import os
import atexit
from openpyxl import Workbook, load_workbook
from openpyxl.utils.dataframe import dataframe_to_rows
import fcntl
import tempfile
import shutil

class COMonitoringSystem:
    def __init__(self):
        self.app = Flask(__name__)
        self.esp32_ip = "192.168.1.100"  # ESP32'nizin IP adresini buraya yazın
        self.esp32_port = 80
        self.measurements_file = "co_measurements.xlsx"
        self.alarms_file = "co_alarms.xlsx"
        self.danger_level = 50  # ppm cinsinden tehlikeli seviye
        self.warning_level = 30  # ppm cinsinden uyarı seviyesi
        self.data_collection_thread = None
        self.stop_collection = False
        self.file_lock = threading.Lock()  # Excel dosyalarına erişim için lock
        
        # Logging ayarları
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('co_monitoring.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        # Excel dosyalarını başlat
        self.init_excel_files()
        
        # Route'ları tanımla
        self.setup_routes()
        
        # Graceful shutdown için cleanup fonksiyonu kaydet
        atexit.register(self.cleanup)
    
    def init_excel_files(self):
        """Excel dosyalarını oluştur ve başlat"""
        try:
            # Ölçümler dosyası
            if not os.path.exists(self.measurements_file):
                df_measurements = pd.DataFrame(columns=[
                    'timestamp', 'co_level', 'temperature', 'humidity', 'status', 'esp32_ip'
                ])
                df_measurements.to_excel(self.measurements_file, index=False, sheet_name='CO_Measurements')
                self.logger.info(f"Ölçümler dosyası oluşturuldu: {self.measurements_file}")
            
            # Alarmlar dosyası
            if not os.path.exists(self.alarms_file):
                df_alarms = pd.DataFrame(columns=[
                    'timestamp', 'alarm_type', 'co_level', 'message'
                ])
                df_alarms.to_excel(self.alarms_file, index=False, sheet_name='CO_Alarms')
                self.logger.info(f"Alarmlar dosyası oluşturuldu: {self.alarms_file}")
            
            self.logger.info("Excel dosyaları başarıyla hazırlandı")
        except Exception as e:
            self.logger.error(f"Excel dosyaları oluşturma hatası: {e}")
            raise
    
    def safe_excel_operation(self, operation_func, *args, **kwargs):
        """Excel dosya işlemlerini güvenli şekilde yapma"""
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                with self.file_lock:
                    return operation_func(*args, **kwargs)
            except PermissionError as e:
                if attempt < max_retries - 1:
                    self.logger.warning(f"Excel dosyası kilitli, {retry_delay} saniye bekleyip tekrar denenecek (deneme {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    self.logger.error(f"Excel dosyasına erişim başarısız: {e}")
                    raise
            except Exception as e:
                self.logger.error(f"Excel işlemi hatası: {e}")
                raise
    
    def read_measurements_excel(self):
        """Ölçümler Excel dosyasını oku"""
        def _read():
            try:
                df = pd.read_excel(self.measurements_file, sheet_name='CO_Measurements')
                # Timestamp sütununu datetime'a çevir
                if not df.empty and 'timestamp' in df.columns:
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                return df
            except FileNotFoundError:
                return pd.DataFrame(columns=['timestamp', 'co_level', 'temperature', 'humidity', 'status', 'esp32_ip'])
            except Exception as e:
                self.logger.error(f"Ölçümler okuma hatası: {e}")
                return pd.DataFrame(columns=['timestamp', 'co_level', 'temperature', 'humidity', 'status', 'esp32_ip'])
        
        return self.safe_excel_operation(_read)
    
    def read_alarms_excel(self):
        """Alarmlar Excel dosyasını oku"""
        def _read():
            try:
                df = pd.read_excel(self.alarms_file, sheet_name='CO_Alarms')
                # Timestamp sütununu datetime'a çevir
                if not df.empty and 'timestamp' in df.columns:
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                return df
            except FileNotFoundError:
                return pd.DataFrame(columns=['timestamp', 'alarm_type', 'co_level', 'message'])
            except Exception as e:
                self.logger.error(f"Alarmlar okuma hatası: {e}")
                return pd.DataFrame(columns=['timestamp', 'alarm_type', 'co_level', 'message'])
        
        return self.safe_excel_operation(_read)
    
    def write_measurements_excel(self, df):
        """Ölçümler Excel dosyasına yaz"""
        def _write():
            # Geçici dosya kullanarak güvenli yazma
            temp_file = f"{self.measurements_file}.tmp"
            try:
                df.to_excel(temp_file, index=False, sheet_name='CO_Measurements')
                # Başarılı yazma sonrası dosyayı değiştir
                shutil.move(temp_file, self.measurements_file)
            except Exception as e:
                # Geçici dosyayı temizle
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                raise e
        
        return self.safe_excel_operation(_write)
    
    def write_alarms_excel(self, df):
        """Alarmlar Excel dosyasına yaz"""
        def _write():
            # Geçici dosya kullanarak güvenli yazma
            temp_file = f"{self.alarms_file}.tmp"
            try:
                df.to_excel(temp_file, index=False, sheet_name='CO_Alarms')
                # Başarılı yazma sonrası dosyayı değiştir
                shutil.move(temp_file, self.alarms_file)
            except Exception as e:
                # Geçici dosyayı temizle
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                raise e
        
        return self.safe_excel_operation(_write)
    
    def get_esp32_data(self):
        """ESP32'den veri çek"""
        try:
            url = f"http://{self.esp32_ip}:{self.esp32_port}/data"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Veri doğrulama
                co_level = float(data.get('co_ppm', 0))
                temperature = data.get('temperature')
                humidity = data.get('humidity')
                
                # Negatif değerleri kontrol et
                if co_level < 0:
                    co_level = 0
                    
                if temperature is not None:
                    temperature = float(temperature)
                    # Mantıklı sıcaklık aralığı (-50 ile +100 derece)
                    if temperature < -50 or temperature > 100:
                        temperature = None
                
                if humidity is not None:
                    humidity = float(humidity)
                    # Nem 0-100 arasında olmalı
                    if humidity < 0 or humidity > 100:
                        humidity = None
                
                return {
                    'co_level': co_level,
                    'temperature': temperature,
                    'humidity': humidity,
                    'success': True
                }
            else:
                self.logger.error(f"ESP32 yanıt hatası: {response.status_code}")
                return {'success': False, 'error': f'HTTP Error: {response.status_code}'}
                
        except requests.exceptions.Timeout:
            self.logger.error("ESP32 bağlantı zaman aşımı")
            return {'success': False, 'error': 'Connection timeout'}
        except requests.exceptions.ConnectionError:
            self.logger.error("ESP32 bağlantı hatası")
            return {'success': False, 'error': 'Connection error'}
        except (ValueError, KeyError) as e:
            self.logger.error(f"ESP32 veri formatı hatası: {e}")
            return {'success': False, 'error': 'Invalid data format'}
        except Exception as e:
            self.logger.error(f"ESP32 beklenmeyen hata: {e}")
            return {'success': False, 'error': str(e)}
    
    def save_measurement(self, co_level, temperature=None, humidity=None):
        """Ölçümü Excel dosyasına kaydet"""
        try:
            # Veri doğrulama
            if co_level is None or co_level < 0:
                self.logger.warning(f"Geçersiz CO değeri: {co_level}")
                return False
            
            # Durum belirleme
            if co_level >= self.danger_level:
                status = 'DANGER'
            elif co_level >= self.warning_level:
                status = 'WARNING'
            else:
                status = 'NORMAL'
            
            # Mevcut verileri oku
            df = self.read_measurements_excel()
            
            # Yeni veri satırı
            new_row = {
                'timestamp': datetime.now(),
                'co_level': co_level,
                'temperature': temperature,
                'humidity': humidity,
                'status': status,
                'esp32_ip': self.esp32_ip
            }
            
            # Yeni satırı ekle
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            
            # Eski verileri temizle (son 10000 kayıt tut - performans için)
            if len(df) > 10000:
                df = df.tail(10000).reset_index(drop=True)
            
            # Excel'e kaydet
            self.write_measurements_excel(df)
            
            # Alarm kontrolü (sadece önceki durumdan farklıysa alarm oluştur)
            if status in ['DANGER', 'WARNING']:
                last_status = self.get_last_status()
                if last_status != status:  # Durum değişikliği varsa alarm oluştur
                    self.save_alarm(status, co_level)
            
            self.logger.info(f"Ölçüm kaydedildi: CO={co_level}ppm, Durum={status}")
            return True
            
        except Exception as e:
            self.logger.error(f"Ölçüm kaydetme hatası: {e}")
            return False
    
    def get_last_status(self):
        """Son durum bilgisini getir (tekrarlayan alarmları önlemek için)"""
        try:
            df = self.read_measurements_excel()
            if len(df) >= 2:
                # Son ikinci kaydın durumunu getir
                return df.iloc[-2]['status']
            return None
            
        except Exception as e:
            self.logger.error(f"Son durum getirme hatası: {e}")
            return None
    
    def save_alarm(self, alarm_type, co_level):
        """Alarm kaydı oluştur"""
        try:
            if alarm_type == 'DANGER':
                message = f"TEHLİKE! CO seviyesi kritik düzeyde: {co_level} ppm"
            else:
                message = f"UYARI! CO seviyesi yüksek: {co_level} ppm"
            
            # Mevcut alarm verilerini oku
            df = self.read_alarms_excel()
            
            # Yeni alarm satırı
            new_alarm = {
                'timestamp': datetime.now(),
                'alarm_type': alarm_type,
                'co_level': co_level,
                'message': message
            }
            
            # Yeni satırı ekle
            df = pd.concat([df, pd.DataFrame([new_alarm])], ignore_index=True)
            
            # Eski alarmları temizle (son 1000 alarm tut)
            if len(df) > 1000:
                df = df.tail(1000).reset_index(drop=True)
            
            # Excel'e kaydet
            self.write_alarms_excel(df)
            
            self.logger.warning(message)
            
        except Exception as e:
            self.logger.error(f"Alarm kaydetme hatası: {e}")
    
    def get_latest_data(self):
        """Son ölçüm verilerini getir"""
        try:
            df = self.read_measurements_excel()
            
            if not df.empty:
                latest = df.iloc[-1]
                return {
                    'co_level': latest['co_level'],
                    'temperature': latest['temperature'] if pd.notna(latest['temperature']) else None,
                    'humidity': latest['humidity'] if pd.notna(latest['humidity']) else None,
                    'status': latest['status'],
                    'timestamp': latest['timestamp'].strftime('%Y-%m-%d %H:%M:%S') if pd.notna(latest['timestamp']) else None
                }
            return None
            
        except Exception as e:
            self.logger.error(f"Son veri getirme hatası: {e}")
            return None
    
    def get_historical_data(self, hours=24):
        """Geçmiş verileri getir"""
        try:
            # Saat sayısını sınırla (performans için)
            hours = min(max(1, hours), 168)  # 1 saat ile 1 hafta arası
            
            df = self.read_measurements_excel()
            
            if not df.empty:
                # Belirtilen saat aralığındaki verileri filtrele
                since = datetime.now() - timedelta(hours=hours)
                df_filtered = df[df['timestamp'] >= since]
                
                # Son 1000 kayıtla sınırla (performans için)
                if len(df_filtered) > 1000:
                    df_filtered = df_filtered.tail(1000)
                
                # Sonuçları dict listesine çevir
                results = []
                for _, row in df_filtered.iterrows():
                    results.append({
                        'timestamp': row['timestamp'].strftime('%Y-%m-%d %H:%M:%S') if pd.notna(row['timestamp']) else None,
                        'co_level': row['co_level'],
                        'temperature': row['temperature'] if pd.notna(row['temperature']) else None,
                        'humidity': row['humidity'] if pd.notna(row['humidity']) else None,
                        'status': row['status']
                    })
                
                return sorted(results, key=lambda x: x['timestamp'], reverse=True)
            
            return []
            
        except Exception as e:
            self.logger.error(f"Geçmiş veri hatası: {e}")
            return []
    
    def get_alarms(self, limit=10):
        """Son alarmları getir"""
        try:
            # Limit değerini sınırla
            limit = min(max(1, limit), 100)
            
            df = self.read_alarms_excel()
            
            if not df.empty:
                # Son kayıtları al
                df_limited = df.tail(limit)
                
                # Sonuçları dict listesine çevir
                results = []
                for _, row in df_limited.iterrows():
                    results.append({
                        'timestamp': row['timestamp'].strftime('%Y-%m-%d %H:%M:%S') if pd.notna(row['timestamp']) else None,
                        'type': row['alarm_type'],
                        'co_level': row['co_level'],
                        'message': row['message']
                    })
                
                return sorted(results, key=lambda x: x['timestamp'], reverse=True)
            
            return []
            
        except Exception as e:
            self.logger.error(f"Alarm getirme hatası: {e}")
            return []
    
    def collect_data_continuously(self):
        """Sürekli veri toplama fonksiyonu"""
        consecutive_errors = 0
        max_consecutive_errors = 10
        
        while not self.stop_collection:
            try:
                data = self.get_esp32_data()
                if data['success']:
                    success = self.save_measurement(
                        data['co_level'],
                        data.get('temperature'),
                        data.get('humidity')
                    )
                    if success:
                        consecutive_errors = 0
                    else:
                        consecutive_errors += 1
                else:
                    consecutive_errors += 1
                    self.logger.warning(f"ESP32'den veri alınamadı: {data.get('error', 'Bilinmeyen hata')}")
                
                # Çok fazla hata varsa bekleme süresini artır
                if consecutive_errors >= max_consecutive_errors:
                    self.logger.error(f"{max_consecutive_errors} ardışık hata. Bekleme süresi artırılıyor.")
                    time.sleep(300)  # 5 dakika bekle
                    consecutive_errors = 0  # Sayacı sıfırla
                else:
                    time.sleep(30)  # 30 saniyede bir veri topla
                
            except Exception as e:
                consecutive_errors += 1
                self.logger.error(f"Veri toplama hatası: {e}")
                time.sleep(60)  # Hata durumunda 1 dakika bekle
    
    def start_data_collection(self):
        """Veri toplama thread'ini başlat"""
        if self.data_collection_thread is None or not self.data_collection_thread.is_alive():
            self.stop_collection = False
            self.data_collection_thread = threading.Thread(target=self.collect_data_continuously)
            self.data_collection_thread.daemon = True
            self.data_collection_thread.start()
            self.logger.info("Veri toplama thread'i başlatıldı")
    
    def stop_data_collection(self):
        """Veri toplama thread'ini durdur"""
        self.stop_collection = True
        if self.data_collection_thread and self.data_collection_thread.is_alive():
            self.data_collection_thread.join(timeout=5)
            self.logger.info("Veri toplama thread'i durduruldu")
    
    def cleanup(self):
        """Temizlik işlemleri"""
        self.logger.info("Sistem kapatılıyor...")
        self.stop_data_collection()
    
    def export_data_to_csv(self, start_date=None, end_date=None):
        """Verileri CSV formatında export et"""
        try:
            df = self.read_measurements_excel()
            
            if not df.empty:
                # Tarih filtresi uygula
                if start_date:
                    df = df[df['timestamp'] >= pd.to_datetime(start_date)]
                if end_date:
                    df = df[df['timestamp'] <= pd.to_datetime(end_date)]
                
                # CSV dosyasına kaydet
                csv_filename = f"co_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                df.to_csv(csv_filename, index=False)
                return csv_filename
            
            return None
            
        except Exception as e:
            self.logger.error(f"CSV export hatası: {e}")
            return None
    
    def setup_routes(self):
        """Flask route'larını tanımla"""
        
        @self.app.route('/')
        def index():
            """Ana sayfa"""
            try:
                latest = self.get_latest_data()
                alarms = self.get_alarms(5)
                
                return render_template('index.html', 
                                     latest=latest, 
                                     alarms=alarms,
                                     danger_level=self.danger_level,
                                     warning_level=self.warning_level)
            except Exception as e:
                self.logger.error(f"Ana sayfa hatası: {e}")
                return f"Hata: {str(e)}", 500
        
        @self.app.route('/api/current')
        def api_current():
            """Güncel veri API"""
            try:
                data = self.get_latest_data()
                if data:
                    return jsonify(data)
                return jsonify({'error': 'Veri bulunamadı'}), 404
            except Exception as e:
                self.logger.error(f"API current hatası: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/history/<int:hours>')
        def api_history(hours):
            """Geçmiş veri API"""
            try:
                data = self.get_historical_data(hours)
                return jsonify(data)
            except Exception as e:
                self.logger.error(f"API history hatası: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/alarms')
        def api_alarms():
            """Alarm geçmişi API"""
            try:
                alarms = self.get_alarms(20)
                return jsonify(alarms)
            except Exception as e:
                self.logger.error(f"API alarms hatası: {e}")
                return jsonify({'error': str(e)}), 500
        
        @self.app.route('/api/manual_read')
        def api_manual_read():
            """Manuel veri okuma API"""
            try:
                data = self.get_esp32_data()
                if data['success']:
                    success = self.save_measurement(
                        data['co_level'],
                        data.get('temperature'),
                        data.get('humidity')
                    )
                    if success:
                        return jsonify({'success': True, 'data': data})
                    else:
                        return jsonify({'success': False, 'error': 'Veri kaydedilemedi'}), 500
                return jsonify({'success': False, 'error': data.get('error')}), 500
            except Exception as e:
                self.logger.error(f"Manuel okuma hatası: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/api/export_csv')
        def api_export_csv():
            """CSV export API"""
            try:
                start_date = request.args.get('start_date')
                end_date = request.args.get('end_date')
                
                filename = self.export_data_to_csv(start_date, end_date)
                if filename:
                    return jsonify({'success': True, 'filename': filename})
                else:
                    return jsonify({'success': False, 'error': 'Export başarısız'}), 500
            except Exception as e:
                self.logger.error(f"CSV export API hatası: {e}")
                return jsonify({'success': False, 'error': str(e)}), 500
        
        @self.app.route('/dashboard')
        def dashboard():
            """Dashboard sayfası"""
            try:
                return render_template('dashboard.html')
            except Exception as e:
                self.logger.error(f"Dashboard hatası: {e}")
                return f"Hata: {str(e)}", 500
        
        @self.app.route('/settings', methods=['GET', 'POST'])
        def settings():
            """Ayarlar sayfası"""
            try:
                if request.method == 'POST':
                    # Form verilerini doğrula
                    new_ip = request.form.get('esp32_ip', '').strip()
                    if new_ip and len(new_ip) > 0:
                        self.esp32_ip = new_ip
                    
                    try:
                        new_danger = float(request.form.get('danger_level', self.danger_level))
                        new_warning = float(request.form.get('warning_level', self.warning_level))
                        
                        # Mantık kontrolü
                        if new_danger > new_warning and new_danger > 0 and new_warning > 0:
                            self.danger_level = new_danger
                            self.warning_level = new_warning
                        else:
                            return jsonify({'success': False, 'error': 'Tehlike seviyesi uyarı seviyesinden büyük olmalı'}), 400
                            
                    except ValueError:
                        return jsonify({'success': False, 'error': 'Geçersiz sayı formatı'}), 400
                    
                    return jsonify({'success': True, 'message': 'Ayarlar güncellendi'})
                
                return render_template('settings.html',
                                     esp32_ip=self.esp32_ip,
                                     danger_level=self.danger_level,
                                     warning_level=self.warning_level)
            except Exception as e:
                self.logger.error(f"Settings hatası: {e}")
                if request.method == 'POST':
                    return jsonify({'success': False, 'error': str(e)}), 500
                return f"Hata: {str(e)}", 500
        
        @self.app.route('/api/status')
        def api_status():
            """Sistem durumu API"""
            try:
                measurements_count = len(self.read_measurements_excel())
                alarms_count = len(self.read_alarms_excel())
                
                return jsonify({
                    'system_status': 'running',
                    'data_collection_active': self.data_collection_thread.is_alive() if self.data_collection_thread else False,
                    'esp32_ip': self.esp32_ip,
                    'danger_level': self.danger_level,
                    'warning_level': self.warning_level,
                    'total_measurements': measurements_count,
                    'total_alarms': alarms_count,
                    'measurements_file': self.measurements_file,
                    'alarms_file': self.alarms_file
                })
            except Exception as e:
                self.logger.error(f"Status API hatası: {e}")
                return jsonify({'error': str(e)}), 500
    
    def run(self, host='0.0.0.0', port=5000, debug=False):
        """Web uygulamasını başlat"""
        try:
            # Veri toplama thread'ini başlat
            self.start_data_collection()
            
            self.logger.info(f"Web sunucusu başlatılıyor: http://{host}:{port}")
            self.logger.info(f"Ölçümler dosyası: {self.measurements_file}")
            self.logger.info(f"Alarmlar dosyası: {self.alarms_file}")
            self.app.run(host=host, port=port, debug=debug, threaded=True)
        except Exception as e:
            self.logger.error(f"Web sunucusu başlatma hatası: {e}")
            self.cleanup()
            raise

# Kullanım
if __name__ == '__main__':
    try:
        # Monitoring sistemini oluştur
        monitor = COMonitoringSystem()
        
        # Web sunucusunu başlat
        monitor.run(debug=True)
    except KeyboardInterrupt:
        print("\nSistem kullanıcı tarafından durduruldu")
    except Exception as e:
        print(f"Sistem hatası: {e}")
    finally:
        print("Sistem kapatıldı")