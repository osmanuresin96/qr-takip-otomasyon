@app.route("/ortak-giris")
def ortak_giris():
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, isim FROM personeller ORDER BY isim ASC")
    personeller = cursor.fetchall()
    conn.close()
    options = "".join([f"<option value='{p[0]}'>{p[1]}</option>" for p in personeller])
    
    html = f"""
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1'><title>Giriş Paneli</title>
    <style>body{{font-family:sans-serif; background:#212529; color:#fff; text-align:center; padding-top:30px;}} .card{{background:#fff; color:#000; padding:25px; margin:15px auto; max-width:400px; border-radius:12px;}} select, input, button{{width:100%; padding:14px; margin-top:15px; border-radius:6px; font-size:16px; font-weight:bold; box-sizing:border-box;}} button{{color:#fff; border:none; cursor:pointer;}} .btn-g{{background:#28a745;}} .btn-c{{background:#dc3545;}} .status{{font-size:14px; margin-top:12px; color:orange; font-weight:bold;}}</style>
    <script>
        function islemYap(islemTipi) {{
            var p_id = document.getElementById("personel_select").value;
            var pin = document.getElementById("pin_input").value;
            var st = document.getElementById("status_text");
            if(!p_id || !pin) {{ alert("Lütfen adınızı seçin ve şifrenizi girin!"); return; }}
            if (navigator.geolocation) {{
                st.innerText = "⏳ Gerçek uydu sinyalleri taranıyor... Lütfen bekleyin.";
                navigator.geolocation.getCurrentPosition(function(pos) {{
                    var veri = {{ personel_id: p_id, pin_kodu: pin, islem: islemTipi, enlem: pos.coords.latitude, boylam: pos.coords.longitude }};
                    st.innerText = "⏳ Konum doğrulanıyor...";
                    fetch('/konum-dogrula', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify(veri) }})
                    .then(r => r.json()).then(data => {{ alert(data.mesaj); if(data.durum === "ok") {{ location.reload(); }} st.innerText = ""; }});
                }}, function(err) {{ alert("❌ GPS Kapalı! Konum servisini açıp tarayıcıya izin verin."); st.innerText = ""; }}, {{ enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }});
            }} else {{ alert("Cihaz GPS desteklemiyor!"); }}
        }}
    </script>
    </head><body><div class='card'>
        <h2>🏢 Giriş Onay Sistemi</h2>
        <select id='personel_select'><option value=''>--- Adınızı Seçin ---</option>{options}</select>
        <input type='password' id='pin_input' placeholder='4 Haneli Giriş PIN' maxlength='4' inputmode='numeric'>
        <button class='btn-g' onclick="islemYap('GİRİŞ')">📍 KONUMU DOĞRULA & GİRİŞ YAP</button>
        <button class='btn-c' onclick="islemYap('ÇIKIŞ')">📍 KONUMU DOĞRULA & ÇIKIŞ YAP</button>
        <a href='/personel-ekran' style='display:inline-block; margin-top:20px; color:#007bff; text-decoration:none; font-weight:bold;'>👁️ Kendi Giriş Saatlerimi Sorgula</a>
        <div id='status_text' class='status'></div>
    </div></body></html>
    """
    return render_template_string(html)
