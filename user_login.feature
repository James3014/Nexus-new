Feature: User Login
  As a registered user
  I want to log into the system
  So that I can access my personalized dashboard

  Scenario: Successful login with valid credentials
    Given the user is on the login page
    When the user enters "valid_username" and "valid_password"
    And clicks the login button
    Then the user should be redirected to the dashboard
    And a welcome message "Welcome, valid_username!" should be displayed

  Scenario: Failed login with invalid credentials
    Given the user is on the login page
    When the user enters "invalid_username" and "wrong_password"
    And clicks the login button
    Then an error message "Invalid username or password" should be displayed
    And the user should remain on the login page

  Scenario: Login attempt with empty fields
    Given the user is on the login page
    When the user leaves the username and password fields empty
    And clicks the login button
    Then an error message "Fields cannot be empty" should be displayed
