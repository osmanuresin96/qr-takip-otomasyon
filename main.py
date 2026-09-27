import os, sqlite3, qrcode, math
import pandas as pd
from io import BytesIO
from datetime import datetime
from flask import Flask, request, render_template_string, redirect, send_file, jsonify

app = Flask(__name__)

# MİLLET MAHALLESİ NO:64/1 KESİN BİNA KOORDİNATLARI VE TOLERANS ÇAPI
SIRKET_ENLEM, SIRKET_BOYLAM = 40.20145, 29.11718
GECERLI_MESAFE_METRE = 60.0

os.makedirs("static", exist_ok=True)

def init_db():
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS personeller")
    cursor.execute("DROP TABLE IF EXISTS yonetici")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS personeller (
            id INTEGER PRIMARY KEY AUTOINCREMENT, isim TEXT NOT NULL, sabit_maas REAL NOT NULL, ek_ucret REAL DEFAULT 0, pin_kodu TEXT NOT NULL
        )""")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kayitlar (
            id INTEGER PRIMARY KEY AUTOINCREMENT, personel_id INTEGER, tarih TEXT, giris_saati TEXT, cikis_saati TEXT, fazla_mesai_saati REAL DEFAULT 0, FOREIGN KEY(personel_id) REFERENCES personeller(id) ON DELETE CASCADE
        )""")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS yonetici (
            id INTEGER PRIMARY KEY, kullanici_adi TEXT NOT NULL, sifre TEXT NOT NULL
        )""")
    cursor.execute("INSERT OR REPLACE INTO yonetici (id, kullanici_adi, sifre) VALUES (1, 'admin', '123456')")
    conn.commit()
    conn.close()

init_db()

def mesafe_hesapla(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi, delta_lambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

def admin_oturum_kontrol():
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("SELECT kullanici_adi, sifre FROM yonetici WHERE id = 1")
    u, p = cursor.fetchone()
    conn.close()
    return request.cookies.get("admin_session") == f"{u}_{p}"
@app.route("/login", methods=["GET", "POST"])
def login_sayfasi():
    hata = ""
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("SELECT kullanici_adi, sifre FROM yonetici WHERE id = 1")
    u, p = cursor.fetchone()
    conn.close()
    if request.method == "POST":
        if request.form.get("username") == u and request.form.get("password") == p:
            response = redirect("/")
            response.set_cookie("admin_session", f"{u}_{p}", max_age=3600)
            return response
        hata = "Kullanici adi veya sifre hatali!"
    return render_template_string(f"""
    <html><body style='font-family:sans-serif; background:#1e222b; display:flex; align-items:center; justify-content:center; height:100vh; margin:0;'><div style='background:#fff; padding:30px; border-radius:10px; width:100%; max-width:340px;'>
        <h3 style='margin:0 0 10px 0; text-align:center;'>Yonetici Girisi</h3>
        <p style='color:red; text-align:center; font-size:14px; margin:0;'>{hata}</p>
        <form method='POST'>
            <input type='text' name='username' placeholder='Kullanici Adi' style='width:100%; padding:12px; margin-top:10px;' required><br>
            <input type='password' name='password' placeholder='Sifre' style='width:100%; padding:12px; margin-top:10px;' required><br>
            <input type='submit' value='Giris Yap' style='width:100%; padding:12px; background:#007bff; color:#fff; font-weight:bold; border:none; margin-top:15px; cursor:pointer;'>
        </form>
    </div></body></html>""")

@app.route("/gizli-kasa-ayarlari", methods=["GET", "POST"])
def gizli_kasa_ayarlari():
    if not admin_oturum_kontrol(): return redirect("/login")
    mesaj = ""
    if request.method == "POST":
        yu, yp = request.form.get("yeni_user"), request.form.get("yeni_pass")
        if yu and yp:
            conn = sqlite3.connect("takip.db")
            cursor = conn.cursor()
            cursor.execute("UPDATE yonetici SET kullanici_adi = ?, sifre = ? WHERE id = 1", (yu, yp))
            conn.commit()
            conn.close()
            mesaj = "Bilgiler guncellendi!"
    return render_template_string(f"""
    <html><body style='font-family:sans-serif; background:#11141a; display:flex; align-items:center; justify-content:center; height:100vh; margin:0; color:#fff;'><div style='background:#fff; color:#333; padding:30px; border-radius:12px; width:100%; max-width:380px;'>
        <h3 style='margin:0 0 10px 0; text-align:center;'>Gizli Sifre Degistirme</h3>
        <p style='color:green; font-weight:bold; font-size:14px; text-align:center;'>{mesaj}</p>
        <form method='POST'>
            Yeni Admin Adi: <input type='text' name='yeni_user' style='width:100%; padding:10px; margin-top:10px;' required><br>
            Yeni Admin Sifresi: <input type='text' name='yeni_pass' style='width:100%; padding:10px; margin-top:10px;' required><br>
            <input type='submit' value='Guncelle' style='width:100%; padding:12px; background:#6f42c1; color:#fff; border:none; font-weight:bold; cursor:pointer; margin-top:15px;'>
        </form>
        <br><a href='/' style='display:block; text-align:center; color:#007bff; text-decoration:none;'>← Paneline Don</a>
    </div></body></html>""")

@app.route("/")
def admin_paneli():
    if not admin_oturum_kontrol(): return redirect("/login")
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, isim, sabit_maas, ek_ucret, pin_kodu FROM personeller")
    personeller_raw = cursor.fetchall()
    rows = ""
    for p in personeller_raw:
        p_id, isim, sabit_maas, ek_ucret, pin = p
        cursor.execute("SELECT SUM(fazla_mesai_saati) FROM kayitlar WHERE personel_id = ?", (p_id,))
        res = cursor.fetchone()
        toplam_mesai = res if res and res is not None else 0
        su = round(sabit_maas / 225, 2)
        mk = round(toplam_mesai * su * 1.5, 2)
        th = round(sabit_maas + mk + ek_ucret, 2)
        rows += f"<tr><td><b>{isim}</b></td><td style='font-weight:bold; color:#6f42c1;'>{pin}</td><td>{sabit_maas:,.2f} TL</td><td>{su:,.2f} TL</td><td>{toplam_mesai} Saat</td><td style='color:red;'>+{mk:,.2f} TL</td><td>{ek_ucret:,.2f} TL</td><td style='color:#28a745; font-weight:bold;'>{th:,.2f} TL</td><td><form action='/ek-ucret' method='POST' style='margin:0;'><input type='hidden' name='p_id' value='{p_id}'><input type='number' name='miktar' style='width:65px; padding:4px;' placeholder='TL' required><input type='submit' value='Ekle' style='background:#28a745; color:#fff; border:none; padding:5px;'></form></td><td><a href='/p-sil/{p_id}' style='background:#dc3545; color:#fff; padding:4px 8px; border-radius:3px; text-decoration:none; font-size:12px;'>Sil</a></td></tr>"
    cursor.execute("SELECT k.tarih, p.isim, k.giris_saati, k.cikis_saati, k.fazla_mesai_saati FROM kayitlar k JOIN personeller p ON k.personel_id = p.id ORDER BY k.id DESC LIMIT 30")
    gecmis_raw = cursor.fetchall()
    gecmis_rows = "".join([f"<tr><td>{g}</td><td><b>{g}</b></td><td style='color:green;'>{g}</td><td>{g if g else 'Iceride'}</td><td>{g} Saat</td></tr>" for g in gecmis_raw])
    conn.close()
    html = f"""
    <html><head><meta charset='utf-8'><title>Yonetim Paneli</title>
    <style>body{{font-family:sans-serif; background:#f4f6f9; padding:25px; color:#333;}} .container{{max-width:1350px; margin:0 auto; background:#fff; padding:20px; border-radius:8px; box-shadow:0 4px 15px rgba(0,0,0,0.08);}} table{{width:100%; border-collapse:collapse; margin-top:15px; font-size:14px;}} th,td{{padding:10px; border-bottom:1px solid #dee2e6; text-align:left;}} th{{background:#212529; color:#fff;}} .form-box{{background:#e9ecef; padding:15px; border-radius:6px; display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;}} input[type=text], input[type=number]{{padding:6px; margin-right:5px; border:1px solid #ddd; border-radius:4px;}}</style>
    </head><body><div class='container'>
        <h2>Sirket Maas, Prim ve Guvenli QR Kontrol Otomasyonu</h2>
        <div class='form-box'>
            <form action='/p-ekle' method='POST' style='margin:0;'>
                <input type='text' name='isim' placeholder='Personel Adi' required> 
                <input type='number' step='0.01' name='sabit_maas' placeholder='Maas' required> 
                <input type='text' name='pin' placeholder='Giris PIN' maxlength='4' required> 
                <input type='submit' value='Personel Tanimla' style='padding:6px 15px; background:#007bff; color:#fff; border:none; cursor:pointer; border-radius:4px;'>
            </form>
            <div>
                <a href='/excel-rapor' style='padding:8px 12px; background:#28a745; color:#fff; text-decoration:none; font-weight:bold; border-radius:4px; margin-right:10px;'>Excel Raporu</a>
                <a href='/ortak-qr-indir' style='padding:8px 12px; background:#6f42c1; color:#fff; text-decoration:none; font-weight:bold; border-radius:4px;'>Ortak QR</a>
            </div>
        </div>
        <table><tr><th>Personel</th><th>Giris PIN</th><th>Sabit Maas</th><th>Saatlik Ucret</th><th>Toplam Mesai</th><th>Mesai Kazanci</th><th>Prim</th><th>Toplam Hak Edilen</th><th>Prim Islemi</th><th>Yonetim</th></tr>{rows}</table>
        <h3>Genel Giris / Cikis Hareket Kayitlari</h3><table><tr><th>Tarih</th><th>Personel Adi</th><th>Giris Saati</th><th>Cikis Saati</th><th>Fazla Mesai</th></tr>{gecmis_rows}</table>
    </div></body></html>"""
    return render_template_string(html)
@app.route("/ortak-grid")
@app.route("/ortak-giris")
def ortak_giris():
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, isim FROM personeller ORDER BY isim ASC")
    personeller = cursor.fetchall()
    conn.close()
    options = "".join([f"<option value='{p}'>{p}</option>" for p in personeller])
    html = f"""
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1'><title>Giris Paneli</title>
    <style>body{{font-family:sans-serif; background:#212529; color:#fff; text-align:center; padding-top:30px;}} .card{{background:#fff; color:#000; padding:25px; margin:15px auto; max-width:400px; border-radius:12px;}} select, input, button{{width:100%; padding:14px; margin-top:15px; border-radius:6px; font-size:16px; font-weight:bold; box-sizing:border-box;}} button{{color:#fff; border:none; cursor:pointer;}} .btn-g{{background:#28a745;}} .btn-c{{background:#dc3545;}} .status{{font-size:14px; margin-top:12px; color:orange; font-weight:bold;}}</style>
    <script>
        function islemYap(islemTipi) {{
            var p_id = document.getElementById("personel_select").value;
            var pin = document.getElementById("pin_input").value;
            var st = document.getElementById("status_text");
            if(!p_id || !pin) {{ alert("Lutfen adinizi secin ve sifrenizi girin!"); return; }}
            if (navigator.geolocation) {{
                st.innerText = "Gercek uydu sinyalleri taraniyor... Lutfen bekleyin.";
                navigator.geolocation.getCurrentPosition(function(pos) {{
                    var veri = {{ personel_id: p_id, pin_kodu: pin, islem: islemTipi, enlem: pos.coords.latitude, boylam: pos.coords.longitude }};
                    st.innerText = "Konum dogrulaniyor...";
                    fetch('/konum-dogrula', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify(veri) }})
                    .then(r => r.json()).then(data => {{ alert(data.mesaj); if(data.durum === "ok") {{ location.reload(); }} st.innerText = ""; }});
                }}, function(err) {{ alert("GPS Kapali! Konum servisini acip tarayiciya izin verin."); st.innerText = ""; }}, {{ enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }});
            }} else {{ alert("Cihaz GPS desteklemiyor!"); }}
        }}
    </script>
    </head><body><div class='card'>
        <h2>Giris Onay Sistemi</h2>
        <select id='personel_select'><option value=''>--- Adinizi Secin ---</option>{options}</select>
        <input type='password' id='pin_input' placeholder='4 Haneli Giris PIN' maxlength='4' inputmode='numeric'>
        <button class='btn-g' onclick="islemYap('GIRIS')">KONUMU DOGRULA & GIRIS YAP</button>
        <button class='btn-c' onclick="islemYap('CIKIS')">KONUMU DOGRULA & CIKIS YAP</button>
        <a href='/personel-ekran' style='display:inline-block; margin-top:20px; color:#007bff; text-decoration:none; font-weight:bold;'>Kendi Giris Saatlerimi Sorgula</a>
        <div id='status_text' class='status'></div>
    </div></body></html>"""
    return render_template_string(html)

@app.route("/konum-dogrula", methods=["POST"])
def konum_dogrula():
    data = request.get_json()
    p_id, pin, islem = data.get("personel_id"), data.get("pin_kodu"), data.get("islem")
    kul_enlem, kul_boylam = float(data.get("enlem")), float(data.get("boylam"))
    mesafe = mesafe_hesapla(SIRKET_ENLEM, SIRKET_BOYLAM, kul_enlem, kul_boylam)
    if mesafe > GECERLI_MESAFE_METRE:
        return jsonify({"durum": "hata", "mesaj": f"ISLEM ENGELLENDI!\\nDukkan sinirlari disindasiniz.\\n\\nOlculen Uzaklik: {round(mesafe, 1)} metre.\\nSapma siniri: {GECERLI_MESAFE_METRE} metredir."})
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("SELECT isim, pin_kodu FROM personeller WHERE id = ?", (p_id,))
    res_p = cursor.fetchone()
    if not res_p or str(res_p[1]) != str(pin):
        conn.close()
        return jsonify({"durum": "hata", "mesaj": "HATA: PIN sifreniz yanlis!"})
    isim = res_p[0]
    simdi = datetime.now()
    bugun, saat_str = simdi.strftime("%Y-%m-%d"), simdi.strftime("%H:%M:%S")
    cursor.execute("SELECT id, giris_saati FROM kayitlar WHERE personel_id = ? AND cikis_saati IS NULL ORDER BY id DESC LIMIT 1", (p_id,))
    acik_kayit = cursor.fetchone()
    if islem == "GIRIS":
        if acik_kayit: mesaj = f"Zaten iceride calisiyor gorunuyorsunuz, {isim}!"
        else:
            cursor.execute("INSERT INTO kayitlar (personel_id, tarih, giris_saati) VALUES (?, ?, ?)", (p_id, bugun, saat_str))
            mesaj = f"BASARILI!\\n{isim}, GIRIS kaydiniz alindi.\\nMesafe Farki: {round(mesafe, 1)} Metre."
    else:
        if not acik_kayit: mesaj = f"Aktif giris kaydiniz bulunamadi, {isim}!"
        else:
            k_id, g_saat = acik_kayit[0], acik_kayit[1]
            g_zamani = datetime.strptime(f"{bugun} {g_saat}", "%Y-%m-%d %H:%M:%S")
            calisilan_saat = round((simdi - g_zamani).total_seconds() / 3600, 2)
            fm = round(calisilan_saat - 8.0, 2) if calisilan_saat > 8.0 else 0.0
            cursor.execute("UPDATE kayitlar SET cikis_saati = ?, fazla_mesai_saati = ? WHERE id = ?", (saat_str, fm, k_id))
            mesaj = f"BASARILI!\\nGule gule {isim}, CIKIS kaydınız alindi.\\nMesafe Farki: {round(mesafe, 1)} Metre."
    conn.commit()
    conn.close()
    return jsonify({"durum": "ok", "mesaj": mesaj})

@app.route("/personel-ekran")
def personel_ekran():
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, isim FROM personeller")
    personeller = cursor.fetchall()
    p_id = request.args.get("p_id")
    gecmis_rows, secili_personel, tm = "", "", 0
    if p_id:
        cursor.execute("SELECT isim FROM personeller WHERE id = ?", (p_id,))
        res_p = cursor.fetchone()
        secili_personel = res_p[0] if res_p else ""
        cursor.execute("SELECT tarih, giris_saati, cikis_saati, fazla_mesai_saati FROM kayitlar WHERE personel_id = ? ORDER BY id DESC", (p_id,))
        kayitlar = cursor.fetchall()
        for k in kayitlar:
            gecmis_rows += f"<tr><td>{k[0]}</td><td>{k[1]}</td><td>{k[2] if k[2] else 'Iceride'}</td><td>{k[3]} Saat</td></tr>"
            tm += k[3]
    conn.close()
    options = "".join([f"<option value='{p[0]}'>{p[1]}</option>" for p in personeller])
    html = f"""
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1'><title>Calisma Gecmisi</title>
    <style>body{{font-family:sans-serif; background:#f4f6f9; color:#333; padding:20px;}} .container{{max-width:800px; margin:0 auto; background:#fff; padding:20px; border-radius:10px;}} table{{width:100%; border-collapse:collapse; margin-top:15px;}} th,td{{padding:10px; border-bottom:1px solid #ddd; text-align:left;}} th{{background:#343a40; color:#fff;}} select, input{{padding:10px; border-radius:5px;}}</style>
    </head><body><div class='container'>
        <h2>Kendi Giris / Cikis Gecmisini Sorgula</h2>
        <form method='GET' action='/personel-ekran'><select name='p_id'><option value=''>--- Adinizi Secin ---</option>{options}</select> <input type='submit' value='Sorgula'></form>
        {{personel_bilgi}}
        <table><tr><th>Tarih</th><th>Giris Saati</th><th>Cikis Saati</th><th>Fazla Mesai</th></tr>{gecmis_rows}</table>
        <br><a href='/ortak-giris' style='color:#007bff; text-decoration:none; font-weight:bold;'>← Giris/Cikis Ekranina Don</a>
    </div></body></html>"""
    p_info = f"<h4>Personel: {secili_personel} | Toplam Fazla Mesai: <span style='color:red;'>{tm} Saat</span></h4>" if secili_personel else ""
    return render_template_string(html.replace("{{personel_bilgi}}", p_info))

@app.route("/ortak-qr-indir")
def ortak_qr_indir():
    if not admin_oturum_kontrol(): return redirect("/login")
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(f"https://{request.host}/ortak-giris")
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    output = BytesIO()
    img.save(output, format="PNG")
    output.seek(0)
    return send_file(output, download_name="Sirket_QR.png", as_attachment=True)

@app.get("/p-sil/<int:p_id>")
def p_sil(p_id):
    if not admin_oturum_kontrol(): return redirect("/login")
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM personeller WHERE id = ?", (p_id,))
    cursor.execute("DELETE FROM kayitlar WHERE personel_id = ?", (p_id,))
    conn.commit()
    conn.close()
    return redirect("/")

@app.post("/p-ekle")
def p_ekle():
    if not admin_oturum_kontrol(): return redirect("/login")
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO personeller (isim, sabit_maas, pin_kodu) VALUES (?, ?, ?)", (request.form['isim'], float(request.form['sabit_maas']), request.form['pin']))
    conn.commit()
    conn.close()
    return redirect("/")

@app.post("/ek-ucret")
def ek_ucret():
    if not admin_oturum_kontrol(): return redirect("/login")
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE personeller SET ek_ucret = ek_ucret + ? WHERE id = ?", (float(request.form['miktar']), int(request.form['p_id'])))
    conn.commit()
    conn.close()
    return redirect("/")

@app.get("/excel-rapor")
def excel_rapor():
    if not admin_oturum_kontrol(): return redirect("/login")
    conn = sqlite3.connect("takip.db")
    df = pd.read_sql_query("SELECT k.tarih AS [Tarih], p.isim AS [Personel Adı], p.sabit_maas AS [Sabit Maaş (TL)], k.giris_saati AS [Giriş Saati], k.cikis_saati AS [Çıkış Saati], k.fazla_mesai_saati AS [Fazla Mesai (Saat)] FROM kayitlar k JOIN personeller p ON k.personel_id = p.id", conn)
    conn.close()
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer: 
        df.to_excel(writer, index=False, sheet_name='Mesai_Raporu')
    output.seek(0)
    return send_file(output, download_name=f"Mesai_Raporu_{datetime.now().strftime('%Y%m%d')}.xlsx", as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
