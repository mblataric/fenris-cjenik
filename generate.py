#!/usr/bin/env python3
"""Dnevni cjenik prema Odluci o objavi cjenika (NN 101/2026).

Dohvaca proizvode iz Shopify teme (predlozak collection.cjenik), generira CSV i XML
cjenik za svaki prodajni objekt iz config.json, arhivira ih i slaze public/index.html.

Pokretanje:  python generate.py [--force] [--source datoteka.json]
"""
import argparse
import csv
import html
import io
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
ARHIVA = PUBLIC / "arhiva"
STANJE = ARHIVA / "stanje.json"

STUPCI = [
    "Naziv",
    "Šifra",
    "Marka",
    "Jedinica mjere",
    "Cijena za jedinicu mjere",
    "Maloprodajna cijena (EUR)",
    "Posebni oblik prodaje",
    "Naziv posebnog oblika prodaje",
    "Najniža cijena u zadnjih 30 dana (EUR)",
    "Sidrena cijena (EUR)",
    "Datum sidrene cijene",
    "Barkod",
    "Raspoloživost",
    "Cijena gotovina/virman (EUR)",
]
XML_POLJA = [
    "naziv", "sifra", "marka", "jedinica_mjere", "cijena_za_jedinicu_mjere",
    "maloprodajna_cijena", "posebni_oblik_prodaje", "naziv_posebnog_oblika_prodaje",
    "najniza_cijena_30_dana", "sidrena_cijena", "datum_sidrene_cijene", "barkod",
    "raspolozivost", "cijena_gotovina_virman",
]


def dohvati(url, pokusaja=4):
    zadnja = None
    for i in range(pokusaja):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "fenris-cjenik/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # mreza, JSON
            zadnja = e
            time.sleep(10 * (i + 1))
    raise RuntimeError(f"Ne mogu dohvatiti {url}: {zadnja}")


def iznos(v):
    """Decimalni zarez, bez oznake valute, prazno za None."""
    return "" if v is None else f"{v:.2f}".replace(".", ",")


def marka(p):
    t = p["title"].lower()
    if "senopex" in t:
        return "Senopex"
    if "rix" in t:
        return "RIX"
    return p.get("vendor") or ""


def naziv(p):
    vt = p.get("variant_title") or ""
    return p["title"] if vt in ("", "Default Title") else f"{p['title']} – {vt}"


def redak(p, datum_sidrenja):
    tags = [t.lower() for t in p.get("tags") or []]
    cijena = p["price"] / 100
    usporedna = (p.get("compare_at_price") or 0) / 100
    jednokratno = "jednokratno-10" in tags

    maloprodajna = round(cijena / 0.9, 2) if jednokratno else cijena
    akcija = (not jednokratno) and usporedna > cijena
    naziv_akcije = ""
    najniza = None
    if akcija:
        naziv_akcije = next((t.split(":", 1)[1].strip().capitalize() for t in p.get("tags") or []
                             if t.lower().startswith("akcija:")), "Rasprodaja")
        najniza = p.get("lowest_30_days") or cijena

    sidrena = p.get("anchor_price")
    d = p.get("anchor_date") or datum_sidrenja
    datum = datetime.strptime(d, "%Y-%m-%d").strftime("%d.%m.%Y.")

    return {
        "naziv": naziv(p),
        "sifra": p.get("sku") or str(p["variant_id"]),
        "marka": marka(p),
        "jedinica_mjere": "kom",
        "cijena_za_jedinicu_mjere": "",
        "maloprodajna_cijena": iznos(maloprodajna),
        "posebni_oblik_prodaje": "DA" if akcija else "NE",
        "naziv_posebnog_oblika_prodaje": naziv_akcije,
        "najniza_cijena_30_dana": iznos(najniza),
        "sidrena_cijena": iznos(sidrena),
        "datum_sidrene_cijene": datum if sidrena is not None else "",
        "barkod": p.get("barcode") or "",
        "raspolozivost": "dostupno" if p.get("available") else "nedostupno",
        "cijena_gotovina_virman": iznos(cijena) if jednokratno else "",
    }


def u_csv(redovi):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(STUPCI)
    for r in redovi:
        w.writerow([r[k] for k in XML_POLJA])
    return "﻿" + buf.getvalue()


def u_xml(redovi, objekt, trgovac, vrijeme):
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<cjenik trgovac="{escape(trgovac, {chr(34): "&quot;"})}" '
           f'oblik_objekta="{escape(objekt["oblik"])}" adresa="{escape(objekt["adresa"])}" '
           f'oznaka_objekta="{escape(objekt["oznaka"])}" vrijeme_objave="{vrijeme}" valuta="EUR">']
    for r in redovi:
        out.append("  <proizvod>")
        out += [f"    <{k}>{escape(r[k])}</{k}>" for k in XML_POLJA]
        out.append("  </proizvod>")
    out.append("</cjenik>")
    return "\n".join(out) + "\n"