@app.route("/konum-dogrula", methods=["POST"])
def konum_dogrula():
    data = request.get_json()
    p_id = data.get("personel_id")
    pin = data.get("pin_kodu")
    islem = data.get("islem")
    kul_enlem, kul_boylam = float(data.get("enlem")), float(data.get("boylam"))
    
    mesafe = mesafe_hesapla(SIRKET_ENLEM, SIRKET_BOYLAM, kul_enlem, kul_boylam)
    if mesafe > GECERLI_MESAFE_METRE:
        return jsonify({"durum": "hata", "mesaj": f"❌ İŞLEM ENGELLENDİ!\nDükkan sınırları dışındasınız.\n\nÖlçülen Uzaklık: {round(mesafe, 1)} metre.\nSapma sınırı: {GECERLI_MESAFE_METRE} metredir."})

    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("SELECT isim, pin_kodu FROM personeller WHERE id = ?", (p_id,))
    res_p = cursor.fetchone()
    if not res_p or str(res_p[1]) != str(pin):
        conn.close()
        return jsonify({"durum": "hata", "mesaj": "❌ HATA: PIN şifreniz yanlış!"})
        
    isim = res_p[0]
    simdi = datetime.now()
    bugun = simdi.strftime("%Y-%m-%d")
    saat_str = simdi.strftime("%H:%M:%S")
    cursor.execute("SELECT id, giris_saati FROM kayitlar WHERE personel_id = ? AND cikis_saati IS NULL ORDER BY id DESC LIMIT 1", (p_id,))
    acik_kayit = cursor.fetchone()
    
    if islem == "GİRİŞ":
        if acik_kayit: mesaj = f"Zaten içeride çalışıyor görünüyorsunuz, {isim}!"
        else:
            cursor.execute("INSERT INTO kayitlar (personel_id, tarih, giris_saati) VALUES (?, ?, ?)", (p_id, bugun, saat_str))
            mesaj = f"✓ BAŞARILI!\n{isim}, GİRİŞ kaydınız alındı.\nMesafe Farkı: {round(mesafe, 1)} Metre."
    else:
        if not acik_kayit: mesaj = f"Aktif giriş kaydınız bulunamadı, {isim}!"
        else:
            k_id, g_saat = acik_kayit
            g_zamani = datetime.strptime(f"{bugun} {g_saat}", "%Y-%m-%d %H:%M:%S")
            calisilan_saat = round((simdi - g_zamani).total_seconds() / 3600, 2)
            fm = round(calisilan_saat - 8.0, 2) if calisilan_saat > 8.0 else 0.0
            cursor.execute("UPDATE kayitlar SET cikis_saati = ?, fazla_mesai_saati = ? WHERE id = ?", (saat_str, fm, k_id))
            mesaj = f"✓ BAŞARILI!\nGüle güle {isim}, ÇIKIŞ kaydınız alındı.\nMesafe Farkı: {round(mesafe, 1)} Metre."
    conn.commit()
    conn.close()
    return jsonify({"durum": "ok", "mesaj": mesaj})
@app.route("/personel-ekran")
def personel_ekran():
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, isim FROM personeller ORDER BY isim ASC")
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
            cikis_str = k[2] if k[2] else "İçeride"
            gecmis_rows += f"<tr><td>{k[0]}</td><td>{k[1]}</td><td>{cikis_str}</td><td>{k[3]} Saat</td></tr>"
            tm += k[3]
    conn.close()
    options = "".join([f"<option value='{p[0]}' {'selected' if p_id==str(p[0]) else ''}>{p[1]}</option>" for p in personeller])
    html = f"""
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1'><title>Çalışma Geçmişi</title>
    <style>body{{font-family:sans-serif; background:#f4f6f9; color:#333; padding:20px;}} .container{{max-width:800px; margin:0 auto; background:#fff; padding:20px; border-radius:10px;}} table{{width:100%; border-collapse:collapse; margin-top:15px;}} th,td{{padding:10px; border-bottom:1px solid #ddd; text-align:left;}} th{{background:#343a40; color:#fff;}} select, input{{padding:10px; border-radius:5px;}}</style>
    </head><body><div class='container'>
        <h2>📊 Kendi Giriş / Çıkış Geçmişini Sorgula</h2>
        <form method='GET' action='/personel-ekran'><select name='p_id'><option value=''>--- Adınızı Seçin ---</option>{options}</select> <input type='submit' value='Sorgula'></form>
        {{personel_bilgi}}
        <table><tr><th>Tarih</th><th>Giriş Saati</th><th>Çıkış Saati</th><th>Fazla Mesai</th></tr>{gecmis_rows}</table>
        <br><a href='/ortak-giris' style='color:#007bff; text-decoration:none; font-weight:bold;'>← Giriş/Çıkış Ekranına Dön</a>
    </div></body></html>"""
    p_info = f"<h4>👤 Personel: {secili_personel} | ⏱️ Toplam Fazla Mesai: <span style='color:red;'>{tm} Saat</span></h4>" if secili_personel else ""
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
    query = "SELECT k.tarih AS [Tarih], p.isim AS [Personel Adı], p.sabit_maas AS [Sabit Maaş (TL)], k.giris_saati AS [Giriş Saati], k.cikis_saati AS [Çıkış Saati], k.fazla_mesai_saati AS [Fazla Mesai (Saat)] FROM kayitlar k JOIN personeller p ON k.personel_id = p.id"
    df = pd.read_sql_query(query, conn)
    conn.close()
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer: df.to_excel(writer, index=False, sheet_name='Mesai_Raporu')
    output.seek(0)
    return send_file(output, download_name=f"Mesai_Raporu_{datetime.now().strftime('%Y%m%d')}.xlsx", as_attachment=True)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
