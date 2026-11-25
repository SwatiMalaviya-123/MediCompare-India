'''
NPPA Regulated
'''

from datetime import date
from decimal import Decimal
import re

from selenium import webdriver # type: ignore
from selenium.webdriver.common.by import By # type: ignore
from selenium.webdriver.support.ui import WebDriverWait # type: ignore
from selenium.webdriver.support import expected_conditions as EC # type: ignore
from selenium.webdriver.common.keys import Keys # type: ignore
import time
import psycopg2 # type: ignore

start_time = time.time()

''' PostgreSQL Connection '''
conn = psycopg2.connect(
    host='localhost',
    port='5432',
    user='postgres',
    password='1234567890',
    database='medicompare'
)

cursor = conn.cursor()

options = webdriver.ChromeOptions()
# options.add_argument("--headless")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")

driver = webdriver.Chrome(options=options)

wait = WebDriverWait(driver, 20)

allowed_forms = {
    'tablet', 'capsule', 'syrup', 'suspension', 'injection',
    'cream', 'ointment', 'gel', 'drops', 'spray',
    'inhaler', 'lozenge', 'powder', 'patch', 'suppository',
    'solution', 'lotion', 'sachet'
}

search_keywords = [
    # Common Medicines
    "Dolo", "Crocin", "Calpol", "Combiflam", "Azithromycin",
    "Amoxicillin", "Cefixime", "Metformin", "Amlodipine",
    "Pantoprazole", "Omeprazole", "Levocetirizine", "Cetirizine",

    # Generic Drug Names
    "Paracetamol", "Ibuprofen", "Aceclofenac", "Diclofenac",
    "Naproxen", "Aspirin", "Pregabalin", "Gabapentin", "Atorvastatin", 
    "Rosuvastatin", "Losartan", "Telmisartan", "Thyroxine",

    # Health Conditions
    "Diabetes", "Blood Pressure", "Hypertension",
    "Heart", "Thyroid", "Fever", "Pain", "Cold", "Cough",
    "Allergy", "Acidity", "Ulcer", "Migraine",
    "Skin", "Hair", "Joint", "Arthritis", "Kidney",
    "Liver", "Eye", "Ear", "Dental", "Women", "Baby",

    # Supplement & Wellness
    "Vitamin", "Vitamin C", "Vitamin D", "Vitamin B12",
    "Calcium", "Iron", "Zinc", "Protein", "Omega 3",
    "Multivitamin", "Probiotic", "Immunity", "Nutrition",

    # Dosage Forms
    "Tablet", "Capsule", "Syrup", "Injection", "Drops",
    "Gel", "Cream", "Ointment", "Powder", "Soap",
    "Shampoo", "Lotion", "Spray", "Inhaler",

    # Ayurvedic / Herbal
    "Ayurvedic", "Herbal", "Ashwagandha", "Tulsi",
    "Aloe Vera", "Neem", "Chyawanprash",

    # OTC / Daily Use
    "Antibiotic", "Antifungal", "Antiseptic",
    "Pain Relief", "Digestive", "Sleep", "Energy",
    "Weight Gain", "Weight Loss", "Sexual Wellness",

    # Category-based broad searches
    "Medicine", "Pharma", "Healthcare", "Wellness",
    "Generic Medicine", "Surgical", "Medical Device"
] # GLUCOMETER MONITOR (SUGARCHECK ADVANCE)



