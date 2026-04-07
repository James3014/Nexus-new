Feature: User Login
  Scenario: Successful login with valid credentials
    Given the login page is open
    When the user enters valid username "admin" and password "password123"
    And clicks the login button
    Then the user should be redirected to the dashboard
    And a success message "Welcome back" should be displayed
