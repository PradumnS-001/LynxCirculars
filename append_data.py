#--- Importing necessary modules ---#
import psycopg2
from psycopg2 import OperationalError
from dotenv import load_dotenv
import os
import fitz
from PIL import Image
import io
from datetime import date
import torch
import logging
import numpy as np
import easyocr
from langchain_huggingface import HuggingFaceEmbeddings

reader = easyocr.Reader(['en'], gpu=torch.cuda.is_available()) # Use GPU if available

#--- Loading environment variables from .env ---#
# Make sure your .env file has: DB_USER, DB_NAME, PASSWORD, HOST, PORT
load_dotenv()

# Sentence-Transformer
device = "cuda" if torch.cuda.is_available() else "cpu"
# Using a standard, effective model for RAG embeddings
model_name = 'sentence-transformers/all-MiniLM-L6-v2'
# Setup logging
logging.basicConfig(filename='app.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

#--- Function to check and establish connection ---#
def _check_connection_and_connect(dbname, user, password, host, port):
    """Establishes connection to the PostgreSQL database."""
    print("Connecting to database...")
    try:
        conn = psycopg2.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port
        )
        print("Connection to PostgreSQL successful!")
        logging.info("Connection to PostgreSQL successful!")
        return conn
    except OperationalError as e:
        print(f"Database connection error: {e}")
        logging.error(f"Unable to connect to PostgreSQL: {e}")
        return None