try:
    url = "https://www.davaindia.com/search"

    products = set()

    for keyword in search_keywords:
        driver.get(url)

        print(f"\nSearch: {keyword}")

        search_bar = wait.until(EC.presence_of_element_located((By.TAG_NAME, "input")))

        search_bar.send_keys(keyword)
        search_bar.send_keys(Keys.ENTER)

        wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "p.line-clamp-2.text-sm.font-semibold.leading-5")))

        time.sleep(3)

        product_names = []

        products_elements = driver.find_elements(By.CSS_SELECTOR, "p.line-clamp-2.text-sm.font-semibold.leading-5")

        for product in products_elements:

            name = product.text.strip()

            if not name:
                continue

            if name not in product_names:
                product_names.append(name)

        print(f"\nTotal Products: {len(product_names)}")

        for i, product_name in enumerate(product_names):

            try:
                print(f"\nProduct: {i + 1}")

                if product_name in products:
                    print(f"Already scraped: {product_name}")
                    print("-" * 60)
                    continue

                products.add(product_name)

                # Re-find product after page reload
                product = wait.until(EC.element_to_be_clickable((By.XPATH, f"//p[contains(normalize-space(), '{product_name}')]")))

                driver.execute_script("arguments[0].click();", product)

                time.sleep(4)


                ''' MEDICINE NAME '''
                medicine_name = None

                try:
                    medicine_name = driver.find_element(By.CSS_SELECTOR, "div.text-xl.font-semibold").text.strip()
                    print(f"Medicine Name: {medicine_name}") 

                except Exception as medicine_name_error:
                    print(f"Medicine Name Error: {medicine_name_error}")
                    break

                
                ''' MARKETER NAME '''
                marketer_name = "Davaindia"

                try:
                    possible_btns = ["Manufactured By", "Seller Information", "Packed By"]
                    
                    for btn_text in possible_btns:
                        elements = driver.find_elements(By.XPATH, f"//button[contains(., '{btn_text}')]")

                        if elements:
                            btn = elements[0]
                            driver.execute_script("arguments[0].click();", btn)
                            content = wait.until(EC.visibility_of_element_located((By.XPATH, f"//button[contains(., '{btn_text}')]/following::div[1]")))
                            text = content.text.strip()
                            marketer_name = text.split("\n")[-1]
                            break
                    print(f"Marketer Name: {marketer_name}")
                
                except:
                    marketer_name = "Davaindia"
                

                ''' SALTS '''
                salt_name = ""
                salt_list = []

                try:
                    salt_elements = driver.find_elements(By.CSS_SELECTOR, "p.text-sm.font-semibold")
                    if len(salt_elements) > 1:
                        salt_name = salt_elements[1].text.strip()
                    salt_list = [s.strip() for s in salt_name.split("&") if s.strip()]
                    print(f"Salt/Composition: {salt_list}")
                
                except:
                    salt_list = []
                

                ''' PRICE '''
                price_value = None

                try:
                    price_value = driver.find_element(By.CSS_SELECTOR, "span.flex.items-center.text-2xl.font-semibold").text.strip()
                    print(f"Price: ₹{price_value.split("\n")[0]}")
                
                except Exception as price_error:
                    print(f"Price Error: {price_error}")
                    continue


                ''' FLAGS :- PRESCRIPTION REQUIRED '''
                rx = False
                prescription_elements = driver.find_elements(By.XPATH, "//div[contains(., 'Prescription Needed')]")
                rx = len(prescription_elements) > 0
                print(f"Prescription Required: {rx}")


                ''' PACK SIZE '''
                pack_text = None

                try:
                    pack = driver.find_elements(By.CSS_SELECTOR, "p.line-clamp-1.text-xs.leading-4.text-label")
                    if pack:
                        text = pack[0].text.strip()
                        parts = [size.strip() for size in text.split(" in ")]
                        pack_text = parts[0]
                    print(f"Pack Size: {pack_text}")

                except:
                    pack_text = None
                

                ''' MANUFACTURER UPSERT '''
                cursor.execute(
                    """ 
                    INSERT INTO manufacturers(
                        canonical_name
                    )
                    VALUES (%s)
                    ON CONFLICT (search_key)
                    DO UPDATE SET updated_at = NOW()
                    RETURNING manufacturer_id
                    """, (marketer_name,)
                )

                manufacturer_id = cursor.fetchone()[0]


                ''' DOSAGE FORM '''
                detected_form = "other"

                medicine_lower = medicine_name.lower()

                for form in allowed_forms:
                    if form in medicine_lower:
                        detected_form = form
                        break
                

                ''' COMPOSITION HASH '''
                composition_hash = ""

                if salt_list:
                    cleaned_salts = []  

                    for s in salt_list:
                        normalized = (s.lower().replace("(", "").replace(")", "").replace(" ", ""))
                        cleaned_salts.append(normalized)

                    cleaned_salts.sort()

                    composition_hash = "|".join(cleaned_salts)

                composition_hash += f"|{detected_form}"


                ''' COMPOSITION UPSERT '''
                cursor.execute(
                    """
                    INSERT INTO compositions(
                        composition_hash,
                        display_name,
                        dosage_form,
                        is_combination
                    )
                    VALUES(%s, %s, %s, %s)
                    ON CONFLICT (composition_hash)
                    DO UPDATE SET updated_at = NOW()
                    RETURNING composition_id
                    """, (composition_hash, 
                          ", ".join(salt_list) if salt_list else medicine_name,
                          detected_form,
                          len(salt_list) > 1)
                )

                composition_id = cursor.fetchone()[0]


                ''' SALTS UPSERT '''
                for salt_name in salt_list:
                    try:
                        cursor.execute(
                            """
                            INSERT INTO salts(
                                canonical_name
                            )
                            VALUES (%s)
                            ON CONFLICT (search_key)
                            DO UPDATE SET updated_at = NOW()
                            RETURNING salt_id
                            """, (salt_name,)
                        )              

                        salt_id = cursor.fetchone()[0]

                        cursor.execute(
                            """
                            INSERT INTO composition_salts(
                                composition_id,
                                salt_id,
                                strength_value,
                                strength_unit
                            )
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
                            """, (composition_id, salt_id, 1, "mg")
                        )
                    
                    except Exception as e:
                        conn.rollback()
                        print(f"Salt Error: {e}")
                

                ''' MEDICINE UPSERT '''
                cursor.execute(
                    """
                    INSERT INTO medicines(
                        brand_name,
                        manufacturer_id,
                        composition_id,
                        prescription_required,
                        primary_source_url,
                        status
                    )
                    VALUES (%s, %s, %s, %s, %s, 'active')
                    ON CONFLICT (brand_search_key, manufacturer_id)
                    DO UPDATE SET
                        updated_at = NOW(),
                        composition_id = EXCLUDED.composition_id,
                        prescription_required = EXCLUDED.prescription_required,
                        primary_source_url = EXCLUDED.primary_source_url
                    RETURNING medicine_id
                    """, (medicine_name, manufacturer_id, composition_id, rx, 'DavaIndia')
                )

                medicine_id = cursor.fetchone()[0]


                ''' PACK UPSERT '''
                pack_id = None

                if pack_text:
                    number_match = re.search(r'(\d+(?:\.\d+)?)', pack_text)

                    pack_size_value = (Decimal(number_match.group(1)) if number_match else Decimal("1"))

                    pack_unit = "unit"

                    if "tablet" in pack_text.lower():
                        pack_unit = "tablet"
                    elif "capsule" in pack_text.lower():
                        pack_unit = "capsule"
                    elif "ml" in pack_text.lower():
                        pack_unit = "ml"
                    elif "gm" in pack_text.lower():
                        pack_unit = "gm"
                    
                    cursor.execute(
                        """
                        INSERT INTO packs(
                            medicine_id,
                            pack_size,
                            pack_unit,
                            pack_description
                        )
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT(medicine_id, pack_size, pack_unit)
                        DO UPDATE SET updated_at = NOW()
                        RETURNING pack_id
                        """, (medicine_id, pack_size_value, pack_unit, pack_text)
                    )

                    pack_id = cursor.fetchone()[0]


                ''' PRICE INSERT '''
                if pack_id and price_value:
                    numeric_price = re.sub(r"[^\d.]", "", price_value)

                    if numeric_price:
                        cursor.execute(
                            """
                            INSERT INTO prices (
                                pack_id,
                                mrp,
                                selling_price,
                                source,
                                source_detail,
                                source_date,
                                quality_status
                            )
                            VALUES (%s, %s, %s, 'partner_feed', 'davaindia scraper', %s, 'pending')
                            """, (pack_id, Decimal(numeric_price), Decimal(numeric_price), date.today())
                        )
                
                ''' COMMIT '''
                conn.commit()
                print("Inserted/Updated Successfully")
                print("-" * 60)

                driver.back()

                time.sleep(3)

                wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "p.line-clamp-2.text-sm.font-semibold.leading-5")))

            except Exception as product_error:
                print(f"Product Error: {product_error}")

                try:
                    driver.back()
                except:
                    pass

                break

        ''' REFRESH MATERIALIZED VIEW '''
        try:
            print("\nRefreshing materialized view...")

            cursor.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY medicine_search;")

            conn.commit()

            print("Materialized view refreshed successfully")

        except Exception as e:
            conn.rollback()
            print(f"Materialized View Refresh Error: {e}")  
        

except Exception as e:
    conn.rollback()
    print(f"Fatal Error: {e}")

finally:
    cursor.close()
    conn.close()
    driver.quit()
    end_time = time.time()
    print(
        f"\nTotal Time: "
        f"{end_time - start_time:.2f} seconds"
    )