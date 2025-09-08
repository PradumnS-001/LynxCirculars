#--- Importing necessary modules ---#
import psycopg2
import dotenv
import os
import PyPDF2
from datetime import date

#--- Loading the envoirnment variables from .env ---#
dotenv.load_dotenv()
password = os.getenv("PASSWORD")
user = os.getenv("USER")
host = os.getenv("HOST")
dbname = os.getenv("DB_NAME")

#--- Connecting to the database ---#
con = psycopg2.connect(dbname=dbname, user=user, password=password, host=host)
psql = con.cursor()

#--- Function to create tables if they don't exist already ---#
def create_table():
    # Creates metadata table
    psql.execute("""
                CREATE TABLE IF NOT EXISTS metadata(
                    id SERIAL PRIMARY KEY,
                    title TEXT NOT NULL,
                    department TEXT NOT NULL,
                    upload_date DATE
                );
                 """)
    # Creates content table
    psql.execute("""
                 CREATE TABLE IF NOT EXISTS content(
                    id SERIAL PRIMARY KEY,
                    metadata_id INT NOT NULL,
                    info TEXT NOT NULL,
                    
                    FOREIGN KEY (metadata_id) REFERENCES metadata(id) ON DELETE CASCADE
                );
                 """)
    # Commits
    psql.connection.commit()
    
#--- Function to insert pdf in the database ---#
def append_data(department, pdf):
    
    # Making sure tables exist
    create_table()
    
    PATH = os.path.join("Circulars", department, pdf)
    # Check if path exists
    if not os.path.exists(PATH):
        print(f"PDF not found: {PATH}")
        # Closing the connection
        psql.close()
        con.close()
        return None
    
    # Parse pdf
    text = ""
    with open(PATH, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
                
    # Check if the pdf is empty
    if not text:
        print(f"PDF {PATH} is empty")
        # Closing the connection
        psql.close()
        con.close()
        return None
            
    current_date = date.today().strftime("%Y-%m-%d")
    
    # Metadata Query
    meta_query = """
        INSERT INTO metadata (title, department, upload_date)
        VALUES (%s, %s, %s)
        RETURNING id;
    """
    
    # Content Query
    con_query = """
        INSERT INTO content (metadata_id, info)
        VALUES (%s, %s);
    """
    try: # To account for insertion errors
    
        # Appending data
        psql.execute(meta_query, (pdf, department, current_date))
        metadata_id = psql.fetchone()[0]
        psql.execute(con_query, (metadata_id, text))
        
        # Commits
        psql.connection.commit()
        print(f"{PATH} has been appended successfully!!")
    
    finally:
        
        # Closing the connection
        psql.close()
        con.close()