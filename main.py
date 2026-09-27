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

# 📌 AYAR 1: ŞİRKETİNİZİN TAM KOORDİNATLARINI BURAYA YAZIN
SIRKET_ENLEM = 40.18245  
SIRKET_BOYLAM = 29.11452 

# 📌 AYAR 2: KAÇ METRE YAKINDAN OKUTABİLSİNLER? (Metre cinsinden sınır)
GECERLI_MESAFE_METRE = 20.0 

os.makedirs("static/qr_codes", exist_ok=True)

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

@app.route("/")
def admin_paneli():
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, isim, sabit_maas, ek_ucret FROM personeller")
    personeller_raw = cursor.fetchall()
    
    rows = ""
    for p in personeller_raw:
        p_id, isim, sabit_maas, ek_ucret = p
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
    <html><head><meta charset='utf-8'><title>Yönetim Paneli</title>
    <style>body{{font-family:Segoe UI,sans-serif; background:#f4f6f9; padding:30px;}} .container{{max-width:1250px; margin:0 auto; background:#fff; padding:25px; border-radius:8px; box-shadow:0 4px 15px rgba(0,0,0,0.08);}} table{{width:100%; border-collapse:collapse; margin-top:20px; font-size:14px; margin-bottom:40px;}} th,td{{padding:12px; border-bottom:1px solid #dee2e6; text-align:left;}} th{{background:#212529; color:#fff;}} .btn-qr{{background:#6f42c1; color:#fff; padding:10px 15px; text-decoration:none; border-radius:4px; font-weight:bold;}} .btn-excel{{padding:10px 15px; background:#28a745; color:#fff; text-decoration:none; border-radius:4px; font-weight:bold;}}</style>
    </head><body><div class='container'>
        <h2>🤖 GPS Korumalı Personel Maaş & QR Takip Paneli</h2>
        <div style='background:#e9ecef; padding:20px; border-radius:6px; margin-bottom:25px; display:flex; justify-content:space-between; align-items:center;'>
            <form action='/personel-ekle' method='POST' style='margin:0;'>
                <input type='text' name='isim' placeholder='Ad Soyad' style='padding:8px; width:220px;' required> 
                <input type='number' step='0.01' name='sabit_maas' placeholder='Aylık Maaş (TL)' style='padding:8px; width:180px;' required> 
                <input type='submit' value='Personel Tanımla' style='padding:8px 15px; background:#007bff; color:#fff; border:none; cursor:pointer; font-weight:bold;'>
            </form>
            <div>
                <a href='/excel-rapor' class='btn-excel' style='margin-right:10px;'>📥 Excel Raporu</a>
                <a href='/ortak-qr-indir' class='btn-qr'>📥 Duvara Asılacak Güvenli Ortak QR İndir</a>
            </div>
        </div>
        <h3>👥 Personel Listesi ve Hakedişler</h3>
        <table>
            <tr><th>Personel</th><th>Durum</th><th>Sabit Maaş</th><th>S. Ücret</th><th>Toplam Mesai</th><th>Mesai Kazancı</th><th>Prim</th><th>Toplam Hak Edilen</th><th>Prim İşlemi</th><th>Yönetim</th></tr>
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
    <style>body{{font-family:sans-serif; background:#212529; color:#fff; text-align:center; padding-top:40px;}} .card{{background:#fff; color:#000; padding:25px; margin:15px; border-radius:12px;}} select, button{{width:100%; padding:14px; margin-top:15px; border-radius:6px; font-size:16px; font-weight:bold;}} button{{color:#fff; border:none; cursor:pointer;}} .btn-giris{{background:#28a745;}} .btn-cikis{{background:#dc3545;}}</style>
    <script>
        function islemYap(islemTipi) {{
            var p_id = document.getElementById("personel_select").value;
            if(!p_id) {{ alert("Lütfen adınızı seçin!"); return; }}
            
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
                    alert("GPS konum izni verilmedi! İşlem iptal edildi.");
                }}, {{ enableHighAccuracy: true, timeout: 5000 }});
            }} else {{
                alert("Telefonunuzun GPS özelliği desteklenmiyor!");
            }}
        }}
    </script>
    </head><body><div class='card'>
        <h2 style='margin-top:0; color:#333;'>📍 Konum Doğrulamalı Giriş</h2>
        <p style='color:#666;'>Lütfen isminizi seçip buradaki butonlara basınız:</p>
        <select id='personel_select'><option value=''>--- İsminizi Seçin ---</option>{options}</select>
	📍 KONUMU DOĞRULA & GİRİŞ YAP📍 KONUMU DOĞRULA & ÇIKIŞ YAP"""
    return render_template_string(html)

@app.route("/konum-dogrula", methods=["POST"])
def konum_dogrula():
    data = request.get_json()
    p_id = data.get("personel_id")
    islem = data.get("islem")
    kul_enlem = float(data.get("enlem"))
    kul_boylam = float(data.get("boylam"))
    
    mesafe = mesafe_hesapla(SIRKET_ENLEM, SIRKET_BOYLAM, kul_enlem, kul_boylam)
    
    if mesafe > GECERLI_MESAFE_METRE:
        return jsonify({"mesaj": f"❌ İŞLEM REDDEDİLDİ!\nŞirket sınırları dışındasınız.\nUzaklık: {round(mesafe, 1)} metre. Giriş sınırı {GECERLI_MESAFE_METRE} metredir!"})
        
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
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
def ortak_qr_indir():
    qr_url = f"https://{request.host}/ortak-giris"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(qr_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    output = BytesIO()
    img.save(output, format="PNG")
    output.seek(0)
    return send_file(output, download_name="Sirket_GPS_Ortak_QR.png", as_attachment=True)

@app.route("/personel-ekle", methods=["POST"])
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
def personel_sil(p_id):
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM personeller WHERE id = ?", (p_id,))
    cursor.execute("DELETE FROM kayitlar WHERE personel_id = ?", (p_id,))
    conn.commit()
    conn.close()
    return redirect("/")

@app.route("/ek-ucret", methods=["POST"])
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
	
