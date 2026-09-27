import os
import sqlite3
import qrcode
import webbrowser
import math
import pandas as pd
from io import BytesIO
from datetime import datetime
from flask import Flask, request, render_template_string, redirect, send_file, jsonify

app = Flask(__name__)

# 🔐 ADMİN PANELİ GİRİŞ BİLGİLERİNİZ
ADMIN_USER = "admin"
ADMIN_PASS = "123456"

# 📌 BURSA YILDIRIM DÜKKAN KOORDİNATLARINIZ VE 10 METRE HASSAS GPS SINIRI
SIRKET_ENLEM = 40.1828
SIRKET_BOYLAM = 29.0984
GECERLI_MESAFE_METRE = 10.0

os.makedirs("static/qr_codes", exist_ok=True)

def init_db():
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS personeller (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            isim TEXT NOT NULL,
            sabit_maas REAL NOT NULL,
            ek_ucret REAL DEFAULT 0,
            pin_kodu TEXT NOT NULL,
            cihaz_id TEXT DEFAULT NULL
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
    conn.commit()
    conn.close()

init_db()

def mesafe_hesapla(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c
@app.route("/login", methods=["GET", "POST"])
def login_sayfasi():
    hata = ""
    if request.method == "POST":
        u = request.form.get("username")
        p = request.form.get("password")
        if u == ADMIN_USER and p == ADMIN_PASS:
            response = redirect("/")
            response.set_cookie("admin_session", "aktif_oturum_guvenli")
            return response
        hata = "❌ Kullanıcı adı veya şifre hatalı!"
        
    return render_template_string(f"""
    <html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>Giriş Yap</title>
    <style>body{{font-family:sans-serif; background:#212529; display:flex; align-items:center; justify-content:center; height:100vh; margin:0;}} .login-card{{background:#fff; padding:30px; border-radius:12px; box-shadow:0 4px 15px rgba(0,0,0,0.3); width:100%; max-width:360px;}} input{{width:100%; padding:12px; margin-top:10px; border:1px solid #ddd; border-radius:6px; box-sizing:border-box; font-size:16px;}} input[type=submit]{{background:#007bff; color:#fff; border:none; font-weight:bold; cursor:pointer; margin-top:20px;}}</style>
    </head><body><div class='login-card'>
        <h3 style='margin:0 0 10px 0; text-align:center; color:#333;'>🔐 Yönetici Girişi</h3>
        <p style='color:red; font-size:14px; text-align:center; margin:0;'>{hata}</p>
        <form method='POST'>
            <input type='text' name='username' placeholder='Kullanıcı Adı' required>
            <input type='password' name='password' placeholder='Şifre' required>
            <input type='submit' value='Sisteme Giriş Yap'>
        </form>
    </div></body></html>
    """)

@app.route("/")
def admin_paneli():
    if request.cookies.get("admin_session") != "aktif_oturum_guvenli":
        return redirect("/login")
        
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, isim, sabit_maas, ek_ucret, pin_kodu, cihaz_id FROM personeller")
    personeller_raw = cursor.fetchall()
    
    rows = ""
    for p in personeller_raw:
        p_id, isim, sabit_maas, ek_ucret, pin, cihaz = p
        cursor.execute("SELECT SUM(fazla_mesai_saati) FROM kayitlar WHERE personel_id = ?", (p_id,))
        res = cursor.fetchone()
        toplam_mesai = res[0] if res and res[0] is not None else 0
        
        saatlik_ucret = round(sabit_maas / 225, 2)
        mesai_kazanci = round(toplam_mesai * saatlik_ucret * 1.5, 2)
        toplam_hakedis = round(sabit_maas + mesai_kazanci + ek_ucret, 2)
        
        cursor.execute("SELECT giris_saati, cikis_saati FROM kayitlar WHERE personel_id = ? ORDER BY id DESC LIMIT 1", (p_id,))
        son_hareket = cursor.fetchone()
        durum = "Dışarıda"
        if son_hareket and son_hareket[0] and not son_hareket[1]:
            durum = "İçeride (Çalışıyor)"

        c_durum = f"<span style='color:green;'>🔒 Bağlı</span> <a href='/c-sifirla/{p_id}' style='color:red; font-size:11px;'>[Sıfırla]</a>" if cihaz else "<span style='color:orange;'>Bekleniyor</span>"

        rows += f"""
        <tr>
            <td><b>{isim}</b></td>
            <td><span style='background:{"#28a745" if durum=="İçeride (Çalışıyor)" else "#6c757d"}; color:#fff; padding:4px 8px; border-radius:3px; font-size:12px;'>{durum}</span></td>
            <td style='font-weight:bold; color:#6f42c1;'>{pin}</td>
            <td>{c_durum}</td>
            <td>{sabit_maas:,.2f} TL</td>
            <td style='color:blue; font-weight:bold;'>{saatlik_ucret:,.2f} TL</td>
            <td><span style='background:#ffc107; padding:2px 6px; border-radius:3px; font-weight:bold;'>{toplam_mesai} Saat</span></td>
            <td style='color:#dc3545; font-weight:bold;'>+{mesai_kazanci:,.2f} TL</td>
            <td>{ek_ucret:,.2f} TL</td>
            <td style='color:#28a745; font-weight:bold; font-size:16px;'>{toplam_hakedis:,.2f} TL</td>
            <td>
                <form action='/ek-ucret' method='POST' style='display:inline;'>
                    <input type='hidden' name='p_id' value='{p_id}'>
                    <input type='number' name='miktar' style='width:70px; padding:4px;' placeholder='Prim' required>
                    <input type='submit' value='Ekle' style='background:#28a745; color:#fff; border:none; padding:4px 6px; cursor:pointer;'>
                </form>
            </td>
            <td><a href='/p-sil/{p_id}' style='background:#dc3545; color:#fff; padding:4px 8px; border-radius:3px; text-decoration:none; font-size:12px;' onclick="return confirm('Silinsin mi?')">Sil</a></td>
        </tr>
        """
    cursor.execute("SELECT k.tarih, p.isim, k.giris_saati, k.cikis_saati, k.fazla_mesai_saati FROM kayitlar k JOIN personeller p ON k.personel_id = p.id ORDER BY k.id DESC LIMIT 30")
    gecmis_raw = cursor.fetchall()
    gecmis_rows = "".join([f"<tr><td>{g[0]}</td><td><b>{g[1]}</b></td><td style='color:green;'>{g[2]}</td><td>{g[3] if g[3] else 'İçeride'}</td><td>{g[4]} Saat</td></tr>" for g in gecmis_raw])
    conn.close()

    html = f"""
    <html><head><meta charset='utf-8'><title>Yönetim Paneli</title>
    <style>body{{font-family:Segoe UI,sans-serif; background:#f4f6f9; padding:25px;}} .container{{max-width:1350px; margin:0 auto; background:#fff; padding:20px; border-radius:8px; box-shadow:0 4px 15px rgba(0,0,0,0.08);}} table{{width:100%; border-collapse:collapse; margin-top:15px; font-size:14px;}} th,td{{padding:10px; border-bottom:1px solid #dee2e6; text-align:left;}} th{{background:#212529; color:#fff;}} .btn-qr{{background:#6f42c1; color:#fff; padding:10px 15px; text-decoration:none; border-radius:4px; font-weight:bold;}} .btn-excel{{padding:10px 15px; background:#28a745; color:#fff; text-decoration:none; border-radius:4px; font-weight:bold;}} .form-box{{background:#e9ecef; padding:15px; border-radius:6px; display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;}} input[type=text], input[type=number]{{padding:6px; margin-right:5px; border:1px solid #ddd; border-radius:4px;}}</style>
    </head><body><div class='container'>
        <h2>🛡️ Şifreli Kurumsal Personel Maaş & Güvenli QR Otomasyonu</h2>
        <div class='form-box'>
            <form action='/p-ekle' method='POST' style='margin:0;'>
                <input type='text' name='isim' placeholder='Personel Adı Soyadı' style='width:220px;' required> 
                <input type='number' step='0.01' name='sabit_maas' placeholder='Aylık Net Maaş' style='width:150px;' required> 
                <input type='text' name='pin' placeholder='4 Haneli Şifre' style='width:110px;' maxlength='4' required> 
                <input type='submit' value='Personel Tanımla' style='padding:6px 15px; background:#007bff; color:#fff; border:none; cursor:pointer; font-weight:bold; border-radius:4px;'>
            </form>
            <div>
                <a href='/excel-rapor' class='btn-excel' style='margin-right:10px;'>📥 Excel Çıktısı</a>
                <a href='/ortak-qr-indir' class='btn-qr'>📥 Ortak Güvenli QR İndir</a>
            </div>
        </div>
        <h3>👥 Personel Maaş, Saat Ücreti ve Hak Ediş Listesi</h3>
        <table>
            <tr><th>Personel</th><th>Durum</th><th>Giriş PIN</th><th>Cihaz</th><th>Sabit Maaş</th><th>Saatlik Ücret</th><th>Toplam Mesai</th><th>Mesai Kazancı</th><th>Prim</th><th>Toplam Hak Edilen</th><th>Prim İşlemi</th><th>Yönetim</th></tr>
            {rows}
        </table>
        <h3>📋 Giriş / Çıkış Hareket Kayıt Geçmişi</h3>
        <table>
            <tr><th>Tarih</th><th>Personel Adı</th><th>Giriş Saati</th><th>Çıkış Saati</th><th>Fazla Mesai</th></tr>
            {gecmis_rows}
        </table>
    </div></body></html>
    """
    return render_template_string(html)
@app.route("/ortak-giris")
def ortak_giris():
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, isim FROM personeller")
    personeller = cursor.fetchall()
    conn.close()
    options = "".join([f"<option value='{p[0]}'>{p[1]}</option>" for p in personeller])

    html = f"""
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1'><title>Güvenli Giriş Sistemi</title>
    <style>body{{font-family:sans-serif; background:#212529; color:#fff; text-align:center; padding-top:20px;}} .card{{background:#fff; color:#000; padding:25px; margin:15px; border-radius:12px; box-shadow:0 4px 10px rgba(0,0,0,0.2);}} select, input, button{{width:100%; padding:14px; margin-top:15px; border-radius:6px; font-size:16px; font-weight:bold; box-sizing:border-box;}} button{{color:#fff; border:none; cursor:pointer;}} .btn-giris{{background:#28a745;}} .btn-cikis{{background:#dc3545;}} .guide-box{{display:none; background:#fff2e6; border:2px dashed #ff9900; padding:15px; margin-top:20px; border-radius:8px; text-align:left; color:#333; font-size:14px;}}</style>
    <script>
        function cihazIdUret() {{ return btoa(navigator.userAgent + navigator.hardwareConcurrency + screen.colorDepth + (new Date().getTimezoneOffset())); }}
        function islemYap(islemTipi) {{
            var p_id = document.getElementById("personel_select").value;
            var pin = document.getElementById("pin_input").value;
            if(!p_id || !pin) {{ alert("Lütfen adınızı seçin ve şifrenizi girin!"); return; }}
            document.getElementById("guide").style.display = "none";
            if (navigator.geolocation) {{
                navigator.geolocation.getCurrentPosition(function(position) {{
                    var veri = {{ personel_id: p_id, pin_kodu: pin, islem: islemTipi, enlem: position.coords.latitude, boylam: position.coords.longitude, fingerprint: cihazIdUret() }};
                    fetch('/konum-dogrula', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify(veri) }})
                    .then(response => response.json()).then(data => {{ alert(data.mesaj); location.reload(); }});
                }}, function(error) {{
                    document.getElementById("guide").style.display = "block";
                    alert("⚠️ GPS Konum Alınamadı! Lütfen konum servislerinizi açıp tekrar deneyin.");
                }}, {{ enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }});
            }} else {{ alert("Telefonunuz GPS desteklemiyor!"); }}
        }}
    </script>
    </head><body><div class='card'>
        <h2 style='margin-top:0; color:#333;'>🔐 Kurumsal Doğrulama Paneli</h2>
        <p style='color:#666;'>Adınızı seçin, 4 haneli PIN şifrenizi girip işlem yapın:</p>
        <select id='personel_select'><option value=''>--- İsminizi Seçin ---</option>{options}</select>
        <input type='password' id='pin_input' placeholder='PIN Şifreniz (••••)' maxlength='4' inputmode='numeric'>
        <button class='btn-giris' onclick="islemYap('GİRİŞ')">📍 KONUMU DOĞRULA & GİRİŞ YAP</button>
        <button class='btn-cikis' onclick="islemYap('ÇIKIŞ')">📍 KONUMU DOĞRULA & ÇIKIŞ YAP</button>
        <a href='/personel-ekran' style='display:inline-block; margin-top:20px; color:#007bff; text-decoration:none; font-weight:bold;'>👁️ Kendi Mesai Saatlerimi Göster</a>
        <div id='guide' class='guide-box'>
            <h4 style='margin-top:0; color:#cc3300;'>💡 Konum İzni Nasıl Açılır?</h4>
            <b>Android (Chrome):</b> Adres çubuğunun yanındaki Kilit simgesinden Konum'a izin verin.<br><br>
            <b>iPhone (Safari):</b> Ayarlar -> Gizlilik -> Konum Servisleri'ni açın. Safari'ye izin verin.
        </div>
    </div></body></html>
    """
    return render_template_string(html)
@app.route("/konum-dogrula", methods=["POST"])
def konum_dogrula():
    data = request.get_json()
    p_id = data.get("personel_id")
    pin = data.get("pin_kodu")
    islem = data.get("islem")
    kul_enlem = float(data.get("enlem"))
    kul_boylam = float(data.get("boylam"))
    fingerprint = data.get("fingerprint")
    
    mesafe = mesafe_hesapla(SIRKET_ENLEM, SIRKET_BOYLAM, kul_enlem, kul_boylam)
    if mesafe > GECERLI_MESAFE_METRE:
        return jsonify({"mesaj": f"❌ İŞLEM REDDEDİLDİ!\nŞirket sınırları dışındasınız.\nUzaklık: {round(mesafe, 1)} metre. Sınırımız {GECERLI_MESAFE_METRE} metredir!"})

    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("SELECT isim, pin_kodu, cihaz_id FROM personeller WHERE id = ?", (p_id,))
    res_p = cursor.fetchone()
    
    if not res_p or str(res_p[1]) != str(pin):
        conn.close()
        return jsonify({"mesaj": "❌ HATA: Girdiğiniz PIN şifresi yanlış!"})
        
    isim, _, db_cihaz = res_p
    if db_cihaz is None:
        cursor.execute("UPDATE personeller SET cihaz_id = ? WHERE id = ?", (fingerprint, p_id))
    elif db_cihaz != fingerprint:
        conn.close()
        return jsonify({"mesaj": f"❌ GÜVENLİK ENGELİ!\n{isim}, bu işlem sadece sizin kendi kayıtlı telefonunuzdan yapılabilir!"})

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
            mesaj = f"✓ BAŞARILI!\n{isim}, GİRİŞ kaydınız saat {saat_str} olarak işlendi."
    else:
        if not acik_kayit:
            mesaj = f"Aktif giriş kaydınız bulunamadı, {isim}!"
        else:
            kayit_id, giris_saati_str = acik_kayit[0], acik_kayit[1]
            giris_zamani = datetime.strptime(f"{bugun} {giris_saati_str}", "%Y-%m-%d %H:%M:%S")
            calisilan_saat = round((simdi - giris_zamani).total_seconds() / 3600, 2)
            fazla_mesai = round(calisilan_saat - 8.0, 2) if calisilan_saat > 8.0 else 0.0
            cursor.execute("UPDATE kayitlar SET cikis_saati = ?, fazla_mesai_saati = ? WHERE id = ?", (saat_str, fazla_mesai, kayit_id))
            mesaj = f"✓ BAŞARILI!\nGüle güle {isim}, ÇIKIŞ kaydınız alındı.\nToplam Süre: {calisilan_saat} saat."
            
    conn.commit()
    conn.close()
    return jsonify({"mesaj": mesaj})

@app.route("/personel-ekran")
def personel_ekran():
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, isim FROM personeller")
    personeller = cursor.fetchall()
    p_id = request.args.get("p_id")
    gecmis_rows = ""
    secili_personel = ""
    toplam_mesai_saati = 0
    if p_id:
        cursor.execute("SELECT isim FROM personeller WHERE id = ?", (p_id,))
        res_p = cursor.fetchone()
        secili_personel = res_p[0] if res_p else ""
        cursor.execute("SELECT tarih, giris_saati, cikis_saati, fazla_mesai_saati FROM kayitlar WHERE personel_id = ? ORDER BY id DESC", (p_id,))
        kayitlar = cursor.fetchall()
        for k in kayitlar:
            gecmis_rows += f"<tr><td>{k[0]}</td><td>{k[1]}</td><td>{k[2] if k[2] else 'İçeride'}</td><td>{k[3]} Saat</td></tr>"
            toplam_mesai_saati += k[3]
    conn.close()
    options = "".join([f"<option value='{p[0]}' {'selected' if p_id==str(p[0]) else ''}>{p[1]}</option>" for p in personeller])
    html = f"""
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1'><title>Personel Çalışma Geçmişi</title>
    <style>body{{font-family:sans-serif; background:#f4f6f9; color:#333; padding:20px;}} .container{{max-width:800px; margin:0 auto; background:#fff; padding:20px; border-radius:10px;}} table{{width:100%; border-collapse:collapse; margin-top:15px;}} th,td{{padding:10px; border-bottom:1px solid #ddd; text-align:left;}} th{{background:#343a40; color:#fff;}} select, input{{padding:10px; border-radius:5px;}}</style>
    </head><body><div class='container'>
        <h2>📊 Kendi Giriş / Çıkış Geçmişini Sorgula</h2>
        <form method='GET' action='/personel-ekran'><select name='p_id'><option value=''>--- Adınızı Seçin ---</option>{options}</select> <input type='submit' value='Sorgula'></form>
        {{personel_bilgi}}
        <table><tr><th>Tarih</th><th>Giriş Saati</th><th>Çıkış Saati</th><th>Fazla Mesai</th></tr>{gecmis_rows}</table>
        <br><a href='/ortak-giris' style='color:#007bff; text-decoration:none; font-weight:bold;'>← Giriş/Çıkış Ekranına Dön</a>
    </div></body></html>
    """
    p_info = f"<h4>👤 Personel: {secili_personel} | ⏱️ Toplam Fazla Mesai: <span style='color:red;'>{toplam_mesai_saati} Saat</span></h4>" if secili_personel else ""
    return render_template_string(html.replace("{{personel_bilgi}}", p_info))

@app.route("/c-sifirla/<int:p_id>")
def cihaz_sifirla(p_id):
    if request.cookies.get("admin_session") != "aktif_oturum_guvenli": return redirect("/login")
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE personeller SET cihaz_id = NULL WHERE id = ?", (p_id,))
    conn.commit()
    conn.close()
    return redirect("/")

@app.route("/ortak-qr-indir")
def ortak_qr_indir():
    if request.cookies.get("admin_session") != "aktif_oturum_guvenli": return redirect("/login")
    qr_url = f"https://{request.host}/ortak-giris"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    output = BytesIO()
    img.save(output, format="PNG")
    output.seek(0)
    return send_file(output, download_name="Sirket_Kurumsal_Ortak_QR.png", as_attachment=True)

@app.route("/p-ekle", methods=["POST"])
def personel_ekle():
    if request.cookies.get("admin_session") != "aktif_oturum_guvenli": return redirect("/login")
    isim = request.form['isim']
    sabit_maas = float(request.form['sabit_maas'])
    pin = request.form['pin']
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO personeller (isim, sabit_maas, pin_kodu) VALUES (?, ?, ?)", (isim, sabit_maas, pin))
    conn.commit()
    conn.close()
    return redirect("/")

@app.route("/p-sil/<int:p_id>")
def personel_sil(p_id):
    if request.cookies.get("admin_session") != "aktif_oturum_guvenli": return redirect("/login")
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM personeller WHERE id = ?", (p_id,))
    cursor.execute("DELETE FROM kayitlar WHERE personel_id = ?", (p_id,))
    conn.commit()
    conn.close()
    return redirect("/")

@app.route("/ek-ucret", methods=["POST"])
def ek_ucret():
    if request.cookies.get("admin_session") != "aktif_oturum_guvenli": return redirect("/login")
    p_id = int(request.form['p_id'])
    miktar = float(request.form['miktar'])
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE personeller SET ek_ucret = ek_ucret + ? WHERE id = ?", (miktar, p_id))
    conn.commit()
    conn.close()
    return redirect("/")

@app.route("/excel-rapor")
def excel_rapor():
    if request.cookies.get("admin_session") != "aktif_oturum_guvenli": return redirect("/login")
    conn = sqlite3.connect("takip.db")
    query = "SELECT k.tarih AS [Tarih], p.isim AS [Personel Adı], p.sabit_maas AS [Sabit Maaş (TL)], k.giris_saati AS [Giriş Saati], k.cikis_saati AS [Çıkış Saati], k.fazla_mesai_saati AS [Fazla Mesai (Saat)] FROM kayitlar k JOIN personeller p ON k.personel_id = p.id"
    df = pd.read_sql_query(query, conn)
    conn.close()
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Mesai_Raporu')
    output.seek(0)
    return send_file(output, download_name=f"Mesai_Raporu_{datetime.now().strftime('%Y%m%d')}.xlsx", as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
