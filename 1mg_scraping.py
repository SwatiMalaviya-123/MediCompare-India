import psycopg2 # type: ignore
from selenium import webdriver # type: ignore
from selenium.webdriver.common.by import By # type: ignore
from selenium.webdriver.support.ui import WebDriverWait # type: ignore
from selenium.webdriver.support import expected_conditions as EC # type: ignore
from selenium.common.exceptions import TimeoutException # type: ignore
from decimal import Decimal
from datetime import date
import time
import re


start_time = time.time()

''' POSTGRESQL CONNECTION '''

conn = psycopg2.connect(
    host="localhost",
    port="5432",
    database="medicompare",
    user="postgres",
    password="1234567890"
)

cursor = conn.cursor()

# LOAD SCRAPED MARKETERS
cursor.execute(
    """
    SELECT marketer_url
    FROM scraped_marketers
    """
)
scraped_marketers = {row[0] for row in cursor.fetchall()}
print(f"Already scraped marketers: {len(scraped_marketers)}")


options = webdriver.ChromeOptions()

# options.add_argument("--headless")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")

driver = webdriver.Chrome(options=options)

wait = WebDriverWait(driver, 20)

marketer_set = set()

allowed_forms = {
    'tablet', 'capsule', 'syrup', 'suspension', 'injection',
    'cream', 'ointment', 'gel', 'drops', 'spray',
    'inhaler', 'lozenge', 'powder', 'patch', 'suppository',
    'solution', 'lotion', 'sachet'
}

''' SAFE PAGE LOAD '''
def safe_get(url, retries=2):
    for _ in range(retries):
        try:
            driver.get(url)
            return True
        except Exception:
            time.sleep(2)
    return False

