import pandas as pd  # type: ignore
import psycopg2  # type: ignore
from decimal import Decimal
from datetime import date
import re

# POSTGRES CONNECTION
conn = psycopg2.connect(
    host='localhost',
    port='5432',
    user='postgres',
    password='1234567890',
    database='medicompare'
)

cursor = conn.cursor()

# LOAD CSV
df = pd.read_csv("janaushadhi.csv")

# DOSAGE FORMS
allowed_forms = {
    'tablet', 'capsule', 'syrup', 'suspension', 'injection',
    'cream', 'ointment', 'gel', 'drops', 'spray',
    'inhaler', 'lozenge', 'powder', 'patch', 'suppository',
    'solution', 'lotion', 'sachet', 'tablets', 'capsules'
}

# LOOP
for _, row in df.iterrows():
    try:
        # CSV VALUES
        generic_name = str(row["Generic Name"]).strip()
        price = str(row["MRP"]).strip()
        pack_size = str(row["Unit Size"]).strip()

        medicine_name = generic_name
        manufacturer_name = "Jan Aushadhi"

        print(f"\nMedicine: {medicine_name}")

        # DOSAGE FORM DETECTION
        detected_form = "other"

        for form in allowed_forms:
            if form in generic_name.lower():
                detected_form = form
                break

        print(f"Dosage Form: {detected_form}")

        # STRENGTH EXTRACTION
        strength_match = re.search(
            r'(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|IU|%)',
            generic_name,
            re.IGNORECASE
        )

        strength_value = Decimal("1")
        strength_unit = "mg"

        if strength_match:
            strength_value = Decimal(strength_match.group(1))
            strength_unit = strength_match.group(2).lower()

        print(f"Strength: {strength_value} {strength_unit}")

        # SALT NAME CLEANING
        salt_name = re.sub(
            r'(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|IU|%)',
            '',
            generic_name,
            flags=re.IGNORECASE
        )

        for form in allowed_forms:
            salt_name = re.sub(
                form,
                '',
                salt_name,
                flags=re.IGNORECASE
            )

        salt_name = re.sub(r'\s+', ' ', salt_name).strip()

        print(f"Salt Name: {salt_name}")

        # MANUFACTURER UPSERT
        cursor.execute(
            """
            INSERT INTO manufacturers(
                canonical_name,
                is_generic_focused,
                is_jan_aushadhi_supplier
            )
            VALUES (%s, %s, %s)

            ON CONFLICT(search_key)
            DO UPDATE SET
                updated_at = NOW(),
                is_generic_focused = TRUE,
                is_jan_aushadhi_supplier = TRUE

            RETURNING manufacturer_id
            """,
            (
                manufacturer_name,
                True,
                True
            )
        )

        manufacturer_id = cursor.fetchone()[0]

        # SALT UPSERT
        cursor.execute(
            """
            INSERT INTO salts(
                canonical_name
            )
            VALUES (%s)

            ON CONFLICT(search_key)
            DO UPDATE SET
                updated_at = NOW()

            RETURNING salt_id
            """,
            (salt_name,)
        )

        salt_id = cursor.fetchone()[0]

        # COMPOSITION HASH
        normalized_salt = (
            salt_name.lower()
            .replace(" ", "")
            .replace("(", "")
            .replace(")", "")
        )

        composition_hash = (
            f"{normalized_salt}"
            f"-{strength_value}"
            f"-{strength_unit}"
            f"|{detected_form}"
        )

        print(f"Composition Hash: {composition_hash}")

        # COMPOSITION UPSERT
        cursor.execute(
            """
            INSERT INTO compositions(
                composition_hash,
                display_name,
                dosage_form,
                is_combination
            )
            VALUES (%s, %s, %s, %s)

            ON CONFLICT(composition_hash)
            DO UPDATE SET
                updated_at = NOW()

            RETURNING composition_id
            """,
            (
                composition_hash,
                generic_name,
                detected_form,
                False
            )
        )

        composition_id = cursor.fetchone()[0]

        # COMPOSITION SALTS
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
            """,
            (
                composition_id,
                salt_id,
                strength_value,
                strength_unit
            )
        )

        # MEDICINE UPSERT
        cursor.execute(
            """
            INSERT INTO medicines(
                brand_name,
                manufacturer_id,
                composition_id,
                prescription_required,
                primary_source_url,
                is_jan_aushadhi,
                is_generic,
                status
            )
            VALUES (
                %s, %s, %s,
                %s, %s, %s,
                %s, 'active'
            )

            ON CONFLICT (
                brand_search_key,
                manufacturer_id
            )

            DO UPDATE SET
                updated_at = NOW(),
                composition_id = EXCLUDED.composition_id,
                prescription_required = EXCLUDED.prescription_required,
                primary_source_url = EXCLUDED.primary_source_url,
                is_jan_aushadhi = TRUE,
                is_generic = TRUE

            RETURNING medicine_id
            """,
            (
                medicine_name,
                manufacturer_id,
                composition_id,
                False,
                'JanAushadhi CSV',
                True,
                True
            )
        )

        medicine_id = cursor.fetchone()[0]

        # PACK PARSING
        number_match = re.search(
            r'(\d+(?:\.\d+)?)',
            pack_size
        )

        pack_size_value = (
            Decimal(number_match.group(1))
            if number_match
            else Decimal("1")
        )

        pack_unit = "unit"

        lower_pack = pack_size.lower()

        if (
            "'" in lower_pack
            or "tab" in lower_pack
        ):
            pack_unit = "tablet"

        elif "cap" in lower_pack:
            pack_unit = "capsule"

        elif "ml" in lower_pack:
            pack_unit = "ml"

        elif "gm" in lower_pack:
            pack_unit = "gm"

        print(f"Pack: {pack_size_value} {pack_unit}")

        # PACK UPSERT
        cursor.execute(
            """
            INSERT INTO packs(
                medicine_id,
                pack_size,
                pack_unit,
                pack_description
            )
            VALUES (%s, %s, %s, %s)

            ON CONFLICT(
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
                pack_size
            )
        )

        pack_id = cursor.fetchone()[0]

        # PRICE INSERT
        numeric_price = re.sub(
            r"[^\d.]",
            "",
            price
        )

        if numeric_price:

            cursor.execute(
                """
                INSERT INTO prices(
                    pack_id,
                    mrp,
                    selling_price,
                    source,
                    source_detail,
                    source_date,
                    quality_status
                )
                VALUES(
                    %s,
                    %s,
                    %s,
                    'partner_feed',
                    'JanAushadhi CSV',
                    %s,
                    'verified'
                )
                """,
                (
                    pack_id,
                    Decimal(numeric_price),
                    Decimal(numeric_price),
                    date.today()
                )
            )

        # COMMIT
        conn.commit()
        print("Inserted Successfully")
        print("-" * 60)

    except Exception as e:
        conn.rollback()
        print(f"Error: {e}")
        print("-" * 60)

# REFRESH MATERIALIZED VIEW
try:
    print("\nRefreshing materialized view...")
    cursor.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY medicine_search;")
    conn.commit()
    print("Materialized view refreshed successfully")

except Exception as e:
    conn.rollback()
    print(f"Materialized View Refresh Error: {e}")

# CLOSE
cursor.close()
conn.close()
print("\nImport Completed")