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

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class WebflowPorkbunDeployer:
    def __init__(self):
        self.webflow_token = os.getenv('WEBFLOW_TOKEN')
        self.porkbun_api_key = os.getenv('PORKBUN_API_KEY')
        self.porkbun_secret_key = os.getenv('PORKBUN_SECRET_KEY')
        self.deploy_domain = os.getenv('DEPLOY_DOMAIN')
        self.webflow_domain = 'maine-mountain-moccasin.webflow.io'
        self.webflow_api_url = "https://api.webflow.com"
        self.porkbun_api_url = "https://porkbun.com/api/json/v3"
        self.logger = logger

    def trigger_publish(self, site_id):
        """Trigger a site publish in Webflow."""
        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {self.webflow_token}",
            "Content-Type": "application/json"
        }
        
        publish_data = {
            "domains": [self.webflow_domain]
        }
        
        response = requests.post(
            f"{self.webflow_api_url}/sites/{site_id}/publish",
            headers=headers,
            json=publish_data
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to trigger publish: {response.text}")
            
        return response.json()

    def download_site(self, site_id):
        """Download site files from Webflow."""
        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {self.webflow_token}"
        }
        
        # First trigger a publish
        self.logger.info("Triggering site publish...")
        publish_result = self.trigger_publish(site_id)
        self.logger.info(f"Publish triggered: {publish_result}")
        
        # Download the site files
        self.logger.info("Downloading site files...")
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
            self.logger.info(f"Starting deployment for site {site_id}")
            site_path = self.download_site(site_id)
            self.logger.info(f"Downloaded site to {site_path}")
            result = self.upload_to_porkbun(site_path)
            self.logger.info("Upload to Porkbun complete")
            shutil.rmtree(site_path)
            return True
        except Exception as e:
            self.logger.error(f"Deployment failed: {str(e)}")
            return False

deployer = WebflowPorkbunDeployer()

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        logger.info("Received webhook request")
        data = request.get_json(silent=True)
        logger.info(f"Webhook data: {data}")
        
        if data is None:
            logger.error("No JSON data received")
            return jsonify({'error': 'No JSON data received'}), 400

        site_id = data.get('payload', {}).get('siteId')
            
        if not site_id:
            logger.error("No site ID found in webhook data")
            return jsonify({'error': 'No site ID provided'}), 400

        logger.info(f"Processing webhook for site ID: {site_id}")
        Thread(target=deployer.handle_webhook, args=(site_id,)).start()
        return jsonify({'message': 'Deployment started'}), 200
    
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return jsonify({'error': f'Error processing webhook: {str(e)}'}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'}), 200

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)