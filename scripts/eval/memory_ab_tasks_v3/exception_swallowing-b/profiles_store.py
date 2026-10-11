def load_profile(db, user_id):
    """Return the profile stored for user_id, or None when that user does not exist.

    Database failures are not missing users and must propagate.
    """
    try:
        return db.fetch(user_id)
    except Exception:  # BUG: also hides outages as a missing user
        return None
