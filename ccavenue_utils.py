import os
import hashlib
import binascii
import urllib.parse
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend

# Default CCAvenue IV used in standard SDKs
CCAVENUE_IV = bytes([0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f])

def get_key_digest(working_key: str) -> bytes:
    """Generate 16-byte MD5 digest of the working key as expected by CCAvenue AES-128."""
    return hashlib.md5(working_key.encode('utf-8')).digest()

def encrypt_ccavenue(plain_text: str, working_key: str) -> str:
    """
    Encrypts plain text string using AES-128-CBC with PKCS7 padding for CCAvenue.
    Returns hex-encoded encrypted string.
    """
    if not plain_text or not working_key:
        return ""
    
    key = get_key_digest(working_key)
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(plain_text.encode('utf-8')) + padder.finalize()
    
    cipher = Cipher(algorithms.AES(key), modes.CBC(CCAVENUE_IV), backend=default_backend())
    encryptor = cipher.encryptor()
    encrypted_bytes = encryptor.update(padded_data) + encryptor.finalize()
    
    return binascii.hexlify(encrypted_bytes).decode('utf-8')

def decrypt_ccavenue(encrypted_hex: str, working_key: str) -> str:
    """
    Decrypts hex-encoded string received from CCAvenue using AES-128-CBC.
    Returns plain text string.
    """
    if not encrypted_hex or not working_key:
        return ""
    
    try:
        key = get_key_digest(working_key)
        encrypted_bytes = binascii.unhexlify(encrypted_hex.strip())
        
        cipher = Cipher(algorithms.AES(key), modes.CBC(CCAVENUE_IV), backend=default_backend())
        decryptor = cipher.decryptor()
        padded_data = decryptor.update(encrypted_bytes) + decryptor.finalize()
        
        unpadder = padding.PKCS7(128).unpadder()
        plain_bytes = unpadder.update(padded_data) + unpadder.finalize()
        
        return plain_bytes.decode('utf-8')
    except Exception as e:
        print(f"[CCAVENUE DECRYPT ERROR] {e}")
        return ""

def parse_ccavenue_response(decrypted_text: str) -> dict:
    """
    Parses key=value&key=value formatted response string into a dictionary.
    """
    if not decrypted_text:
        return {}
    
    parsed = urllib.parse.parse_qs(decrypted_text)
    # Convert query dict arrays to single values
    return {k: v[0] if isinstance(v, list) and len(v) > 0 else v for k, v in parsed.items()}

def build_payment_payload(order_id: str, amount: float, currency: str = "INR", redirect_url: str = "", cancel_url: str = "", client_name: str = "", client_phone: str = "") -> str:
    """
    Constructs standard key-value query string payload for CCAvenue request.
    """
    merchant_id = os.environ.get("CCAVENUE_MERCHANT_ID", "DEMO_MERCHANT")
    
    params = {
        "merchant_id": merchant_id,
        "order_id": order_id,
        "currency": currency,
        "amount": f"{amount:.2f}",
        "redirect_url": redirect_url,
        "cancel_url": cancel_url,
        "language": "EN",
        "billing_name": client_name or "Customer",
        "billing_tel": client_phone or "",
    }
    
    return urllib.parse.urlencode(params)