#--- Function to insert pdf data in the database ---#
def _append_data(conn, embeddings: HuggingFaceEmbeddings, *records):
    """
    Parses PDF files, creates embeddings, checks for duplicates by name
    and similarity, and appends their content to the database.
    Each PDF is processed in its own transaction.
    """

    # Iterating through the records (list of PDF filenames)
    for pdf_filename in records:

        # This outer try-except handles file I/O and parsing errors
        try:
            PATH = os.path.join("Circulars", pdf_filename)

            # Check if path exists
            if not os.path.exists(PATH):
                print(f"PDF not found: {PATH}")
                logging.warning(f"PDF doesn't exist: {PATH}")
                continue

            # Parse pdf
            print(f"Processing {PATH}...")
            full_text = "" # Renamed for clarity
            with fitz.open(PATH) as doc:
                for page in doc:
                    # Extract embedded text
                    page_text = page.get_text("text").strip()
                    if page_text:
                        full_text += page_text + "\n"

                    # Extract inline images and OCR them
                    img_list = page.get_images(full=True)
                    for _, img in enumerate(img_list):
                        xref = img[0]
                        try:
                            base_image = doc.extract_image(xref)
                            image_bytes = base_image["image"]
                            if not image_bytes:
                                logging.warning(f"No image bytes found for xref {xref} in {pdf_filename}")
                                continue

                            image = np.array(Image.open(io.BytesIO(image_bytes)))
                            ocr_results = reader.readtext(image=image, detail=0, paragraph=True) # Use paragraph=True
                            ocr_text = " ".join(ocr_results) # Join paragraphs/lines

                            if ocr_text:
                                ocr_text_cleaned = " ".join(ocr_text.split())
                                full_text += ocr_text_cleaned + "\n"

                        except Exception as ocr_e:
                            logging.warning(f"Could not OCR image xref {xref} in {pdf_filename}: {ocr_e}")
                            print(f"Warning: Could not OCR image xref {xref}: {ocr_e}")

            # Check if the pdf is empty after parsing everything
            full_text = full_text.strip()
            if not full_text:
                print(f"PDF {PATH} resulted in empty text. Skipping.")
                logging.warning(f"Skipping PDF with empty text: {pdf_filename}")
                continue

            # Generate ONE embedding for the ENTIRE text BEFORE the database transaction
            print(f"Generating single embedding for {pdf_filename}...")
            try:
                embedding_vector = embeddings.embed_query(full_text)
                embedding_string = str(embedding_vector) # Convert to string for DB
                print("Single embedding generated.")
            except Exception as embed_e:
                print(f"Error generating single embedding for {pdf_filename}: {embed_e}")
                logging.error(f"Failed to generate single embedding for {pdf_filename}: {embed_e}")
                continue # Skip this PDF if embedding fails

            # This inner try-except handles database operations for this PDF
            try:
                with conn.cursor() as cur:
                    current_date = date.today().strftime("%Y-%m-%d")
                    similarity_threshold = 0.95
                    distance_threshold = 1 - similarity_threshold # = 0.05

                    # 1. Check for duplicate filename (case-insensitive) and delete if found
                    print(f"Checking for existing entry with filename (case-insensitive): {pdf_filename}")
                    delete_name_sql = "DELETE FROM metadata WHERE lower(title) = lower(%s)"
                    cur.execute(delete_name_sql, (pdf_filename,))
                    if cur.rowcount > 0:
                        print(f"Deleted {cur.rowcount} existing metadata entry/entries with the same name.")
                        logging.warning(f"Deleted {cur.rowcount} entries due to filename conflict: {pdf_filename}")

                    # 2. Check for highly similar content (cosine similarity > threshold) and delete if found
                    print(f"Checking for existing entries with cosine similarity > {similarity_threshold}...")
                    select_similar_sql = """
                        SELECT c.metadata_id
                        FROM content c
                        WHERE c.embedding <=> %s < %s
                        LIMIT 1;
                    """
                    cur.execute(select_similar_sql, (embedding_string, distance_threshold))
                    similar_row = cur.fetchone()

                    if similar_row:
                        similar_metadata_id = similar_row[0]
                        print(f"Found highly similar content (similarity > {similarity_threshold}). Deleting old metadata entry (ID: {similar_metadata_id}).")
                        logging.warning(f"Deleting metadata ID {similar_metadata_id} due to high similarity with {pdf_filename}.")
                        delete_similar_sql = "DELETE FROM metadata WHERE id = %s"
                        cur.execute(delete_similar_sql, (similar_metadata_id,))
                        if cur.rowcount > 0:
                             print(f"Deleted similar metadata entry (ID: {similar_metadata_id}).")
                        else:
                             print(f"Warning: Tried to delete similar metadata ID {similar_metadata_id}, but it was not found (maybe already deleted by name check?).")


                    # 3. Insert new metadata (file_hash is removed)
                    print("Inserting new metadata...")
                    meta_sql = """
                    INSERT INTO metadata (title, upload_date)
                    VALUES (%s, %s)
                    RETURNING id;
                    """
                    cur.execute(meta_sql, (pdf_filename, current_date))

                    # Fetch the returned id
                    metadata_id_row = cur.fetchone()
                    if not metadata_id_row:
                         raise Exception("Failed to retrieve metadata ID after insert.")
                    metadata_id = metadata_id_row[0]
                    print(f"New metadata inserted with ID: {metadata_id}")


                    # 4. Insert the single content entry
                    print("Inserting new content...")
                    content_sql = """
                    INSERT INTO content (metadata_id, chunk_text, embedding)
                    VALUES (%s, %s, %s);
                    """
                    # Prepare the single row data as a tuple
                    data_to_insert = (metadata_id, full_text, embedding_string)

                    # Use cur.execute for a single insert
                    cur.execute(content_sql, data_to_insert)
                    print("New content inserted successfully.")

                # If all database operations for this PDF succeed, commit them
                conn.commit()
                print(f"{PATH} has been processed and appended successfully (Metadata ID: {metadata_id})!")
                logging.info(f"Successfully processed and inserted {pdf_filename} as metadata ID {metadata_id}.")

            except (Exception, psycopg2.Error) as db_error:
                print(f"Database error during transaction for {pdf_filename}: {db_error}")
                logging.error(f"Database error for {pdf_filename}: {db_error}")
                # Rollback changes for this specific PDF
                conn.rollback()
                print("Transaction rolled back.")

        except Exception as e:
            # Catches errors from file opening, parsing, embedding etc. before DB transaction
            print(f"An error occurred processing {pdf_filename}: {e}")
            logging.error(f"Outer error processing {pdf_filename}: {str(e)}")
            # No rollback needed here as DB transaction hasn't started or wasn't attempted

# === Load Environment variables ===
user = os.getenv("DB_USER")
dbname = os.getenv("DB_NAME")
password = os.getenv("PASSWORD")
host = os.getenv("HOST")
port = os.getenv("PORT")

# Check if all env vars are loaded
if not all([user, dbname, password, host, port]):
    print("Error: Missing database environment variables in .env file.")
    logging.error("Missing database environment variables.")

# --- Initialize Embeddings Model ---
print(f"Loading embedding model '{model_name}' onto device '{device}'...")
try:
    embeddings = HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={'device': device}
    )
    print("Embedding model loaded successfully.")
except Exception as e:
    print(f"Failed to load embedding model: {e}")
    logging.error(f"Failed to load embedding model '{model_name}': {e}")

#############################################################################

