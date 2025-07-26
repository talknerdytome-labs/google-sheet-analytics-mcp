# Conversational Data Insights AI

This project provides a conversational AI interface for querying large datasets stored in Google Sheets. Users can ask questions in natural language, and the system will generate SQL queries, fetch data from a PostgreSQL database, and provide answers in both text and chart format.

The entire application is orchestrated using Docker Compose, making it easy to set up and run.

## Architecture

The application consists of three main services defined in `docker-compose.yml`:
- **`db`**: A PostgreSQL database that stores the data from the Google Sheet.
- **`backend`**: A Python FastAPI service that handles the conversational AI logic, translating natural language to SQL and generating responses.
- **`webui`**: The [Open WebUI](https://github.com/open-webui/open-webui) frontend that provides the chat interface for the user.

## Prerequisites

- **Docker and Docker Compose:** You must have Docker installed and running on your system. [Install Docker](https://docs.docker.com/get-docker/).
- **Python 3.11+:** Required for running the data sync script locally if needed.
- **A Google Sheet:** You need a Google Sheet with the data you want to analyze. The first row should contain the headers.

## Setup Instructions

### 1. Configure Google API Credentials

This application requires Google API credentials to access your sheet.

1.  **Enable APIs:** Go to the [Google Cloud Console](https://console.cloud.google.com/) and enable the **Google Sheets API** and **Google Drive API** for your project.
2.  **Create Credentials:**
    - Navigate to "APIs & Services" > "Credentials".
    - Click `+ CREATE CREDENTIALS` and select `OAuth client ID`.
    - For the Application type, choose **"Desktop app"**.
    - Click `Create`, and then click `DOWNLOAD JSON`.
3.  **Place the file:**
    - Rename the downloaded file to `credentials.json`.
    - Place this file inside the `backend/` directory of this project.

### 2. Run the Initial Data Sync

Before you can query your data, you must sync it from your Google Sheet to the PostgreSQL database.

1.  **Build the services:**
    ```bash
    docker-compose build
    ```
2.  **Run the sync script:**
    This script will pop up a browser window for you to authenticate with Google on the first run. After authentication, it will create a `token.json` file in the `backend` directory for future use.

    Replace `YOUR_SPREADSHEET_ID` and `"Your Sheet Name"` with your actual sheet details.

    ```bash
    docker-compose run --rm backend python data_pipeline/sync.py YOUR_SPREADSHEET_ID "Your Sheet Name"
    ```

## Running the Application

Once the initial data sync is complete, you can start the full application.

```bash
docker-compose up -d
```

- The Web UI will be available at: **http://localhost:3000**
- The Backend API will be available at: **http://localhost:8000**

## How to Use

1.  Navigate to **http://localhost:3000** in your web browser.
2.  You will be prompted to create an account for Open WebUI. This is just for the UI itself.
3.  After logging in, you can start a new chat. The application will automatically be connected to our custom backend.
4.  Ask questions about your data!
    - "What is the total number of rows?"
    - "Show me a bar chart of sales by product category."
    - "What are the top 5 regions by profit?"

### Re-syncing Data

To update the data in the database with the latest version from your Google Sheet, simply re-run the sync command:

```bash
docker-compose run --rm backend python data_pipeline/sync.py YOUR_SPREADSHEET_ID "Your Sheet Name"
``` 