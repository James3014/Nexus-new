def find_user_email(users, user_id):
    """Return the lowercased email of the user with user_id, or None if absent."""
    user = next((u for u in users if u["id"] == user_id), None)
    return user["email"].lower()  # BUG: user can be None
