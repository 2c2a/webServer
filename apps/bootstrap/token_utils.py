import base64
import json


def encode_provision_token(raw_token: str, scheme: str, host: str) -> str:
    payload = json.dumps({"t": raw_token, "s": scheme, "h": host}, separators=(',', ':'))
    return base64.urlsafe_b64encode(payload.encode('utf-8')).decode('ascii')


def decode_provision_token(encoded: str) -> dict | None:
    try:
        padding = 4 - len(encoded) % 4
        if padding != 4:
            encoded += '=' * padding
        payload = base64.urlsafe_b64decode(encoded.encode('ascii')).decode('utf-8')
        data = json.loads(payload)
        if 't' in data and 's' in data and 'h' in data:
            return data
    except Exception:
        pass
    return None