try:
    ''' GET MARKETERS '''
    url = "https://www.1mg.com/marketers"

    driver.get(url)

    while True:
        wait.until(EC.presence_of_element_located((By.XPATH, "//div[contains(@class,'curved')]//a[contains(@href,'/marketer/')]")))

        marketers = driver.find_elements(By.XPATH, "//div[contains(@class,'curved')]//a[contains(@href,'/marketer/')]")

        for marketer in marketers:
            text = marketer.text.strip()
            href = marketer.get_attribute('href')

            if href and "/marketer/" in href:
                marketer_set.add(href)
            
        try:
            next_button_marketers = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[.//span[text()='Next']]")))

            if not next_button_marketers.is_enabled():
                break
            
            old_marketers = marketers[0]

            driver.execute_script("arguments[0].click();", next_button_marketers)

            wait.until(EC.staleness_of(old_marketers))
        
        except:
            break

    print(len(marketer_set))

    ''' MARKETER LOOP '''
    remaining_marketers = [m for m in marketer_set if m not in scraped_marketers]

    # ALL MARKETERS COMPLETED
    # START NEW SCRAPING CYCLE
    if len(remaining_marketers) == 0:
        print("\nAll marketers scraped")
        print("Starting fresh update cycle...\n")

        cursor.execute(
            """
            TRUNCATE TABLE scraped_marketers
            """
        )
        conn.commit()
        remaining_marketers = list(marketer_set)

    print(f"Remaining marketers: " f"{len(remaining_marketers)}")

    for i, marketer_url in enumerate(remaining_marketers, 1):
        print(f"\n[{i}] {marketer_url}")

        if not safe_get(marketer_url):
            continue

        product_set = set()

        try:
            wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.noLinkColor.MarketerDrugListPage__drug__CtYYv")))

            while True:
                products = driver.find_elements(By.CSS_SELECTOR, "a.noLinkColor.MarketerDrugListPage__drug__CtYYv")

                for p in products:
                    name = p.text.strip()
                    href = p.get_attribute("href")

                    if href and name:
                        if any(f in name.lower() for f in allowed_forms):
                            product_set.add((name, href))

                ''' PAGINATION '''
                try:
                    next_btn = driver.find_element(By.XPATH, "//button[.//span[text()='Next']]")

                    if not next_btn.is_enabled():
                        break

                    prev_url = driver.current_url

                    driver.execute_script("arguments[0].click();", next_btn)

                    wait.until(lambda d: d.current_url != prev_url)

                except Exception:
                    break

            ''' PRODUCT LOOP '''
            for name, link in product_set:
                print(f"\n{link}")

                if not safe_get(link):
                    continue

                wait.until(EC.presence_of_element_located((By.TAG_NAME, "h1")))

                product_url = driver.current_url

                ''' MEDICINE NAME '''
                medicine_name = None

                try:
                    medicine_name = driver.find_element(By.CSS_SELECTOR, "h1.DrugHeader__title-content___2ZaPo, h1.ProductTitle__product-title___3QMYH").text.strip()
                    print(f"Medicine Name: {medicine_name}")

                except:
                    print("Medicine Name: N/A")
                    continue

                ''' MARKETER NAME '''
                marketer_name = None

                try:
                    marketer_name = driver.find_element(By.CSS_SELECTOR, "div.DrugHeader__meta-value___vqYM0, div.ProductTitle__marketer___7Wsj9").text.strip()
                    print(f"Marketer Name: {marketer_name}")

                except:
                    marketer_name = "Unknown"

                ''' SALTS '''
                salt_list = []

                try:
                    if "/drugs/" in product_url:
                        salt = driver.find_element(By.CSS_SELECTOR, "div.saltInfo.DrugHeader__meta-value___vqYM0").text.strip()
                        salt_list = [s.strip() for s in salt.split("+")] if salt else []
                    print(f"Salt/Composition: {salt_list}")

                except:
                    print("Salt/Composition: N/A")

                ''' PRICE '''
                price_value = None

                try:
                    if "/drugs/" in product_url:
                        price = driver.find_element(By.CSS_SELECTOR, "div.DrugPriceBox__best-price___32JXw, div.DrugPriceBox__banned-container___3ngUi, div.DrugPriceBox__price___dj2lv").text.strip()

                        if ("NOT FOR SALE" not in price.upper() and "BANNED" not in price.upper()):
                            price_value = price

                    else:
                        price_element = driver.find_element(By.CSS_SELECTOR, "div.PriceDetails__discount-div___nb724")

                        price_text = price_element.text
                        match = re.search(r'(\d+(?:\.\d+)?)', price_text)

                        if match:
                            price_value = f"₹{match.group(1)}"

                    print(f"Price: {price_value}")

                    if not price_value:
                        print("Skipping product because price is missing")
                        print("-" * 60)
                        continue

                except Exception as e:
                    print("Price Error:", e)
                    print("Skipping product because price extraction failed")
                    print("-" * 60)
                    continue

                ''' FLAGS '''
                nppa = False
                rx = False

                try:
                    if "/drugs/" in product_url:
                        nppa = bool(driver.find_elements(By.CSS_SELECTOR, "div.DrugHeader__nppa_regulation___3_o8J"))
                        rx = bool(driver.find_elements(By.CSS_SELECTOR, "div.DrugHeader__prescription-req___34WVy"))

                    else:
                        nppa = bool(driver.find_elements(By.CSS_SELECTOR, "div.ProductTitle__nppa_regulation___1QntH"))
                        rx = bool(driver.find_elements(By.CSS_SELECTOR, "div.ProductTitle__prescription-req___2JsbF"))

                    print(f"NPPA Regulated: {nppa}")
                    print(f"Prescription Required: {rx}")

                except:
                    print("Flags: N/A")

                ''' PACK SIZE '''
                pack_text = None

                try:
                    if "/drugs/" in product_url:
                        pack = driver.find_elements(By.CSS_SELECTOR, "div.DrugPriceBox__quantity___2LGBX")

                    else:
                        pack = driver.find_elements(By.CSS_SELECTOR, "span.PackSizeLabel__single-packsize___3KEr_")

                    if pack:
                        pack_text = pack[0].text.strip()

                    print(f"Pack Size: {pack_text}")

                except:
                    print("Pack Size: N/A")

                ''' MANUFACTURER UPSERT '''
                cursor.execute(
                    """
                    INSERT INTO manufacturers (
                        canonical_name
                    )

                    VALUES (%s)

                    ON CONFLICT (search_key)

                    DO UPDATE SET
                        updated_at = NOW()

                    RETURNING manufacturer_id
                    """,
                    (marketer_name,)
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
                        normalized = (
                            s.lower()
                            .replace("(", "")
                            .replace(")", "")
                            .replace(" ", "")
                        )

                        cleaned_salts.append(normalized)

                    cleaned_salts.sort()

                    composition_hash = "|".join(cleaned_salts)

                composition_hash += f"|{detected_form}"

                ''' COMPOSITION UPSERT '''
                cursor.execute(
                    """
                    INSERT INTO compositions (
                        composition_hash,
                        display_name,
                        dosage_form,
                        is_combination
                    )

                    VALUES (%s, %s, %s, %s)

                    ON CONFLICT (composition_hash)

                    DO UPDATE SET
                        updated_at = NOW()

                    RETURNING composition_id
                    """,
                    (
                        composition_hash,
                        ", ".join(salt_list)
                        if salt_list else medicine_name,
                        detected_form,
                        len(salt_list) > 1
                    )
                )

                composition_id = cursor.fetchone()[0]

                ''' SALTS UPSERT ''' 
                for salt_name in salt_list:
                    try:
                        cursor.execute(
                            """
                            INSERT INTO salts (
                                canonical_name
                            )

                            VALUES (%s)

                            ON CONFLICT (search_key)

                            DO UPDATE SET
                                updated_at = NOW()

                            RETURNING salt_id
                            """,
                            (salt_name,)
                        )

                        salt_id = cursor.fetchone()[0]

                        cursor.execute(
                            """
                            INSERT INTO composition_salts (
                                composition_id,
                                salt_id,
                                strength_value,
                                strength_unit
                            )

                            VALUES (%s, %s, %s, %s)

                            ON CONFLICT DO NOTHING
                            """,
                            (
                                composition_id,
                                salt_id,
                                1,
                                "mg"
                            )
                        )

                    except Exception as e:

                        conn.rollback()

                        print("Salt Error:", e)

                ''' MEDICINE UPSERT '''
                cursor.execute(
                    """
                    INSERT INTO medicines (
                        brand_name,
                        manufacturer_id,
                        composition_id,
                        prescription_required,
                        nppa_regulated,
                        primary_source_url,
                        status
                    )

                    VALUES (
                        %s, %s, %s,
                        %s, %s, %s,
                        'active'
                    )

                    ON CONFLICT (
                        brand_search_key,
                        manufacturer_id
                    )

                    DO UPDATE SET
                        updated_at = NOW(),
                        composition_id = EXCLUDED.composition_id,
                        prescription_required = EXCLUDED.prescription_required,
                        nppa_regulated = EXCLUDED.nppa_regulated,
                        primary_source_url = EXCLUDED.primary_source_url

                    RETURNING medicine_id
                    """,
                    (
                        medicine_name,
                        manufacturer_id,
                        composition_id,
                        rx,
                        nppa,
                        product_url
                    )
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

                    cursor.execute(
                        """
                        INSERT INTO packs (
                            medicine_id,
                            pack_size,
                            pack_unit,
                            pack_description
                        )

                        VALUES (%s, %s, %s, %s)

                        ON CONFLICT (
                            medicine_id,
                            pack_size,
                            pack_unit
                        )

                        DO UPDATE SET
                            updated_at = NOW()

                        RETURNING pack_id
                        """,
                        (
                            medicine_id,
                            pack_size_value,
                            pack_unit,
                            pack_text
                        )
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

                            VALUES (
                                %s,
                                %s,
                                %s,
                                'partner_feed',
                                '1mg scraper',
                                %s,
                                'pending'
                            )
                            """,
                            (
                                pack_id,
                                Decimal(numeric_price),
                                Decimal(numeric_price),
                                date.today()
                            )
                        )

                ''' COMMIT '''
                conn.commit()
                print("Inserted/Updated Successfully")
                print("-" * 60)


        except TimeoutException:
            print("No product section found")
        
        # SAVE MARKETER PROGRESS
        # EVEN IF NO PRODUCTS FOUND
        try:
            cursor.execute(
                """
                INSERT INTO scraped_marketers (
                    marketer_url
                )

                VALUES (%s)

                ON CONFLICT DO NOTHING
                """,
                (marketer_url,)
            )
            conn.commit()
            print(f"Saved marketer progress: {marketer_url}")

        except Exception as e:
            conn.rollback()
            print(f"Progress Save Error: {e}")


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
    print(f"\nTotal Time: {end_time - start_time:.2f} seconds")