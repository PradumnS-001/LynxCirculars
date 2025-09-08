## Items to be created on the server / Local Envoirnment :
- `.env` file containing env variables - `USER_PASSWORD`, `USER`, `DB_NAME`, and `HOST`
- Folder named `Circulars` containing various `department` folders ( like `Admin`, `EEE` ) each containg their respective circulars
---
## To run this folder:
- In bash run the following command to install all the required libraries
```
cd /path/to/your/project
pip install -r requirements.txt
```
- To append a pdf into the database, import the `append_data` function from `sql.py` and pass in the arguments `department` and `pdf title` in that order.
Example:
```
from sql import append_data
append_data("Admin", "CircularOne.pdf")
```
