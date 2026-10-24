"""Genera apps/api/app/lib/catalogo.json desde la investigación de keywords (resources/keywords-ve.csv).

Uso (desde la raíz): apps/api/.venv/bin/python apps/api/scripts/catalogo_semilla.py resources/keywords-ve.csv apps/api/app/lib/catalogo.json
"""
import csv
import hashlib
import json
import re
import sys
import unicodedata

csv_path, out_path = sys.argv[1], sys.argv[2]
with open(csv_path, encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
vol = {}
for r in rows:
    vol[r["keyword"]] = max(vol.get(r["keyword"], 0), int(r["volume"] or 0))


def v(*kws):
    return max((vol.get(k, 0) for k in kws), default=0)


def slugify(text):
    t = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")
    t = t.replace("'", "").replace("/", "-").replace('"', "")
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def short_id(slug):
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    n = int(hashlib.sha1(slug.encode()).hexdigest(), 16)
    out = ""
    for _ in range(4):
        n, i = divmod(n, len(alphabet))
        out += alphabet[i]
    return out


# ── Categorías: un nivel, el nombre que más se busca en Venezuela ─────────────────────────────
# (slug, nombre, singular, grupo, sinónimos, volumen de la cabeza)
CATS = [
    ("telefonos", "Teléfonos", "teléfono", "Tecnología", ["celulares", "smartphones"], v("teléfonos", "telefonos")),
    ("tablets", "Tablets", "tablet", "Tecnología", [], v("tablets")),
    ("laptops", "Laptops", "laptop", "Tecnología", ["portátiles", "computadoras portátiles"], v("laptops")),
    ("televisores", "Televisores", "televisor", "TV y audio", ["tv", "smart tv"], v("televisores")),
    ("consolas", "Consolas", "consola", "Tecnología", ["videojuegos"], v("consolas")),
    ("audifonos", "Audífonos", "audífono", "TV y audio", ["audifonos", "cascos"], v("audífonos")),
    ("cornetas", "Cornetas", "corneta", "TV y audio", ["parlantes", "bocinas"], v("cornetas")),
    ("impresoras", "Impresoras", "impresora", "Tecnología", [], v("impresoras")),
    ("power-bank", "Power bank", "power bank", "Tecnología", ["cargador portátil"], v("power bank")),
    ("mini-ups", "Mini UPS", "mini UPS", "Electricidad y energía", ["ups para router"], v("mini ups")),
    ("neveras", "Neveras", "nevera", "Línea blanca y cocina", ["refrigeradores"], v("neveras")),
    ("congeladores", "Congeladores", "congelador", "Línea blanca y cocina", [], v("congeladores")),
    ("cocinas", "Cocinas", "cocina", "Línea blanca y cocina", [], v("cocinas")),
    ("lavadoras", "Lavadoras", "lavadora", "Línea blanca y cocina", [], v("lavadoras")),
    ("aires-acondicionados", "Aires acondicionados", "aire acondicionado", "Línea blanca y cocina", ["aire acondicionado split"], v("aires acondicionados")),
    ("licuadoras", "Licuadoras", "licuadora", "Línea blanca y cocina", [], v("licuadoras")),
    ("freidoras-de-aire", "Freidoras de aire", "freidora de aire", "Línea blanca y cocina", [], v("freidoras de aire")),
    ("cafeteras", "Cafeteras", "cafetera", "Línea blanca y cocina", [], v("cafeteras")),
    ("tanques-de-agua", "Tanques de agua", "tanque de agua", "Ferretería", [], v("tanques de agua")),
    ("bombas-de-agua", "Bombas de agua", "bomba de agua", "Ferretería", [], v("bombas de agua")),
    ("motos", "Motos", "moto", "Vehículos", [], v("motos")),
    ("bicicletas", "Bicicletas", "bicicleta", "Vehículos", [], v("bicicletas")),
    ("cauchos", "Cauchos", "caucho", "Vehículos", ["llantas", "neumáticos"], v("cauchos")),
    ("aceite-de-motor", "Aceite de motor", "aceite de motor", "Vehículos", [], v("aceite de motor")),
    ("zapatos-deportivos", "Zapatos deportivos", "zapato deportivo", "Calzado", ["tenis", "gomas", "zapatillas"], v("zapatos deportivos")),
    ("perfumes", "Perfumes", "perfume", "Belleza y cuidado personal", [], v("perfumes")),
    ("proteina", "Proteína", "proteína", "Salud", ["suplementos"], v("proteína")),
    ("memorias-usb", "Memorias USB", "memoria USB", "Tecnología", ["pendrive"], v("memorias usb", "pendrive")),
]

# Facetas con demanda en el CSV: (categoría, atributo, valor, slug, nombre para el H1, keywords)
FACETS = [
    ("televisores", "pulgadas", "32", "32-pulgadas", "Televisores de 32 pulgadas", ["televisores de 32 pulgadas", "televisores 32 pulgadas"]),
    ("televisores", "pulgadas", "43", "43-pulgadas", "Televisores de 43 pulgadas", ["televisores de 43 pulgadas", "televisores 43 pulgadas"]),
    ("televisores", "pulgadas", "50", "50-pulgadas", "Televisores de 50 pulgadas", ["televisores de 50 pulgadas", "televisores 50 pulgadas"]),
    ("televisores", "pulgadas", "55", "55-pulgadas", "Televisores de 55 pulgadas", ["televisores de 55 pulgadas", "televisores 55 pulgadas"]),
    ("televisores", "pulgadas", "65", "65-pulgadas", "Televisores de 65 pulgadas", ["televisores de 65 pulgadas", "televisores 65 pulgadas"]),
    ("zapatos-deportivos", "genero", "dama", "dama", "Zapatos deportivos de dama", ["zapatos deportivos de dama", "zapatos deportivos de damas"]),
    ("zapatos-deportivos", "genero", "hombre", "hombre", "Zapatos deportivos de hombre", ["zapatos para hombres deportivos", "zapatos deportivos para hombre"]),
    ("bicicletas", "rin", "20", "rin-20", "Bicicletas rin 20", ["bicicletas rin 20"]),
    ("bicicletas", "rin", "26", "rin-26", "Bicicletas rin 26", ["bicicletas rin 26"]),
    ("bicicletas", "rin", "16", "rin-16", "Bicicletas rin 16", ["bicicletas rin 16"]),
    ("aires-acondicionados", "btu", "12000", "12000-btu", "Aires acondicionados de 12.000 BTU", ["aires acondicionados 12000 btu", "aire acondicionado split 12000 btu"]),
    ("tanques-de-agua", "litros", "1000", "1000-litros", "Tanques de agua de 1.000 litros", ["tanques de agua de 1000 litros", "tanques de agua 1000 litros"]),
    ("tanques-de-agua", "litros", "2000", "2000-litros", "Tanques de agua de 2.000 litros", ["tanques de agua de 2000 litros", "tanques de agua 2000 litros"]),
]

# Marcas: (slug, nombre, alias)
BRANDS = [
    ("apple", "Apple", ["iphone", "macbook", "airpods"]), ("xiaomi", "Xiaomi", ["redmi", "poco"]), ("samsung", "Samsung", []),
    ("tecno", "Tecno", []), ("infinix", "Infinix", []), ("honor", "Honor", []), ("amazon", "Amazon", []),
    ("lenovo", "Lenovo", []), ("hp", "HP", []), ("sony", "Sony", ["playstation"]), ("nintendo", "Nintendo", []),
    ("microsoft", "Microsoft", ["xbox"]), ("jbl", "JBL", []), ("epson", "Epson", []), ("tcl", "TCL", []),
    ("hisense", "Hisense", []), ("lg", "LG", []), ("hyundai", "Hyundai", []), ("haier", "Haier", []),
    ("mabe", "Mabe", []), ("whirlpool", "Whirlpool", []), ("oster", "Oster", []), ("ninja", "Ninja", []),
    ("rotoplas", "Rotoplas", []), ("pedrollo", "Pedrollo", []), ("bera", "Bera", []), ("empire", "Empire Keeway", ["keeway"]),
    ("kawasaki", "Kawasaki", []), ("gw", "GW", []), ("goodyear", "Goodyear", []), ("motul", "Motul", []),
    ("ipone", "Ipone", []), ("shell", "Shell", []), ("nike", "Nike", ["jordan"]), ("adidas", "Adidas", []),
    ("puma", "Puma", []), ("rs21", "RS21", []), ("carolina-herrera", "Carolina Herrera", []), ("afnan", "Afnan", []),
    ("perry-ellis", "Perry Ellis", []), ("le-labo", "Le Labo", []), ("optimum-nutrition", "Optimum Nutrition", []),
    ("dymatize", "Dymatize", []), ("kingston", "Kingston", []), ("sandisk", "SanDisk", []), ("anker", "Anker", []),
    ("dgk", "DGK", []), ("olax", "Olax", []), ("ninja-kitchen", "Ninja", []),
]
BRANDS = [b for b in BRANDS if b[0] != "ninja-kitchen"]

# Modelos: (nombre, marca, serie, categoría, keywords para el volumen, precio de ejemplo en USD, atributos)
P = []


def p(nombre, marca, serie, cat, kws, usd, **attrs):
    P.append((nombre, marca, serie, cat, kws, usd, attrs))


# Teléfonos
for n, u, kws in [
    ("iPhone 17", 899, ["iphone 17"]), ("iPhone 17 Pro", 1149, ["iphone 17 pro"]), ("iPhone 17 Pro Max", 1299, ["iphone 17 pro max"]),
    ("iPhone 17e", 649, ["iphone 17e"]), ("iPhone 16", 749, ["iphone 16"]), ("iPhone 16e", 579, ["iphone 16e", "iphone 16 e"]),
    ("iPhone 16 Pro Max", 1049, ["iphone 16 pro max"]), ("iPhone 15", 629, ["iphone 15"]), ("iPhone 15 Pro Max", 899, ["iphone 15 pro max"]),
    ("iPhone 14", 499, ["iphone 14"]), ("iPhone 14 Pro Max", 749, ["iphone 14 pro max"]), ("iPhone 13", 389, ["iphone 13"]),
    ("iPhone 13 Pro Max", 559, ["iphone 13 pro max", "iphone 13 pro mx"]), ("iPhone 12", 319, ["iphone 12"]), ("iPhone 11", 259, ["iphone 11"]),
]:
    p(n, "apple", "iPhone", "telefonos", kws, u)
for n, s, u, kws in [
    ("Redmi 15C", "Redmi", 139, ["redmi 15c", "redmi 15 c", "teléfonos redmi 15c"]), ("Redmi Note 15", "Redmi Note", 229, ["redmi note 15"]),
    ("Redmi Note 15 Pro", "Redmi Note", 319, ["redmi note 15 pro"]), ("Redmi 15", "Redmi", 169, ["redmi 15"]),
    ("Redmi A5", "Redmi", 89, ["redmi a5", "redmi a 5"]), ("Redmi Note 14", "Redmi Note", 189, ["redmi note 14"]),
    ("Redmi Note 14 Pro", "Redmi Note", 259, ["redmi note 14 pro"]), ("Redmi 14C", "Redmi", 119, ["redmi 14c", "redmi 14 c"]),
    ("Redmi Note 13", "Redmi Note", 159, ["redmi note 13"]), ("Redmi A7 Pro", "Redmi", 109, ["redmi a7 pro"]),
    ("Poco X7 Pro", "Poco", 299, ["teléfonos poco x7 pro", "poco x7 pro"]),
]:
    p(n, "xiaomi", s, "telefonos", kws, u)
p("Galaxy A16", "samsung", "Galaxy A", "telefonos", ["teléfonos samsung a16"], 169)
p("Galaxy A17", "samsung", "Galaxy A", "telefonos", ["teléfonos samsung a17"], 199)
p("Galaxy A07", "samsung", "Galaxy A", "telefonos", ["celulares samsung a07"], 119)
p("Tecno Spark 40", "tecno", "Spark", "telefonos", ["teléfonos tecno spark"], 129)
p("Infinix Hot 50 Pro", "infinix", "Hot", "telefonos", ["celulares infinix hot 50 pro"], 159)
p("Honor X8b", "honor", "X", "telefonos", ["celulares honor x8b"], 219)
# Tablets
p("Redmi Pad 2", "xiaomi", "Redmi Pad", "tablets", ["redmi pad 2"], 189)
p("Fire 7", "amazon", "Fire", "tablets", ["tablets amazon fire 7"], 69)
p("Fire HD 8", "amazon", "Fire", "tablets", ["tablets amazon fire 8"], 99)
p("Fire HD 10", "amazon", "Fire", "tablets", ["tablets amazon fire 10"], 149)
p("Galaxy Tab A9", "samsung", "Galaxy Tab", "tablets", ["tablets samsung galaxy"], 159)
# Laptops
p("MacBook Air M4", "apple", "MacBook Air", "laptops", ["macbook air m4"], 1099)
p("MacBook Air M5", "apple", "MacBook Air", "laptops", ["macbook air m5"], 1199)
p("MacBook Pro M5", "apple", "MacBook Pro", "laptops", ["macbook pro m5"], 1799)
p("MacBook Air M1", "apple", "MacBook Air", "laptops", ["macbook air m1"], 649)
p("ThinkPad E14", "lenovo", "ThinkPad", "laptops", ["computadoras lenovo thinkpad"], 749)
p("IdeaPad Slim 3", "lenovo", "IdeaPad", "laptops", ["laptops lenovo ideapad"], 499)
p("HP Victus 15", "hp", "Victus", "laptops", ["laptops victus"], 799)
p("HP Pavilion 15", "hp", "Pavilion", "laptops", ["laptops hp pavilion"], 649)
# Televisores
for n, m, u, pulg in [
    ("Smart TV TCL 32 pulgadas", "tcl", 159, "32"), ("Smart TV Samsung 32 pulgadas", "samsung", 199, "32"), ("Smart TV Hyundai 32 pulgadas", "hyundai", 139, "32"),
    ("Smart TV Hisense 43 pulgadas", "hisense", 249, "43"), ("Smart TV Samsung 43 pulgadas", "samsung", 299, "43"), ("Smart TV TCL 50 pulgadas", "tcl", 329, "50"),
    ("Smart TV LG 50 pulgadas", "lg", 389, "50"), ("Smart TV Samsung 55 pulgadas", "samsung", 469, "55"), ("Smart TV Hisense 55 pulgadas", "hisense", 399, "55"),
    ("Smart TV TCL 65 pulgadas", "tcl", 599, "65"),
]:
    p(n, m, "Smart TV", "televisores", [f"televisores de {pulg} pulgadas"] if m == "tcl" else [], u, pulgadas=pulg)
# Consolas
p("PlayStation 5", "sony", "PlayStation", "consolas", ["playstation 5"], 549)
p("PlayStation 5 Pro", "sony", "PlayStation", "consolas", ["playstation 5 pro", "playstation pro 5"], 799)
p("PlayStation 5 Slim", "sony", "PlayStation", "consolas", ["playstation 5 slim"], 499)
p("Nintendo Switch 2", "nintendo", "Switch", "consolas", ["nintendo switch 2", "switch nintendo 2"], 549)
p("Nintendo Switch", "nintendo", "Switch", "consolas", ["nintendo switch 1"], 329)
p("Xbox 360 Slim", "microsoft", "Xbox", "consolas", ["xbox 360 slim", "xbox 360"], 149)
# Audífonos y cornetas
p("AirPods Pro 2", "apple", "AirPods", "audifonos", ["airpods pro 2"], 219)
p("AirPods Pro 3", "apple", "AirPods", "audifonos", ["airpods pro 3"], 269)
p("AirPods 4", "apple", "AirPods", "audifonos", ["airpods 4"], 149)
p("JBL Tune 520BT", "jbl", "Tune", "audifonos", ["audífonos jbl"], 49)
p("JBL Flip 6", "jbl", "Flip", "cornetas", ["cornetas jbl"], 119)
p("JBL Charge 5", "jbl", "Charge", "cornetas", ["cornetas jbl"], 169)
p("JBL Go 4", "jbl", "Go", "cornetas", ["cornetas jbl"], 49)
# Impresoras
p("Epson L3250", "epson", "EcoTank", "impresoras", ["impresoras epson l3250", "impresoras l3250"], 229)
p("Epson L1250", "epson", "EcoTank", "impresoras", ["impresoras epson l1250"], 179)
p("Epson L3210", "epson", "EcoTank", "impresoras", ["impresoras epson l3210"], 199)
p("HP Smart Tank 580", "hp", "Smart Tank", "impresoras", ["impresoras hp smart tank 580"], 219)
p("HP LaserJet P1102w", "hp", "LaserJet", "impresoras", ["impresoras hp laserjet p1102w"], 189)
# Power bank y mini UPS
p("Power bank Anker 20.000 mAh", "anker", "PowerCore", "power-bank", ["power bank 20000 mah", "power bank of 20000mah"], 39)
p("Power bank Anker 10.000 mAh", "anker", "PowerCore", "power-bank", ["power bank 10000mah"], 25)
p("Mini UPS DGK 20.000 mAh", "dgk", "Mini UPS", "mini-ups", ["mini ups dgk 20000mah", "mini ups 20000mah"], 35)
p("Mini UPS Olax 20.000 mAh", "olax", "Mini UPS", "mini-ups", ["mini ups olax 20000mah"], 32)
# Línea blanca y cocina
p("Nevera Samsung 2 puertas 14 pies", "samsung", "Neveras", "neveras", ["neveras samsung 2 puertas"], 649)
p("Nevera Haier 19 pies", "haier", "Neveras", "neveras", ["neveras haier 19 pies"], 799)
p("Nevera Haier 12 pies", "haier", "Neveras", "neveras", ["neveras haier 12 pies"], 449)
p("Nevera Mabe 11 pies", "mabe", "Neveras", "neveras", ["neveras mabe"], 429)
p("Congelador horizontal 100 litros", "haier", "Congeladores", "congeladores", ["congeladores de 100 litros"], 229)
p("Congelador horizontal 150 litros", "haier", "Congeladores", "congeladores", ["congeladores de 150 litros"], 279)
p("Cocina Haier 4 hornillas", "haier", "Cocinas", "cocinas", ["cocinas haier 4 hornillas"], 249)
p("Cocina Haier 5 hornillas", "haier", "Cocinas", "cocinas", ["cocinas haier 5 hornillas"], 329)
p("Cocina Mabe 4 hornillas", "mabe", "Cocinas", "cocinas", ["cocinas mabe 4 hornillas"], 279)
p("Cocina Mabe 6 hornillas", "mabe", "Cocinas", "cocinas", ["cocinas mabe 6 hornillas"], 449)
p("Lavadora Whirlpool 7 kg", "whirlpool", "Lavadoras", "lavadoras", ["lavadoras de 7 kilos", "lavadoras whirlpool"], 349)
p("Lavadora Samsung 11 kg", "samsung", "Lavadoras", "lavadoras", ["lavadoras samsung"], 499)
p("Lavadora LG 13 kg", "lg", "Lavadoras", "lavadoras", ["lavadoras lg"], 579)
p("Aire acondicionado split LG 12.000 BTU", "lg", "Split", "aires-acondicionados", ["aires acondicionados lg"], 399, btu="12000")
p("Aire acondicionado split Samsung 12.000 BTU", "samsung", "Split", "aires-acondicionados", ["aires acondicionados samsung"], 429, btu="12000")
p("Aire acondicionado de ventana 12.000 BTU", "haier", "Ventana", "aires-acondicionados", ["aires acondicionados de ventana 12000 btu"], 329, btu="12000")
p("Aire acondicionado split Haier 18.000 BTU", "haier", "Split", "aires-acondicionados", ["aires acondicionados 18000 btu"], 549, btu="18000")
p("Licuadora Oster Pro 1200", "oster", "Pro", "licuadoras", ["licuadoras oster"], 89)
p("Licuadora Oster clásica 3 velocidades", "oster", "Clásica", "licuadoras", ["licuadoras oster original"], 49)
p("Licuadora Ninja Professional", "ninja", "Professional", "licuadoras", ["licuadoras ninja"], 109)
p("Licuadora Ninja Nutri Ninja", "ninja", "Nutri Ninja", "licuadoras", ["licuadoras ninja modelos"], 79)
p("Freidora de aire Ninja 5,5 L", "ninja", "Air Fryer", "freidoras-de-aire", ["freidoras de aire ninja"], 119)
p("Freidora de aire Oster 4 L", "oster", "Air Fryer", "freidoras-de-aire", ["freidoras de aire oster"], 69)
p("Cafetera Oster 12 tazas", "oster", "Cafeteras", "cafeteras", ["cafeteras oster 12 tazas", "cafeteras oster"], 39)
# Ferretería
for litros, u in [("500", 89), ("1000", 139), ("1500", 199), ("2000", 249), ("5000", 649)]:
    p(f"Tanque de agua Rotoplas {int(litros):,} litros".replace(",", "."), "rotoplas", "Tanques", "tanques-de-agua",
      [f"tanques de agua de {litros} litros", f"tanques de agua {litros} litros"], u, litros=litros)
p("Bomba de agua Pedrollo 1/2 HP", "pedrollo", "PKm", "bombas-de-agua", ["bombas de agua de 1/2 hp", "bombas de agua 1/2 hp"], 79)
p("Bomba de agua Pedrollo 1 HP", "pedrollo", "PKm", "bombas-de-agua", ["bombas de agua de 1 hp"], 119)
# Vehículos
for n, u, kws in [("Bera X1", 1150, ["motos bera x1", "motos x1 bera"]), ("Bera SBR", 1290, ["motos sbr 2025"]), ("Bera Arsen II", 1590, ["motos arsen 2"]),
                  ("Bera Cobra", 1390, ["motos bera cobra"]), ("Bera BWS", 1490, ["motos bera bws"])]:
    p(n, "bera", "Bera", "motos", kws, u)
p("Empire Keeway Horse 150", "empire", "Horse", "motos", ["motos empire keeway"], 1250)
p("Kawasaki Ninja H2R", "kawasaki", "Ninja", "motos", ["motos kawasaki ninja h2r"], 55000)
for rin, u in [("20", 129), ("26", 169), ("16", 109), ("29", 249), ("24", 159)]:
    p(f"Bicicleta montañera GW rin {rin}", "gw", "Montañera", "bicicletas", [f"bicicletas rin {rin}"], u, rin=rin)
p("Caucho de moto 90/90-18", "goodyear", "Moto", "cauchos", ["cauchos 90/90/18", "cauchos 90 90 18"], 39)
p("Caucho Goodyear 235/75 R15", "goodyear", "Wrangler", "cauchos", ["cauchos 235 75 r15"], 119)
p("Aceite Motul 20W50", "motul", "Motul", "aceite-de-motor", ["aceite motul 20w50"], 12)
p("Aceite Ipone 20W50", "ipone", "Ipone", "aceite-de-motor", ["aceite ipone 20w50"], 11)
p("Aceite Shell 20W50", "shell", "Helix", "aceite-de-motor", ["aceite shell 20w50"], 9)
p("Aceite semisintético 15W40", "shell", "Helix", "aceite-de-motor", ["aceite semisintético 15w40"], 10)
# Calzado
p("Nike Air Force 1 '07", "nike", "Air Force 1", "zapatos-deportivos", ["air force one zapatos", "zapatos air force one"], 95, genero="hombre")
p("Nike Air Force 1 '07 Dama", "nike", "Air Force 1", "zapatos-deportivos", ["zapatos nike para mujer"], 95, genero="dama")
p("Air Jordan 4 Retro", "nike", "Jordan", "zapatos-deportivos", ["zapatos retro 4", "zapatos jordan"], 189, genero="hombre")
p("Nike Revolution 7", "nike", "Revolution", "zapatos-deportivos", ["zapatos nike"], 59, genero="dama")
p("Nike Court Vision Low", "nike", "Court Vision", "zapatos-deportivos", ["zapatos nike para hombre"], 69, genero="hombre")
p("Adidas Samba OG", "adidas", "Samba", "zapatos-deportivos", ["zapatos samba", "zapatos samba adidas"], 99, genero="dama")
p("Adidas Campus 00s", "adidas", "Campus", "zapatos-deportivos", ["zapatos campus"], 99, genero="hombre")
p("Adidas Grand Court", "adidas", "Grand Court", "zapatos-deportivos", ["zapatos adidas para mujer"], 55, genero="dama")
p("Adidas Runfalcon 5", "adidas", "Runfalcon", "zapatos-deportivos", ["adidas zapatos deportivos"], 49, genero="dama")
p("Puma Smash 3.0", "puma", "Smash", "zapatos-deportivos", ["zapatos puma"], 45, genero="dama")
p("Puma Caven 2.0", "puma", "Caven", "zapatos-deportivos", ["zapatos puma hombre"], 55, genero="hombre")
p("RS21 Urban", "rs21", "RS21", "zapatos-deportivos", ["zapatos rs21"], 35, genero="hombre")
# Belleza y salud
p("212 VIP Men", "carolina-herrera", "212", "perfumes", ["perfumes 212"], 79)
p("Afnan 9 PM", "afnan", "9 PM", "perfumes", ["perfumes 9 pm"], 39)
p("Afnan 9 AM", "afnan", "9 AM", "perfumes", ["perfumes 9am"], 39)
p("360° Perry Ellis", "perry-ellis", "360°", "perfumes", ["perfumes 360 perry ellis"], 29)
p("Santal 33", "le-labo", "Santal", "perfumes", ["perfumes santal 33"], 249)
p("ISO 100 Dymatize 5 lb", "dymatize", "ISO 100", "proteina", ["proteína iso 100", "iso 100 proteína"], 89)
p("Gold Standard 100% Whey 5 lb", "optimum-nutrition", "Gold Standard", "proteina", ["proteína"], 79)
p("Pendrive Kingston 64 GB", "kingston", "DataTraveler", "memorias-usb", ["pendrive 64gb"], 8)
p("Pendrive SanDisk 128 GB", "sandisk", "Ultra", "memorias-usb", ["pendrive 128gb", "pendrive 128 gb"], 14)

cats = {c[0] for c in CATS}
brand_slugs = {b[0] for b in BRANDS}
productos = []
seen = set()
for nombre, marca, serie, cat, kws, usd, attrs in P:
    assert cat in cats, cat
    assert marca in brand_slugs, marca
    slug = slugify(nombre)
    assert slug not in seen, slug
    seen.add(slug)
    productos.append({
        "id": short_id(slug),
        "slug": slug,
        "nombre": nombre,
        "marca": marca,
        "serie": serie,
        "categoria": cat,
        "busqueda": nombre,
        "volumen": v(*kws),
        "atributos": attrs,
        "precioEjemplo": usd,
    })
ids = [x["id"] for x in productos]
assert len(ids) == len(set(ids)), "ids repetidos"

catalogo = {
    "_doc": "Catálogo semilla de usaprais (Venezuela). Lo genera apps/api/scripts/catalogo_semilla.py desde resources/keywords-ve.csv. "
            "volumen = búsquedas/mes en Google Venezuela (DataForSEO, 2026-10-24). precioEjemplo lo lee SOLO la fuente "
            "de ejemplo (sources/mock.py); los precios reales salen de search_offers.",
    "pais": "ve",
    "categorias": [
        {"slug": s, "nombre": n, "singular": sg, "grupo": g, "sinonimos": syn, "volumen": vv} for s, n, sg, g, syn, vv in CATS
    ],
    "facetas": [
        {"categoria": c, "atributo": a, "valor": val, "slug": s, "nombre": n, "volumen": v(*kws)} for c, a, val, s, n, kws in FACETS
    ],
    "marcas": [{"slug": s, "nombre": n, "alias": al, "volumen": v(s.replace("-", " "), n.lower())} for s, n, al in BRANDS],
    "productos": productos,
}
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(catalogo, f, ensure_ascii=False, indent=1)
print(f"{len(CATS)} categorías, {len(FACETS)} facetas, {len(BRANDS)} marcas, {len(productos)} productos")
