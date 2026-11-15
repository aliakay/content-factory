"""Rebuilds assets/geo/countries.json: every country the atlas draws, with ISO alpha-2/3, numeric id, Turkish and English
names (CLDR through babel + a few house overrides), search aliases, the home bounding box and a label point.

Not run at render time. Needs: python3 with babel, /usr/share/iso-codes (Debian `iso-codes`), node.
    python3 assets/geo/build_countries.py
The data it reads (world-atlas, Natural Earth) is already vendored here; the output is committed."""
import json, os, subprocess, sys

from babel import Locale

HERE = os.path.dirname(os.path.abspath(__file__))
TR, EN = Locale("tr").territories, Locale("en").territories
# house names: short, what a narrator says (CLDR's "Kongo - Kinşasa" / "Hong Kong SAR China" read badly on screen)
NAMES = {
    "US": ("Amerika Birleşik Devletleri", "United States"), "GB": ("Birleşik Krallık", "United Kingdom"),
    "CD": ("Kongo Demokratik Cumhuriyeti", "DR Congo"), "CG": ("Kongo Cumhuriyeti", "Congo"),
    "MM": ("Myanmar", "Myanmar"), "CV": ("Yeşil Burun", "Cape Verde"), "PS": ("Filistin", "Palestine"),
    "HK": ("Hong Kong", "Hong Kong"), "MO": ("Makao", "Macao"), "CZ": ("Çekya", "Czechia"),
    "CI": ("Fildişi Sahili", "Ivory Coast"), "FK": ("Falkland Adaları", "Falkland Islands"),
    "TL": ("Doğu Timor", "East Timor"), "SZ": ("Esvatini", "Eswatini"), "KR": ("Güney Kore", "South Korea"),
    "KP": ("Kuzey Kore", "North Korea"), "RU": ("Rusya", "Russia"), "SY": ("Suriye", "Syria"), "IR": ("İran", "Iran"),
    "VN": ("Vietnam", "Vietnam"), "LA": ("Laos", "Laos"), "BO": ("Bolivya", "Bolivia"), "VE": ("Venezuela", "Venezuela"),
    "TZ": ("Tanzanya", "Tanzania"), "MD": ("Moldova", "Moldova"), "BA": ("Bosna-Hersek", "Bosnia and Herzegovina"),
    "AE": ("Birleşik Arap Emirlikleri", "United Arab Emirates"), "CF": ("Orta Afrika Cumhuriyeti", "Central African Republic"),
    "SS": ("Güney Sudan", "South Sudan"), "XK": ("Kosova", "Kosovo"), "TR": ("Türkiye", "Turkey"),
    "NL": ("Hollanda", "Netherlands"), "MK": ("Kuzey Makedonya", "North Macedonia"), "SA": ("Suudi Arabistan", "Saudi Arabia"),
    "TW": ("Tayvan", "Taiwan"), "EH": ("Batı Sahra", "Western Sahara"), "GL": ("Grönland", "Greenland"),
}
# what people type or say besides the official name (Turkish and English), searched with the same folding as the names
ALIASES = {
    "US": ["ABD", "Amerika", "USA", "America", "United States of America", "Birleşik Devletler"],
    "GB": ["İngiltere", "UK", "Great Britain", "Britain", "England", "Birleşik Krallık"], "RU": ["Russian Federation", "Rusya Federasyonu"],
    "CZ": ["Çek Cumhuriyeti", "Czech Republic"], "AE": ["BAE", "UAE", "Emirates"], "KR": ["South Korea", "Korea"],
    "KP": ["North Korea"], "MK": ["Makedonya", "Macedonia"], "SZ": ["Svaziland", "Swaziland"], "MM": ["Burma", "Birmanya"],
    "CD": ["Kongo", "DRC", "Zaire"], "CI": ["Côte d'Ivoire", "Cote d'Ivoire"], "TR": ["Turkiye", "Türkei"], "NL": ["Holland", "Netherlands"],
    "DE": ["Almanya", "Germany"], "FR": ["Fransa", "France"], "ES": ["İspanya", "Spain"], "IT": ["İtalya", "Italy"],
    "GR": ["Yunanistan", "Greece"], "EG": ["Mısır", "Egypt"], "CN": ["Çin", "China"], "JP": ["Japonya", "Japan"],
    "IN": ["Hindistan", "India"], "BR": ["Brezilya", "Brazil"], "AU": ["Avustralya", "Australia"], "CH": ["İsviçre", "Switzerland"],
    "SE": ["İsveç", "Sweden"], "NO": ["Norveç", "Norway"], "DK": ["Danimarka", "Denmark"], "AT": ["Avusturya", "Austria"],
    "BE": ["Belçika", "Belgium"], "PL": ["Polonya", "Poland"], "UA": ["Ukrayna", "Ukraine"], "AZ": ["Azerbaycan", "Azerbaijan"],
    "GE": ["Gürcistan", "Georgia"], "AM": ["Ermenistan", "Armenia"], "IQ": ["Irak", "Iraq"], "SY": ["Suriye", "Syria"],
    "PS": ["Gazze", "Gaza", "Filistin", "Palestinian Territories"], "CY": ["Kıbrıs", "Cyprus", "KKTC"], "BG": ["Bulgaristan", "Bulgaria"],
    "RO": ["Romanya", "Romania"], "HU": ["Macaristan", "Hungary"], "HR": ["Hırvatistan", "Croatia"], "RS": ["Sırbistan", "Serbia"],
    "AL": ["Arnavutluk", "Albania"], "SA": ["Suudi Arabistan", "Saudi Arabia"], "IL": ["İsrail", "Israel"], "LB": ["Lübnan", "Lebanon"],
    "JO": ["Ürdün", "Jordan"], "KW": ["Kuveyt", "Kuwait"], "LY": ["Libya"], "DZ": ["Cezayir", "Algeria"], "MA": ["Fas", "Morocco"],
    "TN": ["Tunus", "Tunisia"], "ZA": ["Güney Afrika", "South Africa"], "ET": ["Etiyopya", "Ethiopia"], "KZ": ["Kazakistan", "Kazakhstan"],
    "UZ": ["Özbekistan", "Uzbekistan"], "TM": ["Türkmenistan", "Turkmenistan"], "KG": ["Kırgızistan", "Kyrgyzstan"], "AF": ["Afganistan", "Afghanistan"],
    "PK": ["Pakistan"], "BD": ["Bangladeş", "Bangladesh"], "ID": ["Endonezya", "Indonesia"], "TH": ["Tayland", "Thailand"], "PH": ["Filipinler", "Philippines"],
    "MX": ["Meksika", "Mexico"], "CA": ["Kanada", "Canada"], "AR": ["Arjantin", "Argentina"], "CL": ["Şili", "Chile"], "CO": ["Kolombiya", "Colombia"],
    "PE": ["Peru"], "CU": ["Küba", "Cuba"], "FI": ["Finlandiya", "Finland"], "IE": ["İrlanda", "Ireland"], "IS": ["İzlanda", "Iceland"],
    "PT": ["Portekiz", "Portugal"], "LT": ["Litvanya", "Lithuania"], "LV": ["Letonya", "Latvia"], "EE": ["Estonya", "Estonia"], "BY": ["Belarus", "Beyaz Rusya"],
    "SK": ["Slovakya", "Slovakia"], "SI": ["Slovenya", "Slovenia"], "ME": ["Karadağ", "Montenegro"], "SO": ["Somali", "Somaliland"],
    "NG": ["Nijerya", "Nigeria"], "KE": ["Kenya"], "NZ": ["Yeni Zelanda", "New Zealand"], "MN": ["Moğolistan", "Mongolia"], "NP": ["Nepal"],
    "LK": ["Sri Lanka"], "SG": ["Singapur", "Singapore"], "MY": ["Malezya", "Malaysia"], "QA": ["Katar", "Qatar"], "OM": ["Umman", "Oman"], "YE": ["Yemen"],
}