# To create the database tables
def create_database(*args, **kwargs):
    
    conn = _check_connection_and_connect(dbname=dbname, user=user, password=password, host=host, port=port)
    
    if not conn:
        print("Error connecting!")
        logging.info("Connection Error!")
        return
    
    sql = """
    CREATE EXTENSION IF NOT EXISTS vector;
    CREATE TABLE if not exists metadata (
        id SERIAL PRIMARY KEY,
        title VARCHAR(255) NOT NULL,
        upload_date DATE
    );
    CREATE TABLE IF NOT EXISTS content (
        id SERIAL PRIMARY KEY,
        metadata_id INTEGER REFERENCES metadata(id) ON DELETE CASCADE,
        chunk_text TEXT NOT NULL,
        embedding VECTOR(384)
    );
    CREATE INDEX IF NOT EXISTS idx_content_embedding_hnsw ON content USING HNSW (embedding vector_cosine_ops);
    """
    
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            conn.commit() # Commit the transaction
            print("Successfully Created the tables.")
            logging.info("Successfully Created the tables.")
    except (Exception, psycopg2.Error) as error:
        print("Error while creating database!")
        logging.error("Error while creating database!")
        conn.rollback()
    
# To completely delete the entire database
def nuke_database(*args, **kwargs):
    
    conn = _check_connection_and_connect(dbname=dbname, user=user, password=password, host=host, port=port)
    
    if not conn:
        print("Error connecting!")
        logging.info("Connection Error!")
        return
    
    sql = "TRUNCATE TABLE metadata CASCADE;"
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            conn.commit() # Commit the transaction
            print("Successfully truncated metadata and content tables.")
            logging.info("Truncated metadata and content tables.")
    except (Exception, psycopg2.Error) as error:
        print(f"Error while truncating database: {error}")
        logging.error(f"Error truncating database: {error}")
        conn.rollback() # Rollback on error

# To drop specific entries
def delete_data(pdf_titles, *args, **kwargs):
    
    if isinstance(pdf_titles, str):
        titles_to_delete = [pdf_titles] # Convert single string to list
    elif isinstance(pdf_titles, list[str]):
        titles_to_delete = pdf_titles
    else:
        print("Error: pdf_titles must be a string or a list of strings.")
        logging.error("Invalid type provided for pdf_titles in nuke function.")
        return
    
    conn = _check_connection_and_connect(dbname=dbname, user=user, password=password, host=host, port=port)
    
    if not conn:
        print("Error connecting!")
        logging.info("Connection Error!")
        return
    
    sql = "DELETE FROM metadata WHERE lower(title) = lower(%s);"
    total_deleted = 0

    try:
        with conn.cursor() as cur:
            for title in titles_to_delete:
                cur.execute(sql, (title,))
                deleted_count = cur.rowcount # Get number of rows affected by the last execute
                if deleted_count > 0:
                    print(f"Deleted {deleted_count} record(s) for title: {title}")
                    logging.info(f"Deleted {deleted_count} record(s) for title: {title}")
                    total_deleted += deleted_count
                else:
                    print(f"No records found for title: {title}")
                    logging.warning(f"No records found for title: {title} during nuke operation.")
            conn.commit() # Commit after processing all titles
            print(f"--- Nuke operation complete. Total records deleted: {total_deleted} ---")
    except (Exception, psycopg2.Error) as error:
        print(f"Error during nuke operation: {error}")
        logging.error(f"Error during nuke operation: {error}")
        conn.rollback()

# Main function (call this function and pass the list of pdf names)
def append_pdfs(records_to_process, *args, **kwargs):
    
    if isinstance(records_to_process, str):
        records_to_process = [records_to_process] # Convert single string to list
    elif isinstance(records_to_process, list[str]):
        records_to_process = records_to_process
    else:
        print("Error: pdf_titles must be a string or a list of strings.")
        logging.error("Invalid type provided for pdf_titles in append_pdfs function.")
        return

    # --- Connect to Database ---
    conn = _check_connection_and_connect(dbname=dbname, user=user, password=password, host=host, port=port)

    if conn:
        try:
            # Call the function with the connection, embeddings, and the list of records
            _append_data(conn, embeddings, *records_to_process)

        finally:
            # Ensure the connection is closed when done
            if conn:
                conn.close()
                print("\nPostgreSQL connection closed.")
                logging.info("PostgreSQL connection closed.")
    else:
        print("Could not establish database connection. Exiting.")
        
def main():
    pass

if __name__ == "__main__":
    main()