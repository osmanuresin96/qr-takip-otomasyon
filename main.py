@app.route("/ortak-giris")
def ortak_giris():
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, isim FROM personeller ORDER BY isim ASC")
    personeller = cursor.fetchall()
    conn.close()
    options = "".join([f"<option value='{p[0]}'>{p[1]}</option>" for p in personeller])
    
    html = f"""
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1'><title>Giriş Sistemi</title>
    <style>body{{font-family:sans-serif; background:#212529; color:#fff; text-align:center; padding-top:40px;}} .card{{background:#fff; color:#000; padding:25px; margin:15px auto; max-width:400px; border-radius:12px;}} select, input, button{{width:100%; padding:14px; margin-top:15px; border-radius:6px; font-size:16px; font-weight:bold; box-sizing:border-box;}} button{{color:#fff; border:none; cursor:pointer;}} .btn-g{{background:#28a745;}} .btn-c{{background:#dc3545;}} .status{{font-size:14px; margin-top:10px; color:orange; font-weight:bold;}}</style>
    <script>
        function islemYap(islemTipi) {{
            var p_id = document.getElementById("personel_select").value;
            var pin = document.getElementById("pin_input").value;
            var st = document.getElementById("status_text");
            if(!p_id || !pin) {{ alert("Lütfen adınızı seçin ve şifrenizi girin!"); return; }}
            
            if (navigator.geolocation) {{
                st.innerText = "⏳ Hassas GPS uydularına bağlanılıyor, lütfen bekleyin...";
                
                // 📡 Gelişmiş Yüksek Hassasiyetli İzleme Ayarı
                navigator.geolocation.getCurrentPosition(function(position) {{
                    var veri = {{
                        personel_id: p_id,
                        pin_kodu: pin,
                        islem: islemTipi,
                        enlem: position.coords.latitude,
                        boylam: position.coords.longitude
                    }};
                    
                    st.innerText = "⏳ Konum doğrunlanıyor...";
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
                    alert("❌ GPS Bağlantı Hatası! Telefon konum servisini açıp tarayıcıya izin vermelisiniz.");
                    st.innerText = "";
                }}, {{ enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }});
            }} else {{
                alert("Telefonunuz GPS destekleymiyor!");
            }}
        }}
    </script>
    </head><body><div class='card'>
        <h2 style='margin-top:0; color:#333;'>🏢 Giriş Paneli</h2>
        <select id='personel_select'><option value=''>--- Adınızı Seçin ---</option>{options}</select>
        <input type='password' id='pin_input' placeholder='4 Haneli Şifreniz' maxlength='4' inputmode='numeric'>
        <button class='btn-g' onclick="islemYap('GİRİŞ')">📍 KONUMU DOĞRULA & GİRİŞ YAP</button>
        <button class='btn-c' onclick="islemYap('ÇIKIŞ')">📍 KONUMU DOĞRULA & ÇIKIŞ YAP</button>
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
    kul_enlem = float(data.get("enlem"))
    kul_boylam = float(data.get("boylam"))
    
    # 📐 Haversine Küresel Mesafe Hesaplaması
    mesafe = mesafe_hesapla(SIRKET_ENLEM, SIRKET_BOYLAM, kul_enlem, kul_boylam)
    if mesafe > GECERLI_MESAFE_METRE:
        return jsonify({"mesaj": f"❌ İŞLEM ENGELLENDİ!\nDükkan sınırları dışındasınız.\nHesaplanan Mesafe: {round(mesafe, 1)} metre.\nİzin verilen maksimum sapma çapı: {GECERLI_MESAFE_METRE} metredir."})

    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("SELECT isim, pin_kodu FROM personeller WHERE id = ?", (p_id,))
    res_p = cursor.fetchone()
    
    if not res_p or str(res_p[1]) != str(pin):
        conn.close()
        return jsonify({"mesaj": "❌ HATA: Girdiğiniz PIN şifresi yanlış!"})
        
    isim = res_p[0]
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
            mesaj = f"✓ BAŞARILI!\n{isim}, GİRİŞ kaydınız alındı. Mesafe farkı: {round(mesafe, 1)} Metre."
    else:
        if not acik_kayit:
            mesaj = f"Aktif giriş kaydınız bulunamadı, {isim}!"
        else:
            kayit_id, giris_saati_str = acik_kayit
            giris_zamani = datetime.strptime(f"{bugun} {giris_saati_str}", "%Y-%m-%d %H:%M:%S")
            calisilan_saat = round((simdi - giris_zamani).total_seconds() / 3600, 2)
            fazla_mesai = round(calisilan_saat - 8.0, 2) if calisilan_saat > 8.0 else 0.0
            cursor.execute("UPDATE kayitlar SET cikis_saati = ?, fazla_mesai_saati = ? WHERE id = ?", (saat_str, fazla_mesai, kayit_id))
            mesaj = f"✓ BAŞARILI!\nGüle güle {isim}, ÇIKIŞ kaydınız alındı.\nUzaklık farkı: {round(mesafe, 1)} Metre."
            
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
    return send_file(output, download_name="Sirket_QR.png", as_attachment=True)

@app.route("/p-ekle", methods=["POST"])
def personel_ekle():
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO personeller (isim, sabit_maas, pin_kodu) VALUES (?, ?, ?)", (request.form['isim'], float(request.form['sabit_maas']), request.form['pin']))
    conn.commit()
    conn.close()
    return redirect("/")

@app.route("/p-sil/<int:p_id>")
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
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE personeller SET ek_ucret = ek_ucret + ? WHERE id = ?", (float(request.form['miktar']), int(request.form['p_id'])))
    conn.commit()
    conn.close()
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
@app.route("/")
def admin_paneli():
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
        saatlik_ucret = round(sabit_maas / 225, 2)
        mesai_kazanci = round(toplam_mesai * saatlik_ucret * 1.5, 2)
        toplam_hakedis = round(sabit_maas + mesai_kazanci + ek_ucret, 2)
        
        rows += f"<tr><td><b>{isim}</b></td><td style='font-weight:bold; color:#6f42c1;'>{pin}</td><td>{sabit_maas:,.2f} TL</td><td>{saatlik_ucret:,.2f} TL</td><td>{toplam_mesai} Saat</td><td>{mesai_kazanci:,.2f} TL</td><td>{ek_ucret:,.2f} TL</td><td style='color:#28a745; font-weight:bold;'>{toplam_hakedis:,.2f} TL</td><td><form action='/ek-ucret' method='POST' style='margin:0;'><input type='hidden' name='p_id' value='{p_id}'><input type='number' name='miktar' style='width:65px; padding:4px;' placeholder='TL' required><input type='submit' value='Ekle' style='background:#28a745; color:#fff; border:none; padding:5px;'></form></td><td><a href='/p-sil/{p_id}' style='background:#dc3545; color:#fff; padding:4px 8px; border-radius:3px; text-decoration:none; font-size:12px;'>Sil</a></td></tr>"
        
    cursor.execute("SELECT k.tarih, p.isim, k.giris_saati, k.cikis_saati, k.fazla_mesai_saati FROM kayitlar k JOIN personeller p ON k.personel_id = p.id ORDER BY k.id DESC LIMIT 30")
    gecmis_raw = cursor.fetchall()
    gecmis_rows = "".join([f"<tr><td>{g}</td><td><b>{g}</b></td><td style='color:green;'>{g}</td><td>{g if g else 'İçeride'}</td><td>{g} Saat</td></tr>" for g in gecmis_raw])
    conn.close()
    
    html = f"""
    <html><head><meta charset='utf-8'><title>Yönetim Paneli</title>
    <style>body{{font-family:Segoe UI,sans-serif; background:#f4f6f9; padding:25px;}} .container{{max-width:1300px; margin:0 auto; background:#fff; padding:20px; border-radius:8px; box-shadow:0 4px 15px rgba(0,0,0,0.08);}} table{{width:100%; border-collapse:collapse; margin-top:15px; font-size:14px;}} th,td{{padding:10px; border-bottom:1px solid #dee2e6; text-align:left;}} th{{background:#212529; color:#fff;}} .form-box{{background:#e9ecef; padding:15px; border-radius:6px; display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;}} input[type=text], input[type=number]{{padding:6px; margin-right:5px; border:1px solid #ddd; border-radius:4px;}}</style>
    </head><body><div class='container'>
        <h2>📊 Şirket Yönetim Otomasyon Paneli</h2>
        <div class='form-box'>
            <form action='/p-ekle' method='POST' style='margin:0;'>
                <input type='text' name='isim' placeholder='Personel Adı' style='width:220px;' required> 
                <input type='number' step='0.01' name='sabit_maas' placeholder='Maaş' style='width:150px;' required> 
                <input type='text' name='pin' placeholder='PIN Şifre' style='width:110px;' maxlength='4' required> 
                <input type='submit' value='Personel Tanımla' style='padding:6px 15px; background:#007bff; color:#fff; border:none; cursor:pointer;'>
            </form>
            <div><a href='/ortak-qr-indir' style='padding:8px 12px; background:#6f42c1; color:#fff; text-decoration:none; font-weight:bold; border-radius:4px;'>📥 Ortak QR İndir</a></div>
        </div>
        <table><tr><th>Personel</th><th>Giriş PIN</th><th>Sabit Maaş</th><th>Saatlik Ücret</th><th>Toplam Mesai</th><th>Mesai Kazancı</th><th>Prim</th><th>Toplam Hak Edilen</th><th>Prim İşlemi</th><th>Yönetim</th></tr>{rows}</table>
    </div></body></html>
    """
    return render_template_string(html)
@app.route("/ortak-giris")
def ortak_giris():
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, isim FROM personeller ORDER BY isim ASC")
    personeller = cursor.fetchall()
    conn.close()
    options = "".join([f"<option value='{p}'>{p}</option>" for p in personeller])
    
    html = f"""
    <html><head><meta name='viewport' content='width=device-width, initial-scale=1'><title>Giriş Paneli</title>
    <style>body{{font-family:sans-serif; background:#212529; color:#fff; text-align:center; padding-top:30px;}} .card{{background:#fff; color:#000; padding:25px; margin:15px auto; max-width:400px; border-radius:12px;}} select, input, button{{width:100%; padding:14px; margin-top:15px; border-radius:6px; font-size:16px; font-weight:bold; box-sizing:border-box;}} button{{color:#fff; border:none; cursor:pointer;}} .btn-g{{background:#28a745;}} .btn-c{{background:#dc3545;}} .status{{font-size:15px; margin-top:12px; color:orange; font-weight:bold; line-height:1.4;}}</style>
    <script>
        function islemYap(islemTipi) {{
            var p_id = document.getElementById("personel_select").value;
            var pin = document.getElementById("pin_input").value;
            var st = document.getElementById("status_text");
            if(!p_id || !pin) {{ alert("Lütfen adınızı seçin ve şifrenizi girin!"); return; }}
            
            if (navigator.geolocation) {{
                st.innerText = "📡 Gerçek uydu sinyali aranıyor... Lütfen açık alanda/pencere kenarında bekleyin.";
                
                // 🔒 TAM GPS ZORUNLULUĞU (Ağ tabanlı tahmini konumu tamamen engeller)
                navigator.geolocation.getCurrentPosition(function(position) {{
                    var veri = {{
                        personel_id: p_id,
                        pin_kodu: pin,
                        islem: islemTipi,
                        enlem: position.coords.latitude,
                        boylam: position.coords.longitude
                    }};
                    
                    st.innerText = "⏳ Konum merkeze gönderiliyor...";
                    fetch('/konum-dogrula', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify(veri)
                    }})
                    .then(response => response.json())
                    .then(data => {{
                        alert(data.mesaj);
                        if(data.durum === "ok") {{ location.reload(); }}
                        st.innerText = "";
                    }});
                }}, function(error) {{
                    alert("❌ GPS Kapalı! Lütfen telefonun konum servisini açıp tarayıcıya (Chrome/Safari) izin verin.");
                    st.innerText = "";
                }}, {{ enableHighAccuracy: true, timeout: 12000, maximumAge: 0 }});
            }} else {{
                alert("Cihaz GPS desteklemiyor!");
            }}
        }}
    </script>
    </head><body><div class='card'>
        <h2 style='margin-top:0; color:#333;'>🏢 Personel Mesai Sistemi</h2>
        <select id='personel_select'><option value=''>--- Adınızı Seçin ---</option>{options}</select>
        <input type='password' id='pin_input' placeholder='4 Haneli PIN Şifreniz' maxlength='4' inputmode='numeric'>
        <button class='btn-g' onclick="islemYap('GİRİŞ')">📍 KONUMU DOĞRULA & GİRİŞ YAP</button>
        <button class='btn-c' onclick="islemYap('ÇIKIŞ')">📍 KONUMU DOĞRULA & ÇIKIŞ YAP</button>
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
    kul_enlem = float(data.get("enlem"))
    kul_boylam = float(data.get("boylam"))
    
    mesafe = mesafe_hesapla(SIRKET_ENLEM, SIRKET_BOYLAM, kul_enlem, kul_boylam)
    if mesafe > GECERLI_MESAFE_METRE:
        return jsonify({"durum": "hata", "mesaj": f"❌ İŞLEM REDDEDİLDİ!\nDükkan sınırları dışındasınız.\n\nUydunun Ölçtüğü Uzaklık: {round(mesafe, 1)} metre.\nİzin verilen maksimum sapma: {GECERLI_MESAFE_METRE} metredir.\n\n💡 İpucu: Telefonunuzun Ayarlar -> Konum kısmından 'Yüksek İsabet / Tam Konum' ayarını açıp dükkan içinde yer değiştirerek tekrar basın."})

    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("SELECT isim, pin_kodu FROM personeller WHERE id = ?", (p_id,))
    res_p = cursor.fetchone()
    
    if not res_p or str(res_p) != str(pin):
        conn.close()
        return jsonify({"durum": "hata", "mesaj": "❌ HATA: PIN şifreniz yanlış!"})
        
    isim = res_p
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
            mesaj = f"✓ BAŞARILI!\n{isim}, GİRİŞ kaydınız alındı.\nMesafe Farkı: {round(mesafe, 1)} Metre."
    else:
        if not acik_kayit:
            mesaj = f"Aktif giriş kaydınız bulunamadı, {isim}!"
        else:
            kayit_id, giris_saati_str = acik_kayit
            giris_zamani = datetime.strptime(f"{bugun} {giris_saati_str}", "%Y-%m-%d %H:%M:%S")
            calisilan_saat = round((simdi - giris_zamani).total_seconds() / 3600, 2)
            fazla_mesai = round(calisilan_saat - 8.0, 2) if calisilan_saat > 8.0 else 0.0
            cursor.execute("UPDATE kayitlar SET cikis_saati = ?, fazla_mesai_saati = ? WHERE id = ?", (saat_str, fazla_mesai, kayit_id))
            mesaj = f"✓ BAŞARILI!\nGüle güle {isim}, ÇIKIŞ kaydınız alındı.\nMesafe Farkı: {round(mesafe, 1)} Metre."
            
    conn.commit()
    conn.close()
    return jsonify({"durum": "ok", "mesaj": mesaj})

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
    return send_file(output, download_name="Sirket_QR.png", as_attachment=True)

@app.route("/p-ekle", methods=["POST"])
def p_ekle():
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO personeller (isim, sabit_maas, pin_kodu) VALUES (?, ?, ?)", (request.form['isim'], float(request.form['sabit_maas']), request.form['pin']))
    conn.commit()
    conn.close()
    return redirect("/")

@app.route("/p-sil/<int:p_id>")
def p_sil(p_id):
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM personeller WHERE id = ?", (p_id,))
    cursor.execute("DELETE FROM kayitlar WHERE personel_id = ?", (p_id,))
    conn.commit()
    conn.close()
    return redirect("/")

@app.route("/ek-ucret", methods=["POST"])
def ek_ucret():
    conn = sqlite3.connect("takip.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE personeller SET ek_ucret = ek_ucret + ? WHERE id = ?", (float(request.form['miktar']), int(request.form['p_id'])))
    conn.commit()
    conn.close()
    return redirect("/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
