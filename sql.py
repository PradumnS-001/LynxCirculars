#--- Importing necessary modules ---#
from supabase import create_client, Client
from dotenv import load_dotenv
import os
import fitz
import pytesseract
from PIL import Image
import io
from datetime import date
from langchain.text_splitter import CharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
import torch
import logging

#--- Loading environment variables from .env ---#
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Sentence-Transformer
device = "cuda" if torch.cuda.is_available() else "cpu"
model_name = ""

# to split the text before appending
splitter = CharacterTextSplitter(
    chunk_size=250,
    chunk_overlap=50,
    separators=["\n\n", "\n", ".", ",", " "]
)
logging.basicConfig(filename='app.log', level=logging.INFO)


#--- Function to insert pdf in the database ---#
def append_data(*record):
    
    

    # Ensure environment variables are set
    if not all([SUPABASE_URL, SUPABASE_KEY]):
        print("Error: Missing Supabase environment variables.")
        logging.error("Supabase environment variables not found")
        return

    # Iterating through the record
    for item in record:

        try:  # To catch any unexpected error

            # Unpacking tuple
            department, pdf = item
            temp, department = department, "all_pdfs"
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
            department = temp

            # Insert into metadata
            meta_response = supabase.table("metadata").insert({
                "title": pdf,
                "department": department,
                "upload_date": current_date
            }).execute()

            if meta_response.error:
                logging.error(f"Metadata insert error: {meta_response.error}")
                continue

            metadata_id = meta_response.data[0]["id"]

            # Insert into content
            content_response = supabase.table("content").insert({
                "metadata_id": metadata_id,
                "info": chunks
            }).execute()

            if content_response.error:
                logging.error(f"Content insert error: {content_response.error}")
                continue

            print(f"{PATH} has been appended successfully!!")

        except Exception as e:
            print(f"An error occurred: {e}")
            logging.error(f"Error processing {pdf} from department {department}: {str(e)}")


# Main function        
def main():
    pass


if __name__ == "__main__":
    main()
