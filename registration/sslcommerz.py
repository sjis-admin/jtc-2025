
from django.conf import settings
import requests
import hashlib
from urllib.parse import urlencode

class SSLCOMMERZ:
    def __init__(self):
        self.store_id = settings.SSLCOMMERZ_STORE_ID
        self.store_password = settings.SSLCOMMERZ_STORE_PASSWORD
        self.api_url = settings.SSLCOMMERZ_API_URL
        self.validation_url = settings.SSLCOMMERZ_VALIDATION_URL
        self.is_sandbox = settings.SSLCOMMERZ_IS_SANDBOX

    def create_session(self, amount, tran_id, cust_name, cust_email, cust_phone):
        post_data = {
            'store_id': self.store_id,
            'store_passwd': self.store_password,
            'total_amount': str(amount),
            'currency': 'BDT',
            'tran_id': tran_id,
            'success_url': f"{settings.SITE_URL}/registration/payment/success/",
            'fail_url': f"{settings.SITE_URL}/registration/payment/fail/",
            'cancel_url': f"{settings.SITE_URL}/registration/payment/cancel/",
            'ipn_url': f"{settings.SITE_URL}/registration/payment/ipn/",
            'cus_name': cust_name,
            'cus_email': cust_email,
            'cus_phone': cust_phone,
            'shipping_method': 'NO',
            'product_name': 'JTC Registration',
            'product_category': 'Registration',
            'product_profile': 'general',
        }

        try:
            response = requests.post(self.api_url, data=post_data)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            # Log the error
            return {'status': 'FAILED', 'failed_reason': str(e)}

    def validate_ipn(self, post_data):
        store_id = self.store_id
        store_password = self.store_password

        # The IPN data from SSLCommerz
        tran_id = post_data.get('tran_id')
        val_id = post_data.get('val_id')
        amount = post_data.get('amount')
        card_type = post_data.get('card_type')
        store_amount = post_data.get('store_amount')
        card_no = post_data.get('card_no')
        bank_tran_id = post_data.get('bank_tran_id')
        status = post_data.get('status')
        tran_date = post_data.get('tran_date')
        currency = post_data.get('currency')
        card_issuer = post_data.get('card_issuer')
        card_brand = post_data.get('card_brand')
        card_issuer_country = post_data.get('card_issuer_country')
        card_issuer_country_code = post_data.get('card_issuer_country_code')
        currency_type = post_data.get('currency_type')
        currency_amount = post_data.get('currency_amount')
        verify_sign = post_data.get('verify_sign')
        verify_key = post_data.get('verify_key')

        # Construct the validation string
        params_to_hash = {
            'val_id': val_id,
            'store_id': store_id,
            'store_passwd': store_password,
        }
        
        # Prepare the validation request to SSLCommerz
        validation_params = {
            'val_id': val_id,
            'store_id': store_id,
            'store_passwd': store_password,
            'format': 'json'
        }

        try:
            response = requests.get(self.validation_url, params=validation_params)
            response.raise_for_status()
            validation_response = response.json()

            if validation_response.get('status') == 'VALIDATED':
                return True, validation_response
            else:
                return False, validation_response

        except requests.exceptions.RequestException as e:
            # Log the error
            return False, {'status': 'HTTP_ERROR', 'failed_reason': str(e)}
