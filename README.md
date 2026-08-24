# 💸 ClearSpend

ClearSpend is a full-stack expense tracking and SMS parsing application designed to help users automatically monitor, categorize, and analyze their spending habits.

---

## 🛠️ Tech Stack

### **Backend**
* **Framework:** FastAPI (Python)
* **Database:** SQLite with SQLAlchemy ORM
* **Server:** Uvicorn

### **Frontend**
* Modern Web Frontend (HTML, CSS, JavaScript)

---

## 📂 Project Structure

```text
ClearSpend/
│
├── backend/                # FastAPI Backend Service
│   ├── app/                # Application source code (models, database, parser engine)
│   ├── data/               # Sample data and templates (e.g., SMS samples)
│   ├── requirements.txt    # Python dependencies
│   └── clearspend.db       # SQLite database
│
├── frontend/               # Frontend user interface
├── .gitignore              # Git ignore rules
└── README.md               # Project documentation

```
# 🚀 Getting Started Locally
1. Clone the Repository
```bash
git clone [https://github.com/RudraSharma3/ClearSpend.git](https://github.com/RudraSharma3/ClearSpend.git)
cd ClearSpend
```
2. Set Up the Backend
```bash
cd backend
python -m venv venv

# Activate virtual environment:
# On Windows (PowerShell):
venv\Scripts\activate
# On macOS/Linux:
# source venv/bin/activate

pip install -r requirements.txt
```
3. Configure Environment Variables
Create a .env file inside the backend/ folder and add your configuration keys (make sure never to commit this file to GitHub!):
```bash
# Example .env configuration
DATABASE_URL=sqlite:///./clearspend.db
```
4. Run the Backend Server
```bash
python -m uvicorn app.main:app --reload --port 8000
```
# 💡 Features
Automated SMS Parsing: Extracts transaction details from raw text samples.

Expense History: Tracks and lists past categorized spending.

RESTful API: Clean endpoints built with FastAPI for seamless frontend integration.

# 👥 Contributors
Rudra Sharma
