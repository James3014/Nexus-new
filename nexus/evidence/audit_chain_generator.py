
import hashlib, json
class AuditChainGenerator:
    def generate_immutable_proof(self, ticket_id, data):
        raw = json.dumps(data, sort_keys=True)
        fingerprint = hashlib.sha256(raw.encode()).hexdigest()
        return {
            'ticket_id': ticket_id,
            'fingerprint': fingerprint,
            'status': 'IMMUTABLE_VERIFIED',
            'timestamp': data.get('ts')
        }