def main():
    iso = json.load(open("/usr/share/iso-codes/json/iso_3166-1.json", encoding="utf-8"))["3166-1"]
    rows = []
    for r in iso:
        a2 = r["alpha_2"]
        tr, en = NAMES.get(a2) or (TR.get(a2) or r["name"], EN.get(a2) or r["name"])
        rows.append({"id": r["numeric"], "iso2": a2, "iso3": r["alpha_3"], "tr": tr, "en": en, "alt": ALIASES.get(a2, [])})
    rows.append({"id": "383", "iso2": "XK", "iso3": "XKX", "tr": "Kosova", "en": "Kosovo", "alt": ["Kosovo"]})   # user-assigned codes
    p = subprocess.run(["node", os.path.join(HERE, "build_countries.cjs")], input=json.dumps(rows), capture_output=True, text=True)
    if p.returncode:
        sys.exit(p.stderr)
    out = []
    for r in json.loads(p.stdout):
        if not r.pop("geo"):
            continue   # a country the atlas has no shape for (Gibraltar, Tuvalu...): flags still exist, the map does not
        r["num"] = r.pop("id")
        out.append(r)
    out.sort(key=lambda r: r["iso2"])
    with open(os.path.join(HERE, "countries.json"), "w", encoding="utf-8") as f:
        f.write("[\n" + ",\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in out) + "\n]\n")
    print(len(out), "countries")


if __name__ == "__main__":
    main()
