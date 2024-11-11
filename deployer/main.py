import requests
import zipfile
import os
import io
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Retrieve credentials from environment variables
WEBFLOW_TOKEN = os.getenv('WEBFLOW_TOKEN')
WEBFLOW_SITE_ID = os.getenv('WEBFLOW_SITE_ID')  # Add your Webflow Site ID here
PORKBUN_API_KEY = os.getenv('PORKBUN_API_KEY')
PORKBUN_SECRET_KEY = os.getenv('PORKBUN_SECRET_KEY')

# Webflow API endpoint for exporting a site as a ZIP file
WEBFLOW_EXPORT_URL = f'https://api.webflow.com/sites/{WEBFLOW_SITE_ID}/export'

# Porkbun API endpoint for file uploads
PORKBUN_UPLOAD_URL = 'https://porkbun.com/api/json/v3/files/upload'

def download_webflow_site():
    """
    Downloads a ZIP file of the Webflow site using the Webflow API.
    """
    headers = {
        'Authorization': f'Bearer {WEBFLOW_TOKEN}',
        'Accept-Version': '1.0.0'
    }
    response = requests.get(WEBFLOW_EXPORT_URL, headers=headers)
    response.raise_for_status()

    # Handle ZIP download
    with zipfile.ZipFile(io.BytesIO(response.content)) as zip_file:
        zip_file.extractall('webflow_site')  # Extracts ZIP content to webflow_site directory

    print("Webflow site downloaded and extracted.")

def upload_to_porkbun():
    """
    Uploads each file from the downloaded Webflow site to Porkbun hosting.
    """
    headers = {
        'Content-Type': 'application/json'
    }
    files_uploaded = 0

    for root, _, files in os.walk('webflow_site'):
        for file_name in files:
            file_path = os.path.join(root, file_name)
            with open(file_path, 'rb') as file_data:
                # Payload for Porkbun API with authentication and file info
                payload = {
                    'apikey': PORKBUN_API_KEY,
                    'secretapikey': PORKBUN_SECRET_KEY,
                    'filename': os.path.relpath(file_path, 'webflow_site'),  # Maintain directory structure
                }
                files = {
                    'file': file_data
                }
                response = requests.post(PORKBUN_UPLOAD_URL, headers=headers, data=payload, files=files)
                response.raise_for_status()

                files_uploaded += 1
                print(f"Uploaded {file_path} to Porkbun.")

    print(f"Total files uploaded to Porkbun: {files_uploaded}")

def main():
    """
    Main script function to download and upload the Webflow site.
    """
    try:
        download_webflow_site()
        upload_to_porkbun()
        print("Webflow site successfully transferred to Porkbun.")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    main()