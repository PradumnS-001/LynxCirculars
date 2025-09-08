#--- Importing necessary modules ---#
import psycopg2
from dotenv import load_dotenv
import os
import fitz
import pytesseract
from PIL import Image
import io
from datetime import date
from langchain.text_splitter import CharacterTextSplitter
import logging

#--- Loading the envoirnment variables from .env ---#
load_dotenv()
password = os.getenv("PASSWORD")
user = os.getenv("USER")
host = os.getenv("HOST")
dbname = os.getenv("DATABASE_NAME")

# to split the text before appending
splitter = CharacterTextSplitter(
    chunk_size=250,
    chunk_overlap=50,
    separators=["\n\n", "\n", ".", ",", " "]
)
logging.basicConfig(filename='app.log', level=logging.INFO)

#--- Function to create tables if they don't exist already ---#
def create_table(con, psql):
    
    try: # To catch any unexpected error
        
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
                        info TEXT[] NOT NULL,
                        
                        FOREIGN KEY (metadata_id) REFERENCES metadata(id) ON DELETE CASCADE
                    );
                    """)
        # Commits
        con.commit()
        
    # Catch error and print it
    except Exception as e:
        print(f"An error occurred: {e}")
        logging.error(f"Error : {str(e)}")
    
#--- Function to insert pdf in the database ---#
def append_data(*record):
    
    # Ensure environment variables are set
    if not all([password, user, host, dbname]):
        print("Error: Missing environment variables.")
        logging.error("The envoirnment variables are not suffecient enough")
        return
    
    # Connecting to the database
    with psycopg2.connect(dbname=dbname, user=user, password=password, host=host) as con:
        with con.cursor() as psql:
    
            # Making sure tables exist
            create_table(con=con, psql=psql)
            
            # Iterating through the record
            for item in record:
                
                try: # To catch any unexpected error
                
                    # Unpacking tuple
                    department, pdf = item
                    PATH = os.path.join("Circulars", department, pdf)
                    
                    # Check if path exists
                    if not os.path.exists(PATH):
                        print(f"PDF not found: {PATH}")
                        logging.warning(f"PDF doesn't exist: {pdf}")
                        continue
                    
                    # Parse pdf
                    text = ""
                    with fitz.open(PATH) as doc:
                        for page in doc:
                            # Extract embedded text
                            page_text = page.get_text("text").strip()
                            if page_text:
                                text += page_text + "\n"

                            # Extract inline images and OCR them
                            for img in page.get_images(full=True):
                                image_bytes = doc.extract_image(img[0])["image"]

                                pil_img = Image.open(io.BytesIO(image_bytes))
                                ocr_text = pytesseract.image_to_string(pil_img, lang="eng").strip()
                                if ocr_text:
                                    ocr_text = " ".join(ocr_text.split())
                                    text += ocr_text + "\n"
                                
                    # Check if the pdf is empty
                    text = text.strip()
                    if not text:
                        print(f"PDF {PATH} is empty")
                        logging.warning(f"Skipping empty PDF: {pdf}")
                        continue
                            
                    current_date = date.today().strftime("%Y-%m-%d")
                    chunks = splitter.split_text(text)
                    
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
                    # Appending data
                    psql.execute(meta_query, (pdf, department, current_date))
                    metadata_id = psql.fetchone()[0]
                    psql.execute(con_query, (metadata_id, chunks))
                    
                    # Commits
                    con.commit()
                    print(f"{PATH} has been appended successfully!!")
                    
                except Exception as e:
                    print(f"An error occurred: {e}")
                    logging.error(f"Error processing {pdf} from department {department}: {str(e)}")


# Main function        
def main():
    pass
        
if __name__ == "__main__":
    main()