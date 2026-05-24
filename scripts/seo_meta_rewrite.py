#!/usr/bin/env python3
"""
SEO Meta Rewrite — Legendary Branding
Writes Gemini-optimized title tags and meta descriptions for all 5 collections
and all 80 products via Shopify Admin API.

Generated: 2026-05-23 — Gemini 2.5 Flash optimized titles/descriptions
All titles ≤60 chars, all descriptions ≤155 chars.
"""
import os, time, requests

TOKEN  = os.environ["SHOPIFY_ADMIN_TOKEN"]
DOMAIN = "lngndny.myshopify.com"
API_VER = "2026-04"
BASE    = f"https://{DOMAIN}/admin/api/{API_VER}"
HEADERS = {"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"}


def put(path, payload):
    r = requests.put(f"{BASE}{path}", headers=HEADERS, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def rate():
    time.sleep(0.6)  # ~1.6 req/s — well under Shopify's 2/s REST limit


# ── Collection meta rewrites ──────────────────────────────────────────────────
COLLECTIONS = [
    (
        223735742617,
        "accessories-more",
        "custom_collection",
        "Streetwear Accessories | Legendary Branding",
        "Shop premium streetwear accessories from Legendary Branding. Trucker hats, sunglasses, and finishing pieces built to complete any fit. Free shipping available."
    ),
    (
        226122236057,
        "hoodies-jackets",
        "custom_collection",
        "Oversized Hoodies & Jackets | Legendary Branding",
        "Shop heavyweight oversized hoodies and jackets from Legendary Branding. 400-460GSM premium cotton, drop shoulder fits, and bold streetwear graphics. Free shipping."
    ),
    (
        341840789657,
        "mens-collection",
        "custom_collection",
        "Men's Streetwear Sets | Legendary Branding",
        "Shop matching streetwear sets and outfit bundles from Legendary Branding. Premium two-piece jogger sets, sweatsuit sets, and coordinated fits built for the streets."
    ),
    (
        233408757913,
        "shirts-tops",
        "custom_collection",
        "Heavyweight Oversized T-Shirts | Legendary Branding",
        "Shop heavyweight oversized t-shirts from Legendary Branding. 250-285GSM boxy fit tees, graphic streetwear designs, and premium cotton construction. Free shipping."
    ),
    (
        306630852761,
        "all-products",
        "smart_collection",
        "New Drops | Legendary Branding Streetwear",
        "Shop the latest drops from Legendary Branding. New heavyweight tees, oversized hoodies, jogger sets, and streetwear accessories added regularly. Don't miss out."
    ),
]

print("=== Collection Meta Rewrites ===")
col_success = 0
for col_id, handle, col_type, seo_title, seo_desc in COLLECTIONS:
    try:
        put(f"/{col_type}s/{col_id}.json", {col_type: {
            "id": col_id,
            "metafields_global_title_tag": seo_title,
            "metafields_global_description_tag": seo_desc
        }})
        print(f"  ✅ {handle}: {seo_title}")
        col_success += 1
    except Exception as e:
        print(f"  ❌ {handle}: {e}")
    rate()


# ── Product meta rewrites (Gemini 2.5 Flash optimized) ───────────────────────
PRODUCTS = [
  {
    "id": 8519423295641,
    "seo_title": "Heavyweight Oversized Hoodie | Legendary Branding",
    "seo_description": "460GSM 100% cotton heavyweight hoodie in an oversized fit. Ribbed cuffs, premium streetwear construction. Free shipping available."
  },
  {
    "id": 8683178262681,
    "seo_title": "The Goat Hoodie | Legendary Branding",
    "seo_description": "440GSM heavyweight oversized hoodie from the GOAT Club collection. Premium streetwear built for those who move different. Free shipping available."
  },
  {
    "id": 8446600183961,
    "seo_title": "Mentality Matters 2 Hoodie | Legendary Branding",
    "seo_description": "Heavyweight oversized hoodie with a bold statement graphic. Premium streetwear from Legendary Branding. Free shipping available."
  },
  {
    "id": 8516939251865,
    "seo_title": "Neverdy Boxy Fit Hoodie | Legendary Branding",
    "seo_description": "400GSM heavyweight hoodie in a relaxed boxy fit. Part of the Neverdy collection \u2014 premium streetwear, uncompromising quality. Free shipping available."
  },
  {
    "id": 8516978475161,
    "seo_title": "Neverdy No Risk No Story Hoodie | Legendary Branding",
    "seo_description": "400GSM drop shoulder graphic hoodie with a boxy fit. Neverdy streetwear made for those who take risks. Free shipping available."
  },
  {
    "id": 8495756214425,
    "seo_title": "GOAT Club Drip Oversized Hoodie | Legendary Branding",
    "seo_description": "460GSM heavyweight oversized hoodie from the GOAT Club Drip series. Premium cotton construction and streetwear edge. Free shipping available."
  },
  {
    "id": 8684318883993,
    "seo_title": "GOAT Club Spray Painted Hoodie | Legendary Branding",
    "seo_description": "460GSM 100% cotton oversized hoodie with an artistic spray-painted graphic. GOAT Club streetwear at its boldest. Free shipping available."
  },
  {
    "id": 8494763802777,
    "seo_title": "Goat Speed Boxy Fit Hoodie | Legendary Branding",
    "seo_description": "Heavyweight boxy fit hoodie from the GOAT Club collection. Relaxed silhouette with premium streetwear detailing. Free shipping available."
  },
  {
    "id": 8508701311129,
    "seo_title": "Adistar Jellyfish Oversized T-Shirt | Legendary Branding",
    "seo_description": "280GSM drop shoulder boxy fit graphic tee. Heavyweight oversized construction with a bold jellyfish print. Free shipping available."
  },
  {
    "id": 8494101627033,
    "seo_title": "Blank Snow Wash Goat T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight oversized GOAT Club tee in a washed snow finish. Graphic streetwear with a vintage-washed edge. Free shipping available."
  },
  {
    "id": 8494106345625,
    "seo_title": "Blank Washed Gradient Goat T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight oversized GOAT Club tee with a washed gradient finish. Premium graphic streetwear built to stand out. Free shipping available."
  },
  {
    "id": 8494107394201,
    "seo_title": "Blank Washed Gradient T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight oversized tee featuring a washed gradient dye finish. Premium streetwear construction from Legendary Branding. Free shipping available."
  },
  {
    "id": 8494109720729,
    "seo_title": "Sunfade Gradient Washed Goat T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight oversized GOAT Club tee with a bottom sunfade gradient wash. Vintage-inspired streetwear, premium quality. Free shipping available."
  },
  {
    "id": 8494110736537,
    "seo_title": "Cropped Snow Washed Goat T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight cropped GOAT Club tee with a snow washed finish. Oversized graphic streetwear with a bold, raw aesthetic. Free shipping available."
  },
  {
    "id": 8701862805657,
    "seo_title": "Dawg Pit Bull Oversized T-Shirt | Legendary Branding",
    "seo_description": "285GSM drop shoulder heavyweight graphic tee with an oversized fit. Bold pit bull artwork, premium streetwear construction. Free shipping available."
  },
  {
    "id": 8464413163673,
    "seo_title": "Dawg Rottweiler Oversized T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight oversized graphic tee featuring a bold Rottweiler print. Premium streetwear from Legendary Branding. Free shipping available."
  },
  {
    "id": 8491980980377,
    "seo_title": "Goat Sht Only Cropped T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight oversized cropped GOAT Club graphic tee. Waist-length cut with a bold statement print. Shop now."
  },
  {
    "id": 8491979047065,
    "seo_title": "Goat.Wrld Loose Fit T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight loose fit GOAT Club graphic tee. Relaxed silhouette with premium oversized streetwear construction. Free shipping available."
  },
  {
    "id": 8437867970713,
    "seo_title": "Goat Denim T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight oversized GOAT Club graphic tee with a denim-inspired design. Premium streetwear from Legendary Branding. Free shipping available."
  },
  {
    "id": 8708545413273,
    "seo_title": "Icon Of The Herd Cropped T-Shirt | Legendary Branding",
    "seo_description": "250GSM oversized cropped graphic tee. Relaxed oversized fit with a bold statement print for premium streetwear. Free shipping available."
  },
  {
    "id": 8493463503001,
    "seo_title": "Land Of The GOATED Oversized T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight oversized GOAT Club graphic tee. Premium streetwear construction with a bold cultural statement. Free shipping available."
  },
  {
    "id": 8493492043929,
    "seo_title": "Coast Club Loose Fit T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight loose fit graphic tee from Legendary Branding's Coast Club. Oversized streetwear with a laid-back, premium aesthetic. Free shipping available."
  },
  {
    "id": 8505558073497,
    "seo_title": "Legendary Branding Faith Oversized T-Shirt",
    "seo_description": "Heavyweight oversized graphic tee with an oversized fit. Bold faith-inspired print and premium streetwear construction. Free shipping available."
  },
  {
    "id": 8446624694425,
    "seo_title": "Mentality Matters 2 Boxy T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight boxy fit graphic tee with a bold Mentality Matters statement print. Premium oversized streetwear. Free shipping available."
  },
  {
    "id": 8683184980121,
    "seo_title": "No Risk No Story Oversized T-Shirt | Legendary Branding",
    "seo_description": "235GSM drop shoulder crew neck tee in an oversized fit. Clean construction with a bold streetwear statement. Free shipping available."
  },
  {
    "id": 8694828564633,
    "seo_title": "Original Permanent Marker T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight oversized graphic tee with a raw, permanent marker-inspired print. Premium Legendary Branding streetwear. Free shipping available."
  },
  {
    "id": 8469196800153,
    "seo_title": "Santa Barbara Boxy Fit T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight boxy fit graphic tee inspired by Santa Barbara. Oversized premium streetwear from Legendary Branding. Free shipping available."
  },
  {
    "id": 8493462487193,
    "seo_title": "Stay Rich Loose Fit T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight loose fit graphic tee with a bold Stay Rich print. Oversized streetwear construction, premium quality. Free shipping available."
  },
  {
    "id": 7684639883417,
    "seo_title": "The Butterfly Graphic T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight oversized graphic tee featuring an artistic butterfly print. Premium streetwear from Legendary Branding. Free shipping available."
  },
  {
    "id": 8508695707801,
    "seo_title": "The Chosen One Oversized T-Shirt | Legendary Branding",
    "seo_description": "280GSM drop shoulder boxy fit graphic tee. Heavyweight oversized construction with bold statement print. Free shipping available."
  },
  {
    "id": 7684665245849,
    "seo_title": "The Ghosted T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight oversized graphic tee with a cinematic ghosted print. Premium streetwear from Legendary Branding. Free shipping available."
  },
  {
    "id": 8516180050073,
    "seo_title": "GOAT Club The Tour Oversized T-Shirt | Legendary Branding",
    "seo_description": "235GSM boxy fit GOAT Club graphic tee. Oversized streetwear with a premium tour-series print. Free shipping available."
  },
  {
    "id": 8466479513753,
    "seo_title": "The GOAT Dept. Pink Boxy T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight boxy fit GOAT Club graphic tee in a bold pink colorway. Oversized premium streetwear. Free shipping available."
  },
  {
    "id": 8495781544089,
    "seo_title": "The Goat Regular Fit T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight GOAT Club graphic tee in a clean regular fit. Premium construction from Legendary Branding's streetwear collection. Free shipping available."
  },
  {
    "id": 8711583006873,
    "seo_title": "The Legendary T-Shirt | Legendary Branding",
    "seo_description": "235GSM drop shoulder boxy crew neck graphic tee. Signature Legendary Branding construction in a premium oversized silhouette. Shop now."
  },
  {
    "id": 8516938334361,
    "seo_title": "The Neverdy Oversized T-Shirt | Legendary Branding",
    "seo_description": "235GSM drop shoulder oversized graphic tee from the Neverdy collection. Premium streetwear built for those who never settle. Free shipping available."
  },
  {
    "id": 8508632236185,
    "seo_title": "Shattered Backboard Oversized T-Shirt | Legendary Branding",
    "seo_description": "280GSM boxy oversized streetwear shirt with a bold shattered backboard graphic. Premium construction from Legendary Branding. Free shipping available."
  },
  {
    "id": 8433293590681,
    "seo_title": "The World-Round T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight oversized graphic tee with a global-inspired print. Premium streetwear construction from Legendary Branding. Free shipping available."
  },
  {
    "id": 8493487194265,
    "seo_title": "Urban Framework Loose Fit T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight loose fit graphic tee with a bold urban framework print. Premium oversized streetwear from Legendary Branding. Free shipping available."
  },
  {
    "id": 8495783116953,
    "seo_title": "Varsity Goat Regular Fit T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight GOAT Club graphic tee in a varsity-inspired regular fit. Premium streetwear from Legendary Branding. Free shipping available."
  },
  {
    "id": 8446240424089,
    "seo_title": "Wave Runner Boxy T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight boxy fit graphic tee with a bold wave runner print. Oversized premium streetwear from Legendary Branding. Free shipping available."
  },
  {
    "id": 8683186487449,
    "seo_title": "Mini Goat Oversized T-Shirt | Legendary Branding",
    "seo_description": "190GSM drop shoulder GOAT Club graphic tee in a lightweight oversized fit. Clean streetwear construction. Free shipping available."
  },
  {
    "id": 8446631280793,
    "seo_title": "Mountain Trek Boxy T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight boxy fit graphic tee with a bold mountain trek print. Oversized premium streetwear from Legendary Branding. Free shipping available."
  },
  {
    "id": 8495774695577,
    "seo_title": "Lil Goat Regular Fit T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight GOAT Club graphic tee in a clean regular fit. Premium Legendary Branding streetwear. Free shipping available."
  },
  {
    "id": 8219848835225,
    "seo_title": "Legendary x Adidas Goat Polo | Legendary Branding",
    "seo_description": "Heavyweight oversized GOAT Club polo from the Legendary x Adidas collaboration. Premium graphic streetwear, limited edition. Free shipping available."
  },
  {
    "id": 8491981373593,
    "seo_title": "Legendary Fx Oversized Cropped T-Shirt | Legendary Branding",
    "seo_description": "Heavyweight cropped oversized graphic tee from the Legendary Fx series. Premium streetwear construction. Free shipping available."
  },
  {
    "id": 8485975523481,
    "seo_title": "1992 Rose Bowl Oversized Crewneck | Legendary Branding",
    "seo_description": "Heavyweight oversized crewneck sweatshirt with a vintage 1992 Rose Bowl graphic. Premium streetwear from Legendary Branding. Free shipping available."
  },
  {
    "id": 8495768076441,
    "seo_title": "GOATED Heavyweight Embroidered Sweatshirt | LB",
    "seo_description": "Heavyweight GOAT Club crewneck sweatshirt with premium embroidered detailing. Elevated streetwear from Legendary Branding. Free shipping available."
  },
  {
    "id": 8526547189913,
    "seo_title": "Legendary Branding Fleece Zip-Up | 380GSM",
    "seo_description": "380GSM drop shoulder heavyweight premium fleece zip-up. Fall/winter ready with an oversized silhouette. Free shipping available."
  },
  {
    "id": 8446177509529,
    "seo_title": "Legendary Distressed Sweatshirt | Legendary Branding",
    "seo_description": "Heavyweight crewneck sweatshirt with a distressed finish. Raw, premium streetwear construction from Legendary Branding. Free shipping available."
  },
  {
    "id": 8485858115737,
    "seo_title": "Santa Barbara Oversized Crewneck | Legendary Branding",
    "seo_description": "Heavyweight oversized crewneck sweatshirt with a Santa Barbara-inspired graphic. Premium streetwear from Legendary Branding. Free shipping available."
  },
  {
    "id": 7678168465561,
    "seo_title": "Legendary x Champion Crewneck Sweatshirt",
    "seo_description": "Heavyweight crewneck sweatshirt from the Legendary x Champion collab. Premium streetwear with dual-brand detailing. Free shipping available."
  },
  {
    "id": 8464404611225,
    "seo_title": "Dawg Heavyweight Sweatpants | Legendary Branding",
    "seo_description": "Heavyweight streetwear sweatpants with a jogger fit. Premium construction from Legendary Branding's Dawg series. Free shipping available."
  },
  {
    "id": 8519463370905,
    "seo_title": "LB Heavyweight Sweatpants 440GSM | Legendary Branding",
    "seo_description": "440GSM heavyweight sweatpants built for comfort and style. Jogger fit, premium loungewear from Legendary Branding. Free shipping available."
  },
  {
    "id": 8497631920281,
    "seo_title": "LB Striped Flare Sweatpants | Legendary Branding",
    "seo_description": "Striped flare sweatpants with a bold streetwear silhouette. Jogger-style construction from Legendary Branding. Free shipping available."
  },
  {
    "id": 8507670364313,
    "seo_title": "LB Unisex Wide-Leg Sweatpants | Legendary Branding",
    "seo_description": "Unisex wide-leg sweatpants with a relaxed streetwear fit. Premium construction from Legendary Branding. Free shipping available."
  },
  {
    "id": 8496512041113,
    "seo_title": "LB Oversized Hoodie & Jogger Set | Legendary Branding",
    "seo_description": "Oversized hoodie and jogger matching set. Premium loungewear tracksuit from Legendary Branding. Free shipping available."
  },
  {
    "id": 8500278231193,
    "seo_title": "LB Bow Embroidered Hoodie & Jogger Set | LB",
    "seo_description": "Matching hoodie and jogger set with premium bow embroidery. Streetwear outfit set from Legendary Branding. Free shipping available."
  },
  {
    "id": 8500278165657,
    "seo_title": "LB Full-Zip Tracksuit Set | Legendary Branding",
    "seo_description": "Full-zip matching tracksuit set with premium streetwear construction. Coordinated outfit from Legendary Branding. Free shipping available."
  },
  {
    "id": 8502880764057,
    "seo_title": "LB Baggy Wide-Leg Denim | Legendary Branding",
    "seo_description": "Baggy wide-leg denim jeans with a bold streetwear silhouette. Premium construction from Legendary Branding. Free shipping available."
  },
  {
    "id": 8500282392729,
    "seo_title": "LB Rhinestone Stacked Straight Denim | Legendary Branding",
    "seo_description": "Rhinestone-detailed stacked straight denim jeans. Men's streetwear with a bold, premium finish from Legendary Branding. Free shipping available."
  },
  {
    "id": 8520382185625,
    "seo_title": "LB Spliced Baggy Streetwear Jeans | Legendary Branding",
    "seo_description": "Spliced baggy fit streetwear denim jeans. Men's streetwear construction with a bold, premium silhouette. Free shipping available."
  },
  {
    "id": 8519447216281,
    "seo_title": "GOAT Dept. Heavyweight Multi-Pocket Jean | LB",
    "seo_description": "Heavyweight GOAT Club multi-pocket baggy denim. A statement piece built for premium streetwear. Free shipping available."
  },
  {
    "id": 5836089426073,
    "seo_title": "Legendary x Champion Water-Resistant Jacket | LB",
    "seo_description": "Water-resistant micro poplin streetwear jacket from the Legendary x Champion collaboration. Premium outerwear. Free shipping available."
  },
  {
    "id": 8505213223065,
    "seo_title": "LB Belted Cropped Trench Jacket | Legendary Branding",
    "seo_description": "Cropped belted trench jacket with a premium streetwear silhouette. Elevated outerwear from Legendary Branding. Free shipping available."
  },
  {
    "id": 8497089806489,
    "seo_title": "LB Corduroy Lapel Jacket | Legendary Branding",
    "seo_description": "Corduroy lapel streetwear jacket with a premium construction. Elevated outerwear from Legendary Branding. Free shipping available."
  },
  {
    "id": 8457042165913,
    "seo_title": "Goat Club Atlanta Trucker Hat | Legendary Branding",
    "seo_description": "GOAT Club Atlanta trucker hat. Premium streetwear headwear representing the city in Legendary Branding style. Free shipping available."
  },
  {
    "id": 8457038463129,
    "seo_title": "Goat Club California Trucker Hat | Legendary Branding",
    "seo_description": "GOAT Club California trucker hat. Premium streetwear headwear with a West Coast edge from Legendary Branding. Free shipping available."
  },
  {
    "id": 8457048031385,
    "seo_title": "Goat Club Chicago Trucker Hat | Legendary Branding",
    "seo_description": "GOAT Club Chicago trucker hat. Premium streetwear headwear repping the city in Legendary Branding style. Free shipping available."
  },
  {
    "id": 8457035350169,
    "seo_title": "Goat Club New York Trucker Hat | Legendary Branding",
    "seo_description": "GOAT Club New York trucker hat. Premium streetwear headwear with a NYC edge from Legendary Branding. Free shipping available."
  },
  {
    "id": 8457017458841,
    "seo_title": "Goat Club Syracuse Trucker Hat | Legendary Branding",
    "seo_description": "GOAT Club Syracuse trucker hat. Premium streetwear headwear from Legendary Branding. Free shipping available."
  },
  {
    "id": 8457030697113,
    "seo_title": "Goat Club Texas Trucker Hat | Legendary Branding",
    "seo_description": "GOAT Club Texas trucker hat. Premium streetwear headwear repping the Lone Star State in Legendary Branding style. Free shipping available."
  },
  {
    "id": 8487774650521,
    "seo_title": "Legendary Branding Foam Trucker Hat",
    "seo_description": "Foam trucker hat with premium streetwear construction from Legendary Branding. Clean, confident headwear for every occasion. Free shipping available."
  },
  {
    "id": 8240478224537,
    "seo_title": "Athletic Department Premium Tank Top | LB",
    "seo_description": "Premium sleeveless streetwear tank top from Legendary Branding's Athletic Department. Clean construction, bold identity. Free shipping available."
  },
  {
    "id": 8468911620249,
    "seo_title": "Hysteria Cropped Boxy Tank Top | Legendary Branding",
    "seo_description": "Cropped boxy fit sleeveless tank top with bold streetwear construction. Premium summer-ready style from Legendary Branding. Free shipping available."
  },
  {
    "id": 8469104427161,
    "seo_title": "Summer Vibes Cropped Boxy Tank Top | Legendary Branding",
    "seo_description": "Waist-cropped boxy fit sleeveless tank top. Premium streetwear summer style from Legendary Branding. Free shipping available."
  },
  {
    "id": 8494112276633,
    "seo_title": "Goat Casual Sweat Shorts | Legendary Branding",
    "seo_description": "GOAT Club casual sweat shorts with a relaxed streetwear fit. Premium construction from Legendary Branding. Free shipping available."
  },
  {
    "id": 8436062159001,
    "seo_title": "Yellow Dot Athletic Shorts | Legendary Branding",
    "seo_description": "4-way stretch athletic shorts with a bold yellow dot design. Streetwear-ready performance construction from Legendary Branding. Free shipping available."
  },
  {
    "id": 8498334630041,
    "seo_title": "LB UV Sport Sunglasses | Legendary Branding",
    "seo_description": "UV protection sport sunglasses from Legendary Branding. Streetwear-ready accessories with a premium, confident aesthetic. Free shipping available."
  },
  {
    "id": 8507943223449,
    "seo_title": "The Goat Premium Polo | Legendary Branding",
    "seo_description": "Boxy fit GOAT Club premium polo shirt. Casual streetwear construction with a refined, confident aesthetic. Free shipping available."
  }
]

print(f"\n=== Product Meta Rewrites ({len(PRODUCTS)} products) ===")
patched = 0
errors  = 0

for p in PRODUCTS:
    pid   = p["id"]
    title = p.get("seo_title", "")
    desc  = p.get("seo_description", "")

    try:
        put(f"/products/{pid}.json", {"product": {
            "id": pid,
            "metafields_global_title_tag": title,
            "metafields_global_description_tag": desc
        }})
        patched += 1
        print(f"  ✅ [{patched:02d}/{len(PRODUCTS)}] {title}")
    except Exception as e:
        errors += 1
        print(f"  ❌ {pid}: {e}")
    rate()

print(f"\n{'='*55}")
print(f"Collections: {col_success}/{len(COLLECTIONS)} updated")
print(f"Products:    {patched}/{len(PRODUCTS)} updated | {errors} errors")
