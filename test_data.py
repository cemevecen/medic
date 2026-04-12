"""
Test veri kaynağı — gerçekçi ilaç bilgileri
Scrape edilen ve manuel olarak oluşturulmuş veriler
"""

TEST_DRUGS = {
    "augmentin_1000mg": {
        "ticari_ad": "Augmentin 1000 mg",
        "etken_madde": "Amoksisilin trihibrat + Klavulanik asit",
        "dozaj": "1000 mg + 200 mg",
        "form": "Film kaplı tablet",
        "uretici": "GlaxoSmithKline",
        "barkod": "8470001849303",
        "kaynak": "TITCK resmi listesi",
        "aciklama": "Bel ve idrar yolu enfeksiyonları, pnömon, boğmaca tedavisi"
    },
    "parol_500mg": {
        "ticari_ad": "Parol 500 mg",
        "etken_madde": "Parasetamol",
        "dozaj": "500 mg",
        "form": "Film kaplı tablet",
        "uretici": "Atabay Kimya",
        "barkod": "8682221000047",
        "kaynak": "TITCK resmi listesi",
        "aciklama": "Ağrı ve ateş giderici. Başağrısı, diş ağrısı, kas ağrısı tedavisi"
    },
    "aspirin_500mg": {
        "ticari_ad": "Aspirin 500 mg",
        "etken_madde": "Asetilsalisilik asit",
        "dozaj": "500 mg",
        "form": "Tablet",
        "uretici": "Bayer",
        "barkod": "4001468012453",
        "kaynak": "TITCK resmi listesi",
        "aciklama": "Ağrısız ve ateş düşürücü. İltihaplanma giderici. Tromboembolik hastalıkların önlenmesi"
    },
    "ventolin_inhaler": {
        "ticari_ad": "Ventolin İnhaler",
        "etken_madde": "Salbutamol (albuterol)",
        "dozaj": "100 mcg/doz",
        "form": "Doz inhaler",
        "uretici": "GlaxoSmithKline",
        "barkod": "5000158001570",
        "kaynak": "TITCK resmi listesi",
        "aciklama": "Astım ve KOAH'ta bronşu genişletici. Krizleri gidermede kullanılır"
    },
    "omeprazol_20mg": {
        "ticari_ad": "Omeprazol 20 mg",
        "etken_madde": "Omeprazol",
        "dozaj": "20 mg",
        "form": "Kapsül",
        "uretici": "Sandoz",
        "barkod": "7613369106105",
        "kaynak": "TITCK resmi listesi",
        "aciklama": "Mide asitliğini azaltıcı. Peptik ülser, GERD tedavisi"
    },
    "metformin_500mg": {
        "ticari_ad": "Metformin 500 mg",
        "etken_madde": "Metformin hidroklorür",
        "dozaj": "500 mg",
        "form": "Tablet",
        "uretici": "Novartis",
        "barkod": "7680357490149",
        "kaynak": "TITCK resmi listesi",
        "aciklama": "Tip 2 diyabet tedavisi. Kan şekeri düzenleyici"
    },
    "amoxil_500mg": {
        "ticari_ad": "Amoxil 500 mg",
        "etken_madde": "Amoksisilin trihibrat",
        "dozaj": "500 mg",
        "form": "Kapsül",
        "uretici": "GlaxoSmithKline",
        "barkod": "5000158001587",
        "kaynak": "TITCK resmi listesi",
        "aciklama": "Antibiyotik. Enfeksiyonlara karşı etkili"
    },
    "fluconazole_150mg": {
        "ticari_ad": "Fluconazole 150 mg",
        "etken_madde": "Flukonazol",
        "dozaj": "150 mg",
        "form": "Kapsül",
        "uretici": "Pfizer",
        "barkod": "3400922104009",
        "kaynak": "TITCK resmi listesi",
        "aciklama": "Antifungal (mantarlara karşı). Kandida enfeksiyonu tedavisi"
    },
}

def get_test_drug(drug_key: str) -> dict:
    """Test veri setinden bir ilaç bilgisi döndür"""
    return TEST_DRUGS.get(drug_key, {})

def list_test_drugs() -> list:
    """Tüm test ilaç adlarını listele"""
    return list(TEST_DRUGS.keys())

def search_test_drug(query: str) -> dict:
    """Sorguya göre test ilaç ara"""
    query_lower = query.lower().strip()
    for key, drug in TEST_DRUGS.items():
        if query_lower in drug["ticari_ad"].lower() or query_lower in drug["etken_madde"].lower():
            return drug
    return {}

if __name__ == "__main__":
    print("Test Veri Seti:")
    print("-" * 80)
    for name, info in TEST_DRUGS.items():
        print(f"\n{name}:")
        for k, v in info.items():
            print(f"  {k}: {v}")
