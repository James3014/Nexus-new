class LoginService:
    def login(self, username, password):
        if username == "admin" and password == "password123":
            return {
                "status": "success",
                "message": "Welcome back",
                "redirect": "/dashboard"
            }
        else:
            return {
                "status": "error",
                "message": "Invalid credentials",
                "redirect": "/login"
            }
