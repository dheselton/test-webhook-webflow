import os
import requests
import zipfile
import json
from datetime import datetime
import shutil
import logging
from flask import Flask, request, jsonify
from threading import Thread
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

class WebflowPorkbunDeployer:
    def __init__(self):
        self.webflow_token = os.getenv('WEBFLOW_TOKEN')
        self.porkbun_api_key = os.getenv('PORKBUN_API_KEY')
        self.porkbun_secret_key = os.getenv('PORKBUN_SECRET_KEY')
        self.deploy_domain = os.getenv('DEPLOY_DOMAIN')
        self.webflow_api_url = "https://api.webflow.com"
        self.porkbun_api_url = "https://porkbun.com/api/json/v3"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
        
        # Log token info
        self.logger.info(f"Initialized with token: {self.webflow_token[:10]}...")

    def download_site(self, site_id):
        """Download site files from Webflow."""
        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {self.webflow_token}"
        }
        
        self.logger.info(f"Making request to Webflow with headers: {headers}")
        
        # First, let's test the token by getting site info
        test_response = requests.get(
            f"{self.webflow_api_url}/sites/{site_id}",
            headers=headers
        )
        
        self.logger.info(f"Test API call response: {test_response.status_code}")
        self.logger.info(f"Test API response body: {test_response.text}")
        
        # Trigger site export
        self.logger.info("Attempting to trigger site export...")
        response = requests.post(
            f"{self.webflow_api_url}/sites/{site_id}/publish",
            headers=headers
        )
        
        self.logger.info(f"Publish response code: {response.status_code}")
        self.logger.info(f"Publish response body: {response.text}")
        
        if response.status_code != 200:
            raise Exception(f"Failed to trigger site export: {response.text}")
        
        # Download the exported files
        download_response = requests.get(
            f"{self.webflow_api_url}/sites/{site_id}/export",
            headers=headers
        )
        
        if download_response.status_code == 200:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_path = f"webflow_export_{timestamp}.zip"
            
            with open(zip_path, 'wb') as f:
                f.write(download_response.content)
            
            # Extract the zip file
            extract_path = f"webflow_site_{timestamp}"
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_path)
            
            # Clean up zip file
            os.remove(zip_path)
            
            return extract_path
        else:
            raise Exception(f"Failed to download site: {download_response.text}")

    def upload_to_porkbun(self, site_path):
        """Upload files to Porkbun hosting."""
        files = []
        for root, dirs, filenames in os.walk(site_path):
            for filename in filenames:
                file_path = os.path.join(root, filename)
                relative_path = os.path.relpath(file_path, site_path)
                files.append(('files', (relative_path, open(file_path, 'rb'))))

        data = {
            'apikey': self.porkbun_api_key,
            'secretapikey': self.porkbun_secret_key,
            'domain': self.deploy_domain
        }

        response = requests.post(
            f"{self.porkbun_api_url}/hosting/upload",
            data=data,
            files=files
        )

        # Close all opened files
        for _, file_tuple in files:
            file_tuple[1].close()

        if response.status_code == 200:
            self.logger.info(f"Successfully uploaded files to Porkbun for domain {self.deploy_domain}")
            return response.json()
        else:
            raise Exception(f"Failed to upload to Porkbun: {response.text}")

    def handle_webhook(self, site_id):
        """Handle webhook trigger and deploy site."""
        try:
            self.logger.info(f"Received publish trigger for site {site_id}")
            self.logger.info(f"Using token: {self.webflow_token[:10]}...")
            site_path = self.download_site(site_id)
            result = self.upload_to_porkbun(site_path)
            shutil.rmtree(site_path)
            return True
        except Exception as e:
            self.logger.error(f"Webhook handling failed: {str(e)}")
            return False

deployer = WebflowPorkbunDeployer()

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        deployer.logger.info("Received webhook request")
        
        data = request.get_json(silent=True)
        deployer.logger.info(f"Body: {data}")
        
        if data is None:
            deployer.logger.error("No JSON data received")
            return jsonify({'error': 'No JSON data received'}), 400

        site_id = data.get('payload', {}).get('siteId')
            
        if not site_id:
            deployer.logger.error("No site ID found in webhook data")
            return jsonify({'error': 'No site ID provided'}), 400

        deployer.logger.info(f"Processing webhook for site ID: {site_id}")
        Thread(target=deployer.handle_webhook, args=(site_id,)).start()
        return jsonify({'message': 'Deployment started'}), 200
    
    except Exception as e:
        deployer.logger.error(f"Error processing webhook: {str(e)}")
        return jsonify({'error': f'Error processing webhook: {str(e)}'}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'}), 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)