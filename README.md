# RAG PDF Database Manager 🚀

This project provides a set of Python functions to manage a vector database in Supabase (PostgreSQL with `pgvector`) for storing and querying PDF content. It's designed to be the backend for a Retrieval-Augmented Generation (RAG) system.

---

## 🗂️ File Structure

* **`append_data.py`**: This is the core library file. It contains all the functions needed to interact with the database, such as creating tables, adding new PDF data (including chunking and embedding), and deleting data.

*(You will also likely need a `main.py` or similar file to call these functions, a `requirements.txt` for dependencies like `psycopg2-binary` and `sentence-transformers`, and a `.env` file to store your database credentials.)*

---

## ⚙️ How to Use

### 1. Setup

1.  **Install Dependencies**:
    ```bash
    pip install psycopg2 psycopg2-binary python-dotenv PyMuPDF Pillow torch numpy easyocr langchain langchain-huggingface
    ```
2.  **Environment Variables**: Create a `.env` file in your root directory to store your database credentials. The script (not shown but implied) will load these.
    ```ini
    DB_NAME=your_db_name
    DB_USER=your_db_user
    PASSWORD=your_db_password
    HOST=your_db_host
    PORT=your_db_port
    ```

### 2. Basic Workflow

You can import the functions from `append_data.py` into your main script.

```python
import append_data

# 1. Define the PDF(s) you want to add
pdf_to_add = "my_new_research_paper.pdf"
# or
pdf_list = ["paper1.pdf", "manual.pdf", "report.pdf"]

# 2. Create the database tables (if they don't exist)
# Note: append_pdfs() calls this automatically
append_data.create_database()

# 3. Append the PDF(s)
# This will process, embed, and store the PDF
append_data.append_pdfs(pdf_to_add)

# 4. Delete a specific PDF
append_data.delete_data("old_paper.pdf")
# or delete multiple
append_data.delete_data(["old_paper1.pdf", "old_manual.pdf", "old_report.pdf"])

# 5. (If needed) Delete ALL data
# ⚠️ WARNING: This drops all tables!
append_data.nuke_database()
```

---

## 📚 Function Reference

Here are the main functions available in `append_data.py`:

### `create_database()`

```python
def create_database()
```

* **What it does**: Initializes the database.
* **Details**:
    * Ensures the `pgvector` extension is enabled.
    * Creates the `metadata` table (for PDF titles, dates, etc.).
    * Creates the `content` table (for text chunks and their 384-dim embeddings).
    * Sets up an `HNSW` index for fast cosine similarity searches.
    * Links `content` to `metadata` with `ON DELETE CASCADE`, so deleting a PDF title from `metadata` automatically deletes all its associated text chunks.
* It's safe to run this function multiple times; it won't duplicate tables.

### `append_pdfs(records_to_process: str | list[str])`

```python
def append_pdfs(records_to_process)
```

* **What it does**: The main function to add one or more new PDFs to the database.
* **Details**:
    * Accepts a single PDF file path (string) or a list of paths.
    * **Handles Duplicates**: Before adding, it checks for two types of duplicates:
        1.  **Name-based**: If a PDF with the same file name (case-insensitive) already exists, the old version is deleted.
        2.  **Similarity-based**: If the new PDF is found to be semantically similar (cosine similarity > 0.95) to an existing PDF, the old one is deleted to prevent redundant data.
    * Calls `create_database()` automatically.

### `delete_data(pdf_titles: str | list[str])`

```python
def delete_data(pdf_titles)
```

* **What it does**: Deletes one or more specific PDFs (and all their data) from the database.
* **Details**:
    * Accepts a single PDF title (string) or a list of titles.
    * Matching is **case-insensitive**.
    * When it deletes the entry from the `metadata` table, the `ON DELETE CASCADE` rule automatically deletes all corresponding chunks and embeddings from the `content` table.

### `nuke_database()`

```python
def nuke_database()
```

* **What it does**: ⚠️ **EXTREMELY DANGEROUS!**
* **Details**:
    * This function drops the *entire* `metadata` and `content` tables, deleting all your data.
    * Use this *only* if you want to completely reset your database from scratch.
    * "Uncontrolled Catastrophe." **Use at your own risk.**

---

## ✨ Progress So Far

* ✅ **Database Initialization**: `create_database` successfully sets up the required tables and vector extension.
* ✅ **Data Appending**: `append_pdfs` can take single or multiple files and add them.
* ✅ **Duplicate Handling**: Logic is in place (as per your description) to remove old PDFs if a new one with the same name or high semantic similarity is added.
* ✅ **Targeted Deletion**: `delete_data` correctly removes specific PDFs and their associated chunks using `CASCADE`.
* ✅ **Total Deletion**: `nuke_database` provides a "scorched earth" option to drop all tables and start over.
