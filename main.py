import os
import socket
import sqlite3
import qrcode
import webbrowser
import pandas as pd
from io import BytesIO
from datetime import datetime
from flask import Flask, request, render_template_string, redirect, send_file

app = Flask(__name__)

# 📌 Terminalde aldığınız yerel IP adresiniz
BILGISAYAR_IP = "192.168.1.40" 
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
            <td><img src='/static/qr_codes/{p_id}.png' width='65' style='border:1px solid #ccc; border-radius:5px;'></td>
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
            <td>
                <a href='/personel-sil/{p_id}' style='background:#dc3545; color:#fff; padding:5px 10px; border-radius:3px; text-decoration:none; font-size:12px;' onclick="return confirm('Silmek istediğinize emin misiniz?')">Sil</a>
            </td>
        </tr>
        """
        
    cursor.execute("""
        SELECT k.tarih, p.isim, k.giris_saati, k.cikis_saati, k.fazla_mesai_saati 
        FROM kayitlar k 
        JOIN personeller p ON k.personel_id = p.id 
        ORDER BY k.id DESC LIMIT 50
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
    <html><head><meta charset='utf-8'><title>Maaş ve QR Takip Paneli</title>
    <style>
        body{{font-family:Segoe UI, sans-serif; background:#f4f6f9; padding:30px; color:#333;}}
        .container{{max-width:1250px; margin:0 auto; background:#fff; padding:25px; border-radius:8px; box-shadow:0 4px 15px rgba(0,0,0,0.08);}}
        table{{width:100%; border-collapse:collapse; margin-top:20px; font-size:14px; margin-bottom:40px;}}
        th,td{{padding:12px; border-bottom:1px solid #dee2e6; text-align:left;}}
        th{{background:#212529; color:#fff;}}
        .form-group{{background:#e9ecef; padding:20px; border-radius:6px; margin-bottom:25px; display: flex; justify-content: space-between; align-items: center;}}
        input[type=text], input[type=number]{{padding:8px; margin-right:10px; border:1px solid #ced4da; border-radius:4px; width:200px;}}
        input[type=submit]{{padding:8px 20px; background:#007bff; color:#fff; border:none; border-radius:4px; cursor:pointer; font-weight:bold;}}
        .btn-excel{{padding:10px 20px; background:#28a745; color:#fff; border:none; border-radius:4px; cursor:pointer; font-weight:bold; text-decoration:none;}}
        .section-title{{border-left:5px solid #007bff; padding-left:10px; margin-top:30px; color:#212529;}}
    </style>
    </head><body>
    <div class='container'>
        <h2>🤖 Akıllı Personel Maaş & QR Mesai Takip Otomasyonu</h2>
        <p style='color: #495057;'><b>Cihazınızın Güncel IP Adresi: {BILGISAYAR_IP} (Telefonunuz bu IP üzerinden bağlanacak)</b></p>
        
        <div class='form-group'>
            <form action='/personel-ekle' method='POST' style='margin: 0;'>
                <input type='text' name='isim' placeholder='Ad Soyad' required> 
                <input type='number' step='0.01' name='sabit_maas' placeholder='Aylık Sabit Maaş (TL)' required> 
                <input type='submit' value='Kaydet & QR Kod Üret'>
            </form>
            <a href='/excel-rapor' class='btn-excel'>📥 Excel Raporu İndir</a>
        </div>
        
        <h3 class='section-title'>👥 Mevcut Personel Durumları ve Maaş Hakedişleri</h3>
        <table>
            <tr>
                <th>QR Kod</th><th>Personel</th><th>Durum</th><th>Sabit Maaş</th><th>S. Ücret (Maaş/225)</th>
                <th>Toplam Fazla Mesai</th><th>Mesai Kazancı (x1.5)</th><th>Ek Ücret / Prim</th><th>Toplam Hak Edilen</th><th>Prim İşlemi</th><th>Yönetim</th>
            </tr>
            {rows}
        </table>
        
        <h3 class='section-title'>📋 Detaylı Giriş / Çıkış Hareket Geçmişi</h3>
        <table>
            <tr>
                <th>Tarih</th><th>Personel Adı</th><th>Giriş Saati</th><th>Çıkış Saati</th><th>Yazılan Fazla Mesai</th>
            </tr>
            {gecmis_rows}
        </table>
    </div>
    </body></html>
    """
    return render_template_string(html)

@app.route("/personel-ekle", methods=["POST"])
def personel_ekle():
    isim = request.form['isim']
    sabit_maas = float(request.form['sabit_maas'])
    
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO personeller (isim, sabit_maas) VALUES (?, ?)", (isim, sabit_maas))
    p_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    qr_url = f"http://{BILGISAYAR_IP}:5050/okut/{p_id}"
    qr = qrcode.QRCode(version=1, box_size=5, border=2)
    qr.add_data(qr_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(f"static/qr_codes/{p_id}.png")
    
    return redirect("/")

@app.route("/personel-sil/<int:p_id>")
def personel_sil(p_id):
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM personeller WHERE id = ?", (p_id,))
    cursor.execute("DELETE FROM kayitlar WHERE personel_id = ?", (p_id,))
    conn.commit()
    conn.close()
    try:
        os.remove(f"static/qr_codes/{p_id}.png")
    except:
        pass
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

@app.route("/okut/<int:personel_id>")
def qr_okut(personel_id):
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("SELECT isim FROM personeller WHERE id = ?", (personel_id,))
    personel = cursor.fetchone()
    
    if not personel:
        conn.close()
        return "Personel bulunamadı!", 404

    isim = personel[0]
    simdi = datetime.now()
    bugun = simdi.strftime("%Y-%m-%d")
    saat_str = simdi.strftime("%H:%M:%S")

    cursor.execute(
        "SELECT id, giris_saati FROM kayitlar WHERE personel_id = ? AND cikis_saati IS NULL ORDER BY id DESC LIMIT 1",
        (personel_id,)
    )
    acik_kayit = cursor.fetchone()

    if not acik_kayit:
        cursor.execute("INSERT INTO kayitlar (personel_id, tarih, giris_saati) VALUES (?, ?, ?)", (personel_id, bugun, saat_str))
        mesaj = f"Merhaba {isim}, GİRİŞ kaydınız saat {saat_str} olarak alındı. İyi çalışmalar!"
    else:
        kayit_id, giris_saati_str = acik_kayit
        giris_zamani = datetime.strptime(f"{bugun} {giris_saati_str}", "%Y-%m-%d %H:%M:%S")
        calisilan_saat = round((simdi - giris_zamani).total_seconds() / 3600, 2)
        fazla_mesai = round(calisilan_saat - 8.0, 2) if calisilan_saat > 8.0 else 0.0
        
        cursor.execute("UPDATE kayitlar SET cikis_saati = ?, fazla_mesai_saati = ? WHERE id = ?", (saat_str, fazla_mesai, kayit_id))
        mesaj = f"Güle güle {isim}, ÇIKIŞ kaydınız alındı. Toplam: {calisilan_saat} saat çalıştınız. (Fazla Mesai: {fazla_mesai} Saat)"
    
    conn.commit()
    conn.close()

    html = f"""
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1'><style>
    body {{ font-family: sans-serif; background: #212529; color: #fff; text-align: center; padding-top: 60px; }}
    .card {{ background: #fff; color: #000; padding: 25px; margin: 20px auto; max-width: 450px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }}
    h1 {{ color: #28a745; }}
    </style></head><body><div class='card'><h1>✓ İşlem Başarılı</h1><h3>{isim}</h3><p style='font-size:16px;'>{mesaj}</p></div></body></html>
    """
    return render_template_string(html)

if __name__ == "__main__":
    webbrowser.open("http://127.0.0.1:5050")
    app.run(host="0.0.0.0", port=5050, debug=False)

