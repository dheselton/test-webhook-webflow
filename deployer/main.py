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

    def can_publish(self):
        """Check if enough time has passed since last publish."""
        with self.publish_lock:
            if self.last_publish_time is None:
                return True
            elapsed = datetime.now() - self.last_publish_time
            return elapsed > timedelta(seconds=60)

    def update_publish_time(self):
        """Update the last publish time."""
        with self.publish_lock:
            self.last_publish_time = datetime.now()

    def trigger_publish(self, site_id):
        """Trigger a site publish in Webflow."""
        if not self.can_publish():
            wait_time = 60
            self.logger.info(f"Waiting {wait_time} seconds before publishing...")
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
        
        self.update_publish_time()
        return response.json()

    def download_site(self, site_id):
        """Download site files using wget."""
        try:
            # Create a timestamp for unique filenames
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            extract_path = f"webflow_site_{timestamp}"

            # Download the file directly from the site's URL
            site_url = f"https://{self.webflow_domain}"
            self.logger.info(f"Downloading site from: {site_url}")
            
            # Use wget to download the site
            os.system(f'wget -r -k -l inf -p -N -E -H -P {extract_path} {site_url}')
            
            return extract_path
        except Exception as e:
            raise Exception(f"Failed to download site: {str(e)}")

    def upload_to_porkbun(self, site_path):
        """Upload files to Porkbun hosting."""
        files = []
        try:
            self.logger.info("Preparing files for upload...")
            
            # Only include HTML, CSS, JS, and image files
            valid_extensions = ('.html', '.css', '.js', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.ico')
            
            for root, dirs, filenames in os.walk(site_path):
                for filename in filenames:
                    if filename.lower().endswith(valid_extensions):
                        file_path = os.path.join(root, filename)
                        relative_path = os.path.relpath(file_path, site_path)
                        
                        # Clean up the relative path
                        if '/maine-mountain-moccasin.webflow.io/' in relative_path:
                            relative_path = relative_path.split('/maine-mountain-moccasin.webflow.io/')[-1]
                        
                        # Ensure the path starts with a /
                        if not relative_path.startswith('/'):
                            relative_path = '/' + relative_path
                        
                        self.logger.info(f"Adding file: {relative_path}")
                        files.append(('files', (relative_path, open(file_path, 'rb'))))

            data = {
                'apikey': self.porkbun_api_key,
                'secretapikey': self.porkbun_secret_key,
                'domain': self.deploy_domain
            }

            # Use the correct API endpoint
            upload_url = f"{self.porkbun_api_url}/domain/uploadFiles/{self.deploy_domain}"
            self.logger.info(f"Uploading {len(files)} files to {upload_url}...")

            response = requests.post(
                upload_url,
                data=data,
                files=files
            )

            if response.status_code == 200:
                self.logger.info(f"Successfully uploaded files to Porkbun for domain {self.deploy_domain}")
                return response.json()
            else:
                self.logger.error(f"Upload failed with status {response.status_code}")
                self.logger.error(f"Response: {response.text}")
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
            site_path = self.download_site(site_id)
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