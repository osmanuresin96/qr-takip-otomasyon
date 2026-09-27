import os
import sqlite3
import qrcode
import webbrowser
import math
import pandas as pd
from io import BytesIO
from datetime import datetime
from flask import Flask, request, render_template_string, redirect, send_file, jsonify
from flask_httpauth import HTTPBasicAuth

app = Flask(__name__)
auth = HTTPBasicAuth()

# Gelişmiş Veritabanı Kurulumu
def init_db():
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS personeller (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            isim TEXT NOT NULL,
            sabit_maas REAL NOT NULL,
            ek_ucret REAL DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kayitlar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            personel_id INTEGER,
            tarih TEXT,
            giris_saati TEXT,
            cikis_saati TEXT,
            fazla_mesai_saati REAL DEFAULT 0,
            FOREIGN KEY(personel_id) REFERENCES personeller(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ayarlar (
            id INTEGER PRIMARY KEY,
            enlem REAL NOT NULL,
            boylam REAL NOT NULL,
            mesafe REAL NOT NULL,
            admin_user TEXT NOT NULL,
            admin_pass TEXT NOT NULL,
            calisistan_saat REAL NOT NULL,
            mesai_carpan REAL NOT NULL
        )
    """)
    # Varsayılan fabrika ayarlarını yükle (Kullanıcı adı: admin , Şifre: 123456)
    cursor.execute("SELECT COUNT(*) FROM ayarlar")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO ayarlar (id, enlem, boylam, mesafe, admin_user, admin_pass, calisistan_saat, mesai_carpan) 
            VALUES (1, 40.1828, 29.0984, 20.0, 'admin', '123456', 225.0, 1.5)
        """)
    conn.commit()
    conn.close()

init_db()

@auth.verify_password
def verify_password(username, password):
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("SELECT admin_user, admin_pass FROM ayarlar WHERE id = 1")
    db_user, db_pass = cursor.fetchone()
    conn.close()
    if username == db_user and password == db_pass:
        return username
    return None

def mesafe_hesapla(lat1, lon1, lat2, lon2):
    R = 6371000 
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# 🖥️ ŞİFRELİ ADMİN PANELİ
@app.route("/")
@auth.login_required
def admin_paneli():
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    
    # Güncel gelişmiş ayarları çek
    cursor.execute("SELECT enlem, boylam, mesafe, admin_user, admin_pass, calisistan_saat, mesai_carpan FROM ayarlar WHERE id = 1")
    s_enlem, s_boylam, s_mesafe, s_user, s_pass, s_norm, s_carpan = cursor.fetchone()
    
    cursor.execute("SELECT id, isim, sabit_maas, ek_ucret FROM personeller")
    personeller_raw = cursor.fetchall()
    
    rows = ""
    for p in personeller_raw:
        p_id, isim, sabit_maas, ek_ucret = p
        cursor.execute("SELECT SUM(fazla_mesai_saati) FROM kayitlar WHERE personel_id = ?", (p_id,))
        res = cursor.fetchone()
        toplam_mesai = res[0] if res and res[0] is not None else 0
        
        saatlik_ucret = round(sabit_maas / s_norm, 2)
        mesai_kazanci = round(toplam_mesai * saatlik_ucret * s_carpan, 2)
        toplam_hakedis = round(sabit_maas + mesai_kazanci + ek_ucret, 2)
        
        cursor.execute("SELECT giris_saati, cikis_saati FROM kayitlar WHERE personel_id = ? ORDER BY id DESC LIMIT 1", (p_id,))
        son_hareket = cursor.fetchone()
        durum = "Dışarıda"
        if son_hareket and son_hareket[0] and not son_hareket[1]:
            durum = "İçeride (Çalışıyor)"

        rows += f"""
        <tr>
            <td><b>{isim}</b></td>
            <td><span style='background:{"#28a745" if durum=="İçeride (Çalışıyor)" else "#6c757d"}; color:#fff; padding:4px 8px; border-radius:3px; font-size:12px;'>{durum}</span></td>
            <td>{sabit_maas:,.2f} TL</td>
            <td style='color:blue; font-weight:bold;'>{saatlik_ucret:,.2f} TL</td>
            <td><span style='background:#ffc107; padding:2px 6px; border-radius:3px; font-weight:bold;'>{toplam_mesai} Saat</span></td>
            <td style='color:#dc3545; font-weight:bold;'>+{mesai_kazanci:,.2f} TL</td>
            <td>{ek_ucret:,.2f} TL</td>
            <td style='color:#28a745; font-weight:bold; font-size:16px;'>{toplam_hakedis:,.2f} TL</td>
            <td>
                <form action='/ek-ucret' method='POST' style='display:inline;'>
                    <input type='hidden' name='p_id' value='{p_id}'>
                    <input type='number' name='miktar' style='width:80px; padding:4px;' placeholder='Prim TL' required>
                    <input type='submit' value='Ekle' style='background:#28a745; color:#fff; border:none; padding:4px 8px; cursor:pointer; border-radius:3px;'>
                </form>
            </td>
            <td><a href='/personel-sil/{p_id}' style='background:#dc3545; color:#fff; padding:5px 10px; border-radius:3px; text-decoration:none; font-size:12px;' onclick="return confirm('Silmek istediğinize emin misiniz?')">Sil</a></td>
        </tr>
        """
        
    cursor.execute("""
        SELECT k.tarih, p.isim, k.giris_saati, k.cikis_saati, k.fazla_mesai_saati 
        FROM kayitlar k 
        JOIN personeller p ON k.personel_id = p.id 
        ORDER BY k.id DESC LIMIT 30
    """)
    gecmis_raw = cursor.fetchall()
    
    gecmis_rows = ""
    for g in gecmis_raw:
        cikis_str = g[3] if g[3] else "<span style='color:orange; font-weight:bold;'>Henüz Çıkmadı</span>"
        gecmis_rows += f"""
        <tr>
            <td>{g[0]}</td>
            <td><b>{g[1]}</b></td>
            <td style='color:green;'>{g[2]}</td>
            <td>{cikis_str}</td>
            <td style='font-weight:bold; color:{"#dc3545" if g[4] > 0 else "#333"};'>{g[4]} Saat</td>
        </tr>
        """
    conn.close()

    html = f"""
    <html><head><meta charset='utf-8'><title>🛡️ Kurumsal Yönetim Paneli</title>
    <style>body{{font-family:Segoe UI,sans-serif; background:#f4f6f9; padding:30px;}} .container{{max-width:1300px; margin:0 auto; background:#fff; padding:25px; border-radius:8px; box-shadow:0 4px 15px rgba(0,0,0,0.08);}} table{{width:100%; border-collapse:collapse; margin-top:20px; font-size:14px; margin-bottom:40px;}} th,td{{padding:12px; border-bottom:1px solid #dee2e6; text-align:left;}} th{{background:#212529; color:#fff;}} .btn-qr{{background:#6f42c1; color:#fff; padding:10px 15px; text-decoration:none; border-radius:4px; font-weight:bold;}} .btn-excel{{padding:10px 15px; background:#28a745; color:#fff; text-decoration:none; border-radius:4px; font-weight:bold;}} .form-box{{background:#e9ecef; padding:15px; border-radius:6px; margin-bottom:20px; border:1px solid #ddd;}}</style>
    </head><body><div class='container'>
        <h2>🛡️ Kurumsal Güvenli Yönetim Otomasyon Paneli</h2>
        
        <!-- ⚙️ PANEL VE GPS AYARLARI FORMU -->
        <div class='form-box' style='background: #eef2f7; border-left: 5px solid #007bff; display: flex; flex-wrap: wrap; gap: 15px;'>
            <form action='/ayarlari-guncelle' method='POST' style='margin:0; width:100%; display:flex; flex-wrap:wrap; gap:10px; align-items:center;'>
                <b style='color:#0056b3;'>📍 Konum Ayarı:</b>
                Enlem: <input type='text' name='enlem' value='{s_enlem}' style='padding:5px; width:100px;' required>
                Boylam: <input type='text' name='boylam' value='{s_boylam}' style='padding:5px; width:100px;' required>
                Mesafe (Metre): <input type='number' name='mesafe' value='{s_mesafe}' style='padding:5px; width:60px;' required>
                
                <b style='color:#6f42c1; margin-left:15px;'>🔐 Admin Girişi:</b>
                Kullanıcı: <input type='text' name='admin_user' value='{s_user}' style='padding:5px; width:90px;' required>
                Şifre: <input type='text' name='admin_pass' value='{s_pass}' style='padding:5px; width:90px;' required>
                
                <b style='color:#28a745; margin-left:15px;'>📊 Hesap Normu:</b>
                Aylık Norm Saat: <input type='number' name='calisistan_saat' value='{s_norm}' style='padding:5px; width:65px;' required>
                Mesai Çarpanı: <input type='text' name='mesai_carpan' value='{s_carpan}' style='padding:5px; width:50px;' required>
                
                <input type='submit' value='Tüm Ayarları Kaydet' style='padding:6px 15px; background:#007bff; color:#fff; border:none; cursor:pointer; font-weight:bold; border-radius:4px;'>
            </form>
        </div>

        <div class='form-box' style='display:flex; justify-content:space-between; align-items:center;'>
            <form action='/personel-ekle' method='POST' style='margin:0;'>
                <input type='text' name='isim' placeholder='Ad Soyad' style='padding:8px; width:220px;' required> 
                <input type='number' step='0.01' name='sabit_maas' placeholder='Aylık Maaş (TL)' style='padding:8px; width:180px;' required> 
                <input type='submit' value='Personel Tanımla' style='padding:8px 15px; background:#28a745; color:#fff; border:none; cursor:pointer; font-weight:bold;'>
            </form>
            <div>
                <a href='/excel-rapor' class='btn-excel' style='margin-right:10px;'>📥 Excel Raporu</a>
                <a href='/ortak-qr-indir' class='btn-qr'>📥 Duvara Asılacak Güvenli Ortak QR İndir</a>
            </div>
        </div>
        
        <h3>👥 Personel Listesi ve Hakedişler</h3>
        <table>
        {rows}
        </table>
        <h3>📋 Giriş / Çıkış Hareket Geçmişi</h3>
        <table>
            <tr><th>Tarih</th><th>Personel Adı</th><th>Giriş Saati</th><th>Çıkış Saati</th><th>Yazılan Fazla Mesai</th></tr>
            {gecmis_rows}
        </table>
    </div></body></html>
    """
    return render_template_string(html)

@app.route("/ayarlari-guncelle", methods=["POST"])
@auth.login_required
def ayarlari_guncelle():
    enlem = float(request.form['enlem'])
    boylam = float(request.form['boylam'])
    mesafe = float(request.form['mesafe'])
    user = request.form['admin_user']
    pas = request.form['admin_pass']
    norm = float(request.form['calisistan_saat'])
    carpan = float(request.form['mesai_carpan'])
    
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE ayarlar SET enlem=?, boylam=?, mesafe=?, admin_user=?, admin_pass=?, calisistan_saat=?, mesai_carpan=? WHERE id=1
    """, (enlem, boylam, mesafe, user, pas, norm, carpan))
    conn.commit()
    conn.close()
    return redirect("/")

@app.route("/ortak-giris")
def ortak_giris():
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, isim FROM personeller")
    personeller = cursor.fetchall()
    conn.close()
    
    options = "".join([f"<option value='{p[0]}'>{p[1]}</option>" for p in personeller])
    
    html = f"""
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1'><title>GPS Giriş Kontrolü</title>
    <style>
        body{{font-family:sans-serif; background:#212529; color:#fff; text-align:center; padding-top:20px;}}
        .card{{background:#fff; color:#000; padding:25px; margin:15px; border-radius:12px; box-shadow:0 4px 10px rgba(0,0,0,0.2);}}
        select, button{{width:100%; padding:14px; margin-top:15px; border-radius:6px; font-size:16px; font-weight:bold; box-sizing:border-box;}}
        button{{color:#fff; border:none; cursor:pointer;}} .btn-giris{{background:#28a745;}} .btn-cikis{{background:#dc3545;}}
        .guide-box{{display:none; background:#fff2e6; border:2px dashed #ff9900; padding:15px; margin-top:20px; border-radius:8px; text-align:left; color:#333; font-size:14px;}}
    </style>
    <script>
        function islemYap(islemTipi) {{
            var p_id = document.getElementById("personel_select").value;
            if(!p_id) {{ alert("Lütfen adınızı seçin!"); return; }}
            document.getElementById("guide").style.display = "none";
            if (navigator.geolocation) {{
                navigator.geolocation.getCurrentPosition(function(position) {{
                    var veri = {{
                        personel_id: p_id,
                        islem: islemTipi,
                        enlem: position.coords.latitude,
                        boylam: position.coords.longitude
                    }};
                    fetch('/konum-dogrula', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify(veri)
                    }})
                    .then(response => response.json())
                    .then(data => {{
                        alert(data.mesaj);
                        location.reload();
                    }});
                }}, function(error) {{
                    document.getElementById("guide").style.display = "block";
                    alert("⚠️ GPS Konum Hatası!\\nKonum izni kapalı veya algılanamadı. Lütfen aşağıdaki açma kılavuzunu uygulayın!");
                }}, {{ enableHighAccuracy: true, timeout: 7000 }});
            }} else {{
                alert("Telefonunuzun GPS özelliği desteklenmiyor!");
            }}
        }}
    </script>
    </head><body><div class='card'>
        <h2 style='margin-top:0; color:#333;'>📍 Konum Doğrulamalı Giriş</h2>
        <p style='color:#666;'>Lütfen isminizi seçip buradaki butonlara basınız:</p>
        <select id='personel_select'><option value=''>--- İsminizi Seçin ---</option>{options}</select>
        <button class='btn-giris' onclick="islemYap('GİRİŞ')">📍 KONUMU DOĞRULA & GİRİŞ YAP</button>
        <button class='btn-cikis' onclick="islemYap('ÇIKIŞ')">📍 KONUMU DOĞRULA & ÇIKIŞ YAP</button>
        
        <div id='guide' class='guide-box'>
            <h4 style='margin-top:0; color:#cc3300;'>💡 Konum İzni Nasıl Açılır?</h4>
            <b>🤖 Android (Chrome) Kullanıcıları:</b><br>
            1. Üstteki adres çubuğunun yanındaki Kilit (🔒) simgesine basın.<br>
            2. Site Ayarları'na girip Konum seçeneğini İzin Ver yapın ve sayfayı yenileyin.<br><br>
            <b>🍏 iPhone (Safari) Kullanıcıları:</b><br>
            1. Ayarlar -> Gizlilik -> Konum Servisleri'ni aktif edin.<br>
            2. Ayarlar -> Safari -> en alttaki Konum seçeneğini İzin Ver yapın ve sayfayı yenileyin.
        </div>
    </div></body></html>
    """
    return render_template_string(html)

@app.route("/konum-dogrula", methods=["POST"])
def konum_dogrula():
    data = request.get_json()
    p_id = data.get("personel_id")
    islem = data.get("islem")
    kul_enlem = float(data.get("enlem"))
    kul_boylam = float(data.get("boylam"))
    
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("SELECT enlem, boylam, mesafe FROM ayarlar WHERE id = 1")
    sirket_enlem, sirket_boylam, sirket_mesafe = cursor.fetchone()
    
    mesafe = mesafe_hesapla(sirket_enlem, sirket_boylam, kul_enlem, kul_boylam)
    
    if mesafe > sirket_mesafe:
        conn.close()
        return jsonify({"mesaj": f"❌ İŞLEM REDDEDİLDİ!\nŞirket sınırları dışındasınız.\nUzaklık: {round(mesafe, 1)} metre. Giriş sınırınız {sirket_mesafe} metredir!"})
        
    cursor.execute("SELECT isim FROM personeller WHERE id = ?", (p_id,))
    res = cursor.fetchone()
    isim = res[0] if res else "Bilinmeyen"
    
    simdi = datetime.now()
    bugun = simdi.strftime("%Y-%m-%d")
    saat_str = simdi.strftime("%H:%M:%S")
    
    cursor.execute("SELECT id, giris_saati FROM kayitlar WHERE personel_id = ? AND cikis_saati IS NULL ORDER BY id DESC LIMIT 1", (p_id,))
    acik_kayit = cursor.fetchone()
    
    if islem == "GİRİŞ":
        if acik_kayit:
            mesaj = f"Zaten içeride çalışıyor görünüyorsunuz, {isim}!"
        else:
            cursor.execute("INSERT INTO kayitlar (personel_id, tarih, giris_saati) VALUES (?, ?, ?)", (p_id, bugun, saat_str))
            mesaj = f"✓ BAŞARILI!\n{isim}, GİRİŞ kaydınız saat {saat_str} olarak sisteme işlendi."
    else:
        if not acik_kayit:
            mesaj = f"Aktif giriş kaydınız bulunamadı, {isim}!"
        else:
            kayit_id, giris_saati_str = acik_kayit
            giris_zamani = datetime.strptime(f"{bugun} {giris_saati_str}", "%Y-%m-%d %H:%M:%S")
            calisilan_saat = round((simdi - giris_zamani).total_seconds() / 3600, 2)
            fazla_mesai = round(calisilan_saat - 8.0, 2) if calisilan_saat > 8.0 else 0.0
            cursor.execute("UPDATE kayitlar SET cikis_saati = ?, fazla_mesai_saati = ? WHERE id = ?", (saat_str, fazla_mesai, kayit_id))
            mesaj = f"✓ BAŞARILI!\nGüle güle {isim}, ÇIKIŞ kaydınız alındı.\nToplam: {calisilan_saat} saat. (Mesai: {fazla_mesai} Saat)"
            
    conn.commit()
    conn.close()
    return jsonify({"mesaj": mesaj})

@app.route("/ortak-qr-indir")
@auth.login_required
def ortak_qr_indir():
    qr_url = f"https://{request.host}/ortak-giris"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    output = BytesIO()
    img.save(output, format="PNG")
    output.seek(0)
    return send_file(output, download_name="Sirket_Kurumsal_Ortak_QR.png", as_attachment=True)

@app.route("/personel-ekle", methods=["POST"])
@auth.login_required
def personel_ekle():
    isim = request.form['isim']
    sabit_maas = float(request.form['sabit_maas'])
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO personeller (isim, sabit_maas) VALUES (?, ?)", (isim, sabit_maas))
    conn.commit()
    conn.close()
    return redirect("/")

@app.route("/personel-sil/<int:p_id>")
@auth.login_required
def personel_sil(p_id):
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM personeller WHERE id = ?", (p_id,))
    cursor.execute("DELETE FROM kayitlar WHERE personel_id = ?", (p_id,))
    conn.commit()
    conn.close()
    return redirect("/")

@app.route("/ek-ucret", methods=["POST"])
@auth.login_required
def ek_ucret():
    p_id = int(request.form['p_id'])
    miktar = float(request.form['miktar'])
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE personeller SET ek_ucret = ek_ucret + ? WHERE id = ?", (miktar, p_id))
    conn.commit()
    conn.close()
    return redirect("/")

@app.route("/excel-rapor")
@auth.login_required
def excel_rapor():
    conn = sqlite3.connect("takip.db")
    query = """
    SELECT k.tarih AS [Tarih], p.isim AS [Personel Adı], p.sabit_maas AS [Sabit Maaş (TL)],
           k.giris_saati AS [Giriş Saati], k.cikis_saati AS [Çıkış Saati], 
           k.fazla_mesai_saati AS [Fazla Mesai (Saat)]
    FROM kayitlar k 
    JOIN personeller p ON k.personel_id = p.id
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Mesai_Raporu')
    output.seek(0)
    return send_file(output, download_name=f"Mesai_Raporu_{datetime.now().strftime('%Y%m%d')}.xlsx", as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
