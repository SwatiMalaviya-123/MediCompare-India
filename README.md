# MediCompare India

MediCompare India is a medicine comparison platform that helps users search, compare, and explore alternative medicines based on composition and strength.

## Features

- Search medicines by name and composition.
- Compare medicines and their details.
- Find alternative medicines.
- Browse medicine information.
- Database-driven medicine search.

## Technologies Used

- **Backend:** Python, FastAPI
- **Frontend:** HTML, CSS, JavaScript
- **Database:** PostgreSQL
- **Data Collection:** Python Web Scraping

## Project Structure

- `main.py` – Backend application.
- `index.html` – Main frontend page.
- `style.css` – Frontend styling.
- `script.js` – Frontend functionality.
- `medicompare_schema.sql` – Database schema.
- `1mg_scraping.py` – 1mg data scraping.
- `davaindia_scraping.py` – DavaIndia data scraping.
- `janaushadhi_import.py` – Jan Aushadhi data import.

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/SwatiMalaviya-123/MediCompare-India.git
   ```

2. Navigate to the project directory:

   ```bash
   cd MediCompare-India
   ```

3. Install dependencies:

   ```bash
   pip install fastapi uvicorn psycopg2-binary
   ```

4. Configure your PostgreSQL database and environment variables.

5. Run the application:

   ```bash
   uvicorn main:app --reload
   ```

## Author

Swati Malaviya

GitHub: [SwatiMalaviya-123](https://github.com/SwatiMalaviya-123)