## Items to be created in the Local Envoirnment :
- Create a `.env` file containing env following variables - `PASSWORD`, `USER`, `DATABASE_NAME`, and `HOST`.
- Create a Folder named `Circulars` containing various `department` folders ( like `Admin`, `EEE` ) each containg their respective circulars.
---
## How to use:
- In bash run the following command to install all the required libraries.
```bash
cd /path/to/your/project
pip install -r requirements.txt
```
- To append a pdf into the database, import the `append_data` function from `sql.py` and pass in the arguments `department` and `pdf title` in that order.
Example Code: `example.py`
```python
from sql import append_data
append_data("Admin", "MessRegistration.pdf")
```
- The `append_data` function will automatically create tables if they don't already exist.
- The `append_data` expects the input to be of size (*,2) - it expects a list of tuples of `(department, pdf_path)`.