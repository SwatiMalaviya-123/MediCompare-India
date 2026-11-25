from fastapi import FastAPI  # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type:ignore
import psycopg2  # type: ignore
import re

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/search")
def search(q: str, search_type: str):

    conn = psycopg2.connect(
        host="localhost",
        port="5432",
        database="medicompare",
        user="postgres",
        password="1234567890"
    )

    # SEARCH BY MEDICINE NAME
    if search_type == "medicine":
        sql = """
            WITH best_match AS (
                SELECT
                    medicine_id,
                    brand_name,
                    composition_display,
                    dosage_form,
                    manufacturer_name,
                    prescription_required,
                    nppa_regulated,
                    min_pack_mrp,
                    pack_display,
                    COALESCE(similarity(brand_name, %s), 0) AS score
                FROM medicine_search
                WHERE
                    brand_search_key LIKE make_search_key(%s) || '%%'
                    OR brand_name ILIKE '%%' || %s || '%%'
                    OR brand_name %% %s
            ),
            ranked AS (
                SELECT *,
                    ROW_NUMBER() OVER (
                        PARTITION BY medicine_id
                        ORDER BY score DESC
                    ) AS rn
                FROM best_match
            )

            SELECT
                medicine_id,
                brand_name,
                composition_display,
                dosage_form,
                manufacturer_name,
                prescription_required,
                nppa_regulated,
                min_pack_mrp,
                pack_display,
                score
            FROM ranked
            WHERE rn = 1
            ORDER BY score DESC, brand_name ASC;
        """

        params = (q, q, q, q)

    # SEARCH BY COMPOSITION
    else:
        # Extract strength + unit
        strength_match = re.search(
            r'(\d+(?:\.\d+)?)\s*(mg|ml|mcg|g)',
            q,
            re.I
        )

        strength = None
        unit = None

        if strength_match:
            strength = strength_match.group(1)
            unit = strength_match.group(2).lower()

        # Remove strength/unit from composition
        composition = re.sub(
            r'(\d+(?:\.\d+)?)\s*(mg|ml|mcg|g)',
            '',
            q,
            flags=re.I
        ).strip()

        # SQL
        sql = r"""
        WITH best_match AS (

            SELECT
                medicine_id,
                brand_name,
                composition_display,
                dosage_form,
                manufacturer_name,
                prescription_required,
                nppa_regulated,
                min_pack_mrp,
                pack_display,
                COALESCE(similarity(composition_display, %s), 0) AS score

            FROM medicine_search

            WHERE (%s IS NULL OR composition_display ~* (%s || '.*?' || %s || '\s*' || %s)) 
        ),

        ranked AS (

            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY medicine_id
                    ORDER BY score DESC
                ) AS rn

            FROM best_match
        )

        SELECT
            medicine_id,
            brand_name,
            composition_display,
            dosage_form,
            manufacturer_name,
            prescription_required,
            nppa_regulated,
            min_pack_mrp,
            pack_display,
            score

        FROM ranked

        WHERE rn = 1

        ORDER BY score DESC, brand_name ASC;
        """

        params = (
            q,
            composition,
            composition,
            strength,
            unit
        )

    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()

    results = []

    for row in rows:
        results.append({
            "medicine_id": row[0],
            "brand_name": row[1],
            "composition": row[2],
            "dosage_form": row[3],
            "manufacturer": row[4],
            "prescription_required": row[5],
            "nppa_regulated": row[6],
            "min_pack_mrp": row[7],
            "pack_display": row[8]
        })

    conn.close()

    return results


@app.get("/alternatives/{medicine_id}")
def alternatives(medicine_id: int):

    conn = psycopg2.connect(
        host="localhost",
        port="5432",
        database="medicompare",
        user="postgres",
        password="1234567890"
    )

    with conn.cursor() as cursor:

        # Get original medicine
        cursor.execute("""
            SELECT
                medicine_id,
                brand_name,
                manufacturer_name,
                composition_display,
                dosage_form,
                min_pack_mrp,
                pack_display
            FROM medicine_search
            WHERE medicine_id = %s
            LIMIT 1
        """, (medicine_id,))

        medicine = cursor.fetchone()

        if not medicine:
            return {
                "original": None,
                "alternatives": []
            }

        original = {
            "medicine_id": medicine[0],
            "brand_name": medicine[1],
            "manufacturer": medicine[2],
            "composition": medicine[3],
            "dosage_form": medicine[4],
            "min_pack_mrp": float(medicine[5]),
            "pack_display": medicine[6]
        }

        composition = medicine[3]
        dosage_form = medicine[4]
        price = medicine[5]
        pack_size = medicine[6]

        # Find cheaper alternatives
        cursor.execute("""
            SELECT
                medicine_id,
                brand_name,
                manufacturer_name,
                composition_display,
                min_pack_mrp,
                pack_display,
                dosage_form
            FROM medicine_search
            WHERE
                composition_display = %s
                AND dosage_form = %s
                AND min_pack_mrp < %s
                AND pack_display = %s
                AND medicine_id != %s
            ORDER BY min_pack_mrp ASC
            LIMIT 20
        """, (composition, dosage_form, price, pack_size, medicine_id))

        rows = cursor.fetchall()

    conn.close()

    alternatives = []

    for row in rows:
        alternatives.append({
            "medicine_id": row[0],
            "brand_name": row[1],
            "manufacturer": row[2],
            "composition": row[3],
            "min_pack_mrp": float(row[4]),
            "pack_display": row[5],
            "dosage_form": row[6]
        })

    return {
        "original": original,
        "alternatives": alternatives
    }
    