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

def get_ccavenue_credentials() -> dict:
    """Returns active CCAvenue credentials based on CCAVENUE_MODE env var (TEST or PRODUCTION)."""
    raw_mode = os.environ.get("CCAVENUE_MODE", "").strip().upper()
    
    # Auto-detect mode if CCAVENUE_MODE is not explicitly specified
    if not raw_mode:
        gateway = os.environ.get("CCAVENUE_GATEWAY_URL", "").lower()
        if "secure.ccavenue.com" in gateway or (os.environ.get("CCAVENUE_MERCHANT_ID") and not os.environ.get("CCAVENUE_TEST_MERCHANT_ID")):
            mode = "PRODUCTION"
        else:
            mode = "TEST"
    else:
        mode = raw_mode

    if mode == "PRODUCTION":
        return {
            "mode": "PRODUCTION",
            "merchant_id": os.environ.get("CCAVENUE_PROD_MERCHANT_ID", os.environ.get("CCAVENUE_MERCHANT_ID", "2934389")),
            "access_code": os.environ.get("CCAVENUE_PROD_ACCESS_CODE", os.environ.get("CCAVENUE_ACCESS_CODE", "AVFG94NG06AF44GFFA")),
            "working_key": os.environ.get("CCAVENUE_PROD_WORKING_KEY", os.environ.get("CCAVENUE_WORKING_KEY", "F87E75A5907420050076D82F20AF1FCE")),
            "gateway_url": os.environ.get("CCAVENUE_PROD_GATEWAY_URL", os.environ.get("CCAVENUE_GATEWAY_URL", "https://secure.ccavenue.com/transaction/transaction.do?command=initiateTransaction"))
        }
    else:
        return {
            "mode": "TEST",
            "merchant_id": os.environ.get("CCAVENUE_TEST_MERCHANT_ID", os.environ.get("CCAVENUE_MERCHANT_ID", "2934389")),
            "access_code": os.environ.get("CCAVENUE_TEST_ACCESS_CODE", os.environ.get("CCAVENUE_ACCESS_CODE", "AVFG94NG06AF44GFFA")),
            "working_key": os.environ.get("CCAVENUE_TEST_WORKING_KEY", os.environ.get("CCAVENUE_WORKING_KEY", "F87E75A5907420050076D82F20AF1FCE")),
            "gateway_url": os.environ.get("CCAVENUE_TEST_GATEWAY_URL", os.environ.get("CCAVENUE_GATEWAY_URL", "https://test.ccavenue.com/transaction/transaction.do?command=initiateTransaction"))
        }

def build_payment_payload(order_id: str, amount: float, currency: str = "INR", redirect_url: str = "", cancel_url: str = "", client_name: str = "", client_phone: str = "", merchant_id: str = "") -> str:
    """
    Constructs standard key-value query string payload for CCAvenue request matching official CCAvenue SDK formatting.
    """
    if not merchant_id:
        creds = get_ccavenue_credentials()
        merchant_id = creds["merchant_id"]
    
    name = (client_name or "Customer").strip()
    phone = (client_phone or "").strip()
    
    # Official CCAvenue Integration Kit builds raw un-encoded parameter string
    payload_parts = [
        f"merchant_id={merchant_id}",
        f"order_id={order_id}",
        f"currency={currency}",
        f"amount={amount:.2f}",
        f"redirect_url={redirect_url}",
        f"cancel_url={cancel_url}",
        f"language=EN",
        f"billing_name={name}",
        f"billing_tel={phone}"
    ]
    
    return "&".join(payload_parts)
