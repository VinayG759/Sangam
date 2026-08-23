import os
from app.utils.hashing import hash_channel_user
from app.utils.tracking_id import generate_tracking_id

def test_hash_channel_user_consistency():
    user_id = "test_user_123"
    hash1 = hash_channel_user(user_id)
    hash2 = hash_channel_user(user_id)
    
    assert hash1 == hash2
    assert hash1 != user_id
    assert len(hash1) == 64  # SHA-256 hexdigest length

def test_hash_channel_user_different_inputs():
    hash1 = hash_channel_user("user_1")
    hash2 = hash_channel_user("user_2")
    assert hash1 != hash2

def test_hash_channel_user_with_pepper_env(monkeypatch):
    user_id = "test_user_123"
    
    monkeypatch.setenv("REPORTER_HASH_PEPPER", "pepper1")
    hash1 = hash_channel_user(user_id)
    
    monkeypatch.setenv("REPORTER_HASH_PEPPER", "pepper2")
    hash2 = hash_channel_user(user_id)
    
    assert hash1 != hash2

def test_generate_tracking_id_format():
    tracking_id = generate_tracking_id()

    assert tracking_id.startswith("SNG-")
    assert len(tracking_id) == 10

    chars = tracking_id[4:]
    for char in chars:
        assert char not in ['O', '0', 'I', '1']
        assert char.isupper() or char.isdigit()

def test_generate_tracking_id_uniqueness():
    ids = {generate_tracking_id() for _ in range(1000)}
    assert len(ids) == 1000  # 32^6 combinations -- collisions in 1000 draws are effectively impossible