def index_html(cfg, stanje, sada):
    rows = []
    for o in cfg["objekti"]:
        mapa = f"{o['oblik']}-{o['oznaka']}"
        arhiva = sorted((ARHIVA / mapa).glob("*.csv"), reverse=True)
        stavke = "".join(
            f'<li><a href="arhiva/{mapa}/{html.escape(f.name)}">{html.escape(f.name)}</a>'
            f' · <a href="arhiva/{mapa}/{html.escape(f.with_suffix(".xml").name)}">XML</a></li>'
            for f in arhiva)
        rows.append(f"""
<section>
  <h2>{html.escape(o['naziv'])}</h2>
  <p>Trenutačno važeći cjenik: <a href="{mapa}/cjenik.csv">CSV</a> · <a href="{mapa}/cjenik.xml">XML</a>
  <br><small>Zadnja objava: {html.escape(stanje.get(mapa, {}).get('zadnja_objava', '–'))}</small></p>
  <details><summary>Arhiva (zadnjih {cfg['zadrzi_dana']} dana)</summary><ul>{stavke}</ul></details>
</section>""")
    return f"""<!doctype html>
<html lang="hr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Cjenik – Fenris Hunting</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 16px;color:#111}}
h1{{font-size:1.5rem}}h2{{font-size:1.15rem;margin-top:2rem}}a{{color:#0b57d0}}small{{color:#555}}</style></head>
<body>
<h1>Cjenik proizvoda</h1>
<p>{html.escape(cfg['trgovac'])}.<br>
Objava cjenika u strojno čitljivom obliku prema Odluci o objavi cjenika proizvoda i usluga kao mjeri
izravne kontrole cijena (NN 101/2026). Cjenik se ažurira svaki dan prije 8:00.
Sidrena (dodatna) cijena je maloprodajna cijena na dan 10. 9. 2026.</p>
<p>Format: CSV (UTF-8, odvojeno točka-zarezom, decimalni zarez, cijene u EUR s PDV-om) i XML.
Web trgovina: <a href="{cfg['web']}">{cfg['web']}</a></p>
{''.join(rows)}
<p><small>Generirano: {sada.strftime('%d.%m.%Y. %H:%M')}</small></p>
</body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="objavi novu verziju i ako je danas već objavljena")
    ap.add_argument("--check", action="store_true", help="izlazni kod 2 ako neki proizvod nema sidrenu cijenu")
    ap.add_argument("--source", help="lokalna JSON datoteka umjesto dohvaćanja s weba (za test)")
    args = ap.parse_args()

    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    tz = ZoneInfo(cfg["vremenska_zona"])
    sada = datetime.now(tz)
    danas = sada.strftime("%Y-%m-%d")

    data = json.loads(Path(args.source).read_text(encoding="utf-8")) if args.source else dohvati(cfg["izvor"])
    proizvodi = data.get("products") or []
    if not proizvodi:
        sys.exit("GREŠKA: izvor nije vratio nijedan proizvod.")
    redovi = sorted((redak(p, cfg["datum_sidrenja"]) for p in proizvodi), key=lambda r: (r["marka"], r["naziv"]))
    bez_sidra = [r["naziv"] for r in redovi if not r["sidrena_cijena"]]

    ARHIVA.mkdir(parents=True, exist_ok=True)
    stanje = json.loads(STANJE.read_text(encoding="utf-8")) if STANJE.exists() else {}
    vrijeme_naziv = sada.strftime("%d.%m.%Y_%H-%M")
    vrijeme_iso = sada.isoformat(timespec="seconds")
    objavljeno = 0

    for o in cfg["objekti"]:
        mapa = f"{o['oblik']}-{o['oznaka']}"
        s = stanje.setdefault(mapa, {"broj_pohrane": 0})
        if s.get("datum") == danas and not args.force:
            print(f"{mapa}: danas već objavljeno ({s.get('zadnja_objava')}), preskačem.")
            continue
        s["broj_pohrane"] += 1
        ime = f"{o['oblik']}_{o['adresa']}_{o['oznaka']}_{s['broj_pohrane']:03d}_{vrijeme_naziv}"
        csv_txt, xml_txt = u_csv(redovi), u_xml(redovi, o, cfg["trgovac"], vrijeme_iso)
        for folder in (ARHIVA / mapa, PUBLIC / mapa):
            folder.mkdir(parents=True, exist_ok=True)
        (ARHIVA / mapa / f"{ime}.csv").write_text(csv_txt, encoding="utf-8")
        (ARHIVA / mapa / f"{ime}.xml").write_text(xml_txt, encoding="utf-8")
        (PUBLIC / mapa / "cjenik.csv").write_text(csv_txt, encoding="utf-8")
        (PUBLIC / mapa / "cjenik.xml").write_text(xml_txt, encoding="utf-8")
        s.update(datum=danas, zadnja_objava=sada.strftime("%d.%m.%Y. %H:%M"), datoteka=f"{ime}.csv")
        objavljeno += 1
        print(f"{mapa}: objavljeno {ime}.csv/.xml ({len(redovi)} proizvoda)")

    # arhiva: brisi starije od zadrzi_dana (datum iz naziva datoteke)
    granica = (sada - timedelta(days=cfg["zadrzi_dana"])).date()
    for f in ARHIVA.glob("*/*.*"):
        m = re.search(r"_(\d{2}\.\d{2}\.\d{4})_\d{2}-\d{2}\.(csv|xml)$", f.name)
        if m and datetime.strptime(m.group(1), "%d.%m.%Y").date() < granica:
            f.unlink()

    STANJE.write_text(json.dumps(stanje, ensure_ascii=False, indent=2), encoding="utf-8")
    (PUBLIC / "index.html").write_text(index_html(cfg, stanje, sada), encoding="utf-8")
    (PUBLIC / "CNAME").write_text(cfg["domena_cjenika"] + "\n", encoding="utf-8")
    (PUBLIC / ".nojekyll").write_text("", encoding="utf-8")

    for n in bez_sidra:
        print(f"::warning::Proizvod bez sidrene cijene (upisati metapolje custom.sidrena_cijena): {n}")
    print(f"Gotovo. Novih objava: {objavljeno}.")
    if args.check and bez_sidra:
        sys.exit(2)


if __name__ == "__main__":
    main()
