# Dnevni cjenik – Fenris Hunting

Objava cjenika u .csv i .xml obliku prema Odluci o objavi cjenika proizvoda i usluga (NN 101/2026).

- Javna adresa: https://cjenik.fenris-hunting.hr
- Trenutačni cjenik po objektu: `/<oblik>-<oznaka>/cjenik.csv` i `cjenik.xml`
- Arhiva (35 dana): `/arhiva/<oblik>-<oznaka>/`, naziv datoteke:
  `oblik_adresa_oznaka_brojPohrane_DD.MM.GGGG_HH-MM.csv`

## Kako radi

1. Shopify tema (predložak `templates/collection.cjenik.liquid`) na
   `https://fenris-hunting.hr/collections/all?view=cjenik` vraća JSON sa svim proizvodima,
   cijenama, dostupnošću i metapoljima `custom.sidrena_cijena`, `custom.sidrena_cijena_datum`
   i `custom.najniza_cijena_30d`.
2. GitHub Actions (`.github/workflows/cjenik.yml`) svaki dan prije 8:00 pokreće `generate.py`,
   koji generira datoteke za svaki objekt iz `config.json`, sprema ih u arhivu i objavljuje na GitHub Pages.
3. Ako neki proizvod nema sidrenu cijenu, zadnji korak radnje ne prolazi i GitHub šalje e-mail.

## Održavanje

- **Novi proizvod:** u Shopifyju upisati *Sidrena cijena* (cijena na dan prvog uvrštenja u prodaju)
  i *Sidrena cijena datum*. RIX proizvodima dodati tag `jednokratno-10`.
- **Akcija:** postaviti usporednu cijenu (compare-at) na najnižu cijenu iz zadnjih 30 dana.
  Naziv akcije u cjeniku zadaje se tagom `akcija:Naziv` (zadano: „Rasprodaja“).
- **Ručna objava:** Actions → Dnevni cjenik → Run workflow (opcija *force* za novu verziju isti dan).
- **Lokalni test:** `python3 generate.py --source primjer.json`
