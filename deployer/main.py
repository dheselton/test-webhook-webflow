import os
import requests
import zipfile
import json
from datetime import datetime, timedelta
import shutil
import logging
from flask import Flask, request, jsonify
from threading import Thread, Lock
from dotenv import load_dotenv
import time

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
        self.last_publish_time = None
        self.publish_lock = Lock()
        self.current_deployments = set()

    def is_already_deploying(self, site_id):
        """Check if a deployment is already in progress for this site."""
        return site_id in self.current_deployments

    def get_site_files(self, site_id):
        """Get site files using Webflow API."""
        try:
            headers = {
                "accept": "application/json",
                "authorization": f"Bearer {self.webflow_token}"
            }

            # Create a timestamp for unique filenames
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_path = f"webflow_export_{timestamp}.zip"
            extract_path = f"webflow_site_{timestamp}"

            # Download the file directly from the site's URL
            site_url = f"https://maine-mountain-moccasin.webflow.io"
            self.logger.info(f"Downloading site from: {site_url}")
            
            # Use wget or similar tool to download the site
            os.system(f'wget -r -k -l inf -p -N -E -H -P {extract_path} {site_url}')
            
            return extract_path
        except Exception as e:
            raise Exception(f"Failed to get site files: {str(e)}")

    def trigger_publish(self, site_id):
        """Trigger a site publish in Webflow."""
        # Wait if last publish was less than 60 seconds ago
        if self.last_publish_time:
            elapsed = (datetime.now() - self.last_publish_time).total_seconds()
            if elapsed < 60:
                wait_time = 60 - elapsed
                self.logger.info(f"Waiting {wait_time} seconds before next publish...")
                time.sleep(wait_time)

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
        
        if response.status_code == 429:  # Rate limit
            self.logger.info("Hit rate limit, waiting 60 seconds...")
            time.sleep(60)
            return self.trigger_publish(site_id)
        
        if response.status_code != 200:
            raise Exception(f"Failed to trigger publish: {response.text}")
        
        self.last_publish_time = datetime.now()
        return response.json()

    def upload_to_porkbun(self, site_path):
        """Upload files to Porkbun hosting."""
        files = []
        try:
            for root, dirs, filenames in os.walk(site_path):
                for filename in filenames:
                    file_path = os.path.join(root, filename)
                    relative_path = os.path.relpath(file_path, site_path)
                    if not filename.startswith('.'):  # Skip hidden files
                        files.append(('files', (relative_path, open(file_path, 'rb'))))

            data = {
                'apikey': self.porkbun_api_key,
                'secretapikey': self.porkbun_secret_key,
                'domain': self.deploy_domain
            }

            self.logger.info(f"Uploading {len(files)} files to Porkbun...")
            response = requests.post(
                f"{self.porkbun_api_url}/hosting/upload",
                data=data,
                files=files
            )

            if response.status_code == 200:
                self.logger.info(f"Successfully uploaded files to Porkbun for domain {self.deploy_domain}")
                return response.json()
            else:
                raise Exception(f"Failed to upload to Porkbun: {response.text}")
        finally:
            # Close all opened files
            for _, file_tuple in files:
                try:
                    file_tuple[1].close()
                except:
                    pass

    def handle_webhook(self, site_id):
        """Handle webhook trigger and deploy site."""
        if self.is_already_deploying(site_id):
            self.logger.info(f"Deployment already in progress for site {site_id}")
            return False

        try:
            self.current_deployments.add(site_id)
            self.logger.info(f"Starting deployment for site {site_id}")
            
            # First trigger publish
            self.logger.info("Triggering publish...")
            self.trigger_publish(site_id)
            
            # Wait for publish to complete
            self.logger.info("Waiting for publish to complete...")
            time.sleep(15)
            
            # Get and download the site files
            self.logger.info("Getting site files...")
            site_path = self.get_site_files(site_id)
            self.logger.info(f"Downloaded site to {site_path}")
            
            # Upload to Porkbun
            self.logger.info("Uploading to Porkbun...")
            result = self.upload_to_porkbun(site_path)
            self.logger.info("Upload to Porkbun complete")
            
            # Cleanup
            shutil.rmtree(site_path)
            return True
        except Exception as e:
            self.logger.error(f"Deployment failed: {str(e)}")
            return False
        finally:
            self.current_deployments.remove(site_id)

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

        if deployer.is_already_deploying(site_id):
            logger.info(f"Deployment already in progress for site {site_id}")
            return jsonify({'message': 'Deployment already in progress'}), 200

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