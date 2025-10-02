import psycopg2
from psycopg2 import OperationalError
import os
from dotenv import load_dotenv

def check_connection_and_connect(dbname, user, password, host, port):
    try:
        conn = psycopg2.connect(
            dbname=dbname,
            user=user,
            password=password,
            host=host,
            port=port
        )
        print("Connection successful!")
        return conn
    except OperationalError as e:
        print(f"Error: {e}")
        print("Unable to connect to the PostgreSQL server")
        exit()

# === Load Environment variables ===
load_dotenv()
user = os.getenv("USER")
dbname = os.getenv("DB_NAME")
password = os.getenv("PASSWORD")
host = os.getenv("HOST")
port = os.getenv("PORT")
conn = check_connection_and_connect(dbname=dbname, user=user, password=password, host=host, port=port)

cur = conn.cursor()
cur.execute("SELECT * FROM students;")
rows = cur.fetchall()
conn.close()

for row in rows:
    print(row)

from whoosh.fields import Schema, TEXT, ID
from whoosh.index import create_in
import os

schema = Schema(id=ID(stored=True), name=TEXT(stored=True), gender=TEXT(stored=True))

if not os.path.exists("indexdir"):
    os.mkdir("indexdir")

ix = create_in("indexdir", schema)
writer = ix.writer()

for row in rows:
    doc_id, name, gender = row
    writer.add_document(id=str(doc_id), name=name, gender=gender)

writer.commit()

from whoosh.qparser import MultifieldParser

with ix.searcher() as searcher:
    parser = MultifieldParser(["name", "gender"], schema=ix.schema)
    query = parser.parse("bob")
    results = searcher.search(query)
    for r in results:
        print(f"{r['id']} | {r['name']} | {r['gender']}")